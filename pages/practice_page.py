import io
import json
import os
import re
import uuid
import requests
import streamlit as st
import streamlit.components.v1 as st_components
from datetime import date, datetime, timedelta, timezone
from streamlit_autorefresh import st_autorefresh
from modules.config import *
from modules.utils import *
from modules.profiles import *
from modules.ai_client import *
from modules.lessons import *
from modules.shadowing import *
from modules.sessions import *
from modules.podcasts import *
from modules.stories import *
from modules.ai_lessons import *
from modules.vocabulary import *
from modules.immersion import *
from modules.real_english import *
from modules.sessions import _build_translation_targets, _format_translation_question, _question_prompt_from_target
from modules.lessons import _collect_practice_lesson_catalog, _practice_catalog_item_label
from modules.ai_lessons import _recent_practice_sessions
from modules.utils import _seconds_between_iso, _seconds_since_iso

def initialize_state():
    if "active_session" not in st.session_state:
        st.session_state.active_session = None


def render_practice_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Pratique audio instantanee avec l'IA")
    st.write(
        "Enregistrez votre audio, envoyez-le, puis ecoutez la reponse vocale de l'IA."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    practice_level_default = get_profile_module_level(profile, "practice")
    practice_level = st.radio(
        "Niveau cible de la session",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(practice_level_default),
        horizontal=True,
        key=f"practice-level-{profile_id}",
    )
    if practice_level != practice_level_default:
        set_profile_module_level(profile_id, "practice", practice_level)

    practice_catalog = _collect_practice_lesson_catalog(profile_id)
    practice_items = practice_catalog.get("items", [])
    if practice_items:
        st.info(
            f"Base de pratique detectee: {practice_catalog.get('completed_count', 0)} lecon(s) terminee(s) + "
            f"{practice_catalog.get('in_progress_count', 0)} en cours (Lecons audio + Anglais reel)."
        )
    else:
        st.warning(
            "Aucune lecon terminee/en cours detectee. La pratique IA utilisera les themes generaux par defaut."
        )

    practice_mode = st.radio(
        "Mode",
        ["Guide par mes lecons", "Dialogue libre sur toutes mes lecons"],
        horizontal=True,
    )

    drill_label = st.selectbox(
        "Drill oral cible",
        list(PRACTICE_DRILL_MODES.keys()),
        index=0,
        help="Choisis un entrainement cible pour combler l'ecart comprehension vs production orale.",
    )
    drill_cfg = PRACTICE_DRILL_MODES[drill_label]
    training_mode = drill_cfg["key"]
    training_settings = {}

    if training_mode == "conversation_stress":
        training_settings["stress_reply_seconds"] = st.slider(
            "Delai reponse cible (secondes)",
            min_value=5,
            max_value=20,
            value=10,
            help="Objectif de rapidite entre la question de l'IA et ta reponse.",
        )
    elif training_mode == "fr_to_en":
        direction_label = st.radio(
            "Sens de traduction",
            ["Français -> English", "English -> Français"],
            horizontal=True,
            help="L'IA te pose la phrase et tu réponds dans la langue cible.",
        )
        training_settings["translation_direction"] = (
            "fr_to_en" if direction_label == "Français -> English" else "en_to_fr"
        )
    elif training_mode == "tense_switch":
        training_settings["target_tense"] = st.selectbox(
            "Temps cible",
            ["present", "past", "future"],
            index=0,
            help="L'IA va te faire rester dans ce temps, puis te demander des reformulations.",
        )

    st.caption(f"Drill actif: {drill_label} — {drill_cfg['description']}")

    selected_theme = None
    selected_objective = ""
    selected_lesson_context = {}
    if practice_mode == "Guide par mes lecons":
        if practice_items:
            item_options = []
            item_map = {}
            for idx, item in enumerate(practice_items):
                label = f"{_practice_catalog_item_label(item)} #{idx + 1}"
                item_options.append(label)
                item_map[label] = item

            pick_mode = st.radio(
                "Choix de la lecon",
                ["Je choisis une lecon", "L'IA choisit"],
                horizontal=True,
            )
            if pick_mode == "Je choisis une lecon":
                selected_label = st.selectbox(
                    "Lecon de reference",
                    item_options,
                    key=f"practice-lesson-{profile_id}",
                )
            else:
                auto_pick_key = f"practice-auto-lesson-{profile_id}"
                if st.button("Choisir une lecon automatiquement"):
                    st.session_state[auto_pick_key] = choose_theme_with_ai(item_options)
                selected_label = st.session_state.get(auto_pick_key, item_options[0])
                st.info(f"Lecon proposee: {selected_label}")

            selected_item = item_map.get(selected_label, practice_items[0])
            selected_theme = str(
                selected_item.get("theme")
                or selected_item.get("title")
                or "General conversation"
            )
            selected_lesson_context = {
                "focus_items": [selected_item],
                "topic_pool": [
                    selected_theme,
                    str(selected_item.get("title") or selected_theme),
                ],
            }
            selected_objective = st.text_input(
                "Objectif de la session (optionnel)",
                value=(
                    f"Reuse chunks from this lesson: {selected_item.get('title', selected_theme)}. "
                    "Stay natural and fluent in American English."
                ),
            )
        else:
            pick_mode = st.radio(
                "Choix du theme", ["Je choisis", "L'IA choisit"], horizontal=True
            )
            if pick_mode == "Je choisis":
                selected_theme = st.selectbox(
                    "Theme de la session", list(ESSENTIAL_THEMES.keys())
                )
            else:
                if st.button("Choisir un theme automatiquement"):
                    st.session_state.auto_theme = choose_theme_with_ai()
                selected_theme = st.session_state.get(
                    "auto_theme", list(ESSENTIAL_THEMES.keys())[0]
                )
                st.info(f"Theme propose: {selected_theme}")
            selected_objective = st.text_input(
                "Objectif de la session (optionnel)",
                value="Practice natural chunks and stay fluent in this topic.",
            )
    else:
        if practice_items:
            selected_theme = "Mes lecons (audio + anglais reel)"
            selected_lesson_context = {
                "focus_items": practice_items,
                "topic_pool": practice_catalog.get("topic_pool", []),
            }
            with st.expander(
                f"Themes utilises en dialogue libre ({len(practice_items)})",
                expanded=False,
            ):
                for item in practice_items:
                    st.markdown(f"- {_practice_catalog_item_label(item)}")
            selected_objective = st.text_input(
                "Objectif de la session (optionnel)",
                value=(
                    "Dialogue libre base sur toutes mes lecons terminees/en cours. "
                    "Reutiliser les expressions et varier les situations reels."
                ),
            )
        else:
            selected_theme = "Free conversation"
            selected_objective = st.text_input(
                "Objectif de la session (optionnel)",
                value="Keep the conversation practical and natural in daily-life contexts.",
            )

    if st.button("Demarrer une nouvelle session"):
        mode_value = "guided" if practice_mode == "Guide par mes lecons" else "free"
        theme_value = selected_theme or "Free conversation"
        session_lesson_context = dict(selected_lesson_context)

        if training_mode == "fr_to_en":
            translation_targets = _build_translation_targets(
                profile_id=profile_id,
                lesson_context=session_lesson_context,
                max_total=36,
                max_per_lesson=6,
            )
            if not translation_targets:
                st.error(
                    "Le drill de traduction necessite des lecons en cours/terminees avec phrases exploitables. "
                    "Selectionnez une lecon a reviser ou envoyez vos lecons vers Shadowing d'abord."
                )
                return

            session_lesson_context["translation_targets"] = translation_targets
            direction = training_settings.get("translation_direction", "fr_to_en")
            direction_label = "FR -> EN" if direction == "fr_to_en" else "EN -> FR"
            st.info(
                f"{len(translation_targets)} phrase(s) de vos lecons seront utilisees pour la traduction {direction_label}."
            )

        st.session_state.active_session = new_session(
            mode_value,
            theme_value,
            selected_objective,
            target_cefr=practice_level,
            training_mode=training_mode,
            training_settings=training_settings,
            lesson_context=session_lesson_context,
        )
        st.session_state.pop("practice_last_processed_audio", None)
        st.success(f"Session demarree: {st.session_state.active_session['id']}")

    session_data = st.session_state.active_session
    if session_data and session_data.get("profile_id", "default") != profile_id:
        st.session_state.active_session = None
        session_data = None

    if not session_data:
        st.info("Demarrez une session pour activer les echanges audio.")
        return

    active_drill_key = session_data.get("training_mode", "standard")
    active_drill_label = next(
        (
            lbl
            for lbl, cfg in PRACTICE_DRILL_MODES.items()
            if cfg.get("key") == active_drill_key
        ),
        active_drill_key,
    )
    st.caption(
        f"Session active: {session_data['id']} | Mode: {session_data['mode']} | Theme: {session_data['theme']} | Niveau: {session_data.get('target_cefr', 'B1')} | Drill: {active_drill_label}"
    )

    with st.expander("🗂 Historique IA recent (sauvegarde automatique)"):
        hist_sessions = _recent_practice_sessions(limit=20)
        if not hist_sessions:
            st.info("Aucune session IA sauvegardee pour le moment.")
        else:
            options = [
                f"{s.get('id')} | {s.get('theme', 'N/A')} | {len(s.get('turns', []))} tours"
                for s in hist_sessions
            ]
            selected_hist_idx = st.selectbox(
                "Sessions recentes",
                range(len(hist_sessions)),
                format_func=lambda i: options[i],
                key="practice-hist-select",
            )
            selected_hist = hist_sessions[selected_hist_idx]
            col_h1, col_h2 = st.columns([1, 1])
            with col_h1:
                if st.button(
                    "📂 Charger cette session",
                    key=f"practice-load-session-{selected_hist.get('id')}",
                    width="stretch",
                ):
                    st.session_state.active_session = selected_hist
                    st.session_state.pop("practice_last_processed_audio", None)
                    st.rerun()
            with col_h2:
                st.caption(f"Creee le {selected_hist.get('created_at', '')}")

            if selected_hist.get("evaluation"):
                st.markdown("**Derniere evaluation de cette session :**")
                st.markdown(selected_hist["evaluation"].get("text", ""))

            st.markdown("**Derniers echanges :**")
            for turn in selected_hist.get("turns", [])[-4:]:
                st.markdown(f"- Vous: {turn.get('user_text', '')}")
                st.markdown(f"- IA: {turn.get('ai_text', '')}")

    # ── Timer 4 minutes (Sauf pour la traduction qui finit à son rythme) ──
    is_translation_drill = active_drill_key == "fr_to_en"
    MAX_SESSION_SECONDS = (
        3600 if is_translation_drill else 240
    )  # 1h si traduction, sinon 4 min
    WARN_SECONDS = 3600 if is_translation_drill else 210  # avertir a 3:30
    elapsed = get_elapsed_seconds(session_data)
    remaining = max(0, MAX_SESSION_SECONDS - elapsed)
    progress = min(1.0, elapsed / MAX_SESSION_SECONDS)
    mins_e, secs_e = divmod(elapsed, 60)
    mins_r, secs_r = divmod(remaining, 60)
    final_timeout_turn_done = bool(session_data.get("final_timeout_turn_done", False))
    allow_final_timeout_turn = not final_timeout_turn_done and not bool(
        session_data.get("evaluation")
    )

    if not is_translation_drill:
        if elapsed >= MAX_SESSION_SECONDS:
            if allow_final_timeout_turn:
                st.warning(
                    f"⏰ Session de 4 minutes atteinte ({mins_e}:{secs_e:02d}). "
                    "Envoyez un DERNIER message audio: l'IA vous repondra avant l'evaluation."
                )
            else:
                st.error(
                    f"⏰ Session de 4 minutes terminee ({mins_e}:{secs_e:02d})."
                    " Obtenez votre evaluation ou demarrez une nouvelle session."
                )
        elif elapsed >= WARN_SECONDS:
            st.warning(
                f"⚠️ Moins de 30 secondes restantes ({mins_r}:{secs_r:02d}) !"
                " Terminez votre dernier echange rapidement."
            )
        st.progress(
            progress,
            text=f"⏱️ {mins_e}:{secs_e:02d} ecoulees  |  {mins_r}:{secs_r:02d} restantes  (limite : 4:00)",
        )
    else:
        # Pour la traduction, on affiche juste la durée écoulée sans limite de progression
        st.caption(
            f"⏱️ {mins_e}:{secs_e:02d} ecoulees (la session se termine quand vous avez fini les phrases)."
        )

    if active_drill_key == "conversation_stress":
        stress_limit = int(
            session_data.get("training_settings", {}).get("stress_reply_seconds", 10)
        )
        if session_data.get("turns"):
            anchor_time = session_data["turns"][-1].get("created_at")
        else:
            anchor_time = session_data.get("started_at")
        since_prompt = _seconds_since_iso(anchor_time)
        if since_prompt > stress_limit:
            st.warning(
                f"Conversation stress: vise une reponse en <= {stress_limit}s (actuel: {since_prompt}s)."
            )

    # ── Conversation en cours (affichée AVANT l'input pour que l'input reste en bas) ──
    st.subheader("Conversation en cours")
    if not session_data["turns"]:
        # Refresh starter question for translation drill sessions opened before recent prompt fixes.
        if session_data.get("training_mode") == "fr_to_en":
            _pending = session_data.get("pending_translation_target")
            _direction = str(
                session_data.get("training_settings", {}).get(
                    "translation_direction", "fr_to_en"
                )
            )
            if isinstance(_pending, dict):
                _fresh_question = _format_translation_question(
                    session_data, _pending, _direction
                )
                _current_starter = str(
                    session_data.get("starter_ai_text") or ""
                ).strip()
                if _fresh_question and _fresh_question != _current_starter:
                    session_data["starter_ai_text"] = _fresh_question
                    _meta = session_data.get("starter_drill_meta")
                    if not isinstance(_meta, dict):
                        _meta = {"drill": "fr_to_en"}
                    _meta["direction"] = _direction
                    _meta["lesson"] = str(_pending.get("lesson") or "").strip()
                    _meta["source_id"] = str(_pending.get("source_id") or "").strip()
                    _meta["expected_english"] = str(
                        _pending.get("expected_english") or ""
                    ).strip()
                    _meta["prompt_text"] = _question_prompt_from_target(
                        session_data, _pending, _direction
                    )
                    _meta["contextual_question"] = _fresh_question
                    session_data["starter_drill_meta"] = _meta
                    # Force audio regeneration with the refreshed question text.
                    session_data["starter_ai_audio_path"] = ""
                    session_data["starter_ai_audio_mime"] = "audio/wav"
                    save_session(session_data)
                    st.session_state.active_session = session_data

        starter_text = str(session_data.get("starter_ai_text") or "").strip()
        if session_data.get("training_mode") == "fr_to_en" and starter_text:
            # Show intro/progress OUTSIDE the chat bubble for translation drills
            _s_meta = session_data.get("starter_drill_meta")
            if isinstance(_s_meta, dict):
                _s_fb = _s_meta.get("feedback_blocks")
                if isinstance(_s_fb, list):
                    for fb_line in _s_fb:
                        st.info(fb_line)
                _s_prog = _s_meta.get("progress_line", "")
                if _s_prog:
                    st.caption(_s_prog)

            with st.chat_message("assistant"):
                st.markdown(starter_text)

                starter_audio_path = str(
                    session_data.get("starter_ai_audio_path") or ""
                ).strip()
                starter_audio_mime = (
                    str(
                        session_data.get("starter_ai_audio_mime") or "audio/wav"
                    ).strip()
                    or "audio/wav"
                )

                if not starter_audio_path or not os.path.exists(starter_audio_path):
                    # starter_text is now ONLY the question (matches TTS)
                    speech_text = starter_text
                    if speech_text:
                        starter_direction = str(
                            session_data.get("training_settings", {}).get(
                                "translation_direction", "fr_to_en"
                            )
                        )
                        starter_lang_hint = (
                            "fr" if starter_direction == "fr_to_en" else "en"
                        )
                        with st.spinner(
                            "Lecture automatique de la premiere phrase de revision..."
                        ):
                            audio_bytes, audio_mime, err = text_to_speech_openrouter(
                                speech_text,
                                language_hint=starter_lang_hint,
                            )
                        if (err or not audio_bytes) and ELEVENLABS_API_KEY:
                            fallback_audio, fallback_mime, fallback_err = (
                                text_to_speech_elevenlabs(speech_text)
                            )
                            if not fallback_err and fallback_audio:
                                audio_bytes, audio_mime, err = (
                                    fallback_audio,
                                    fallback_mime,
                                    None,
                                )

                        if err or not audio_bytes:
                            st.warning(
                                "Audio indisponible pour la premiere phrase (TTS)."
                            )
                        elif audio_bytes:
                            audio_ext = ext_from_mime(audio_mime)
                            audio_name = f"{session_data['id']}-starter-ai.{audio_ext}"
                            starter_audio_path = save_audio_bytes(
                                audio_name, audio_bytes
                            )
                            starter_audio_mime = audio_mime
                            session_data["starter_ai_audio_path"] = starter_audio_path
                            session_data["starter_ai_audio_mime"] = starter_audio_mime
                            save_session(session_data)
                            st.session_state.active_session = session_data
                            st.rerun()

                if starter_audio_path and os.path.exists(starter_audio_path):
                    starter_audio_dom_id = "starter_ai_audio_" + re.sub(
                        r"[^a-zA-Z0-9_]",
                        "_",
                        str(session_data.get("id") or "starter"),
                    )
                    with open(starter_audio_path, "rb") as _sf:
                        _sab64 = base64.b64encode(_sf.read()).decode()
                    st_components.html(
                        f"""
                        <audio id="{starter_audio_dom_id}" autoplay controls style="width:100%">
                          <source src="data:{starter_audio_mime};base64,{_sab64}">
                        </audio>
                        <script>
                          (function() {{
                            const a = document.getElementById("{starter_audio_dom_id}");
                            if (!a) return;
                            const tryPlay = () => a.play().catch(() => {{}});
                            tryPlay();
                            document.addEventListener("click", tryPlay, {{ once: true }});
                            document.addEventListener("keydown", tryPlay, {{ once: true }});
                            document.addEventListener("touchstart", tryPlay, {{ once: true }});
                          }})();
                        </script>
                        """,
                        height=80,
                    )
        else:
            st.write(
                "Aucun echange pour le moment — enregistrez votre premier message ci-dessous."
            )
    else:
        for turn in session_data["turns"]:
            with st.chat_message("user"):
                st.markdown(turn["user_text"])
                if os.path.exists(turn["user_audio_path"]):
                    st.audio(turn["user_audio_path"])

            # For translation drills: show feedback/progress OUTSIDE the AI chat bubble
            _turn_drill = turn.get("drill_meta")
            if isinstance(_turn_drill, dict) and _turn_drill.get("drill") == "fr_to_en":
                _fb = _turn_drill.get("feedback_blocks")
                if isinstance(_fb, list) and _fb:
                    for fb_line in _fb:
                        if fb_line.startswith("✅"):
                            st.success(fb_line)
                        elif fb_line.startswith("❌"):
                            st.error(fb_line)
                        else:
                            st.info(fb_line)
                _prog = _turn_drill.get("progress_line", "")
                if _prog:
                    st.caption(_prog)

            with st.chat_message("assistant"):
                st.markdown(turn["ai_text"])
                ai_path = turn.get("ai_audio_path", "")
                if ai_path and os.path.exists(ai_path):
                    # Autoplay uniquement pour le dernier tour fraichement genere
                    if (
                        turn.get("turn") == st.session_state.get("autoplay_turn")
                        and os.path.getsize(ai_path) > 0
                    ):
                        mime = st.session_state.get("autoplay_audio_mime", "audio/wav")
                        with open(ai_path, "rb") as _af:
                            _ab64 = base64.b64encode(_af.read()).decode()
                        st_components.html(
                            f'<audio autoplay style="width:100%" controls>'
                            f'<source src="data:{mime};base64,{_ab64}">'
                            f"</audio>",
                            height=60,
                        )
                        st.session_state.pop("autoplay_turn", None)
                        st.session_state.pop("autoplay_audio_path", None)
                        st.session_state.pop("autoplay_audio_mime", None)
                    else:
                        st.audio(ai_path)

    # ── Evaluation ──
    if session_data.get("evaluation"):
        st.subheader("Evaluation")
        st.markdown(session_data["evaluation"]["text"])

    st.divider()

    if session_data.get("evaluation"):
        st.info("Session terminee. Pour continuer, demarrez une nouvelle session.")
        if st.button("🔁 Recommencer une nouvelle session", type="primary"):
            st.session_state.active_session = None
            st.session_state.pop("practice_last_processed_audio", None)
            st.rerun()
        return

    # ── Audio input EN BAS (toujours visible, suit la conversation) ──
    # Clé dynamique basée sur le nombre de tours : force le reset du widget après chaque envoi
    n_turns = len(session_data["turns"])
    audio_key = f"practice_audio_input_{session_data['id']}_{n_turns}"
    eval_clicked = False

    if elapsed < MAX_SESSION_SECONDS or allow_final_timeout_turn:
        st.markdown("**🎙️ Votre message :**")
        if elapsed < MAX_SESSION_SECONDS:
            st.caption(
                "Envoi automatique: dès que vous arretez l'enregistrement, le message est envoye a l'IA."
            )
        else:
            st.caption(
                "Temps ecoule: envoyez votre dernier message maintenant. L'evaluation sera disponible juste apres la reponse de l'IA."
            )
        audio_file = st.audio_input(
            "Cliquez sur le micro, parlez, puis cliquez à nouveau pour arrêter",
            key=audio_key,
        )

        auto_send_ready = False
        user_audio_bytes = None
        if audio_file:
            candidate_bytes = audio_file.getvalue()
            fingerprint = hashlib.sha1(candidate_bytes).hexdigest()
            marker = f"{audio_key}:{fingerprint}"
            if st.session_state.get("practice_last_processed_audio") != marker:
                st.session_state["practice_last_processed_audio"] = marker
                auto_send_ready = True
                user_audio_bytes = candidate_bytes

        if elapsed < MAX_SESSION_SECONDS:
            col_clear, col_eval = st.columns([1, 1])
            with col_clear:
                if st.button("🗑️ Effacer", width="stretch"):
                    st.session_state.pop(audio_key, None)
                    st.session_state.pop("practice_last_processed_audio", None)
                    st.rerun()
            with col_eval:
                eval_clicked = st.button("📊 Evaluer", width="stretch")
        else:
            if st.button("🗑️ Effacer", width="stretch"):
                st.session_state.pop(audio_key, None)
                st.session_state.pop("practice_last_processed_audio", None)
                st.rerun()
    else:
        audio_file = None
        auto_send_ready = False
        user_audio_bytes = None
        col_eval_only = st.columns(1)[0]
        with col_eval_only:
            eval_clicked = st.button(
                "📊 Obtenir la note de fin de session",
                type="primary",
                width="stretch",
            )

    if auto_send_ready:
        if not user_audio_bytes:
            st.warning("Aucun audio detecte. Reessayez l'enregistrement.")
        else:
            user_submitted_at = now_iso()
            last_anchor = (
                session_data["turns"][-1].get("created_at")
                if session_data.get("turns")
                else session_data.get("started_at")
            )
            response_latency_seconds = _seconds_between_iso(
                last_anchor, user_submitted_at
            )
            if len(user_audio_bytes) < 100:
                st.warning("L'audio est trop court. Parlez plus longtemps.")
            else:
                turn_index = len(session_data["turns"]) + 1
                user_audio_name = f"{session_data['id']}-turn-{turn_index}-user.wav"
                user_audio_path = save_audio_bytes(user_audio_name, user_audio_bytes)

                with st.spinner("Transcription..."):
                    user_text, err = transcribe_audio_with_openrouter(
                        user_audio_bytes, audio_format="wav"
                    )
                if err:
                    st.error(f"Erreur transcription: {err}")
                else:
                    # For translation drills, don't accumulate messages in history
                    # (the drill logic doesn't use message history)
                    if not is_translation_drill:
                        session_data["messages"].append(
                            {"role": "user", "content": user_text}
                        )
                    with st.spinner("L'IA prepare sa reponse..."):
                        ai_text, err, drill_meta = get_ai_reply(
                            session_data, user_text, elapsed_seconds=elapsed
                        )
                    if err:
                        st.error(f"Erreur reponse IA: {err}")
                    else:
                        if not is_translation_drill:
                            session_data["messages"].append(
                                {"role": "assistant", "content": ai_text}
                            )
                        with st.spinner("Synthese vocale..."):
                            # ai_text is now ONLY the question for translation drills
                            tts_text = ai_text
                            tts_lang_hint = None
                            if is_translation_drill:
                                drill_direction = str(
                                    (drill_meta or {}).get(
                                        "direction",
                                        session_data.get(
                                            "training_settings", {}
                                        ).get("translation_direction", "fr_to_en"),
                                    )
                                )
                                tts_lang_hint = (
                                    "fr" if drill_direction == "fr_to_en" else "en"
                                )
                            ai_audio_bytes, ai_audio_mime, err = (
                                text_to_speech_openrouter(
                                    tts_text,
                                    language_hint=tts_lang_hint,
                                )
                            )
                        if err:
                            ai_audio_mime = "audio/wav"
                            ai_audio_bytes = b""

                        ai_ext = ext_from_mime(ai_audio_mime)
                        ai_audio_name = (
                            f"{session_data['id']}-turn-{turn_index}-ai.{ai_ext}"
                        )
                        ai_audio_path = save_audio_bytes(ai_audio_name, ai_audio_bytes)

                        turn_record = {
                            "turn": turn_index,
                            "created_at": now_iso(),
                            "user_submitted_at": user_submitted_at,
                            "response_latency_seconds": response_latency_seconds,
                            "user_audio_path": user_audio_path,
                            "user_text": user_text,
                            "ai_text": ai_text,
                            "ai_audio_path": ai_audio_path,
                            "ai_audio_mime": ai_audio_mime,
                            "drill_meta": drill_meta,
                        }
                        if elapsed >= MAX_SESSION_SECONDS:
                            session_data["final_timeout_turn_done"] = True
                        session_data["turns"].append(turn_record)
                        save_session(session_data)  # sauvegarde automatique
                        st.session_state.active_session = session_data
                        st.session_state["autoplay_turn"] = turn_index
                        st.session_state["autoplay_audio_path"] = ai_audio_path
                        st.session_state["autoplay_audio_mime"] = ai_audio_mime
                        st.session_state.pop(audio_key, None)
                        st.rerun()

    if eval_clicked:
        if not session_data["turns"]:
            st.warning("Faites au moins un echange avant de demander l'evaluation.")
        else:
            with st.spinner("Evaluation en cours..."):
                result, err = evaluate_session(session_data)
            if err:
                st.error(f"Erreur evaluation: {err}")
            else:
                session_data["evaluation"] = {"created_at": now_iso(), "text": result}
                save_session(session_data)
                st.session_state.active_session = session_data
                st.rerun()

