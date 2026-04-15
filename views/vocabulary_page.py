import io
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone

import requests
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit_autorefresh import st_autorefresh

from modules.ai_client import *
from modules.ai_lessons import *
from modules.config import *
from modules.immersion import *
from modules.lessons import *
from modules.podcasts import *
from modules.profiles import *
from modules.real_english import *
from modules.sessions import *
from modules.shadowing import *
from modules.stories import *
from modules.utils import *
from modules.utils import _audio_player_with_repeat
from modules.vocabulary import *
from modules.vocabulary import (
    _save_example_audio,
    _save_review_audio,
    _srs_update_rated,
)


def render_vocabulary_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("📖 Vocabulaire, Traduction & Flashcards")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    vocab_level_default = get_profile_module_level(profile, "vocabulary")
    vocab_level = st.radio(
        "Niveau cible vocabulaire",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(vocab_level_default),
        horizontal=True,
        key=f"vocab-level-{profile_id}",
    )
    if vocab_level != vocab_level_default:
        set_profile_module_level(profile_id, "vocabulary", vocab_level)

    tab_translate, tab_flash, tab_hist = st.tabs(
        ["🔍 Traduction & Explication", "🃏 Flashcards (SRS)", "📚 Historique"]
    )

    # ── Tab 1 : Translation & Explanation ────────────────────────────────────
    with tab_translate:
        st.subheader("Analyser un mot ou une expression")
        term_input = st.text_input(
            "Mot, expression idiomatique, chunk…",
            placeholder="ex: to bite the bullet, run out of, nevertheless…",
            key="vocab-term-input",
        )
        tts_voice_labels = list(STORY_NARRATOR_VOICES.keys())
        col_voice, col_btn = st.columns([2, 1])
        with col_voice:
            v_label = st.selectbox(
                "Voix TTS", tts_voice_labels, index=0, key="vocab-voice"
            )
        with col_btn:
            st.write("")
            st.write("")
            analyze_btn = st.button(
                "✨ Analyser",
                key="vocab-analyze-btn",
                type="primary",
                width="stretch",
            )

        if analyze_btn:
            if not term_input.strip():
                st.warning("Entre un mot ou une expression.")
            else:
                # Clean previous result and its example audio
                st.session_state.pop("vocab_current", None)
                for _i in range(10):
                    st.session_state.pop(f"vocab_ex_audio_{_i}", None)
                with st.spinner("Analyse en cours…"):
                    result, err = translate_and_explain(
                        term_input.strip(),
                        target_cefr=vocab_level,
                    )
                if err:
                    st.error(f"Erreur IA : {err}")
                else:
                    st.session_state["vocab_current"] = result

        result = st.session_state.get("vocab_current")
        if result:
            st.markdown("---")
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(f"### {result.get('term', term_input)}")
                badge_level = result.get("level", "")
                pos = result.get("part_of_speech", "")
                if badge_level or pos:
                    st.caption(f"{pos}  ·  {badge_level}")
                st.markdown(f"**🇫🇷 Traduction :** {result.get('translation', '')}")
                st.markdown(f"**📝 Explication :** {result.get('explanation', '')}")
                synonyms = result.get("synonyms", [])
                if synonyms:
                    st.markdown(
                        f"**🔗 Synonymes / expressions proches :** {', '.join(synonyms)}"
                    )
            with col_b:
                if st.button(
                    "💾 Sauvegarder dans mon vocabulaire",
                    key="vocab-save-btn",
                    width="stretch",
                ):
                    entries = load_vocab(profile_id=profile_id)
                    existing_terms = [e.get("term", "").lower() for e in entries]
                    if result.get("term", "").lower() in existing_terms:
                        st.info("Ce mot est déjà dans ton vocabulaire.")
                    else:
                        entry_id = str(uuid.uuid4())[:8]
                        examples_with_audio = []
                        for _ei, _ex in enumerate(result.get("examples", [])):
                            _ab = st.session_state.get(f"vocab_ex_audio_{_ei}")
                            _ap = (
                                _save_example_audio(
                                    entry_id,
                                    _ei,
                                    _ab,
                                    profile_id=profile_id,
                                )
                                if _ab
                                else None
                            )
                            examples_with_audio.append({"text": _ex, "audio_path": _ap})
                        entry = {
                            "id": entry_id,
                            "profile_id": profile_id,
                            "term": result.get("term", term_input),
                            "created_at": now_iso(),
                            "translation": result.get("translation", ""),
                            "part_of_speech": result.get("part_of_speech", ""),
                            "explanation": result.get("explanation", ""),
                            "examples": examples_with_audio,
                            "synonyms": result.get("synonyms", []),
                            "level": result.get("level", ""),
                            "srs": {
                                "next_review": now_iso(),
                                "interval": 1,
                                "ease": 2.5,
                                "repetitions": 0,
                                "last_result": None,
                            },
                            "review_history": [],
                        }
                        entries.append(entry)
                        save_vocab(entries, profile_id=profile_id)
                        # Clean up current analysis from session state
                        st.session_state.pop("vocab_current", None)
                        for _i in range(10):
                            st.session_state.pop(f"vocab_ex_audio_{_i}", None)
                        st.success(f"«{entry['term']}» sauvegardé !")

            st.markdown("#### 💬 Phrases d'exemple")
            voice = STORY_NARRATOR_VOICES.get(v_label, "alloy")
            for i, ex in enumerate(result.get("examples", [])):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{i+1}.** {ex}")
                with c2:
                    if st.button(f"🔊 Audio", key=f"vocab-ex-audio-{i}"):
                        with st.spinner("Génération audio…"):
                            audio_bytes, _, tts_err = text_to_speech_openrouter(
                                ex, voice=voice, language_hint="en"
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            st.session_state[f"vocab_ex_audio_{i}"] = audio_bytes
                audio_key = f"vocab_ex_audio_{i}"
                if st.session_state.get(audio_key):
                    _audio_player_with_repeat(
                        st.session_state[audio_key], "audio/wav", key=f"voc_{audio_key}"
                    )

    # ── Tab 2 : Flashcards SRS ────────────────────────────────────────────────
    with tab_flash:
        st.subheader("Flashcards — répétition espacée")

        flash_mode_label = st.radio(
            "Mode",
            ["🔤 Normal (terme → phrase)", "🔁 Inversé (définition → terme)"],
            horizontal=True,
            key="flash-mode-radio",
        )
        is_reverse = "Inversé" in flash_mode_label

        entries = load_vocab(profile_id=profile_id)
        due = get_due_cards(entries)

        total = len(entries)
        total_due = len(due)
        c1, c2, c3 = st.columns(3)
        c1.metric("Mots au total", total)
        c2.metric("À réviser aujourd'hui", total_due)
        c3.metric(
            "Maîtrisés (≥5 rép.)",
            sum(1 for e in entries if e.get("srs", {}).get("repetitions", 0) >= 5),
        )

        if not due:
            if total == 0:
                st.info(
                    "Ton vocabulaire est vide. Analyse des mots dans l'onglet **Traduction** et sauvegarde-les."
                )
            else:
                st.success(
                    "✅ Toutes les révisions du jour sont faites ! Reviens demain."
                )
            return

        mode_key = f"flash_mode_{profile_id}_{is_reverse}"
        if (
            "flash_idx" not in st.session_state
            or st.session_state.get("flash_mode_key") != mode_key
            or st.session_state.get("flash_profile_id") != profile_id
        ):
            st.session_state["flash_idx"] = 0
            st.session_state["flash_initial_due"] = total_due
            st.session_state["flash_mode_key"] = mode_key
            st.session_state["flash_profile_id"] = profile_id
            st.session_state["flash_revealed"] = False
            st.session_state["flash_eval_result"] = None
            st.session_state["flash_user_audio_bytes"] = None
            st.session_state["flash_user_audio_path"] = None

        initial_due = st.session_state.get("flash_initial_due", total_due)
        card_number = st.session_state.get("flash_idx", 0) + 1

        if not due:
            st.success("✅ Toutes les révisions du jour sont faites ! Reviens demain.")
            st.session_state.pop("flash_idx", None)
            st.session_state.pop("flash_initial_due", None)
            return

        idx = st.session_state["flash_idx"] % len(due)
        card = due[idx]

        st.markdown(f"**Carte {card_number} / {initial_due}**")
        st.markdown("---")

        # Card face
        if not is_reverse:
            st.markdown(f"## {card['term']}")
            pos = card.get("part_of_speech", "")
            level = card.get("level", "")
            if pos or level:
                st.caption(f"{pos}  ·  {level}")
            st.markdown(
                "*Utilise ce mot/cette expression dans une phrase à voix haute.*"
            )
        else:
            st.markdown("### Quel est le mot ou l'expression décrit ci-dessous ?")
            st.markdown(f"> {card.get('explanation', '')}")
            synonyms = card.get("synonyms", [])
            if synonyms:
                st.caption(
                    f"Indices — synonymes / expressions proches : {', '.join(synonyms)}"
                )
            st.markdown("*Prononce le terme / chunk correspondant en audio.*")

        # Audio recorder — use raw flash_idx (never modulo'd) so the key is
        # always unique and Streamlit never restores a previous card's audio.
        _mic_key = f"flash-mic-{profile_id}-{st.session_state.get('flash_idx', 0)}-{is_reverse}"
        user_audio_widget = st.audio_input(
            "🎤 Enregistre ta réponse",
            key=_mic_key,
        )
        if user_audio_widget:
            st.session_state["flash_user_audio_bytes"] = user_audio_widget.read()

        col_submit, col_reveal, col_skip = st.columns(3)

        with col_submit:
            if st.button(
                "✅ Soumettre",
                key="flash-submit",
                type="primary",
                width="stretch",
            ):
                user_bytes = st.session_state.get("flash_user_audio_bytes")
                if not user_bytes:
                    st.warning("Enregistre d'abord une réponse audio.")
                else:
                    with st.spinner("Transcription & évaluation…"):
                        user_text, stt_err = transcribe_audio_with_openrouter(
                            user_bytes
                        )
                    if stt_err:
                        st.error(f"Transcription : {stt_err}")
                    else:
                        if is_reverse:
                            eval_result, eval_err = evaluate_reverse_flashcard(
                                card["term"], user_text
                            )
                        else:
                            eval_result, eval_err = evaluate_vocab_usage(
                                card["term"],
                                card.get("explanation", card.get("translation", "")),
                                user_text,
                            )
                        if eval_err:
                            st.error(f"Évaluation : {eval_err}")
                        else:
                            eval_result["user_text"] = user_text
                            audio_path = _save_review_audio(
                                card["id"],
                                user_bytes,
                                profile_id=profile_id,
                            )
                            st.session_state["flash_user_audio_path"] = audio_path
                            st.session_state["flash_eval_result"] = eval_result
                            st.session_state["flash_revealed"] = True

        with col_reveal:
            if st.button("👁 Voir la réponse", key="flash-reveal", width="stretch"):
                st.session_state["flash_revealed"] = True

        with col_skip:
            if st.button("⏭ Passer", key="flash-skip", width="stretch"):
                st.session_state.pop(_mic_key, None)
                st.session_state["flash_idx"] = st.session_state.get("flash_idx", 0) + 1
                st.session_state["flash_revealed"] = False
                st.session_state["flash_eval_result"] = None
                st.session_state["flash_user_audio_bytes"] = None
                st.session_state["flash_user_audio_path"] = None
                st.rerun()

        # Reveal zone
        if st.session_state.get("flash_revealed"):
            st.markdown("---")
            if is_reverse:
                st.markdown(f"**✅ Réponse :** `{card['term']}`")
                st.markdown(f"**🇫🇷 Traduction :** {card.get('translation', '')}")
            else:
                st.markdown(f"**🇫🇷 Traduction :** {card.get('translation', '')}")
                st.markdown(f"**📝 Explication :** {card.get('explanation', '')}")

            examples = card.get("examples", [])
            if examples:
                st.markdown("**Exemples :**")
                for ex_idx, ex_item in enumerate(examples):
                    txt = ex_item["text"] if isinstance(ex_item, dict) else ex_item
                    ex_audio = (
                        ex_item.get("audio_path") if isinstance(ex_item, dict) else None
                    )
                    st.markdown(f"- {txt}")
                    if ex_audio and os.path.exists(ex_audio):
                        with open(ex_audio, "rb") as _af:
                            _audio_player_with_repeat(
                                _af.read(), "audio/wav", key=f"flash_ex_{ex_idx}"
                            )

            eval_result = st.session_state.get("flash_eval_result")
            if eval_result:
                user_text = eval_result.get("user_text", "")
                score = eval_result.get("score", 0)
                correct = eval_result.get("correct", False)
                feedback = eval_result.get("feedback", "")
                st.markdown(f"**Ta réponse :** *{user_text}*")
                saved_path = st.session_state.get("flash_user_audio_path")
                if saved_path and os.path.exists(saved_path):
                    st.audio(saved_path, format="audio/wav")
                if correct:
                    st.success(f"✅ Correct ! Score : {score}/100 — {feedback}")
                else:
                    st.error(f"❌ À retravailler. Score : {score}/100 — {feedback}")

            # 4-rating buttons
            st.markdown("##### Comment tu t'en es sorti ?")
            r0, r1, r2, r3 = st.columns(4)

            def _apply_rating(rating: int, label: str):
                _all = load_vocab(profile_id=profile_id)
                _eval = st.session_state.get("flash_eval_result")
                _ap = st.session_state.get("flash_user_audio_path")
                for e in _all:
                    if e["id"] == card["id"]:
                        e["srs"] = _srs_update_rated(e.get("srs", {}), rating=rating)
                        e["srs"]["last_result"] = label
                        rev = {
                            "date": now_iso(),
                            "mode": "reverse" if is_reverse else "normal",
                            "rating": rating,
                            "rating_label": label,
                            "user_text": _eval.get("user_text", "") if _eval else "",
                            "score": _eval.get("score") if _eval else None,
                            "audio_path": _ap,
                        }
                        if "review_history" not in e:
                            e["review_history"] = []
                        e["review_history"].append(rev)
                        break
                save_vocab(_all, profile_id=profile_id)
                st.session_state.pop(_mic_key, None)
                st.session_state["flash_idx"] = st.session_state.get("flash_idx", 0) + 1
                st.session_state["flash_revealed"] = False
                st.session_state["flash_eval_result"] = None
                st.session_state["flash_user_audio_bytes"] = None
                st.session_state["flash_user_audio_path"] = None
                st.rerun()

            with r0:
                if st.button("❌ À revoir", key="flash-r0", width="stretch"):
                    _apply_rating(0, "À revoir")
            with r1:
                if st.button("😬 Difficile", key="flash-r1", width="stretch"):
                    _apply_rating(1, "Difficile")
            with r2:
                if st.button(
                    "✅ Bien", key="flash-r2", width="stretch", type="primary"
                ):
                    _apply_rating(2, "Bien")
            with r3:
                if st.button("🌟 Facile", key="flash-r3", width="stretch"):
                    _apply_rating(3, "Facile")

    # ── Tab 3 : History ───────────────────────────────────────────────────────
    with tab_hist:
        st.subheader("Historique de mon vocabulaire")
        entries = load_vocab(profile_id=profile_id)
        if not entries:
            st.info("Aucun mot sauvegardé pour le moment.")
        else:
            search = st.text_input(
                "🔎 Rechercher",
                placeholder="Filtrer par mot…",
                key="vocab-hist-search",
            )
            hist_voice_label = st.selectbox(
                "Voix TTS pour les exemples",
                list(STORY_NARRATOR_VOICES.keys()),
                index=0,
                key="vocab-hist-voice",
            )
            hist_voice = STORY_NARRATOR_VOICES.get(hist_voice_label, "alloy")
            filtered = entries
            if search.strip():
                q = search.strip().lower()
                filtered = [
                    e
                    for e in entries
                    if q in e.get("term", "").lower()
                    or q in e.get("translation", "").lower()
                ]

            st.caption(f"{len(filtered)} mot(s) affiché(s)")

            for entry in reversed(filtered):
                srs = entry.get("srs", {})
                reps = srs.get("repetitions", 0)
                next_rev = srs.get("next_review", "")[:10]
                mastery = "🟢" if reps >= 5 else ("🟡" if reps >= 2 else "🔴")
                with st.expander(
                    f"{mastery} **{entry['term']}** — {entry.get('translation', '')}  ·  rév. {next_rev}"
                ):
                    st.markdown(
                        f"**Niveau :** {entry.get('level', '')}  ·  {entry.get('part_of_speech', '')}"
                    )
                    st.markdown(f"**Explication :** {entry.get('explanation', '')}")
                    synonyms = entry.get("synonyms", [])
                    if synonyms:
                        st.markdown(f"**Synonymes :** {', '.join(synonyms)}")

                    st.markdown("**Exemples :**")
                    for ex_idx, ex_item in enumerate(entry.get("examples", [])):
                        txt = ex_item["text"] if isinstance(ex_item, dict) else ex_item
                        audio_path = (
                            ex_item.get("audio_path")
                            if isinstance(ex_item, dict)
                            else None
                        )

                        st.markdown(f"**{ex_idx + 1}.** {txt}")
                        if audio_path and os.path.exists(audio_path):
                            with open(audio_path, "rb") as _af:
                                _audio_player_with_repeat(
                                    _af.read(),
                                    "audio/wav",
                                    key=f"vrev_{entry['id']}_{ex_idx}",
                                )
                            ca, cb = st.columns(2)
                            with ca:
                                if st.button(
                                    "🗑 Supprimer audio",
                                    key=f"vocab-ex-del-{entry['id']}-{ex_idx}",
                                    width="stretch",
                                ):
                                    os.remove(audio_path)
                                    _all = load_vocab(profile_id=profile_id)
                                    for _e in _all:
                                        if _e["id"] == entry["id"] and isinstance(
                                            _e["examples"][ex_idx], dict
                                        ):
                                            _e["examples"][ex_idx]["audio_path"] = None
                                            break
                                    save_vocab(_all, profile_id=profile_id)
                                    st.rerun()
                            with cb:
                                if st.button(
                                    "🔄 Régénérer audio",
                                    key=f"vocab-ex-regen-{entry['id']}-{ex_idx}",
                                    width="stretch",
                                ):
                                    with st.spinner("Génération audio…"):
                                        _ab, _, _err = text_to_speech_openrouter(
                                            txt, voice=hist_voice, language_hint="en"
                                        )
                                    if _err:
                                        st.error(_err)
                                    else:
                                        _new_path = _save_example_audio(
                                            entry["id"],
                                            ex_idx,
                                            _ab,
                                            profile_id=profile_id,
                                        )
                                        _all = load_vocab(profile_id=profile_id)
                                        for _e in _all:
                                            if _e["id"] == entry["id"] and isinstance(
                                                _e["examples"][ex_idx], dict
                                            ):
                                                _e["examples"][ex_idx][
                                                    "audio_path"
                                                ] = _new_path
                                                break
                                        save_vocab(_all, profile_id=profile_id)
                                        st.rerun()
                        else:
                            if st.button(
                                "🔊 Générer audio",
                                key=f"vocab-ex-gen-{entry['id']}-{ex_idx}",
                                width="stretch",
                            ):
                                with st.spinner("Génération audio…"):
                                    _ab, _, _err = text_to_speech_openrouter(
                                        txt, voice=hist_voice, language_hint="en"
                                    )
                                if _err:
                                    st.error(_err)
                                else:
                                    _new_path = _save_example_audio(
                                        entry["id"],
                                        ex_idx,
                                        _ab,
                                        profile_id=profile_id,
                                    )
                                    _all = load_vocab(profile_id=profile_id)
                                    for _e in _all:
                                        if _e["id"] == entry["id"]:
                                            if isinstance(_e["examples"][ex_idx], dict):
                                                _e["examples"][ex_idx][
                                                    "audio_path"
                                                ] = _new_path
                                            break
                                    save_vocab(_all, profile_id=profile_id)
                                    st.rerun()

                    # Review history with audio playback
                    reviews = entry.get("review_history", [])
                    if reviews:
                        st.markdown(f"**Historique des révisions ({len(reviews)}) :**")
                        for ri, rev in enumerate(reversed(reviews[-10:])):
                            date_str = rev.get("date", "")[:16].replace("T", " ")
                            mode_icon = "🔁" if rev.get("mode") == "reverse" else "🔤"
                            label = rev.get("rating_label", "—")
                            sc = rev.get("score")
                            score_str = f"  ·  Score {sc}/100" if sc is not None else ""
                            utxt = rev.get("user_text", "")
                            st.caption(
                                f"{mode_icon} {date_str}  ·  **{label}**{score_str}"
                                + (f"  —  *{utxt}*" if utxt else "")
                            )
                            ap = rev.get("audio_path")
                            if ap and os.path.exists(ap):
                                with open(ap, "rb") as _af:
                                    _audio_player_with_repeat(
                                        _af.read(),
                                        "audio/wav",
                                        key=f"vhist_{entry['id']}_{ri}",
                                    )

                    col_srs, col_del = st.columns([3, 1])
                    with col_srs:
                        st.caption(
                            f"Répétitions : {reps}  ·  Intervalle : {srs.get('interval', 1)} j  ·  "
                            f"Facilité : {srs.get('ease', 2.5):.1f}  ·  Dernier résultat : {srs.get('last_result', '—')}"
                        )
                    with col_del:
                        if st.button("🗑 Supprimer", key=f"vocab-del-{entry['id']}"):
                            all_entries = load_vocab(profile_id=profile_id)
                            all_entries = [
                                e for e in all_entries if e["id"] != entry["id"]
                            ]
                            save_vocab(all_entries, profile_id=profile_id)
                            st.rerun()
