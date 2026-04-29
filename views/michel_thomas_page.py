import hashlib
import io
import json
import os
import time as _time
import wave

import streamlit as st
import streamlit.components.v1 as _components

from modules.ai_client import (
    openrouter_chat,
    text_to_speech_openrouter,
    transcribe_audio_with_openrouter,
    tts_smart,
)
from modules.config import (
    CEFR_LEVELS,
    CHAT_MODEL,
    MT_DIALOGUE_THEMES,
    MT_GRAMMAR_CONCEPTS,
    STORY_NARRATOR_VOICES,
)
from modules.michel_thomas import (
    _save_dialogue_full_audio,
    _save_lesson_course_audio,
    _save_lesson_example_audio,
    _save_lesson_practice_audio,
    _save_themed_dialogue_line_audio,
    _update_dialogue_full_audio,
    _update_lesson_course_audio_path,
    _update_lesson_example_audio,
    _update_lesson_practice_audio,
    _update_themed_dialogue_line_audio,
    build_lesson_narration_script,
    evaluate_practice_pair,
    generate_lesson_session,
    generate_themed_dialogue,
    load_mt_lesson_sessions,
    load_mt_themed_dialogues,
    save_mt_lesson_sessions,
    save_mt_themed_dialogues,
)
from modules.profiles import (
    get_active_profile,
    get_profile_module_level,
    set_profile_module_level,
)
from modules.utils import extract_json_from_text

# ── helpers ───────────────────────────────────────────────────────────────────


