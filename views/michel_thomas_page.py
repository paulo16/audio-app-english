import os

import streamlit as st
from modules.ai_client import text_to_speech_openrouter
from modules.config import (
    CEFR_LEVELS,
    MT_GRAMMAR_CONCEPTS,
    MT_DIALOGUE_THEMES,
    STORY_NARRATOR_VOICES,
)
from modules.michel_thomas import (
    _save_lesson_example_audio,
    _save_themed_dialogue_line_audio,
    _update_lesson_example_audio,
    _update_themed_dialogue_line_audio,
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


# ── helpers ───────────────────────────────────────────────────────────────────


def _load_audio(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
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
            concepts = MT_GRAMMAR_CONCEPTS.get(level, [])
            concept = st.selectbox(
                "Concept grammatical",
                concepts,
                key="lesson_concept_sel",
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
            )

    if generate_btn:
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
        st.info("Aucune leçon générée. Choisis un concept et clique sur **Générer la leçon**.")
        return

    session_labels = [
        f"{s.get('lesson', {}).get('title_fr', s.get('concept', '?'))} ({s.get('level', '?')}) — {s.get('created_at', '')[:10]}"
        for s in sessions
    ]
    active_sid = st.session_state.get("lesson_active_sid", sessions[0]["id"])
    active_idx = next((i for i, s in enumerate(sessions) if s["id"] == active_sid), 0)

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

    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#1e3a5f,#0d2137);padding:20px 24px;border-radius:14px;margin-bottom:16px">
  <span style="font-size:11px;color:#8ab4e8;font-weight:700;letter-spacing:2px;text-transform:uppercase">Niveau {level} · Leçon</span><br/>
  <span style="font-size:24px;font-weight:800;color:#ffffff">{lesson.get('title_fr', '')}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown("### 💡 C'est quoi ?")
    st.info(lesson.get("what_is_it_fr", ""))

    when_raw = lesson.get("when_to_use_fr", "")
    if when_raw:
        st.markdown("### 🗓️ Quand l'utiliser ?")
        for line in when_raw.split("\n"):
            line = line.strip()
            if line:
                st.markdown(line)

    struct = lesson.get("structure", {})
    if any(struct.values()):
        st.markdown("### 🧩 Structure")
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

    analogy = lesson.get("analogy_fr", "")
    if analogy:
        st.markdown("### 🇫🇷 L'analogie avec le français")
        st.success(analogy)

    kp = lesson.get("key_points_fr", [])
    if kp:
        st.markdown("### ⚠️ Points importants")
        for point in kp:
            st.markdown(f"- {point}")

    examples = lesson.get("examples", [])
    if examples:
        st.markdown("### 🔍 Exemples")
        fresh_sessions = load_mt_lesson_sessions(profile_id)
        fresh = next((s for s in fresh_sessions if s["id"] == sid), session)
        fresh_examples = fresh.get("lesson", {}).get("examples", examples)

        for i, ex in enumerate(fresh_examples):
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
                            ab, _, tts_err = text_to_speech_openrouter(en, voice=voice, language_hint="en")
                        if not tts_err:
                            path = _save_lesson_example_audio(sid, i, "en", ab)
                            _update_lesson_example_audio(profile_id, sid, i, "audio_path_en", path)
                            st.rerun()
                        else:
                            st.error(tts_err)
            with col_fr:
                if audio_fr:
                    st.audio(audio_fr, format="audio/wav")
                else:
                    if st.button(f"🔊 FR", key=f"ex-fr-gen-{sid}-{i}"):
                        with st.spinner("TTS..."):
                            ab, _, tts_err = text_to_speech_openrouter(fr_txt, voice="shimmer", language_hint="fr")
                        if not tts_err:
                            path = _save_lesson_example_audio(sid, i, "fr", ab)
                            _update_lesson_example_audio(profile_id, sid, i, "audio_path_fr", path)
                            st.rerun()
                        else:
                            st.error(tts_err)
            with col_cnt:
                st.caption(f"Exemple {i + 1}/{len(fresh_examples)}")

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
        st.success("🎉 Séquence terminée ! Retourne voir le cours ou génère une nouvelle leçon.")
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
    else:
        badge = "🇬🇧 → 🇫🇷  Traduis en **FRANÇAIS**"
        badge_color = "#1a3320"

    st.markdown(
        f"<div style='background:{badge_color};padding:8px 14px;border-radius:8px;margin-bottom:12px;"
        f"font-size:13px;font-weight:700;color:#fff'>{badge}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
<div style="background:#2a2a3e;padding:20px 24px;border-radius:12px;margin-bottom:16px;text-align:center">
  <span style="font-size:22px;font-weight:700;color:#ffffff">{prompt_text}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    if hint:
        st.caption(f"💡 Indice : {hint}")

    if not st.session_state[submitted_key]:
        user_input = st.text_input(
            "Ta traduction",
            key=f"practice_input_{sid}_{idx}",
            placeholder="Écris ta réponse ici…",
        )
        submit_col, skip_col = st.columns([3, 1])
        with submit_col:
            if st.button(
                "✅ Valider",
                key=f"practice_submit_{sid}_{idx}",
                type="primary",
                disabled=not (user_input or "").strip(),
                use_container_width=True,
            ):
                with st.spinner("Évaluation en cours…"):
                    eval_result, err = evaluate_practice_pair(pair, user_input.strip())
                if err:
                    st.error(err)
                else:
                    st.session_state[eval_key] = eval_result
                    st.session_state[submitted_key] = True
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
                st.rerun()
    else:
        eval_result = st.session_state.get(eval_key, {})
        score = eval_result.get("score", 0)
        correct = eval_result.get("correct", False)
        feedback = eval_result.get("feedback_fr", "")
        improved = eval_result.get("improved_answer", "")
        expected = pair.get("answer", "")

        score_color = "#4caf50" if score >= 75 else "#ff9800" if score >= 50 else "#f44336"
        icon = "✅" if correct else "💪"
        st.markdown(
            f"""
<div style="background:#1a1a2e;padding:16px 20px;border-radius:12px;border-left:6px solid {score_color};margin-bottom:12px">
  <span style="font-size:28px;font-weight:800;color:{score_color}">{icon} {score}/100</span><br/>
  <span style="color:#ddd;font-size:15px">{feedback}</span>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
<div style="background:#1e3a5f;padding:10px 16px;border-radius:8px;margin-bottom:8px">
  <span style="font-size:11px;color:#8ab4e8;font-weight:700">✔️ RÉPONSE ATTENDUE</span><br/>
  <span style="font-size:17px;color:#fff;font-weight:600">{expected}</span>
</div>
""",
            unsafe_allow_html=True,
        )

        if improved and improved != expected:
            st.markdown(
                f"""
<div style="background:#332200;padding:10px 16px;border-radius:8px;margin-bottom:8px">
  <span style="font-size:11px;color:#ffb74d;font-weight:700">💡 VERSION AMÉLIORÉE</span><br/>
  <span style="font-size:16px;color:#ffe0b2">{improved}</span>
</div>
""",
                unsafe_allow_html=True,
            )

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
                st.rerun()
        with retry_col:
            if st.button(
                "🔁 Retry",
                key=f"practice_retry_{sid}_{idx}",
                use_container_width=True,
            ):
                st.session_state[submitted_key] = False
                st.session_state.pop(eval_key, None)
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
                index=CEFR_LEVELS.index(saved_level if saved_level in CEFR_LEVELS else "B1"),
                key="dial_level_sel",
            )
        with c2:
            theme = st.selectbox(
                "Thème de vie",
                MT_DIALOGUE_THEMES,
                key="dial_theme_sel",
            )
        with c3:
            concepts = MT_GRAMMAR_CONCEPTS.get(level, [])
            grammar_focus = st.selectbox(
                "Focus grammatical",
                concepts,
                key="dial_grammar_sel",
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

        gen_col, _ = st.columns([2, 3])
        with gen_col:
            gen_btn = st.button(
                "✨ Générer le dialogue",
                key="dial_gen_btn",
                type="primary",
                use_container_width=True,
            )

    if gen_btn:
        with st.spinner(f"Génération du dialogue « {theme} »..."):
            session, err = generate_themed_dialogue(theme, grammar_focus, level, profile_id)
        if err:
            st.error(f"Erreur : {err}")
        else:
            sessions = load_mt_themed_dialogues(profile_id)
            sessions.insert(0, session)
            save_mt_themed_dialogues(sessions, profile_id)
            st.session_state["dial_active_sid"] = session["id"]
            st.rerun()

    sessions = load_mt_themed_dialogues(profile_id)
    if not sessions:
        st.info("Aucun dialogue généré. Choisis un thème et clique sur **Générer le dialogue**.")
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

    missing = [l for l in lines if not (l.get("audio_path_en") and os.path.exists(l.get("audio_path_en", "")))]
    if missing:
        gen_col, _ = st.columns([2, 3])
        with gen_col:
            if st.button("🔊 Générer audio toutes les lignes", key=f"gen_all_audio_{sid}", use_container_width=True):
                prog = st.progress(0)
                total = len(lines)
                for li, line in enumerate(lines):
                    if not (line.get("audio_path_en") and os.path.exists(line.get("audio_path_en", ""))):
                        ab, _, tts_err = text_to_speech_openrouter(
                            line.get("line_en", ""), voice=voice, language_hint="en"
                        )
                        if not tts_err:
                            path = _save_themed_dialogue_line_audio(sid, li, ab)
                            _update_themed_dialogue_line_audio(profile_id, sid, li, path)
                    prog.progress((li + 1) / total)
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
        audio_en = _load_audio(line.get("audio_path_en"))

        speaker_idx = speaker_names.index(spk) if spk in speaker_names else li % 2
        align = "left" if speaker_idx == 0 else "right"
        c_en = colors_en[speaker_idx % 2]
        c_fr = colors_fr[speaker_idx % 2]
        grammar_badge = (
            f" <span style='background:#7c4dff;color:#fff;font-size:10px;padding:2px 7px;border-radius:12px;margin-left:8px'>{grammar_tag}</span>"
            if grammar_tag else ""
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

        a_col, _ = st.columns([1, 8])
        with a_col:
            if audio_en:
                st.audio(audio_en, format="audio/wav")
            else:
                if st.button("🔊", key=f"dial-line-gen-{sid}-{li}", help="Générer audio"):
                    with st.spinner("TTS..."):
                        ab, _, tts_err = text_to_speech_openrouter(line_en, voice=voice, language_hint="en")
                    if not tts_err:
                        path = _save_themed_dialogue_line_audio(sid, li, ab)
                        _update_themed_dialogue_line_audio(profile_id, sid, li, path)
                        st.rerun()
                    else:
                        st.error(tts_err)

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


def render_michel_thomas_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("🎓 Anglais avec l'IA — Leçons & Dialogues")
    st.caption(f"Profil actif : {profile.get('name', 'Profil principal')}")

    tab_lesson, tab_dialogue = st.tabs(["📖 Leçon & Pratique", "💬 Dialogues"])

    with tab_lesson:
        _render_lesson_tab(profile, profile_id)

    with tab_dialogue:
        _render_dialogue_tab(profile, profile_id)
