import hashlib
import os

import streamlit as st

from modules.ai_client import (openrouter_chat, text_to_speech_openrouter,
                               transcribe_audio_with_openrouter)
from modules.config import (CEFR_LEVELS, CHAT_MODEL, MT_DIALOGUE_THEMES,
                            MT_GRAMMAR_CONCEPTS, STORY_NARRATOR_VOICES)
from modules.michel_thomas import (_save_dialogue_full_audio,
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
                                   save_mt_themed_dialogues)
from modules.profiles import (get_active_profile, get_profile_module_level,
                              set_profile_module_level)

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


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Leçon & Pratique
# ═══════════════════════════════════════════════════════════════════════════════


def _render_lesson_tab(profile, profile_id):
    st.subheader("📖 Leçon & Pratique — Anglais / Français")
    st.caption(
        "Choisis un concept grammatical. L'IA génère un cours bilingue complet "
        "avec exemples audio et une séquence de pratique alternée FR→EN / EN→FR."
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

    session_labels = [
        f"{s.get('lesson', {}).get('title_fr', s.get('concept', '?'))} ({s.get('level', '?')}) — {s.get('created_at', '')[:10]}"
        for s in sessions
    ]
    active_sid = st.session_state.get("lesson_active_sid", sessions[0]["id"])
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
                ab, _, tts_err = text_to_speech_openrouter(
                    script, voice=voice, language_hint="fr"
                )
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
                ab, _, tts_err = text_to_speech_openrouter(
                    script, voice=voice, language_hint="fr"
                )
            if not tts_err:
                path = _save_lesson_course_audio(sid, ab)
                _update_lesson_course_audio_path(profile_id, sid, path)
                st.rerun()
            else:
                st.error(tts_err)

    st.markdown("---")

    # ── Written course — collapsed by default ─────────────────────────────────
    with st.expander("📖 Voir le cours écrit", expanded=False):
        what = fresh_lesson.get("what_is_it_fr", "")
        if what:
            st.markdown("**💡 C'est quoi ?**")
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

            col_en, col_fr, col_cnt = st.columns([1, 1, 2])
            with col_en:
                if audio_en:
                    st.audio(audio_en, format="audio/wav")
                else:
                    if st.button(f"🔊 EN", key=f"ex-en-gen-{sid}-{i}"):
                        with st.spinner("TTS..."):
                            ab, _, tts_err = text_to_speech_openrouter(
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
                            ab, _, tts_err = text_to_speech_openrouter(
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
                ab, _, tts_err = text_to_speech_openrouter(
                    prompt_text, language_hint=prompt_lang
                )
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
                            _fb_ab, _, _fb_err = text_to_speech_openrouter(
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
                            _imp_ab, _, _imp_err = text_to_speech_openrouter(
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
                    ab, _, tts_err = text_to_speech_openrouter(
                        feedback, language_hint="fr"
                    )
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
                    ab, _, tts_err = text_to_speech_openrouter(
                        expected, language_hint=answer_lang
                    )
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
                        ab, _, tts_err = text_to_speech_openrouter(
                            improved, language_hint=answer_lang
                        )
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

    all_have_audio = lines and all(
        l.get("audio_path_en") and os.path.exists(l.get("audio_path_en", ""))
        for l in lines
    )

    # ── Full audio (single player) ─────────────────────────────────────────────
    full_audio_path = fresh.get("full_audio_path", "")
    full_audio_bytes = _load_audio(full_audio_path) if full_audio_path else None

    if full_audio_bytes:
        st.markdown("#### 🎧 Dialogue complet")
        st.audio(full_audio_bytes, format="audio/wav")
        if st.button("🔄 Regénérer l'audio complet", key=f"regen_full_{sid}"):
            prog = st.progress(0)
            for li, line in enumerate(lines):
                ab, _, tts_err = text_to_speech_openrouter(
                    line.get("line_en", ""), voice=voice, language_hint="en"
                )
                if not tts_err and ab:
                    p = _save_themed_dialogue_line_audio(sid, li, ab)
                    _update_themed_dialogue_line_audio(profile_id, sid, li, p)
                    lines[li]["audio_path_en"] = p
                prog.progress((li + 1) / len(lines))
            merged = _concat_wav_files([l.get("audio_path_en", "") for l in lines])
            if merged:
                fp = _save_dialogue_full_audio(sid, merged)
                _update_dialogue_full_audio(profile_id, sid, fp)
            st.rerun()
        st.markdown("---")
    elif all_have_audio:
        gen_col, _ = st.columns([2, 3])
        with gen_col:
            if st.button(
                "🔗 Fusionner en un seul audio",
                key=f"merge_audio_{sid}",
                type="primary",
                use_container_width=True,
            ):
                merged = _concat_wav_files([l.get("audio_path_en", "") for l in lines])
                if merged:
                    fp = _save_dialogue_full_audio(sid, merged)
                    _update_dialogue_full_audio(profile_id, sid, fp)
                    st.rerun()
                else:
                    st.error("Impossible de fusionner les audios.")
    else:
        gen_col, _ = st.columns([2, 3])
        with gen_col:
            if st.button(
                "🔊 Générer l'audio du dialogue",
                key=f"gen_all_audio_{sid}",
                type="primary",
                use_container_width=True,
            ):
                prog = st.progress(0)
                for li, line in enumerate(lines):
                    if not (
                        line.get("audio_path_en")
                        and os.path.exists(line.get("audio_path_en", ""))
                    ):
                        ab, _, tts_err = text_to_speech_openrouter(
                            line.get("line_en", ""), voice=voice, language_hint="en"
                        )
                        if not tts_err and ab:
                            p = _save_themed_dialogue_line_audio(sid, li, ab)
                            _update_themed_dialogue_line_audio(profile_id, sid, li, p)
                            lines[li]["audio_path_en"] = p
                    prog.progress((li + 1) / len(lines))
                merged = _concat_wav_files([l.get("audio_path_en", "") for l in lines])
                if merged:
                    fp = _save_dialogue_full_audio(sid, merged)
                    _update_dialogue_full_audio(profile_id, sid, fp)
                st.rerun()

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
            f"You are a friendly and encouraging English language teacher having a spoken "
            f"conversation with a French-speaking student to help them practice English. "
            f"The student's CEFR level is {fp_level}. "
            f"Focus conversation naturally around these themes: {themes_str}. "
            f"Weave in practice of these grammar structures: {concepts_str}. "
            f"Keep each reply concise (2-4 sentences max). "
            f"Speak exclusively in English. When you deliberately use one of the target grammar "
            f"structures, add a very brief French note at the end in parentheses, e.g.: "
            f"(→ 2nd conditionnel). "
            f"If the student makes a noticeable grammar mistake, gently correct it by repeating "
            f"the correct form naturally in your reply. "
            f"Start by greeting the student warmly and asking an opening question related to the themes."
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
            ai_audio_bytes, _, tts_err = text_to_speech_openrouter(
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
    fp_voice_active = st.session_state.get("fp_voice", fp_voice if not is_active else "shimmer")

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
            st.audio(audio_bytes, format="audio/wav")

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
                    ai_audio_bytes, _, _ = text_to_speech_openrouter(
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

    tab_lesson, tab_dialogue, tab_free = st.tabs(
        ["📖 Leçon & Pratique", "💬 Dialogues", "🎙️ Pratique libre"]
    )

    with tab_lesson:
        _render_lesson_tab(profile, profile_id)

    with tab_dialogue:
        _render_dialogue_tab(profile, profile_id)

    with tab_free:
        _render_free_practice_tab(profile, profile_id)
