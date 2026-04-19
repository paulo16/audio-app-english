import io
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone

import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from modules.ai_client import *
from modules.ai_lessons import *
from modules.ai_lessons import _save_ai_lesson_example_audio
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
from modules.utils import _audio_player_with_repeat, _seconds_since_iso
from modules.vocabulary import *


def render_ai_lessons_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Lecons basees sur vos echanges IA")
    st.write(
        "Ces lecons sont generees depuis vos conversations IA pour corriger vos vrais points faibles a l'oral."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    ai_level_default = get_profile_module_level(profile, "ai_lessons")
    ai_level = st.radio(
        "Niveau cible des lecons",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(ai_level_default),
        horizontal=True,
        key=f"ai-lessons-level-{profile_id}",
    )
    if ai_level != ai_level_default:
        set_profile_module_level(profile_id, "ai_lessons", ai_level)

    voice_label = st.selectbox(
        "Voix audio des exemples",
        list(STORY_NARRATOR_VOICES.keys()),
        index=0,
        key="ai-lessons-voice",
    )
    lesson_voice = STORY_NARRATOR_VOICES.get(voice_label, "alloy")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        session_limit = st.slider(
            "Nombre de sessions IA a analyser",
            min_value=3,
            max_value=30,
            value=12,
            key="ai-lessons-session-limit",
        )
    with col_b:
        lesson_count = st.slider(
            "Nombre de lecons",
            min_value=2,
            max_value=8,
            value=4,
            key="ai-lessons-count",
        )

    custom_instr_ai = st.text_area(
        "Instructions supplementaires (optionnel)",
        value="",
        height=80,
        placeholder="Ex: Focus sur les phrasal verbs, ajouter des exercices de prononciation, inclure du vocabulaire technique...",
        key="ai-lessons-custom-instr",
    )

    if st.button(
        "Generer / Regenerer mes lecons personnalisees",
        type="primary",
        width="stretch",
        key="ai-lessons-generate",
    ):
        with st.spinner("Analyse des conversations et generation des lecons..."):
            lessons, err = generate_ai_lessons_from_sessions(
                session_limit=session_limit,
                lesson_count=lesson_count,
                target_cefr=ai_level,
                custom_instructions=custom_instr_ai,
            )
        if err:
            st.error(f"Erreur generation lecons: {err}")
        else:
            save_ai_lessons(lessons, profile_id=profile_id)
            st.success(f"{len(lessons)} lecon(s) personnalisee(s) creee(s).")
            st.rerun()

    lessons = load_ai_lessons(profile_id=profile_id)
    if not lessons:
        st.info(
            "Aucune lecon personnalisee pour l'instant. Generez-les depuis vos echanges IA."
        )
        return

    st.caption(f"{len(lessons)} lecon(s) disponible(s)")
    for lesson in lessons:
        lid = lesson.get("id", uuid.uuid4().hex[:8])
        with st.expander(f"🎯 {lesson.get('focus', 'Lecon personnalisee')}"):
            st.markdown(f"**Concept a etudier :** {lesson.get('concept', '')}")

            mistakes = lesson.get("common_mistakes", [])
            if mistakes:
                st.markdown("**Points a corriger observes :**")
                for m in mistakes:
                    st.markdown(f"- {m}")

            tips = lesson.get("tips_to_remember", [])
            if tips:
                st.markdown("**Tips a retenir :**")
                for t in tips:
                    st.markdown(f"- {t}")

            examples = lesson.get("examples", [])
            st.markdown("**Phrases d'exemple (avec audio) :**")
            if not examples:
                st.caption("Pas d'exemple disponible.")
            if examples and st.button(
                "🔊 Generer tous les audios des exemples",
                key=f"ai-lesson-gen-all-{lid}",
                width="stretch",
            ):
                with st.spinner("Generation de tous les audios des exemples..."):
                    all_lessons = load_ai_lessons(profile_id=profile_id)
                    target = next((l for l in all_lessons if l.get("id") == lid), None)
                    if not target:
                        st.error("Lecon introuvable.")
                    else:
                        for ex_idx, ex_item in enumerate(target.get("examples", [])):
                            text = (
                                ex_item.get("text", "")
                                if isinstance(ex_item, dict)
                                else str(ex_item)
                            )
                            if not text.strip():
                                continue
                            ab, _, tts_err = text_to_speech_openrouter(
                                text,
                                voice=lesson_voice,
                                language_hint="en",
                            )
                            if tts_err:
                                continue
                            new_path = _save_ai_lesson_example_audio(lid, ex_idx, ab)
                            if isinstance(target["examples"][ex_idx], dict):
                                target["examples"][ex_idx]["audio_path"] = new_path
                        save_ai_lessons(all_lessons, profile_id=profile_id)
                st.rerun()
            for ex_idx, ex_item in enumerate(examples):
                text = (
                    ex_item.get("text", "")
                    if isinstance(ex_item, dict)
                    else str(ex_item)
                )
                audio_path = (
                    ex_item.get("audio_path") if isinstance(ex_item, dict) else None
                )
                st.markdown(f"**{ex_idx + 1}.** {text}")
                if audio_path and os.path.exists(audio_path):
                    with open(audio_path, "rb") as _af:
                        _audio_player_with_repeat(
                            _af.read(), "audio/wav", key=f"ai_les_{lid}_{ex_idx}"
                        )
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "🔄 Regenerer audio",
                            key=f"ai-lesson-regen-{lid}-{ex_idx}",
                            width="stretch",
                        ):
                            with st.spinner("Generation audio..."):
                                ab, _, tts_err = text_to_speech_openrouter(
                                    text,
                                    voice=lesson_voice,
                                    language_hint="en",
                                )
                            if tts_err:
                                st.error(tts_err)
                            else:
                                new_path = _save_ai_lesson_example_audio(
                                    lid, ex_idx, ab
                                )
                                all_lessons = load_ai_lessons(profile_id=profile_id)
                                for l in all_lessons:
                                    if l.get("id") == lid and ex_idx < len(
                                        l.get("examples", [])
                                    ):
                                        l["examples"][ex_idx]["audio_path"] = new_path
                                        break
                                save_ai_lessons(all_lessons, profile_id=profile_id)
                                st.rerun()
                    with c2:
                        if st.button(
                            "🗑 Supprimer audio",
                            key=f"ai-lesson-del-{lid}-{ex_idx}",
                            width="stretch",
                        ):
                            if audio_path and os.path.exists(audio_path):
                                os.remove(audio_path)
                            all_lessons = load_ai_lessons(profile_id=profile_id)
                            for l in all_lessons:
                                if l.get("id") == lid and ex_idx < len(
                                    l.get("examples", [])
                                ):
                                    l["examples"][ex_idx]["audio_path"] = None
                                    break
                            save_ai_lessons(all_lessons, profile_id=profile_id)
                            st.rerun()
                else:
                    if st.button(
                        "🔊 Generer audio",
                        key=f"ai-lesson-gen-{lid}-{ex_idx}",
                        width="stretch",
                    ):
                        with st.spinner("Generation audio..."):
                            ab, _, tts_err = text_to_speech_openrouter(
                                text,
                                voice=lesson_voice,
                                language_hint="en",
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            new_path = _save_ai_lesson_example_audio(lid, ex_idx, ab)
                            all_lessons = load_ai_lessons(profile_id=profile_id)
                            for l in all_lessons:
                                if l.get("id") == lid and ex_idx < len(
                                    l.get("examples", [])
                                ):
                                    l["examples"][ex_idx]["audio_path"] = new_path
                                    break
                            save_ai_lessons(all_lessons, profile_id=profile_id)
                            st.rerun()

            st.markdown("---")
            mini_task = lesson.get("mini_task", {})
            target_seconds = int(mini_task.get("target_time_seconds", 120) or 120)
            st.markdown(
                f"**Mini-task ({target_seconds} sec) :** {mini_task.get('instruction', '')}"
            )
            checklist = mini_task.get("success_checklist", [])
            if checklist:
                st.markdown("**Checklist de reussite :**")
                for item in checklist:
                    st.markdown(f"- {item}")

            start_key = f"ai-mini-start-{lid}"
            eval_key = f"ai-mini-eval-{lid}"
            answer_key = f"ai-mini-answer-{lid}"
            audio_key = f"ai-mini-audio-{lid}"
            active_key = "ai-mini-active-lesson"

            cstart, cretry = st.columns(2)
            with cstart:
                if st.button(
                    "▶️ Demarrer / Redemarrer le chrono",
                    key=f"ai-mini-start-btn-{lid}",
                    width="stretch",
                ):
                    st.session_state[start_key] = now_iso()
                    st.session_state[active_key] = lid
                    st.session_state.pop(eval_key, None)
                    st.rerun()
            with cretry:
                if st.button(
                    "♻️ Recommencer la mini-task",
                    key=f"ai-mini-retry-btn-{lid}",
                    width="stretch",
                ):
                    st.session_state[start_key] = now_iso()
                    st.session_state[active_key] = lid
                    st.session_state[answer_key] = ""
                    st.session_state.pop(audio_key, None)
                    st.session_state.pop(eval_key, None)
                    st.rerun()

            started_at = st.session_state.get(start_key)
            if started_at:
                elapsed = _seconds_since_iso(started_at)
                remaining = max(0, target_seconds - elapsed)
                st.progress(
                    min(1.0, elapsed / max(1, target_seconds)),
                    text=f"Temps ecoule: {elapsed}s  |  Temps restant cible: {remaining}s",
                )
                if st.session_state.get(active_key) == lid and remaining > 0:
                    st_autorefresh(
                        interval=1000,
                        key=f"ai-mini-refresh-{lid}",
                    )
                if remaining == 0 and st.session_state.get(active_key) == lid:
                    st.session_state.pop(active_key, None)
                    st.info(
                        "⏰ 2 minutes terminees. Soumets ton audio ou ton texte pour evaluation."
                    )

            st.markdown("**🎤 Reponse audio (optionnel) :**")
            mini_audio_widget = st.audio_input(
                "Enregistre ta mini-task puis clique pour soumettre",
                key=audio_key,
            )
            col_transc, col_submit_audio = st.columns(2)
            with col_transc:
                transcribe_clicked = st.button(
                    "📝 Transcrire mon audio",
                    key=f"ai-mini-transcribe-btn-{lid}",
                    width="stretch",
                )
            with col_submit_audio:
                submit_audio_clicked = st.button(
                    "🎤 Soumettre audio",
                    key=f"ai-mini-submit-audio-btn-{lid}",
                    width="stretch",
                    type="primary",
                )

            if transcribe_clicked:
                if not mini_audio_widget:
                    st.warning("Enregistre d'abord ton audio pour la mini-task.")
                else:
                    with st.spinner("Transcription de l'audio..."):
                        transcribed, terr = transcribe_audio_with_openrouter(
                            mini_audio_widget.getvalue(),
                            audio_format="wav",
                        )
                    if terr:
                        st.error(f"Erreur transcription: {terr}")
                    else:
                        st.session_state[answer_key] = transcribed
                        st.success("Transcription ajoutee dans le champ texte.")
                        st.rerun()

            if submit_audio_clicked:
                if not mini_audio_widget:
                    st.warning("Enregistre d'abord ton audio pour soumettre.")
                else:
                    with st.spinner("Transcription + evaluation de l'audio..."):
                        transcribed, terr = transcribe_audio_with_openrouter(
                            mini_audio_widget.getvalue(),
                            audio_format="wav",
                        )
                    if terr:
                        st.error(f"Erreur transcription: {terr}")
                    else:
                        st.session_state[answer_key] = transcribed
                        eval_result, eval_err = evaluate_ai_lesson_mini_task(
                            lesson, transcribed
                        )
                        if eval_err:
                            st.error(f"Erreur evaluation: {eval_err}")
                        else:
                            st.session_state[eval_key] = eval_result

            answer = st.text_area(
                "Ta reponse (texte libre ou transcription de ton oral)",
                key=answer_key,
                placeholder="Ecris ici ta production pour verifier si tu as compris le concept...",
                height=120,
            )
            if st.button(
                "✅ Verifier ma mini-task",
                key=f"ai-mini-eval-btn-{lid}",
                width="stretch",
            ):
                with st.spinner("Evaluation de ta mini-task..."):
                    eval_result, eval_err = evaluate_ai_lesson_mini_task(lesson, answer)
                if eval_err:
                    st.error(f"Erreur evaluation: {eval_err}")
                else:
                    st.session_state[eval_key] = eval_result

            mini_eval = st.session_state.get(eval_key)
            if mini_eval:
                score = mini_eval.get("score", 0)
                correct = mini_eval.get("correct", False)
                feedback = mini_eval.get("feedback_fr", "")
                improved = mini_eval.get("improved_answer", "")
                if correct:
                    st.success(f"Score: {score}/100 — {feedback}")
                else:
                    st.warning(f"Score: {score}/100 — {feedback}")
                if improved:
                    st.markdown(f"**Version amelioree suggeree :** {improved}")

                if improved:
                    st.markdown(f"**Version amelioree suggeree :** {improved}")