def _load_audio(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None


def _concat_wav_files(paths):
    """Concatenate WAV files into one. Returns bytes or None."""
    valid = [p for p in paths if p and os.path.exists(p)]
    if not valid:
        return None
    try:
        params = None
        frames_list = []
        for p in valid:
            with wave.open(p, "rb") as wf:
                if params is None:
                    params = wf.getparams()
                frames_list.append(wf.readframes(wf.getnframes()))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wout:
            wout.setparams(params)
            for frames in frames_list:
                wout.writeframes(frames)
        return buf.getvalue()
    except Exception:
        return None


def _generate_dialogue_full_audio(session, sid, profile_id, voice):
    """Generate all missing line audios, merge them, and persist a single dialogue file."""
    lines = session.get("lines", [])
    if not lines:
        return False, "Aucune ligne de dialogue disponible."

    for li, line in enumerate(lines):
        if line.get("audio_path_en") and os.path.exists(line.get("audio_path_en", "")):
            continue

        ab, _, tts_err = tts_smart(
            line.get("line_en", ""), voice=voice, language_hint="en"
        )
        if tts_err or not ab:
            return False, tts_err or f"Audio indisponible pour la ligne {li + 1}."

        path = _save_themed_dialogue_line_audio(sid, li, ab)
        _update_themed_dialogue_line_audio(profile_id, sid, li, path)
        lines[li]["audio_path_en"] = path

    merged = _concat_wav_files([line.get("audio_path_en", "") for line in lines])
    if not merged:
        return False, "Impossible de générer l'audio complet du dialogue."

    full_path = _save_dialogue_full_audio(sid, merged)
    _update_dialogue_full_audio(profile_id, sid, full_path)
    return True, None


def _force_play_latest_audio_js(tag: str):
    """Attempt to force-play the latest audio element rendered by Streamlit."""
    _components.html(
        f"""
<div id="ap-{tag}" style="display:none"></div>
<script>
(function() {{
        let attempts = 0;
        function tryPlay() {{
            try {{
                const doc = window.parent.document;
                const audios = doc.querySelectorAll('audio');
                if (!audios || !audios.length) {{
                    if (attempts++ < 20) setTimeout(tryPlay, 120);
                    return;
                }}
                const a = audios[audios.length - 1];
                a.autoplay = true;
                a.muted = false;
                a.volume = 1.0;
                const p = a.play();
                if (p && p.catch) {{
                    p.catch(() => {{
                        if (attempts++ < 20) setTimeout(tryPlay, 120);
                    }});
                }}
            }} catch (e) {{
                if (attempts++ < 20) setTimeout(tryPlay, 120);
            }}
        }}
        tryPlay();
}})();
</script>
""",
        height=0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Leçon & Pratique
# ═══════════════════════════════════════════════════════════════════════════════


def _render_lesson_tab(profile, profile_id):
    st.subheader("📖 Leçon & Pratique — Anglais / Français")
    st.caption(
        "Choisis un concept grammatical. L'IA génère surtout des usages américains réels "
        "(situations concrètes, intention du locuteur, comparaison avec le français naturel)."
    )

    saved_level = get_profile_module_level(profile, "michel_thomas") or "B1"
    if saved_level not in CEFR_LEVELS:
        saved_level = "B1"

    with st.expander("⚙️ Paramètres de la leçon", expanded=True):
        c1, c2, c3 = st.columns([1, 2, 1])
        with c1:
            level = st.selectbox(
                "Niveau CEFR",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index(saved_level),
                key="lesson_level_sel",
            )
            if level != saved_level:
                set_profile_module_level(profile_id, "michel_thomas", level)
        with c2:
            all_lesson_concepts = MT_GRAMMAR_CONCEPTS.get(level, [])
            concepts_selected = st.multiselect(
                "Concept(s) grammatical(aux)",
                all_lesson_concepts,
                key="lesson_concept_sel",
                placeholder="Choisir un ou plusieurs concepts…",
            )
        with c3:
            voices = list(STORY_NARRATOR_VOICES.values())
            voice_labels = list(STORY_NARRATOR_VOICES.keys())
            voice_idx = st.selectbox(
                "Voix anglaise",
                range(len(voice_labels)),
                format_func=lambda i: voice_labels[i],
                key="lesson_voice_sel",
            )
            voice = voices[voice_idx]

        gen_col, _ = st.columns([2, 3])
        with gen_col:
            generate_btn = st.button(
                "✨ Générer la leçon",
                key="lesson_gen_btn",
                type="primary",
                use_container_width=True,
                disabled=not concepts_selected,
            )

    if generate_btn:
        concept = " & ".join(concepts_selected)
        with st.spinner(f"Génération du cours sur « {concept} »..."):
            session, err = generate_lesson_session(concept, level, profile_id)
        if err:
            st.error(f"Erreur : {err}")
        else:
            sessions = load_mt_lesson_sessions(profile_id)
            sessions.insert(0, session)
            save_mt_lesson_sessions(sessions, profile_id)
            st.session_state["lesson_active_sid"] = session["id"]
            st.session_state.pop(f"lesson_mode_{session['id']}", None)
            st.rerun()

    sessions = load_mt_lesson_sessions(profile_id)
    if not sessions:
        st.info(
            "Aucune leçon générée. Choisis un concept et clique sur **Générer la leçon**."
        )
        return

    selected_concept_signature = " & ".join(concepts_selected)
    concept_signature_key = "lesson_last_concept_signature"
    if concepts_selected:
        previous_signature = st.session_state.get(concept_signature_key)
        if previous_signature != selected_concept_signature:
            concept_tokens = [
                c.strip().casefold() for c in concepts_selected if c.strip()
            ]
            level_sessions = [
                s for s in sessions if s.get("level") == level
            ] or sessions

            matched_session = None
            for s in level_sessions:
                session_concept = str(s.get("concept", "")).casefold()
                if concept_tokens and all(
                    tok in session_concept for tok in concept_tokens
                ):
                    matched_session = s
                    break

            if matched_session:
                st.session_state["lesson_active_sid"] = matched_session["id"]

        st.session_state[concept_signature_key] = selected_concept_signature
    else:
        st.session_state.pop(concept_signature_key, None)

    session_labels = [
        f"{s.get('lesson', {}).get('title_fr', s.get('concept', '?'))} ({s.get('level', '?')}) — {s.get('created_at', '')[:10]}"
        for s in sessions
    ]
    active_sid = st.session_state.get("lesson_active_sid", sessions[0]["id"])
    if not any(s.get("id") == active_sid for s in sessions):
        active_sid = sessions[0]["id"]
    active_idx = next((i for i, s in enumerate(sessions) if s["id"] == active_sid), 0)

    sel_col, del_col = st.columns([5, 1])
    with sel_col:
        chosen_idx = st.selectbox(
            "Leçon active",
            range(len(sessions)),
            index=active_idx,
            format_func=lambda i: session_labels[i],
            key="lesson_session_sel",
        )
    st.session_state["lesson_active_sid"] = sessions[chosen_idx]["id"]
    session = sessions[chosen_idx]
    sid = session["id"]

    with del_col:
        st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
        if st.button("🗑️", key=f"lesson_del_{sid}", help="Supprimer cette leçon"):
            sessions = load_mt_lesson_sessions(profile_id)
            sessions = [s for s in sessions if s["id"] != sid]
            save_mt_lesson_sessions(sessions, profile_id)
            st.session_state.pop("lesson_active_sid", None)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    mode_key = f"lesson_mode_{sid}"
    if mode_key not in st.session_state:
        st.session_state[mode_key] = "course"

    m1, m2 = st.columns(2)
    with m1:
        if st.button(
            "📚 Cours",
            key=f"lesson_mode_course_{sid}",
            type="primary" if st.session_state[mode_key] == "course" else "secondary",
            use_container_width=True,
        ):
            st.session_state[mode_key] = "course"
            st.rerun()
    with m2:
        if st.button(
            "🏋️ Pratique",
            key=f"lesson_mode_practice_{sid}",
            type="primary" if st.session_state[mode_key] == "practice" else "secondary",
            use_container_width=True,
        ):
            st.session_state[mode_key] = "practice"
            st.session_state[f"practice_idx_{sid}"] = 0
            st.session_state[f"practice_submitted_{sid}"] = False
            st.rerun()

    st.markdown("---")

    if st.session_state[mode_key] == "course":
        _render_lesson_course(session, sid, profile_id, voice)
    else:
        _render_lesson_practice(session, sid, profile_id)


def _render_lesson_course(session, sid, profile_id, voice):
    lesson = session.get("lesson", {})
    level = session.get("level", "?")

    # Reload for fresh audio paths
    fresh_sessions = load_mt_lesson_sessions(profile_id)
    fresh = next((s for s in fresh_sessions if s["id"] == sid), session)
    fresh_lesson = fresh.get("lesson", lesson)

    # ── Title card ─────────────────────────────────────────────────────────────
    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#1e3a5f,#0d2137);padding:20px 24px;border-radius:14px;margin-bottom:16px">
  <span style="font-size:11px;color:#8ab4e8;font-weight:700;letter-spacing:2px;text-transform:uppercase">Niveau {level} · Leçon</span><br/>
  <span style="font-size:24px;font-weight:800;color:#ffffff">{fresh_lesson.get('title_fr', '')}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    # ── Course audio — prominently first ───────────────────────────────────────
    st.markdown("### 🎧 Écouter le cours")
    course_audio_bytes = _load_audio(fresh_lesson.get("course_audio_path"))

    if course_audio_bytes:
        st.audio(course_audio_bytes, format="audio/wav")
        if st.button("🔄 Regénérer l'audio du cours", key=f"regen_course_audio_{sid}"):
            script = build_lesson_narration_script(fresh_lesson)
            with st.spinner("Génération de l'audio du cours…"):
                ab, _, tts_err = tts_smart(script, voice=voice, language_hint="fr")
            if not tts_err:
                path = _save_lesson_course_audio(sid, ab)
                _update_lesson_course_audio_path(profile_id, sid, path)
                st.rerun()
            else:
                st.error(tts_err)
    else:
        st.info("L'audio du cours n'a pas encore été généré.")
        if st.button(
            "🔊 Générer l'audio du cours",
            key=f"gen_course_audio_{sid}",
            type="primary",
            use_container_width=True,
        ):
            script = build_lesson_narration_script(fresh_lesson)
            with st.spinner("Génération de l'audio du cours (quelques secondes)…"):
                ab, _, tts_err = tts_smart(script, voice=voice, language_hint="fr")
            if not tts_err:
                path = _save_lesson_course_audio(sid, ab)
                _update_lesson_course_audio_path(profile_id, sid, path)
                st.rerun()
            else:
                st.error(tts_err)

    st.markdown("---")

    # ── ACTION TOOLS — situation / binary decision / chunks ────────────────────
    situation = fresh_lesson.get("situation_fr", "")
    decision = fresh_lesson.get("decision_binaire_fr", "")
    chunks = fresh_lesson.get("chunks", [])

    if situation or decision or chunks:
        st.markdown("### 🎯 Outils pour ne pas réfléchir")

        if situation:
            st.markdown(
                f"""
<div style="background:linear-gradient(135deg,#1a2a1a,#0f1f0f);padding:16px 20px;border-radius:12px;border-left:5px solid #4caf50;margin-bottom:12px">
  <span style="font-size:11px;color:#81c784;font-weight:700;letter-spacing:2px;text-transform:uppercase">🎬 La scène — quand est-ce qu'un Américain dit ça ?</span><br/>
  <span style="font-size:15px;color:#e8f5e9;line-height:1.7">{situation}</span>
</div>
""",
                unsafe_allow_html=True,
            )

        if decision:
            lines = decision.strip().split("\n")
            decision_html = "".join(
                f"<div style='padding:6px 0;font-size:15px;color:#fff;line-height:1.6'>{line}</div>"
                for line in lines
                if line.strip()
            )
            st.markdown(
                f"""
<div style="background:linear-gradient(135deg,#1e1a2e,#130f22);padding:16px 20px;border-radius:12px;border-left:5px solid #9c27b0;margin-bottom:12px">
  <span style="font-size:11px;color:#ce93d8;font-weight:700;letter-spacing:2px;text-transform:uppercase">🔀 Décision binaire — la règle rapide</span><br/>
  {decision_html}
</div>
""",
                unsafe_allow_html=True,
            )

        if chunks:
            chunks_html = "".join(
                f"<div style='display:inline-block;background:#1e3a5f;border:1px solid #4a90d9;border-radius:8px;"
                f"padding:8px 14px;margin:4px;font-size:15px;font-weight:600;color:#e8f0fe'>{c}</div>"
                for c in chunks
            )
            st.markdown(
                f"""
<div style="background:#12223a;padding:16px 20px;border-radius:12px;border-left:5px solid #2196f3;margin-bottom:12px">
  <span style="font-size:11px;color:#90caf9;font-weight:700;letter-spacing:2px;text-transform:uppercase">💬 Chunks à mémoriser — copie-colle dans ta tête</span><br/>
  <div style="margin-top:10px">{chunks_html}</div>
</div>
""",
                unsafe_allow_html=True,
            )

        st.markdown("---")

    # ── Written course — collapsed by default ─────────────────────────────────
    with st.expander("📖 Voir le cours écrit", expanded=False):
        what = fresh_lesson.get("what_is_it_fr", "")
        if what:
            st.markdown("**💡 Ce que les Américains veulent exprimer**")
            st.info(what)

        when_raw = fresh_lesson.get("when_to_use_fr", "")
        if when_raw:
            st.markdown("**🗓️ Quand l'utiliser ?**")
            for line in when_raw.split("\n"):
                line = line.strip()
                if line:
                    st.markdown(line)

        struct = fresh_lesson.get("structure", {})
        if any(struct.values()):
            st.markdown("**🧩 Structure**")
            struct_html = ""
            for label, formula in [
                ("Affirmative", struct.get("affirmative", "")),
                ("Négative", struct.get("negative", "")),
                ("Question", struct.get("question", "")),
            ]:
                if formula:
                    struct_html += (
                        f"<div style='background:#1a1a2e;padding:10px 16px;border-radius:8px;"
                        f"border-left:4px solid #7c4dff;margin-bottom:8px'>"
                        f"<span style='color:#b39ddb;font-size:11px;font-weight:700'>{label}</span><br/>"
                        f"<code style='color:#e8d5ff;font-size:15px'>{formula}</code></div>"
                    )
            st.markdown(struct_html, unsafe_allow_html=True)

        analogy = fresh_lesson.get("analogy_fr", "")
        if analogy:
            st.markdown("**🇫🇷 L'analogie avec le français**")
            st.success(analogy)

        kp = fresh_lesson.get("key_points_fr", [])
        if kp:
            st.markdown("**⚠️ Points importants**")
            for point in kp:
                st.markdown(f"- {point}")

    # ── Examples with individual audio ────────────────────────────────────────
    examples = fresh_lesson.get("examples", [])
    if examples:
        st.markdown("### 🔍 Exemples")
        for i, ex in enumerate(examples):
            en = ex.get("english", "")
            fr_txt = ex.get("french", "")
            us_context = ex.get("us_context_fr", "")
            intention = ex.get("intention_fr", "")
            compare_fr = ex.get("compare_fr", "")
            audio_en = _load_audio(ex.get("audio_path_en"))
            audio_fr = _load_audio(ex.get("audio_path_fr"))

            st.markdown(
                f"""
<div style="background:#1e3a5f;padding:12px 18px;border-radius:10px;border-left:5px solid #4a90d9;margin-bottom:4px">
  <span style="font-size:11px;color:#8ab4e8;font-weight:700">🇬🇧 ANGLAIS</span><br/>
  <span style="font-size:18px;font-weight:700;color:#fff">{en}</span>
</div>
<div style="background:#1a3320;padding:10px 18px;border-radius:10px;border-left:5px solid #4caf50;margin-bottom:10px">
  <span style="font-size:11px;color:#88c989;font-weight:700">🇫🇷 FRANÇAIS</span><br/>
  <span style="font-size:16px;color:#e8f5e9">{fr_txt}</span>
</div>
""",
                unsafe_allow_html=True,
            )

            if us_context:
                st.caption(f"🇺🇸 Contexte typique: {us_context}")
            if intention:
                st.caption(f"🎯 Nuance voulue: {intention}")
            if compare_fr:
                st.caption(f"🇫🇷 Comparaison FR naturelle: {compare_fr}")

            col_en, col_fr, col_cnt = st.columns([1, 1, 2])
            with col_en:
                if audio_en:
                    st.audio(audio_en, format="audio/wav")
                else:
                    if st.button(f"🔊 EN", key=f"ex-en-gen-{sid}-{i}"):
                        with st.spinner("TTS..."):
                            ab, _, tts_err = tts_smart(
                                en, voice=voice, language_hint="en"
                            )
                        if not tts_err:
                            path = _save_lesson_example_audio(sid, i, "en", ab)
                            _update_lesson_example_audio(
                                profile_id, sid, i, "audio_path_en", path
                            )
                            st.rerun()
                        else:
                            st.error(tts_err)
            with col_fr:
                if audio_fr:
                    st.audio(audio_fr, format="audio/wav")
                else:
                    if st.button(f"🔊 FR", key=f"ex-fr-gen-{sid}-{i}"):
                        with st.spinner("TTS..."):
                            ab, _, tts_err = tts_smart(
                                fr_txt, voice="shimmer", language_hint="fr"
                            )
                        if not tts_err:
                            path = _save_lesson_example_audio(sid, i, "fr", ab)
                            _update_lesson_example_audio(
                                profile_id, sid, i, "audio_path_fr", path
                            )
                            st.rerun()
                        else:
                            st.error(tts_err)
            with col_cnt:
                st.caption(f"Exemple {i + 1}/{len(examples)}")

    st.markdown("---")
    if st.button(
        "🏋️ Aller à la Pratique →",
        key=f"goto_practice_{sid}",
        type="primary",
        use_container_width=True,
    ):
        st.session_state[f"lesson_mode_{sid}"] = "practice"
        st.session_state[f"practice_idx_{sid}"] = 0
        st.session_state[f"practice_submitted_{sid}"] = False
        st.rerun()


def _render_lesson_practice(session, sid, profile_id):
    pairs = session.get("practice_pairs", [])
    if not pairs:
        st.warning("Aucune paire de pratique disponible. Régénère la leçon.")
        return

    idx_key = f"practice_idx_{sid}"
    submitted_key = f"practice_submitted_{sid}"
    eval_key = f"practice_eval_{sid}"

    if idx_key not in st.session_state:
        st.session_state[idx_key] = 0
    if submitted_key not in st.session_state:
        st.session_state[submitted_key] = False

    total = len(pairs)
    idx = st.session_state[idx_key]

    st.progress(idx / total, text=f"Exercice {idx + 1} / {total}")

    if idx >= total:
        st.balloons()
        st.success(
            "🎉 Séquence terminée ! Retourne voir le cours ou génère une nouvelle leçon."
        )
        if st.button("🔄 Recommencer", key=f"restart_practice_{sid}"):
            st.session_state[idx_key] = 0
            st.session_state[submitted_key] = False
            st.session_state.pop(eval_key, None)
            st.rerun()
        return

    pair = pairs[idx]
    direction = pair.get("direction", "fr_to_en")
    prompt_text = pair.get("prompt", "")
    hint = pair.get("hint", "")
    usage_note = pair.get("usage_note_fr", "")

    if direction == "fr_to_en":
        badge = "🇫🇷 → 🇬🇧  Traduis en **ANGLAIS**"
        badge_color = "#1e3a5f"
        prompt_lang = "fr"
        answer_lang = "en"
    else:
        badge = "🇬🇧 → 🇫🇷  Traduis en **FRANÇAIS**"
        badge_color = "#1a3320"
        prompt_lang = "en"
        answer_lang = "fr"

    st.markdown(
        f"<div style='background:{badge_color};padding:8px 14px;border-radius:8px;margin-bottom:12px;"
        f"font-size:13px;font-weight:700;color:#fff'>{badge}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<div style="background:#2a2a3e;padding:20px 24px;border-radius:12px;margin-bottom:8px;text-align:center">
  <span style="font-size:22px;font-weight:700;color:#ffffff">{prompt_text}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    # ── Prompt audio ───────────────────────────────────────────────────────────
    prompt_audio_path = pair.get("audio_path_prompt", "")
    prompt_audio_bytes = _load_audio(prompt_audio_path) if prompt_audio_path else None
    if prompt_audio_bytes:
        st.audio(prompt_audio_bytes, format="audio/wav")
    else:
        if st.button("🔊 Écouter la phrase", key=f"practice_prompt_audio_{sid}_{idx}"):
            with st.spinner("Génération de l'audio…"):
                ab, _, tts_err = tts_smart(prompt_text, language_hint=prompt_lang)
            if not tts_err and ab:
                path = _save_lesson_practice_audio(sid, idx, "prompt", ab)
                _update_lesson_practice_audio(
                    profile_id, sid, idx, "audio_path_prompt", path
                )
                # Update in-memory pairs list so audio shows immediately
                pairs[idx]["audio_path_prompt"] = path
                st.rerun()
            else:
                st.warning("Audio indisponible.")

    if hint:
        st.caption(f"💡 Indice : {hint}")
    if usage_note:
        st.caption(f"🇺🇸 Pourquoi cette forme ici : {usage_note}")

    audio_key = f"mt_practice_audio_{sid}_{idx}"
    transcript_key = f"mt_practice_transcript_{sid}_{idx}"
    marker_key = f"mt_practice_marker_{sid}_{idx}"
    user_audio_bytes_key = f"mt_practice_abytes_{sid}_{idx}"

    if not st.session_state[submitted_key]:
        st.markdown("**🎙️ Ta réponse en audio :**")
        user_audio_file = st.audio_input(
            "Enregistre ta réponse, puis clique à nouveau pour arrêter",
            key=audio_key,
        )

        if user_audio_file:
            candidate_bytes = user_audio_file.getvalue()
            fingerprint = hashlib.sha1(candidate_bytes).hexdigest()
            if st.session_state.get(marker_key) != fingerprint:
                st.session_state[marker_key] = fingerprint
                with st.spinner("Transcription…"):
                    transcript, t_err = transcribe_audio_with_openrouter(
                        candidate_bytes, audio_format="wav"
                    )
                if t_err:
                    st.warning(f"Transcription échouée : {t_err}")
                else:
                    st.session_state[transcript_key] = transcript
                    st.session_state[user_audio_bytes_key] = candidate_bytes

        user_input = st.session_state.get(transcript_key, "")
        if user_input:
            st.caption(f"📝 Transcription : *{user_input}*")

        submit_col, skip_col = st.columns([3, 1])
        with submit_col:
            if st.button(
                "✅ Valider",
                key=f"practice_submit_{sid}_{idx}",
                type="primary",
                disabled=not user_input.strip(),
                use_container_width=True,
            ):
                with st.spinner("Évaluation en cours…"):
                    eval_result, err = evaluate_practice_pair(pair, user_input.strip())
                if err:
                    st.error(err)
                else:
                    st.session_state[eval_key] = eval_result
                    st.session_state[submitted_key] = True
                    # Generate TTS for feedback and improved answer eagerly
                    _feedback_text = eval_result.get("feedback_fr", "")
                    _improved = eval_result.get("improved_answer", "")
                    if _feedback_text:
                        with st.spinner("Audio de la correction…"):
                            _fb_ab, _, _fb_err = tts_smart(
                                _feedback_text, language_hint="fr"
                            )
                        if not _fb_err and _fb_ab:
                            _fb_path = _save_lesson_practice_audio(
                                sid, idx, "feedback", _fb_ab
                            )
                            _update_lesson_practice_audio(
                                profile_id, sid, idx, "audio_path_feedback", _fb_path
                            )
                            pairs[idx]["audio_path_feedback"] = _fb_path
                    if _improved and _improved != pair.get("answer", ""):
                        with st.spinner("Audio de la version améliorée…"):
                            _imp_ab, _, _imp_err = tts_smart(
                                _improved, language_hint=answer_lang
                            )
                        if not _imp_err and _imp_ab:
                            _imp_path = _save_lesson_practice_audio(
                                sid, idx, "improved", _imp_ab
                            )
                            _update_lesson_practice_audio(
                                profile_id, sid, idx, "audio_path_improved", _imp_path
                            )
                            pairs[idx]["audio_path_improved"] = _imp_path
                    st.rerun()
        with skip_col:
            if st.button(
                "⏭️ Passer",
                key=f"practice_skip_{sid}_{idx}",
                use_container_width=True,
            ):
                st.session_state[idx_key] = idx + 1
                st.session_state[submitted_key] = False
                st.session_state.pop(eval_key, None)
                st.session_state.pop(transcript_key, None)
                st.session_state.pop(marker_key, None)
                st.session_state.pop(user_audio_bytes_key, None)
                st.rerun()
    else:
        eval_result = st.session_state.get(eval_key, {})
        score = eval_result.get("score", 0)
        correct = eval_result.get("correct", False)
        feedback = eval_result.get("feedback_fr", "")
        improved = eval_result.get("improved_answer", "")
        expected = pair.get("answer", "")

        # ── User's recorded answer ─────────────────────────────────────────────
        user_transcript = st.session_state.get(transcript_key, "")
        user_audio_stored = st.session_state.get(user_audio_bytes_key)
        if user_transcript or user_audio_stored:
            st.markdown("**🎙️ Ta réponse :**")
            if user_transcript:
                st.caption(f"📝 {user_transcript}")
            if user_audio_stored:
                st.audio(user_audio_stored, format="audio/wav")

        st.markdown("---")

        # ── Score + feedback text ──────────────────────────────────────────────
        score_color = (
            "#4caf50" if score >= 75 else "#ff9800" if score >= 50 else "#f44336"
        )
        icon = "✅" if correct else "💪"
        st.markdown(
            f"""
<div style="background:#1a1a2e;padding:16px 20px;border-radius:12px;border-left:6px solid {score_color};margin-bottom:8px">
  <span style="font-size:28px;font-weight:800;color:{score_color}">{icon} {score}/100</span><br/>
  <span style="color:#ddd;font-size:15px">{feedback}</span>
</div>
""",
            unsafe_allow_html=True,
        )

        # ── Feedback audio (correction) ────────────────────────────────────────
        feedback_audio_path = pair.get("audio_path_feedback", "")
        feedback_audio_bytes = (
            _load_audio(feedback_audio_path) if feedback_audio_path else None
        )
        if feedback_audio_bytes:
            st.audio(feedback_audio_bytes, format="audio/wav")
        elif feedback:
            if st.button(
                "🔊 Écouter la correction", key=f"practice_feedback_audio_{sid}_{idx}"
            ):
                with st.spinner("Génération de l'audio…"):
                    ab, _, tts_err = tts_smart(feedback, language_hint="fr")
                if not tts_err and ab:
                    path = _save_lesson_practice_audio(sid, idx, "feedback", ab)
                    _update_lesson_practice_audio(
                        profile_id, sid, idx, "audio_path_feedback", path
                    )
                    pairs[idx]["audio_path_feedback"] = path
                    st.rerun()
                else:
                    st.warning("Audio indisponible.")

        # ── Expected answer ────────────────────────────────────────────────────
        st.markdown(
            f"""
<div style="background:#1e3a5f;padding:10px 16px;border-radius:8px;margin-bottom:4px">
  <span style="font-size:11px;color:#8ab4e8;font-weight:700">✔️ RÉPONSE ATTENDUE</span><br/>
  <span style="font-size:17px;color:#fff;font-weight:600">{expected}</span>
</div>
""",
            unsafe_allow_html=True,
        )

        # ── Answer audio ───────────────────────────────────────────────────────
        answer_audio_path = pair.get("audio_path_answer", "")
        answer_audio_bytes = (
            _load_audio(answer_audio_path) if answer_audio_path else None
        )
        if answer_audio_bytes:
            st.audio(answer_audio_bytes, format="audio/wav")
        else:
            if st.button(
                "🔊 Écouter la réponse", key=f"practice_answer_audio_{sid}_{idx}"
            ):
                with st.spinner("Génération de l'audio…"):
                    ab, _, tts_err = tts_smart(expected, language_hint=answer_lang)
                if not tts_err and ab:
                    path = _save_lesson_practice_audio(sid, idx, "answer", ab)
                    _update_lesson_practice_audio(
                        profile_id, sid, idx, "audio_path_answer", path
                    )
                    pairs[idx]["audio_path_answer"] = path
                    st.rerun()
                else:
                    st.warning("Audio indisponible.")

        # ── Improved answer ────────────────────────────────────────────────────
        if improved and improved != expected:
            st.markdown(
                f"""
<div style="background:#332200;padding:10px 16px;border-radius:8px;margin-bottom:4px">
  <span style="font-size:11px;color:#ffb74d;font-weight:700">💡 VERSION AMÉLIORÉE</span><br/>
  <span style="font-size:16px;color:#ffe0b2">{improved}</span>
</div>
""",
                unsafe_allow_html=True,
            )
            improved_audio_path = pair.get("audio_path_improved", "")
            improved_audio_bytes = (
                _load_audio(improved_audio_path) if improved_audio_path else None
            )
            if improved_audio_bytes:
                st.audio(improved_audio_bytes, format="audio/wav")
            else:
                if st.button(
                    "🔊 Écouter la version améliorée",
                    key=f"practice_improved_audio_{sid}_{idx}",
                ):
                    with st.spinner("Génération de l'audio…"):
                        ab, _, tts_err = tts_smart(improved, language_hint=answer_lang)
                    if not tts_err and ab:
                        path = _save_lesson_practice_audio(sid, idx, "improved", ab)
                        _update_lesson_practice_audio(
                            profile_id, sid, idx, "audio_path_improved", path
                        )
                        pairs[idx]["audio_path_improved"] = path
                        st.rerun()
                    else:
                        st.warning("Audio indisponible.")

        next_col, retry_col = st.columns([3, 1])
        with next_col:
            is_last = idx >= total - 1
            if st.button(
                "🎉 Terminer" if is_last else "➡️ Exercice suivant",
                key=f"practice_next_{sid}_{idx}",
                type="primary",
                use_container_width=True,
            ):
                st.session_state[idx_key] = idx + 1
                st.session_state[submitted_key] = False
                st.session_state.pop(eval_key, None)
                st.session_state.pop(transcript_key, None)
                st.session_state.pop(marker_key, None)
                st.session_state.pop(user_audio_bytes_key, None)
                st.rerun()
        with retry_col:
            if st.button(
                "🔁 Retry",
                key=f"practice_retry_{sid}_{idx}",
                use_container_width=True,
            ):
                st.session_state[submitted_key] = False
                st.session_state.pop(eval_key, None)
                st.session_state.pop(transcript_key, None)
                st.session_state.pop(marker_key, None)
                st.session_state.pop(user_audio_bytes_key, None)
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Dialogues thématiques
# ═══════════════════════════════════════════════════════════════════════════════


def _render_dialogue_tab(profile, profile_id):
    st.subheader("💬 Dialogues — Immersion par thème & grammaire")
    st.caption(
        "Choisis un thème de vie quotidienne et un focus grammatical. "
        "L'IA génère un dialogue réaliste avec audio, spotlight grammatical et vocabulaire."
    )

    saved_level = get_profile_module_level(profile, "michel_thomas") or "B1"

    with st.expander("⚙️ Paramètres du dialogue", expanded=True):
        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
        with c1:
            level = st.selectbox(
                "Niveau",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index(
                    saved_level if saved_level in CEFR_LEVELS else "B1"
                ),
                key="dial_level_sel",
            )
        with c2:
            themes_selected = st.multiselect(
                "Thème(s) de vie",
                MT_DIALOGUE_THEMES,
                key="dial_theme_sel",
                placeholder="Choisir un ou plusieurs thèmes…",
            )
        with c3:
            concepts = MT_GRAMMAR_CONCEPTS.get(level, [])
            grammar_focuses_selected = st.multiselect(
                "Focus grammatical",
                concepts,
                key="dial_grammar_sel",
                placeholder="Choisir un ou plusieurs concepts…",
            )
        with c4:
            voices = list(STORY_NARRATOR_VOICES.values())
            voice_labels = list(STORY_NARRATOR_VOICES.keys())
            voice_idx = st.selectbox(
                "Voix",
                range(len(voice_labels)),
                format_func=lambda i: voice_labels[i],
                key="dial_voice_sel",
            )
            voice = voices[voice_idx]

        gen_col, qty_col, _ = st.columns([2, 1, 2])
        with gen_col:
            gen_btn = st.button(
                "✨ Générer le(s) dialogue(s)",
                key="dial_gen_btn",
                type="primary",
                use_container_width=True,
                disabled=not (themes_selected or grammar_focuses_selected),
            )
        with qty_col:
            gen_qty = st.number_input(
                "Quantité",
                min_value=1,
                max_value=5,
                value=1,
                step=1,
                key="dial_gen_qty",
                help="Nombre de dialogues à générer d'un coup",
            )

    if gen_btn:
        theme = " & ".join(themes_selected) if themes_selected else "general"
        grammar_focus = (
            " & ".join(grammar_focuses_selected) if grammar_focuses_selected else ""
        )
        qty = int(st.session_state.get("dial_gen_qty", 1))
        last_sid = None
        errors = []
        prog = st.progress(0) if qty > 1 else None
        for i in range(qty):
            with st.spinner(
                f"Génération du dialogue « {theme} »"
                + (f" ({i + 1}/{qty})" if qty > 1 else "")
                + "..."
            ):
                session, err = generate_themed_dialogue(
                    theme, grammar_focus, level, profile_id
                )
            if err:
                errors.append(err)
            else:
                sessions = load_mt_themed_dialogues(profile_id)
                sessions.insert(0, session)
                save_mt_themed_dialogues(sessions, profile_id)
                audio_ok, audio_err = _generate_dialogue_full_audio(
                    session, session["id"], profile_id, voice
                )
                if not audio_ok and audio_err:
                    errors.append(f"Audio dialogue {i + 1}: {audio_err}")
                last_sid = session["id"]
            if prog:
                prog.progress((i + 1) / qty)
        if errors:
            st.error(" | ".join(errors))
        if last_sid:
            st.session_state["dial_active_sid"] = last_sid
            st.rerun()

    sessions = load_mt_themed_dialogues(profile_id)
    if not sessions:
        st.info(
            "Aucun dialogue généré. Choisis un thème et clique sur **Générer le dialogue**."
        )
        return

    session_labels = [
        f"{s.get('title', s.get('theme', '?'))} ({s.get('level', '?')}) — {s.get('created_at', '')[:10]}"
        for s in sessions
    ]
    active_sid = st.session_state.get("dial_active_sid", sessions[0]["id"])
    active_idx = next((i for i, s in enumerate(sessions) if s["id"] == active_sid), 0)

    chosen_idx = st.selectbox(
        "Dialogue actif",
        range(len(sessions)),
        index=active_idx,
        format_func=lambda i: session_labels[i],
        key="dial_session_sel",
    )
    st.session_state["dial_active_sid"] = sessions[chosen_idx]["id"]
    session = sessions[chosen_idx]
    sid = session["id"]

    st.markdown("---")
    _render_dialogue_session(session, sid, profile_id, voice)


def _render_dialogue_session(session, sid, profile_id, voice):
    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#1a2e1a,#0d1f0d);padding:18px 22px;border-radius:14px;margin-bottom:14px">
  <span style="font-size:11px;color:#88c989;font-weight:700;letter-spacing:2px">
    {session.get('theme','')} · {session.get('grammar_focus','')} · Niveau {session.get('level','')}
  </span><br/>
  <span style="font-size:22px;font-weight:800;color:#ffffff">{session.get('title','')}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    context_fr = session.get("context_fr", "")
    if context_fr:
        st.info(f"📍 **Contexte** : {context_fr}")

    speakers = session.get("speakers", [])
    if speakers:
        speaker_str = " · ".join(
            f"**{s.get('name', '?')}** ({s.get('role', '')})" for s in speakers
        )
        st.caption(f"🎭 Personnages : {speaker_str}")

    fresh_sessions = load_mt_themed_dialogues(profile_id)
    fresh = next((s for s in fresh_sessions if s["id"] == sid), session)
    lines = fresh.get("lines", [])

    # ── Full audio (single player) ─────────────────────────────────────────────
    full_audio_path = fresh.get("full_audio_path", "")
    full_audio_bytes = _load_audio(full_audio_path) if full_audio_path else None

    if full_audio_bytes:
        st.markdown("#### 🎧 Dialogue complet")
        st.audio(full_audio_bytes, format="audio/wav")
        if st.button("🔄 Regénérer l'audio complet", key=f"regen_full_{sid}"):
            for li, line in enumerate(lines):
                line["audio_path_en"] = None
                _update_themed_dialogue_line_audio(profile_id, sid, li, None)
            with st.spinner("Régénération de l'audio complet…"):
                ok, err = _generate_dialogue_full_audio(fresh, sid, profile_id, voice)
            if ok:
                st.rerun()
            else:
                st.error(err)
        st.markdown("---")
    else:
        gen_col, _ = st.columns([2, 3])
        with gen_col:
            if st.button(
                "🔊 Générer l'audio du dialogue",
                key=f"gen_all_audio_{sid}",
                type="primary",
                use_container_width=True,
            ):
                with st.spinner("Génération de l'audio complet du dialogue…"):
                    ok, err = _generate_dialogue_full_audio(
                        fresh, sid, profile_id, voice
                    )
                if ok:
                    st.rerun()
                else:
                    st.error(err)

    imm_key = f"dial_immersion_{sid}"
    if imm_key not in st.session_state:
        st.session_state[imm_key] = False

    im_col, bil_col = st.columns(2)
    with im_col:
        if st.button(
            "🎧 Mode immersion (EN uniquement)",
            key=f"dial_imm_on_{sid}",
            type="primary" if st.session_state[imm_key] else "secondary",
            use_container_width=True,
        ):
            st.session_state[imm_key] = True
            st.rerun()
    with bil_col:
        if st.button(
            "🌍 Mode bilingue (EN + FR)",
            key=f"dial_imm_off_{sid}",
            type="primary" if not st.session_state[imm_key] else "secondary",
            use_container_width=True,
        ):
            st.session_state[imm_key] = False
            st.rerun()

    immersion = st.session_state[imm_key]

    st.markdown("#### 🗣️ Dialogue")
    speaker_names = [s.get("name", "") for s in speakers]
    colors_en = ["#1e3a5f", "#1a2a3a"]
    colors_fr = ["#1a3320", "#142a1a"]

    for li, line in enumerate(lines):
        spk = line.get("speaker", "")
        line_en = line.get("line_en", "")
        line_fr = line.get("line_fr", "")
        grammar_tag = line.get("grammar_tag", "")

        speaker_idx = speaker_names.index(spk) if spk in speaker_names else li % 2
        align = "left" if speaker_idx == 0 else "right"
        c_en = colors_en[speaker_idx % 2]
        c_fr = colors_fr[speaker_idx % 2]
        grammar_badge = (
            f" <span style='background:#7c4dff;color:#fff;font-size:10px;padding:2px 7px;border-radius:12px;margin-left:8px'>{grammar_tag}</span>"
            if grammar_tag
            else ""
        )

        st.markdown(
            f"""
<div style="text-align:{align};margin-bottom:6px">
  <span style="font-size:11px;color:#8ab4e8;font-weight:700">{spk}{grammar_badge}</span><br/>
  <div style="display:inline-block;background:{c_en};padding:10px 16px;border-radius:12px;max-width:80%;text-align:left">
    <span style="font-size:16px;color:#fff;font-weight:600">{line_en}</span>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )

        if not immersion and line_fr:
            st.markdown(
                f"""
<div style="text-align:{align};margin-bottom:2px">
  <div style="display:inline-block;background:{c_fr};padding:6px 14px;border-radius:10px;max-width:80%;text-align:left">
    <span style="font-size:13px;color:#c8e6c9">{line_fr}</span>
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

    spotlight = session.get("grammar_spotlight", [])
    if spotlight:
        st.markdown("---")
        st.markdown("#### 🔬 Grammaire — Spotlight")
        for gs in spotlight:
            with st.expander(f"📌 {gs.get('structure', '')}", expanded=False):
                st.markdown("**Exemple dans le dialogue :**")
                st.info(gs.get("example_from_dialogue", ""))
                st.markdown(f"**Explication :** {gs.get('explanation_fr', '')}")

    vocab = session.get("vocabulary_fr", [])
    if vocab:
        st.markdown("---")
        st.markdown("#### 📖 Vocabulaire clé")
        cols = st.columns(3)
        for vi, v in enumerate(vocab):
            with cols[vi % 3]:
                st.markdown(
                    f"""
<div style="background:#1a1a2e;padding:10px 14px;border-radius:10px;margin-bottom:8px">
  <span style="font-size:15px;font-weight:700;color:#7c4dff">{v.get('word','')}</span><br/>
  <span style="color:#ccc;font-size:13px">{v.get('french','')}</span><br/>
  <span style="color:#888;font-size:11px;font-style:italic">{v.get('tip','')}</span>
</div>
""",
                    unsafe_allow_html=True,
                )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Quiz Chrono
# ═══════════════════════════════════════════════════════════════════════════════


def _estimate_quiz_time(sentence: str, level: str) -> int:
    """Estimate fair response time in seconds (recording overhead included)."""
    words = len(sentence.split())
    # level bonus: more time for beginners
    bonus = {"A1": 6, "A2": 4, "B1": 2, "B2": 1, "C1": 0, "C2": 0}.get(level, 2)
    # base 10s + 0.9s per word + recording overhead 3s + level bonus
    t = 10 + words * 0.9 + 3 + bonus
    return min(30, max(10, round(t)))


def _generate_quiz_questions(
    level: str, concepts: list, themes: list, count: int, direction: str
):
    """Generate quiz questions via AI. Returns (questions_list, error_str)."""
    concepts_str = ", ".join(concepts) if concepts else "any grammar structures"
    themes_str = ", ".join(themes) if themes else "everyday life"

    if direction == "both":
        dir_note = f"Mix both directions: roughly half fr_to_en, half en_to_fr."
    elif direction == "fr_to_en":
        dir_note = (
            'All direction must be "fr_to_en" (prompt in French, answer in English).'
        )
    else:
        dir_note = (
            'All direction must be "en_to_fr" (prompt in English, answer in French).'
        )

        prompt = f"""You are a bilingual English-French quiz generator focused on real American usage.
Generate exactly {count} translation quiz questions for a French native speaker at CEFR level {level}.
Grammar focus: {concepts_str}
Themes: {themes_str}
{dir_note}

Return ONLY a valid JSON array, no markdown, no commentary:
[
    {{
        "direction": "fr_to_en",
        "prompt": "phrase française à traduire",
        "answer": "expected English answer",
        "usage_note_fr": "Contexte typique où un Américain utiliserait cette forme + ce qu'il veut exprimer"
    }},
    {{
        "direction": "en_to_fr",
        "prompt": "English sentence to translate",
        "answer": "traduction française attendue",
        "usage_note_fr": "Comparaison courte avec le français naturel"
    }}
]

Rules:
- Natural sentences fitting {level} level.
- Weave grammar concepts and themes naturally into each sentence.
- Vary sentence length and complexity across questions.
- Provide the most idiomatic correct translation as the answer.
- Do not generate random textbook-style prompts. Use realistic US contexts (work, coffee shop, commute, texting, customer support, friends, etc.).
- For each question, add "usage_note_fr" in French to explain why this tense/form is used in that context.
- IMPORTANT tense mapping for duration:
    - For ongoing actions with "depuis + durée/date" in French, prefer French present (e.g. "Elle étudie le français depuis 3 ans")
        and English present perfect / present perfect continuous ("She has studied..." / "She has been studying...").
    - Avoid unnatural French like "a étudié ... depuis 3 ans" when the action is still ongoing.
    - Use French passé composé + "pendant" only for completed past duration.
- Return exactly {count} items in the array.
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.5,
        max_tokens=2500,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, list):
        return None, "L'IA n'a pas retourné un tableau JSON valide."

    questions = []
    for item in data:
        if not isinstance(item, dict):
            continue
        d = item.get("direction", "fr_to_en")
        p = str(item.get("prompt", "")).strip()
        a = str(item.get("answer", "")).strip()
        if not p or not a:
            continue
        questions.append(
            {
                "direction": d,
                "prompt": p,
                "answer": a,
                "usage_note_fr": str(item.get("usage_note_fr", "")).strip(),
                "allowed_time": _estimate_quiz_time(p, level),
                "audio_bytes": None,
            }
        )
    if not questions:
        return None, "Aucune question générée, réessaie."
    return questions, None


def _quiz_countdown_html(remaining_sec: float, total_sec: int) -> str:
    """Return an HTML/JS circular countdown timer component."""
    pct = max(0.0, min(1.0, remaining_sec / total_sec))
    color = "#4caf50" if pct > 0.5 else "#ff9800" if pct > 0.25 else "#f44336"
    remaining_ms = max(0, int(remaining_sec * 1000))
    return f"""
<div style="display:flex;align-items:center;gap:18px;padding:8px 0">
  <div style="position:relative;width:72px;height:72px;flex-shrink:0">
    <svg width="72" height="72" viewBox="0 0 72 72">
      <circle cx="36" cy="36" r="30" fill="none" stroke="#2a2a3e" stroke-width="7"/>
      <circle id="qz-ring" cx="36" cy="36" r="30" fill="none"
        stroke="{color}" stroke-width="7"
        stroke-dasharray="188.5" stroke-dashoffset="{188.5 * (1 - pct):.1f}"
        stroke-linecap="round" transform="rotate(-90 36 36)"
        style="transition:stroke 0.3s"/>
    </svg>
    <div id="qz-text" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
      font-size:17px;font-weight:800;color:#fff;font-family:monospace">
      {int(remaining_sec)}s
    </div>
  </div>
  <div>
    <div style="font-size:13px;color:#aaa">⏱ Temps restant</div>
    <div style="font-size:11px;color:#666">Temps alloué : {total_sec}s</div>
  </div>
</div>
<script>
(function() {{
  const totalMs = {total_sec * 1000};
  const remainMs = {remaining_ms};
  const circ = 188.5;
  const ring = document.getElementById('qz-ring');
  const txt  = document.getElementById('qz-text');
  const startTs = Date.now();
  function tick() {{
    const elapsed = Date.now() - startTs;
    const left = Math.max(0, remainMs - elapsed);
    const pct = left / totalMs;
    const offset = circ * (1 - pct);
    if (ring) ring.setAttribute('stroke-dashoffset', offset.toFixed(1));
    if (ring) ring.setAttribute('stroke', pct > 0.5 ? '#4caf50' : pct > 0.25 ? '#ff9800' : '#f44336');
    if (txt) txt.textContent = Math.ceil(left / 1000) + 's';
    if (left > 0) requestAnimationFrame(tick);
    else {{
      if (txt) txt.textContent = '0s';
      // Auto-click the timeout button in the parent Streamlit frame
      try {{
        const frame = window.parent.document;
        const btns = frame.querySelectorAll('button');
        for (let b of btns) {{
          if (b.getAttribute('data-qz-timeout') === 'true') {{ b.click(); break; }}
        }}
        // Fallback: find by aria-label
        for (let b of btns) {{
          if (b.getAttribute('aria-label') === '__qz_timeout__') {{ b.click(); break; }}
        }}
      }} catch(e) {{}}
    }}
  }}
  requestAnimationFrame(tick);
}})();
</script>
"""


def _quiz_history_path(profile_id: str) -> str:
    """Return path to the quiz history JSON file for this profile."""
    return os.path.join("data", "mt_lessons", f"quiz-history-{profile_id}.json")


def _load_quiz_history(profile_id: str) -> list:
    """Load quiz history list from disk (newest first)."""
    path = _quiz_history_path(profile_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_quiz_history(profile_id: str, entry: dict) -> None:
    """Append a quiz result entry to the history file (cap at 100 entries)."""
    path = _quiz_history_path(profile_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    history = _load_quiz_history(profile_id)
    history.insert(0, entry)
    history = history[:100]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds as mm:ss."""
    secs = int(round(seconds))
    m, s = divmod(secs, 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _render_quiz_tab(profile, profile_id):
    st.subheader("⚡ Quiz Chrono — Traduction Express")
    st.caption(
        "L'IA te donne une phrase en audio. Traduis-la avant la fin du chrono. "
        "Réponds à l'oral : ta réponse est transcrite et évaluée automatiquement."
    )

    is_active = st.session_state.get("quiz_active", False)

    with st.expander("⚙️ Paramètres du quiz", expanded=not is_active):
        r1c1, r1c2 = st.columns([1, 3])
        with r1c1:
            saved_level = get_profile_module_level(profile, "michel_thomas") or "B1"
            if saved_level not in CEFR_LEVELS:
                saved_level = "B1"
            quiz_level = st.selectbox(
                "Niveau CEFR",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index(saved_level),
                key="quiz_level_sel",
                disabled=is_active,
            )
        with r1c2:
            quiz_concepts = st.multiselect(
                "Concept(s) grammatical(aux)",
                MT_GRAMMAR_CONCEPTS.get(quiz_level, []),
                key="quiz_concepts_sel",
                placeholder="Tous les concepts du niveau…",
                disabled=is_active,
            )

        quiz_themes = st.multiselect(
            "Thème(s) de conversation",
            MT_DIALOGUE_THEMES,
            key="quiz_themes_sel",
            placeholder="Tous les thèmes…",
            disabled=is_active,
        )

        r2c1, r2c2, r2c3 = st.columns(3)
        with r2c1:
            quiz_count = st.number_input(
                "Nombre de questions",
                min_value=3,
                max_value=50,
                value=8,
                step=1,
                key="quiz_count_sel",
                disabled=is_active,
            )
        with r2c2:
            quiz_direction = st.selectbox(
                "Sens de traduction",
                ["Les deux", "Français → Anglais", "Anglais → Français"],
                key="quiz_dir_sel",
                disabled=is_active,
            )
        with r2c3:
            voices = list(STORY_NARRATOR_VOICES.values())
            voice_labels = list(STORY_NARRATOR_VOICES.keys())
            quiz_voice_idx = st.selectbox(
                "Voix IA",
                range(len(voice_labels)),
                format_func=lambda i: voice_labels[i],
                key="quiz_voice_sel",
                disabled=is_active,
            )
            quiz_voice = voices[quiz_voice_idx]

        ctrl1, ctrl2 = st.columns(2)
        with ctrl1:
            start_btn = st.button(
                "▶️ Lancer le quiz",
                key="quiz_start_btn",
                type="primary",
                use_container_width=True,
                disabled=is_active,
            )
        with ctrl2:
            stop_btn = st.button(
                "⏹️ Abandonner / Réinitialiser",
                key="quiz_stop_btn",
                use_container_width=True,
                disabled=not is_active,
            )

    if stop_btn:
        for k in list(st.session_state.keys()):
            if k.startswith("quiz_") and k not in (
                "quiz_level_sel",
                "quiz_concepts_sel",
                "quiz_themes_sel",
                "quiz_count_sel",
                "quiz_dir_sel",
                "quiz_voice_sel",
            ):
                del st.session_state[k]
        st.rerun()

    if start_btn:
        dir_map = {
            "Les deux": "both",
            "Français → Anglais": "fr_to_en",
            "Anglais → Français": "en_to_fr",
        }
        direction_code = dir_map.get(
            st.session_state.get("quiz_dir_sel", "Les deux"), "both"
        )
        with st.spinner("Génération des questions…"):
            questions, err = _generate_quiz_questions(
                quiz_level,
                st.session_state.get("quiz_concepts_sel", []),
                st.session_state.get("quiz_themes_sel", []),
                int(st.session_state.get("quiz_count_sel", 8)),
                direction_code,
            )
        if err:
            st.error(f"Erreur : {err}")
            return

        # Pre-generate TTS for all prompts
        prog = st.progress(0, text="Génération des audios…")
        failed_audio_count = 0
        for i, q in enumerate(questions):
            lang = "fr" if q["direction"] == "fr_to_en" else "en"
            voice_for_prompt = "shimmer" if lang == "fr" else quiz_voice
            ab, mime, tts_err = tts_smart(
                q["prompt"], voice=voice_for_prompt, language_hint=lang
            )
            questions[i]["audio_bytes"] = ab
            questions[i]["audio_mime"] = mime or "audio/wav"
            questions[i]["audio_error"] = tts_err
            if not ab:
                failed_audio_count += 1
            prog.progress(
                (i + 1) / len(questions), text=f"Audio {i+1}/{len(questions)}…"
            )

        if failed_audio_count:
            st.warning(
                f"{failed_audio_count} question(s) sans audio au préchargement. "
                "Le quiz tentera de régénérer l'audio automatiquement à l'affichage."
            )

        st.session_state["quiz_active"] = True
        st.session_state["quiz_questions"] = questions
        st.session_state["quiz_current_idx"] = 0
        st.session_state["quiz_score"] = {"correct": 0, "wrong": 0, "skipped": 0}
        st.session_state["quiz_level"] = quiz_level
        st.session_state["quiz_voice"] = quiz_voice
        st.session_state["quiz_global_start"] = _time.time()
        st.rerun()

    if not is_active:
        st.info(
            "Configure les paramètres et clique sur **▶️ Lancer le quiz** pour commencer."
        )
        return

    # ── Active quiz ────────────────────────────────────────────────────────────
    questions = st.session_state.get("quiz_questions", [])
    idx = st.session_state.get("quiz_current_idx", 0)
    score = st.session_state.get("quiz_score", {"correct": 0, "wrong": 0, "skipped": 0})
    total_q = len(questions)
    quiz_voice_active = st.session_state.get("quiz_voice", "alloy")
    quiz_level_active = st.session_state.get("quiz_level", "B1")

    # ── Scoreboard ─────────────────────────────────────────────────────────────
    s_col1, s_col2, s_col3, s_col4 = st.columns(4)
    with s_col1:
        st.metric("Question", f"{min(idx + 1, total_q)} / {total_q}")
    with s_col2:
        st.metric("✅ Correct", score["correct"])
    with s_col3:
        st.metric("❌ Raté", score["wrong"])
    with s_col4:
        st.metric("⏩ Passé", score["skipped"])

    st.markdown("---")

    # ── Quiz finished ──────────────────────────────────────────────────────────
    if idx >= total_q:
        total_answered = score["correct"] + score["wrong"] + score["skipped"]
        pct = round(score["correct"] / total_answered * 100) if total_answered else 0
        icon = "🏆" if pct >= 80 else "👍" if pct >= 50 else "💪"

        # Compute total elapsed time
        global_start = st.session_state.get("quiz_global_start")
        total_elapsed_sec = (_time.time() - global_start) if global_start else 0.0
        elapsed_display = _format_duration(total_elapsed_sec)

        # Save result to history (only once per quiz run, guard with a flag)
        if not st.session_state.get("quiz_result_saved"):
            import datetime as _dt

            entry = {
                "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
                "question_count": total_q,
                "correct": score["correct"],
                "wrong": score["wrong"],
                "skipped": score["skipped"],
                "score_pct": pct,
                "total_time_sec": round(total_elapsed_sec, 1),
            }
            _save_quiz_history(profile_id, entry)
            st.session_state["quiz_result_saved"] = True

        # Load history to compute improvement
        history = _load_quiz_history(profile_id)
        # Find previous run with same question count (skip the entry we just saved = index 0)
        prev_same = next(
            (h for h in history[1:] if h.get("question_count") == total_q), None
        )

        if prev_same:
            delta_pct = pct - prev_same["score_pct"]
            delta_time = total_elapsed_sec - prev_same.get(
                "total_time_sec", total_elapsed_sec
            )
            score_trend = (
                "📈 +" if delta_pct > 0 else ("📉 " if delta_pct < 0 else "➡️ ")
            ) + f"{abs(delta_pct):.0f}%"
            time_trend = (
                "⚡ -" if delta_time < 0 else ("🐢 +" if delta_time > 0 else "➡️ ")
            ) + _format_duration(abs(delta_time))
            improvement_html = f"""
  <div style="font-size:15px;color:#a0c8ff;margin-top:8px">
    vs run précédent ({total_q}q) : score {score_trend} &nbsp;|&nbsp; temps {time_trend}
  </div>"""
        else:
            improvement_html = ""

        st.markdown(
            f"""
<div style="background:linear-gradient(135deg,#1e3a5f,#0d2137);padding:28px 32px;
            border-radius:16px;text-align:center;margin:20px 0">
  <div style="font-size:48px">{icon}</div>
  <div style="font-size:28px;font-weight:800;color:#fff;margin:8px 0">Quiz terminé !</div>
  <div style="font-size:20px;color:#8ab4e8">{score['correct']} / {total_answered} correctes — {pct}%</div>
  <div style="font-size:17px;color:#ffd580;margin-top:6px">⏱️ Temps total : {elapsed_display}</div>
  {improvement_html}
</div>
""",
            unsafe_allow_html=True,
        )

        # ── History table (last 10 runs for same question count) ────────────
        same_count_history = [h for h in history if h.get("question_count") == total_q][
            :10
        ]
        if len(same_count_history) > 1:
            with st.expander(f"📊 Historique — {total_q} questions", expanded=True):
                rows = []
                for i, h in enumerate(same_count_history):
                    prev_h = (
                        same_count_history[i + 1]
                        if i + 1 < len(same_count_history)
                        else None
                    )
                    if prev_h:
                        d_pct = h["score_pct"] - prev_h["score_pct"]
                        d_time = h.get("total_time_sec", 0) - prev_h.get(
                            "total_time_sec", 0
                        )
                        trend_score = (
                            "↑" if d_pct > 0 else ("↓" if d_pct < 0 else "=")
                        ) + f" {abs(d_pct):.0f}%"
                        trend_time = (
                            ("⚡" if d_time < 0 else ("🐢" if d_time > 0 else "="))
                            + " "
                            + _format_duration(abs(d_time))
                        )
                    else:
                        trend_score = "—"
                        trend_time = "—"
                    rows.append(
                        {
                            "Date": h.get("timestamp", "")[:16].replace("T", " "),
                            "Score": f"{h['score_pct']}%",
                            "Correct": h.get("correct", "?"),
                            "Temps": _format_duration(h.get("total_time_sec", 0)),
                            "Δ Score": trend_score,
                            "Δ Temps": trend_time,
                        }
                    )
                st.dataframe(rows, use_container_width=True)
        if st.button(
            "🔄 Nouveau quiz",
            key="quiz_restart_btn",
            type="primary",
            use_container_width=True,
        ):
            for k in list(st.session_state.keys()):
                if k.startswith("quiz_") and k not in (
                    "quiz_level_sel",
                    "quiz_concepts_sel",
                    "quiz_themes_sel",
                    "quiz_count_sel",
                    "quiz_dir_sel",
                    "quiz_voice_sel",
                ):
                    del st.session_state[k]
            st.rerun()
        return

    question = questions[idx]
    direction = question["direction"]
    prompt_text = question["prompt"]
    answer_text = question["answer"]
    usage_note = question.get("usage_note_fr", "")
    allowed_time = question["allowed_time"]

    # Keys for this question
    result_key = f"quiz_result_{idx}"
    eval_key = f"quiz_eval_{idx}"
    transcript_key = f"quiz_transcript_{idx}"
    marker_key = f"quiz_marker_{idx}"
    start_key = f"quiz_start_{idx}"

    # Record start time once per question
    if start_key not in st.session_state:
        st.session_state[start_key] = _time.time()

    start_time = st.session_state[start_key]
    elapsed = _time.time() - start_time
    remaining = max(0.0, allowed_time - elapsed)
    result = st.session_state.get(result_key)

    # Auto-expire: if time is up and user hasn't submitted
    if result is None and remaining <= 0:
        st.session_state[result_key] = "timeout"
        result = "timeout"

    # ── Question card ──────────────────────────────────────────────────────────
    if direction == "fr_to_en":
        badge = "🇫🇷 → 🇬🇧  Comment dit-on ça en <b>ANGLAIS</b> ?"
        badge_bg = "#1e3a5f"
    else:
        badge = "🇬🇧 → 🇫🇷  Comment dit-on ça en <b>FRANÇAIS</b> ?"
        badge_bg = "#1a3320"

    st.markdown(
        f"<div style='background:{badge_bg};padding:10px 16px;border-radius:10px;"
        f"font-size:14px;font-weight:700;color:#fff;margin-bottom:12px'>{badge}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<div style="background:#2a2a3e;padding:22px 28px;border-radius:14px;
            text-align:center;margin-bottom:14px">
  <span style="font-size:24px;font-weight:800;color:#ffffff">{prompt_text}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    if usage_note:
        st.info(f"🇺🇸 Contexte d'usage: {usage_note}")

    # Play prompt audio
    audio_bytes = question.get("audio_bytes")
    if not audio_bytes:
        lang = "fr" if direction == "fr_to_en" else "en"
        voice_for_prompt = "shimmer" if lang == "fr" else quiz_voice_active
        with st.spinner("Génération audio de la question…"):
            ab, mime, tts_err = tts_smart(
                prompt_text, voice=voice_for_prompt, language_hint=lang
            )
        if ab:
            question["audio_bytes"] = ab
            question["audio_mime"] = mime or "audio/wav"
            question["audio_error"] = None
            st.session_state["quiz_questions"][idx] = question
            audio_bytes = ab
        else:
            question["audio_error"] = tts_err or "Audio indisponible"
            st.session_state["quiz_questions"][idx] = question

    if audio_bytes:
        st.audio(
            audio_bytes,
            format=question.get("audio_mime", "audio/wav"),
            autoplay=True,
        )
        _force_play_latest_audio_js(f"quiz-{idx}")
    elif question.get("audio_error"):
        st.warning(f"Audio question indisponible: {question.get('audio_error')}")

    if result is None:
        # ── Countdown timer ────────────────────────────────────────────────────
        _components.html(_quiz_countdown_html(remaining, allowed_time), height=90)

        # Hidden auto-timeout button (clicked by JS when timer hits 0)
        # We render it with an aria-label that the JS targets
        timeout_col = st.columns([1, 4])[0]
        with timeout_col:
            timeout_btn = st.button(
                "⏰",
                key=f"quiz_auto_timeout_{idx}",
                help="Temps écoulé — cliquer pour passer à la réponse",
            )
        if timeout_btn:
            st.session_state[result_key] = "timeout"
            score["skipped"] += 1
            st.session_state["quiz_score"] = score
            st.rerun()

        # ── Audio input ────────────────────────────────────────────────────────
        st.markdown("**🎙️ Enregistre ta traduction :**")
        user_audio = st.audio_input(
            "Parle maintenant, puis arrête l'enregistrement",
            key=f"quiz_audio_input_{idx}",
        )

        if user_audio:
            candidate = user_audio.getvalue()
            fp = hashlib.sha1(candidate).hexdigest()
            if st.session_state.get(marker_key) != fp:
                st.session_state[marker_key] = fp
                with st.spinner("Transcription en cours…"):
                    transcript, t_err = transcribe_audio_with_openrouter(
                        candidate, audio_format="wav"
                    )
                if t_err:
                    st.warning(f"Transcription échouée : {t_err}")
                elif transcript:
                    st.session_state[transcript_key] = transcript
                    # Check time AFTER transcription
                    elapsed_now = _time.time() - start_time
                    if elapsed_now > allowed_time:
                        st.session_state[result_key] = "timeout"
                        score["wrong"] += 1
                        st.session_state["quiz_score"] = score
                    else:
                        # Evaluate answer
                        with st.spinner("Évaluation…"):
                            eval_result, eval_err = evaluate_practice_pair(
                                {
                                    "direction": direction,
                                    "prompt": prompt_text,
                                    "answer": answer_text,
                                },
                                transcript,
                            )
                        if eval_err or not eval_result:
                            st.session_state[result_key] = "timeout"
                        else:
                            st.session_state[eval_key] = eval_result
                            if (
                                eval_result.get("correct")
                                or eval_result.get("score", 0) >= 60
                            ):
                                st.session_state[result_key] = "correct"
                                score["correct"] += 1
                            else:
                                st.session_state[result_key] = "wrong"
                                score["wrong"] += 1
                            st.session_state["quiz_score"] = score
                    st.rerun()

        # Manual skip
        skip_col = st.columns([3, 1])[1]
        with skip_col:
            if st.button(
                "⏩ Passer", key=f"quiz_manual_skip_{idx}", use_container_width=True
            ):
                st.session_state[result_key] = "timeout"
                score["skipped"] += 1
                st.session_state["quiz_score"] = score
                st.rerun()

    else:
        # ── Result display ─────────────────────────────────────────────────────
        transcript = st.session_state.get(transcript_key, "")
        eval_result = st.session_state.get(eval_key, {})

        if result == "correct":
            elapsed_display = int(_time.time() - start_time)
            feedback = eval_result.get("feedback_fr", "")
            improved = eval_result.get("improved_answer", "")
            st.markdown(
                f"""
<div style="background:linear-gradient(135deg,#1a3320,#0d2210);padding:18px 22px;
            border-radius:14px;border-left:6px solid #4caf50;margin-bottom:10px">
  <div style="font-size:28px;font-weight:800;color:#4caf50">✅ Bravo ! — {elapsed_display}s</div>
  <div style="color:#c8e6c9;font-size:15px;margin-top:4px">{feedback}</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if transcript:
                st.caption(f"📝 Tu as dit : *{transcript}*")
            if improved:
                st.info(f"💡 Version améliorée : **{improved}**")

        elif result == "wrong":
            elapsed_display = int(_time.time() - start_time)
            feedback = eval_result.get("feedback_fr", "")
            score_val = eval_result.get("score", 0)
            st.markdown(
                f"""
<div style="background:linear-gradient(135deg,#3a1a1a,#210d0d);padding:18px 22px;
            border-radius:14px;border-left:6px solid #f44336;margin-bottom:10px">
  <div style="font-size:24px;font-weight:800;color:#f44336">❌ Pas tout à fait — {score_val}/100</div>
  <div style="color:#ffcdd2;font-size:15px;margin-top:4px">{feedback}</div>
</div>
""",
                unsafe_allow_html=True,
            )
            if transcript:
                st.caption(f"📝 Tu as dit : *{transcript}*")

        else:  # timeout or skipped
            timed_out_by_time = elapsed > allowed_time + 1
            msg = "⏰ Temps écoulé !" if timed_out_by_time else "⏩ Passé !"
            st.markdown(
                f"""
<div style="background:linear-gradient(135deg,#33220a,#201500);padding:18px 22px;
            border-radius:14px;border-left:6px solid #ff9800;margin-bottom:10px">
  <div style="font-size:24px;font-weight:800;color:#ff9800">{msg}</div>
  <div style="color:#ffe0b2;font-size:15px;margin-top:4px">
    Ne t'inquiète pas, continue à t'entraîner !
  </div>
</div>
""",
                unsafe_allow_html=True,
            )

        # ── Correct answer ─────────────────────────────────────────────────────
        answer_lang = "en" if direction == "fr_to_en" else "fr"
        st.markdown(
            f"""
<div style="background:#1e3a5f;padding:12px 18px;border-radius:10px;margin:10px 0">
  <span style="font-size:11px;color:#8ab4e8;font-weight:700">✔️ IL FALLAIT DIRE</span><br/>
  <span style="font-size:20px;color:#fff;font-weight:700">{answer_text}</span>
</div>
""",
            unsafe_allow_html=True,
        )

        # TTS for the correct answer
        answer_audio_key = f"quiz_answer_audio_{idx}"
        answer_mime_key = f"quiz_answer_mime_{idx}"
        if answer_audio_key not in st.session_state:
            voice_ans = quiz_voice_active if answer_lang == "en" else "shimmer"
            ab, mime, _ = tts_smart(
                answer_text, voice=voice_ans, language_hint=answer_lang
            )
            st.session_state[answer_audio_key] = ab
            st.session_state[answer_mime_key] = mime or "audio/wav"
        ans_audio = st.session_state.get(answer_audio_key)
        ans_mime = st.session_state.get(answer_mime_key, "audio/wav")
        if ans_audio:
            st.audio(ans_audio, format=ans_mime)

        # ── Next question ──────────────────────────────────────────────────────
        is_last = idx >= total_q - 1
        next_label = "🎉 Voir les résultats" if is_last else "➡️ Question suivante"
        if st.button(
            next_label, key=f"quiz_next_{idx}", type="primary", use_container_width=True
        ):
            st.session_state["quiz_current_idx"] = idx + 1
            st.rerun()


# ── Main entry point ──────────────────────────────────────────────────────────


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Pratique libre avec l'IA (conversation audio)
# ═══════════════════════════════════════════════════════════════════════════════


def _render_free_practice_tab(profile, profile_id):
    st.subheader("🎙️ Pratique libre avec l'IA — Conversation audio")
    st.caption(
        "Choisis tes thèmes et concepts grammaticaux. L'IA démarre une conversation "
        "parlée avec toi : elle s'exprime en anglais (audio), tu enregistres ta réponse "
        "à chaque tour et elle te corrige naturellement."
    )

    saved_level = get_profile_module_level(profile, "michel_thomas") or "B1"
    if saved_level not in CEFR_LEVELS:
        saved_level = "B1"

    is_active = st.session_state.get("fp_active", False)

    with st.expander("⚙️ Paramètres de la conversation", expanded=not is_active):
        c1, c2 = st.columns([1, 3])
        with c1:
            fp_level = st.selectbox(
                "Niveau CEFR",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index(saved_level),
                key="fp_level_sel",
                disabled=is_active,
            )
        with c2:
            all_fp_concepts = MT_GRAMMAR_CONCEPTS.get(fp_level, [])
            fp_concepts = st.multiselect(
                "Concept(s) grammatical(aux)",
                all_fp_concepts,
                key="fp_concepts_sel",
                placeholder="Choisir un ou plusieurs concepts…",
                disabled=is_active,
            )

        fp_themes = st.multiselect(
            "Thème(s) de conversation",
            MT_DIALOGUE_THEMES,
            key="fp_themes_sel",
            placeholder="Choisir un ou plusieurs thèmes…",
            disabled=is_active,
        )

        voices = list(STORY_NARRATOR_VOICES.values())
        voice_labels = list(STORY_NARRATOR_VOICES.keys())
        fp_voice_idx = st.selectbox(
            "Voix de l'IA",
            range(len(voice_labels)),
            format_func=lambda i: voice_labels[i],
            key="fp_voice_sel",
            disabled=is_active,
        )
        fp_voice = voices[fp_voice_idx]

        ctrl_col1, ctrl_col2 = st.columns(2)
        with ctrl_col1:
            start_btn = st.button(
                "▶️ Démarrer la conversation",
                key="fp_start_btn",
                type="primary",
                use_container_width=True,
                disabled=is_active or not (fp_themes or fp_concepts),
            )
        with ctrl_col2:
            stop_btn = st.button(
                "⏹️ Terminer / Réinitialiser",
                key="fp_stop_btn",
                use_container_width=True,
                disabled=not is_active,
            )

    if stop_btn:
        for key in list(st.session_state.keys()):
            if key.startswith("fp_"):
                del st.session_state[key]
        st.rerun()

    if start_btn:
        themes_str = ", ".join(fp_themes) if fp_themes else "daily life"
        concepts_str = ", ".join(fp_concepts) if fp_concepts else "general English"

        system_prompt = (
            f"You are a strict and encouraging English language teacher having a spoken "
            f"conversation with a French-speaking student to help them practice English. "
            f"The student's CEFR level is {fp_level}. "
            f"CRITICAL: Your job is to FORCE the student to use these grammar structures: {concepts_str}. "
            f"You MUST weave these target grammar structures into EVERY reply and deliberately encourage "
            f"the student to use them in their answers. Ask questions that require them to use these structures. "
            f"If the student tries to answer without using the target grammar, reject their answer politely "
            f"and ask them to rephrase using the target structure. "
            f"Focus conversation naturally around these themes: {themes_str}. "
            f"Keep each reply concise (2-4 sentences max). "
            f"Speak exclusively in English. When you deliberately use one of the target grammar "
            f"structures, add a very brief French note at the end in parentheses, e.g.: "
            f"(→ 2nd conditionnel). "
            f"If the student makes a noticeable grammar mistake, gently correct it by repeating "
            f"the correct form naturally in your reply. "
            f"Start by greeting the student warmly and asking an opening question that REQUIRES "
            f"them to use one of the target grammar structures."
        )

        with st.spinner("L'IA prépare son premier message…"):
            ai_text, ai_err = openrouter_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Start the conversation."},
                ],
                CHAT_MODEL,
                temperature=0.7,
                max_tokens=200,
            )
        if ai_err:
            st.error(f"Erreur IA : {ai_err}")
            return

        with st.spinner("Génération de l'audio de l'IA…"):
            ai_audio_bytes, _, tts_err = tts_smart(
                ai_text, voice=fp_voice, language_hint="en"
            )

        st.session_state["fp_active"] = True
        st.session_state["fp_system_prompt"] = system_prompt
        st.session_state["fp_voice"] = fp_voice
        st.session_state["fp_history"] = [{"role": "ai", "text": ai_text}]
        st.session_state["fp_audio_0"] = ai_audio_bytes
        st.rerun()

    if not st.session_state.get("fp_active", False):
        st.info(
            "Configure les paramètres ci-dessus puis clique sur **▶️ Démarrer** pour commencer."
        )
        return

    # ── Render conversation history ────────────────────────────────────────────
    history = st.session_state.get("fp_history", [])
    fp_voice_active = st.session_state.get(
        "fp_voice", fp_voice if not is_active else "shimmer"
    )

    st.markdown("### 🗣️ Conversation")

    for i, turn in enumerate(history):
        role = turn["role"]
        text = turn["text"]
        audio_bytes = st.session_state.get(f"fp_audio_{i}")

        if role == "ai":
            st.markdown(
                f"""
<div style="background:#1e3a5f;padding:12px 18px;border-radius:12px;border-left:5px solid #4a90d9;margin-bottom:4px;max-width:85%">
  <span style="font-size:10px;color:#8ab4e8;font-weight:700;text-transform:uppercase">🤖 IA — Anglais</span><br/>
  <span style="font-size:15px;color:#fff">{text}</span>
</div>
""",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
<div style="background:#1a3320;padding:12px 18px;border-radius:12px;border-right:5px solid #4caf50;
            margin-bottom:4px;margin-left:15%;text-align:right">
  <span style="font-size:10px;color:#88c989;font-weight:700;text-transform:uppercase">🎙️ Toi</span><br/>
  <span style="font-size:15px;color:#e8f5e9">{text}</span>
</div>
""",
                unsafe_allow_html=True,
            )

        if audio_bytes:
            should_autoplay = role == "ai"
            st.audio(audio_bytes, format="audio/wav", autoplay=should_autoplay)
            if should_autoplay:
                _force_play_latest_audio_js(f"fp-{i}")

        st.markdown("")

    # ── User's turn ────────────────────────────────────────────────────────────
    # User turn when len(history) is odd (1, 3, 5…) — AI started at 0
    next_turn_idx = len(history)
    is_user_turn = next_turn_idx % 2 == 1

    if is_user_turn:
        st.markdown("---")
        st.markdown("**🎙️ Ton tour — Réponds en anglais :**")

        transcript_key = f"fp_transcript_{next_turn_idx}"
        marker_key = f"fp_marker_{next_turn_idx}"

        user_audio_file = st.audio_input(
            "Enregistre ta réponse",
            key=f"fp_audio_input_{next_turn_idx}",
        )

        if user_audio_file:
            candidate_bytes = user_audio_file.getvalue()
            fingerprint = hashlib.sha1(candidate_bytes).hexdigest()
            if st.session_state.get(marker_key) != fingerprint:
                st.session_state[marker_key] = fingerprint
                with st.spinner("Transcription…"):
                    transcript, t_err = transcribe_audio_with_openrouter(
                        candidate_bytes, audio_format="wav"
                    )
                if t_err:
                    st.warning(f"Transcription échouée : {t_err}")
                else:
                    st.session_state[transcript_key] = transcript

        transcript = st.session_state.get(transcript_key, "")
        if transcript:
            st.caption(f"📝 Transcription : *{transcript}*")

        send_col, _ = st.columns([2, 3])
        with send_col:
            if st.button(
                "✅ Envoyer ma réponse",
                key=f"fp_send_{next_turn_idx}",
                type="primary",
                disabled=not transcript.strip(),
                use_container_width=True,
            ):
                # Store user audio bytes before rerun
                if user_audio_file:
                    st.session_state[f"fp_audio_{next_turn_idx}"] = (
                        user_audio_file.getvalue()
                    )

                # Check if concepts are used (if concepts were selected)
                fp_concepts = st.session_state.get("fp_concepts_sel", [])
                user_response_lower = transcript.strip().lower()

                # Simple concept check: see if any concept keywords appear
                concepts_used = False
                if not fp_concepts or len(fp_concepts) == 0:
                    # No specific concepts selected, accept any response
                    concepts_used = True
                else:
                    # Map concept names to common keywords/patterns for detection
                    concept_keywords = {
                        "Present Continuous": ["ing ", "-ing", "is ", "are ", "am "],
                        "Past Continuous": ["was ", "were ", "ing"],
                        "Present Perfect": ["have ", "has ", "ed", "'ve", "'s"],
                        "Past Perfect": ["had ", "ed"],
                        "Conditionals": ["would ", "if ", "should ", "could "],
                        "Passif": ["is ", "are ", "was ", "were ", "be ", "been"],
                        "Reported Speech": ["said ", "told ", "asked "],
                        "Phrasal Verbs": [
                            " up",
                            " down",
                            " out",
                            " back",
                            " on",
                            " off",
                        ],
                        "Modal Verbs": [
                            "must ",
                            "could ",
                            "should ",
                            "would ",
                            "can ",
                            "may ",
                        ],
                        "Relative Clauses": [" that ", " who ", " which ", " where "],
                    }

                    # Check if at least one concept keyword appears in response
                    for concept in fp_concepts:
                        keywords = concept_keywords.get(concept, [concept.lower()])
                        for keyword in keywords:
                            if keyword in user_response_lower:
                                concepts_used = True
                                break
                        if concepts_used:
                            break

                # If concepts not used, ask user to retry
                if not concepts_used:
                    st.warning(
                        f"⚠️ Tu dois utiliser les concepts choisis dans ta réponse : {', '.join(fp_concepts)} ! "
                        f"Essaie encore avec la structure grammaticale cible."
                    )
                    st.session_state["fp_history"] = history
                    return

                # Append user turn
                history.append({"role": "user", "text": transcript.strip()})

                # Build messages for AI
                system_prompt = st.session_state.get("fp_system_prompt", "")
                messages = [{"role": "system", "content": system_prompt}]
                for turn in history:
                    r = "assistant" if turn["role"] == "ai" else "user"
                    messages.append({"role": r, "content": turn["text"]})

                # Generate AI response
                with st.spinner("L'IA réfléchit…"):
                    ai_text, ai_err = openrouter_chat(
                        messages, CHAT_MODEL, temperature=0.7, max_tokens=200
                    )
                if ai_err:
                    st.error(f"Erreur IA : {ai_err}")
                    st.session_state["fp_history"] = history
                    return

                with st.spinner("Génération de l'audio de l'IA…"):
                    ai_audio_bytes, _, _ = tts_smart(
                        ai_text, voice=fp_voice_active, language_hint="en"
                    )

                ai_turn_idx = next_turn_idx + 1
                history.append({"role": "ai", "text": ai_text})
                st.session_state[f"fp_audio_{ai_turn_idx}"] = ai_audio_bytes
                st.session_state["fp_history"] = history
                # Clear transcript for next user turn
                st.session_state.pop(transcript_key, None)
                st.session_state.pop(marker_key, None)
                st.rerun()


# ── Main entry point ──────────────────────────────────────────────────────────


def render_michel_thomas_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("🎓 Anglais avec l'IA — Leçons & Dialogues")
    st.caption(f"Profil actif : {profile.get('name', 'Profil principal')}")

    tab_lesson, tab_dialogue, tab_free, tab_quiz = st.tabs(
        ["📖 Leçon & Pratique", "💬 Dialogues", "🎙️ Pratique libre", "⚡ Quiz Chrono"]
    )

    with tab_lesson:
        _render_lesson_tab(profile, profile_id)

    with tab_dialogue:
        _render_dialogue_tab(profile, profile_id)

    with tab_free:
        _render_free_practice_tab(profile, profile_id)

    with tab_quiz:
        _render_quiz_tab(profile, profile_id)
