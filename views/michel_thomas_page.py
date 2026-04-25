import os
import uuid

import streamlit as st
from modules.ai_client import (
    text_to_speech_openrouter,
    transcribe_audio_with_openrouter,
    tts_smart,
)
from modules.config import (
    CEFR_LEVELS,
    MT_PERFECTIONNEMENT_BASE_DIR,
    MT_PERFECTIONNEMENT_DISCS,
    MT_TENSES_BY_LEVEL,
    MT_THEMES_BY_LEVEL,
    STORY_NARRATOR_VOICES,
)
from modules.michel_thomas import (
    _save_dial_line_audio,
    _save_dial_phrase_audio,
    _save_mt_perf_step_audio,
    _save_mt_perf_step_fr_audio,
    _save_mt_step_audio,
    _save_mt_step_fr_audio,
    _update_dial_line_audio,
    _update_dial_phrase_audio,
    _update_perf_step_audio_path,
    evaluate_mt_step,
    generate_mt_dialogue_session,
    generate_mt_perfectionnement_session,
    generate_mt_session,
    load_mt_dialogue_sessions,
    load_mt_perf_sessions,
    load_mt_sessions,
    save_mt_dialogue_sessions,
    save_mt_perf_sessions,
    save_mt_sessions,
)
from modules.profiles import (
    get_active_profile,
    get_profile_module_level,
    set_profile_module_level,
)
from modules.utils import _audio_player_with_repeat, now_iso


def _update_step_audio_path(profile_id, sid, step_idx, field_name, new_path):
    """Persist an audio path update for a single step in the JSON store."""
    all_sessions = load_mt_sessions(profile_id)
    for s in all_sessions:
        if s["id"] == sid and step_idx < len(s.get("steps", [])):
            s["steps"][step_idx][field_name] = new_path
            break
    save_mt_sessions(all_sessions, profile_id)


def _render_mt_ia_tab(profile, profile_id):
    """Render the existing AI-generated Michel Thomas session tab."""
    st.write(
        "Ecoute la phrase en francais, reponds (idealement a l'oral), puis compare/corrige. "
        "Le but n'est pas de memoriser par effort, mais d'ancrer des patterns avec repetition active (Once more)."
    )

    # ── Settings ─────────────────────────────────────────────────────────────
    with st.expander("⚙️ Parametres de la session", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            level_default = get_profile_module_level(profile, "michel_thomas")
            level = st.selectbox(
                "Niveau CEFR",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index(level_default),
                key=f"mt-level-{profile_id}",
            )
            if level != level_default:
                set_profile_module_level(profile_id, "michel_thomas", level)

            themes_for_level = MT_THEMES_BY_LEVEL.get(level, MT_THEMES_BY_LEVEL["B1"])
            theme = st.selectbox(
                "Theme de la session",
                themes_for_level,
                key=f"mt-theme-{profile_id}-{level}",
            )

        with col2:
            tenses_for_level = MT_TENSES_BY_LEVEL.get(level, MT_TENSES_BY_LEVEL["B1"])
            tense_options = ["🔀 Tout pratiquer (aléatoire)"] + tenses_for_level
            tense_focus = st.selectbox(
                "Temps / structure grammaticale a pratiquer",
                tense_options,
                key=f"mt-tense-{profile_id}-{level}",
            )
            step_count = st.slider(
                "Nombre d'etapes",
                min_value=4,
                max_value=10,
                value=7,
                key="mt-step-count",
            )

        voice_label = st.selectbox(
            "Voix audio (TTS)",
            list(STORY_NARRATOR_VOICES.keys()),
            index=0,
            key="mt-voice",
        )
        mt_voice = STORY_NARRATOR_VOICES.get(voice_label, "alloy")

        if st.button(
            "Generer une nouvelle session Michel Thomas",
            type="primary",
            use_container_width=True,
            key="mt-generate-btn",
        ):
            import random as _random

            effective_tense = (
                _random.choice(tenses_for_level)
                if tense_focus.startswith("🔀")
                else tense_focus
            )
            with st.spinner(
                f"Generation de {step_count} etapes — Theme: {theme} | Temps: {effective_tense}..."
            ):
                session, err = generate_mt_session(
                    level=level,
                    theme=theme,
                    tense_focus=effective_tense,
                    step_count=step_count,
                    profile_id=profile_id,
                )
            if err:
                st.error(f"Erreur lors de la generation : {err}")
            else:
                sessions = load_mt_sessions(profile_id)
                sessions.insert(0, session)
                save_mt_sessions(sessions, profile_id)
                st.session_state["mt_active_session_id"] = session["id"]
                st.session_state["mt_active_step_idx"] = 0
                st.success(
                    f"Session generee : {len(session['steps'])} etapes — {theme} / {tense_focus}"
                )
                st.rerun()

    sessions = load_mt_sessions(profile_id)
    if not sessions:
        st.info(
            "Aucune session pour l'instant. Configurez les parametres ci-dessus et cliquez sur Generer."
        )
        return

    # ── Session selector ─────────────────────────────────────────────────────
    session_labels = {
        s[
            "id"
        ]: f"{s.get('level','?')} | {s.get('theme','?')} | {s.get('tense_focus','?')} — {s.get('created_at','')[:10]}"
        for s in sessions
    }
    active_sid = st.session_state.get("mt_active_session_id", sessions[0]["id"])
    if active_sid not in session_labels:
        active_sid = sessions[0]["id"]
        st.session_state["mt_active_session_id"] = active_sid

    selected_sid = st.selectbox(
        "Session active",
        list(session_labels.keys()),
        index=list(session_labels.keys()).index(active_sid),
        format_func=lambda sid: session_labels[sid],
        key="mt-session-selector",
    )
    if selected_sid != active_sid:
        st.session_state["mt_active_session_id"] = selected_sid
        st.session_state["mt_active_step_idx"] = 0
        st.rerun()

    # Delete session
    if st.button(
        "Supprimer cette session",
        key="mt-delete-session",
        type="secondary",
    ):
        sessions = [s for s in sessions if s["id"] != selected_sid]
        save_mt_sessions(sessions, profile_id)
        if sessions:
            st.session_state["mt_active_session_id"] = sessions[0]["id"]
        else:
            st.session_state.pop("mt_active_session_id", None)
        st.session_state["mt_active_step_idx"] = 0
        st.rerun()

    active_session = next((s for s in sessions if s["id"] == selected_sid), None)
    if not active_session:
        st.warning("Session introuvable.")
        return

    steps = active_session.get("steps", [])
    if not steps:
        st.warning("Cette session ne contient pas d'etapes.")
        return

    total = len(steps)
    step_idx = int(st.session_state.get("mt_active_step_idx", 0))
    step_idx = max(0, min(step_idx, total - 1))

    # ── Progress bar ─────────────────────────────────────────────────────────
    st.markdown(
        f"**Etape {step_idx + 1} / {total}** — {active_session.get('tense_focus', '')} | {active_session.get('theme', '')}"
    )
    st.progress((step_idx + 1) / total)

    step = steps[step_idx]
    sid = active_session["id"]
    step_key = f"{sid}_step{step_idx}"

    # ── 1. PHRASE FRANÇAISE + audio FR (toujours accessible) ────────────────
    st.markdown("---")

    # Build-ups scaffold (aide progressive avant la phrase complète)
    build_ups = step.get("build_ups", [])
    if len(build_ups) > 1:
        with st.expander(
            "🪜 Aide progressive (construction étape par étape)", expanded=False
        ):
            st.caption(
                "Comme Michel Thomas — construis la phrase morceau par morceau :"
            )
            for bi, chunk in enumerate(build_ups):
                st.markdown(
                    f"<div style='background:#0d2440;padding:8px 14px;border-radius:6px;"
                    f"border-left:3px solid #4a90d9;margin-bottom:4px;color:#c9ddff;font-size:15px'>"
                    f"{'→ ' * bi}<strong>{chunk}</strong></div>",
                    unsafe_allow_html=True,
                )

    st.markdown(
        f"""
<div style="background:#1e3a5f;padding:18px 22px;border-radius:10px;border-left:5px solid #4a90d9;margin-bottom:6px">
  <span style="font-size:13px;color:#8ab4e8;font-weight:600;letter-spacing:1px">PHRASE EN FRANCAIS</span><br/>
  <span style="font-size:22px;font-weight:700;color:#ffffff">{step.get('french','')}</span>
</div>
""",
        unsafe_allow_html=True,
    )
    fr_audio_path = step.get("fr_audio_path")
    if fr_audio_path and os.path.exists(fr_audio_path):
        with open(fr_audio_path, "rb") as af:
            _audio_player_with_repeat(
                af.read(), "audio/wav", key=f"mt-fr-player-{step_key}"
            )
        if st.button(
            "🔄 Regenerer l'audio français",
            key=f"mt-fr-regen-{step_key}",
            use_container_width=True,
        ):
            with st.spinner("Generation audio français..."):
                ab, _, tts_err = text_to_speech_openrouter(
                    step.get("french", ""), voice=mt_voice, language_hint="fr"
                )
            if tts_err:
                st.error(tts_err)
            else:
                new_path = _save_mt_step_fr_audio(sid, step_idx, ab)
                _update_step_audio_path(
                    profile_id, sid, step_idx, "fr_audio_path", new_path
                )
                st.rerun()
    else:
        if st.button(
            "🔊 Ecouter la phrase en français",
            key=f"mt-fr-gen-{step_key}",
            use_container_width=True,
            type="primary",
        ):
            with st.spinner("Generation audio français..."):
                ab, _, tts_err = text_to_speech_openrouter(
                    step.get("french", ""), voice=mt_voice, language_hint="fr"
                )
            if tts_err:
                st.error(tts_err)
            else:
                new_path = _save_mt_step_fr_audio(sid, step_idx, ab)
                _update_step_audio_path(
                    profile_id, sid, step_idx, "fr_audio_path", new_path
                )
                st.rerun()

    # ── 2. TENTATIVE (audio recommande) + boutons d'action ───────────────────
    attempt_key = f"mt-attempt-{step_key}"
    eval_key = f"mt-eval-{step_key}"
    reveal_key = f"mt-reveal-{step_key}"

    answer_mode = st.radio(
        "Repondre par",
        ["🎙️ Audio (recommande)", "⌨️ Texte"],
        horizontal=True,
        key=f"mt-answer-mode-{profile_id}",
    )

    audio_input = None
    stt_key = f"mt-stt-{step_key}"
    transcript_edit_key = f"mt-transcript-edit-{step_key}"
    if answer_mode.startswith("🎙️"):
        audio_input = st.audio_input(
            "Enregistre ta traduction en anglais",
            key=f"mt-audio-attempt-{step_key}",
            help="Comme Michel Thomas : reponds a voix haute, puis on corrige.",
        )
        if st.session_state.get(stt_key):
            st.caption("Transcription (modifiable) :")
            st.text_area(
                "",
                value=st.session_state.get(stt_key, ""),
                key=transcript_edit_key,
                label_visibility="collapsed",
                height=90,
            )
        else:
            st.caption("La transcription apparaitra ici apres evaluation.")
    else:
        attempt = st.text_input(
            "Ta traduction en anglais :",
            key=attempt_key,
            placeholder="Type your English translation here...",
        )

    col_eval, col_en_audio, col_reveal = st.columns(3)
    with col_eval:
        eval_clicked = st.button(
            "✅ Evaluer ma traduction",
            key=f"mt-eval-btn-{step_key}",
            use_container_width=True,
        )
    with col_en_audio:
        listen_en_clicked = st.button(
            "🔊 Ecouter la traduction",
            key=f"mt-listen-en-btn-{step_key}",
            use_container_width=True,
            help="Ecouter la réponse anglaise sans voir le texte",
        )
    with col_reveal:
        if st.button(
            "👁 Voir la reponse",
            key=f"mt-reveal-btn-{step_key}",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state[reveal_key] = True

    if eval_clicked:
        # Determine attempt text (from audio transcript or direct input)
        attempt_text = ""
        if answer_mode.startswith("🎙️"):
            if audio_input is None:
                st.warning("Enregistre d'abord ta traduction (audio) avant d'evaluer.")
            else:
                audio_bytes = audio_input.getvalue()
                mime = getattr(audio_input, "type", "") or ""
                if "wav" in mime:
                    audio_format = "wav"
                elif "mpeg" in mime or "mp3" in mime:
                    audio_format = "mp3"
                elif "webm" in mime:
                    audio_format = "opus"
                else:
                    audio_format = "wav"

                with st.spinner("Transcription de ton audio..."):
                    transcript, stt_err = transcribe_audio_with_openrouter(
                        audio_bytes, audio_format=audio_format
                    )
                if stt_err:
                    st.error(stt_err)
                else:
                    st.session_state[stt_key] = transcript
                    attempt_text = transcript

                    # If user already edited transcript area, prefer edited value
                    edited = st.session_state.get(transcript_edit_key)
                    if isinstance(edited, str) and edited.strip():
                        attempt_text = edited
        else:
            attempt_text = st.session_state.get(attempt_key, "")

        if attempt_text and attempt_text.strip():
            with st.spinner("Evaluation en cours..."):
                result, err = evaluate_mt_step(step, attempt_text)
            if err:
                st.error(f"Erreur : {err}")
            else:
                st.session_state[eval_key] = result
        elif not answer_mode.startswith("🎙️"):
            st.warning("Ecris d'abord ta traduction avant de l'evaluer.")

    if listen_en_clicked:
        en_audio_check = step.get("audio_path")
        if not (en_audio_check and os.path.exists(en_audio_check)):
            with st.spinner("Generation de l'audio anglais..."):
                ab, _, tts_err = text_to_speech_openrouter(
                    step.get("english", ""), voice=mt_voice, language_hint="en"
                )
            if tts_err:
                st.error(tts_err)
            else:
                new_path = _save_mt_step_audio(sid, step_idx, ab)
                _update_step_audio_path(
                    profile_id, sid, step_idx, "audio_path", new_path
                )
                st.rerun()

    # Re-read step after possible audio_path update
    sessions_fresh = load_mt_sessions(profile_id)
    active_session_fresh = next(
        (s for s in sessions_fresh if s["id"] == sid), active_session
    )
    steps_fresh = active_session_fresh.get("steps", [])
    if step_idx < len(steps_fresh):
        step = steps_fresh[step_idx]

    # ── 3. AUDIO ANGLAIS — toujours accessible une fois genere ────────────────
    en_audio_path = step.get("audio_path")
    if en_audio_path and os.path.exists(en_audio_path):
        st.markdown("**🔊 Traduction anglaise (audio) :**")
        with open(en_audio_path, "rb") as af:
            _audio_player_with_repeat(
                af.read(), "audio/wav", key=f"mt-en-player-{step_key}"
            )
        if st.button(
            "🔄 Regenerer l'audio anglais",
            key=f"mt-regen-en-{step_key}",
            use_container_width=True,
        ):
            with st.spinner("Generation audio anglais..."):
                ab, _, tts_err = text_to_speech_openrouter(
                    step.get("english", ""), voice=mt_voice, language_hint="en"
                )
            if tts_err:
                st.error(tts_err)
            else:
                new_path = _save_mt_step_audio(sid, step_idx, ab)
                _update_step_audio_path(
                    profile_id, sid, step_idx, "audio_path", new_path
                )
                st.rerun()

    # ── 4. RESULTAT DE L'EVALUATION ──────────────────────────────────────────
    once_more_key = f"mt-once-more-{step_key}"
    eval_result = st.session_state.get(eval_key)
    if eval_result:
        score = eval_result.get("score", 0)
        correct = eval_result.get("correct", False)
        feedback = eval_result.get("feedback_fr", "")
        improved = eval_result.get("improved_answer", "")
        if correct and score >= 80:
            st.success(f"Score : {score}/100 — {feedback}")
        else:
            st.warning(f"Score : {score}/100 — {feedback}")
        if improved:
            st.markdown(
                f"""
<div style="background:#1a3320;padding:12px 18px;border-radius:8px;border-left:4px solid #4caf50;margin-top:8px">
  <span style="font-size:12px;color:#88c989;font-weight:600">VERSION AMELIOREE</span><br/>
  <span style="font-size:18px;color:#e8f5e9">{improved}</span>
</div>
""",
                unsafe_allow_html=True,
            )
        # Once more — répétition active (méthode Michel Thomas)
        correct_phrase = improved if improved else step.get("english", "")
        st.markdown("---")
        st.markdown(
            "<div style='background:#2a1f00;padding:10px 16px;border-radius:8px;border-left:4px solid #f0c040;margin-bottom:8px'>"
            "<span style='color:#f0c040;font-weight:700;font-size:13px'>🔁 ONCE MORE — Répète maintenant à voix haute puis écris la phrase :</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        once_more_input = st.text_input(
            "",
            key=f"mt-once-more-input-{step_key}",
            placeholder=f"Écris : {correct_phrase}",
            label_visibility="collapsed",
        )
        if once_more_input.strip().lower() == correct_phrase.strip().lower():
            st.session_state[once_more_key] = True
        if st.session_state.get(once_more_key):
            st.success("✓ Parfait ! La phrase est bien ancrée.")
        elif (
            once_more_input.strip()
            and once_more_input.strip().lower() != correct_phrase.strip().lower()
        ):
            st.warning(f"Pas tout à fait — la phrase exacte : *{correct_phrase}*")

    # ── 5. REPONSE REVELEE (texte + vocab + grammaire + variations audio) ─────
    revealed = st.session_state.get(reveal_key, False)
    if revealed:
        english = step.get("english", "")
        st.markdown(
            f"""
<div style="background:#1a3320;padding:18px 22px;border-radius:10px;border-left:5px solid #4caf50;margin-top:8px">
  <span style="font-size:13px;color:#88c989;font-weight:600;letter-spacing:1px">TRADUCTION ANGLAISE</span><br/>
  <span style="font-size:24px;font-weight:700;color:#e8f5e9">{english}</span>
</div>
""",
            unsafe_allow_html=True,
        )

        vocab = step.get("vocabulary", [])
        if vocab:
            st.markdown("#### Vocabulaire cle")
            for v in vocab:
                word = v.get("word", "")
                tip = v.get("tip", "")
                fr = v.get("french", "")
                st.markdown(
                    f"""
<div style="background:#2d2d2d;padding:10px 16px;border-radius:8px;margin-bottom:6px">
  <span style="font-size:16px;font-weight:700;color:#f0c040">🔑 {word}</span>
  {"<span style='color:#aaa;font-size:13px'> — " + fr + "</span>" if fr else ""}
  {"<br/><span style='color:#ccc;font-size:14px'>💡 " + tip + "</span>" if tip else ""}
</div>
""",
                    unsafe_allow_html=True,
                )

        # Pattern link — connexion avec ce que l'apprenant connait deja
        pattern_link = step.get("pattern_link", "")
        if pattern_link and pattern_link not in (
            "Pas de lien encore — c'est la structure de base : sujet + verbe.",
            "",
        ):
            st.markdown(
                f"<div style='background:#1f1a00;padding:10px 16px;border-radius:8px;"
                f"border-left:4px solid #f0c040;margin-bottom:8px'>"
                f"<span style='color:#f0c040;font-size:12px;font-weight:700'>🔗 MÊME PRINCIPE QUE...</span><br/>"
                f"<span style='color:#fff8dc;font-size:14px'>{pattern_link}</span></div>",
                unsafe_allow_html=True,
            )

        grammar_note = step.get("grammar_note", "")
        if grammar_note:
            st.markdown("#### Note de grammaire")
            st.info(grammar_note)

        variations = step.get("practice_variations", [])
        if variations:
            st.markdown("#### Phrases d'entrainement")
            for vi, var_text in enumerate(variations):
                vcol_text, vcol_audio = st.columns([4, 1])
                with vcol_text:
                    st.markdown(f"**{vi + 1}.** *{var_text}*")
                with vcol_audio:
                    var_audio_key = f"mt-var-audio-{step_key}-{vi}"
                    if st.button(
                        "🔊",
                        key=f"mt-var-btn-{step_key}-{vi}",
                        help=f"Ecouter : {var_text}",
                        use_container_width=True,
                    ):
                        with st.spinner("Generation..."):
                            ab, _, tts_err = text_to_speech_openrouter(
                                var_text, voice=mt_voice, language_hint="en"
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            st.session_state[var_audio_key] = ab
                    var_audio_bytes = st.session_state.get(var_audio_key)
                    if var_audio_bytes:
                        _audio_player_with_repeat(
                            var_audio_bytes,
                            "audio/wav",
                            key=f"mt-var-player-{step_key}-{vi}",
                        )

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("---")
    nav_prev, nav_counter, nav_next = st.columns([1, 2, 1])
    with nav_prev:
        if st.button(
            "Etape precedente",
            key=f"mt-prev-{step_key}",
            disabled=step_idx == 0,
            use_container_width=True,
        ):
            st.session_state["mt_active_step_idx"] = step_idx - 1
            st.rerun()
    with nav_counter:
        st.markdown(
            f"<div style='text-align:center;padding-top:8px;color:#888'>Etape {step_idx + 1} / {total}</div>",
            unsafe_allow_html=True,
        )
    with nav_next:
        if step_idx < total - 1:
            if st.button(
                "Etape suivante",
                key=f"mt-next-{step_key}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state["mt_active_step_idx"] = step_idx + 1
                st.rerun()
        else:
            st.success("Fin de la session ! Bravo.")

    # ── All steps overview (collapsed) ───────────────────────────────────────
    with st.expander(f"Vue d'ensemble de la session ({total} etapes)"):
        for i, s in enumerate(steps):
            is_current = i == step_idx
            marker = "▶️" if is_current else f"{i + 1}."
            french_short = s.get("french", "")
            english_short = s.get("english", "")
            reveal_i = st.session_state.get(f"mt-reveal-{sid}_step{i}", False)
            if reveal_i:
                st.markdown(
                    f"{marker} **FR:** {french_short} → **EN:** {english_short}"
                )
            else:
                st.markdown(f"{marker} **FR:** {french_short} → *[non revele]*")
            if is_current:
                if st.button(
                    f"Aller a l'etape {i + 1}",
                    key=f"mt-goto-current-{i}",
                    use_container_width=True,
                ):
                    pass  # already on this step
            else:
                if st.button(
                    f"Aller a l'etape {i + 1}",
                    key=f"mt-goto-{i}",
                    use_container_width=True,
                ):
                    st.session_state["mt_active_step_idx"] = i
                    st.rerun()


# ── Perfectionnement tab ──────────────────────────────────────────────────────


def _render_tip_card(tip: dict):
    """Render the Michel Thomas Tip card prominently."""
    title = tip.get("title_fr", "Concept")
    explanation = tip.get("explanation_fr", "")
    ex_en = tip.get("example_given_en", "")
    ex_fr = tip.get("example_given_fr", "")
    analogy = tip.get("analogy_fr", "")

    st.markdown(
        f"""
<div style="background:linear-gradient(135deg,#1a0a00,#2d1400);padding:22px 26px;border-radius:14px;
border:2px solid #e67e22;margin-bottom:16px">
  <div style="font-size:11px;color:#e67e22;font-weight:700;letter-spacing:2px;margin-bottom:6px">
    🎓 TIP MICHEL THOMAS
  </div>
  <div style="font-size:20px;font-weight:800;color:#f39c12;margin-bottom:12px">{title}</div>
  <div style="font-size:15px;color:#fdebd0;line-height:1.7;margin-bottom:14px">{explanation}</div>
  {"<div style='background:#2d1a00;padding:12px 16px;border-radius:8px;border-left:4px solid #e67e22;margin-bottom:10px'>"
   "<span style='font-size:12px;color:#e67e22;font-weight:600'>EXEMPLE DONNÉ</span><br/>"
   f"<span style='font-size:17px;font-weight:700;color:#fef9e7'>{ex_en}</span><br/>"
   f"<span style='font-size:14px;color:#aaa;font-style:italic'>{ex_fr}</span>"
   "</div>" if ex_en else ""}
  {"<div style='background:#1a1000;padding:10px 14px;border-radius:8px;border-left:3px solid #f39c12'>"
   "<span style='font-size:12px;color:#f39c12;font-weight:600'>🔗 ANALOGIE FR → EN</span><br/>"
   f"<span style='font-size:14px;color:#fdebd0'>{analogy}</span>"
   "</div>" if analogy else ""}
</div>
""",
        unsafe_allow_html=True,
    )


def _render_mt_perfectionnement_tab(profile, profile_id):
    """Render the Perfectionnement tab (CD 8-11 real audio + AI tip-first sessions)."""
    st.write(
        "Sélectionne un disc, choisis le concept à pratiquer. "
        "Le **Tip Michel Thomas** s'affiche d'abord, puis tu écoutes le vrai audio du CD, "
        "et enfin tu pratiques avec des phrases progressives."
    )

    # ── Settings ─────────────────────────────────────────────────────────────
    with st.expander("⚙️ Nouveau : Disc & Concept", expanded=True):
        disc_names = list(MT_PERFECTIONNEMENT_DISCS.keys())
        disc_label = st.selectbox(
            "Disc",
            disc_names,
            key=f"perf-disc-{profile_id}",
        )
        disc_info = MT_PERFECTIONNEMENT_DISCS[disc_label]
        concepts_for_disc = disc_info["concepts"]
        concept = st.selectbox(
            "Concept à pratiquer",
            ["🔀 Tout pratiquer (aléatoire)"] + concepts_for_disc,
            key=f"perf-concept-{profile_id}-{disc_label}",
        )

        col_steps, col_voice = st.columns(2)
        with col_steps:
            step_count = st.slider(
                "Nombre d'étapes",
                min_value=4,
                max_value=10,
                value=7,
                key="perf-step-count",
            )
        with col_voice:
            voice_label = st.selectbox(
                "Voix TTS",
                list(STORY_NARRATOR_VOICES.keys()),
                index=0,
                key="perf-voice",
            )
        perf_voice = STORY_NARRATOR_VOICES.get(voice_label, "alloy")

        if st.button(
            "🎓 Générer session Perfectionnement",
            type="primary",
            use_container_width=True,
            key="perf-generate-btn",
        ):
            import random as _random

            effective_concept = (
                _random.choice(concepts_for_disc)
                if concept.startswith("🔀")
                else concept
            )
            with st.spinner(
                f"Génération — {effective_concept} ({step_count} étapes)..."
            ):
                session, err = generate_mt_perfectionnement_session(
                    disc_name=disc_label,
                    concept=effective_concept,
                    step_count=step_count,
                    profile_id=profile_id,
                )
            if err:
                st.error(f"Erreur lors de la génération : {err}")
            else:
                sessions = load_mt_perf_sessions(profile_id)
                sessions.insert(0, session)
                save_mt_perf_sessions(sessions, profile_id)
                st.session_state["perf_active_session_id"] = session["id"]
                st.session_state["perf_active_step_idx"] = 0
                st.success(
                    f"Session générée : {len(session['steps'])} étapes — {effective_concept}"
                )
                st.rerun()

    sessions = load_mt_perf_sessions(profile_id)
    if not sessions:
        st.info(
            "Aucune session Perfectionnement. Configurez ci-dessus et cliquez sur Générer."
        )
        return

    # Read voice from session state (set by selectbox above)
    voice_label_current = st.session_state.get(
        "perf-voice", list(STORY_NARRATOR_VOICES.keys())[0]
    )
    perf_voice = STORY_NARRATOR_VOICES.get(voice_label_current, "alloy")

    # ── Session selector ─────────────────────────────────────────────────────
    session_labels = {
        s[
            "id"
        ]: f"{s.get('disc','?')} | {s.get('concept','?')} — {s.get('created_at','')[:10]}"
        for s in sessions
    }
    active_sid = st.session_state.get("perf_active_session_id", sessions[0]["id"])
    if active_sid not in session_labels:
        active_sid = sessions[0]["id"]
        st.session_state["perf_active_session_id"] = active_sid

    col_sel, col_del = st.columns([4, 1])
    with col_sel:
        selected_sid = st.selectbox(
            "Session active",
            list(session_labels.keys()),
            index=list(session_labels.keys()).index(active_sid),
            format_func=lambda sid: session_labels[sid],
            key="perf-session-selector",
        )
    with col_del:
        st.write("")
        st.write("")
        if st.button(
            "🗑️ Supprimer", key="perf-delete-session", use_container_width=True
        ):
            sessions = [s for s in sessions if s["id"] != selected_sid]
            save_mt_perf_sessions(sessions, profile_id)
            if sessions:
                st.session_state["perf_active_session_id"] = sessions[0]["id"]
            else:
                st.session_state.pop("perf_active_session_id", None)
            st.session_state["perf_active_step_idx"] = 0
            st.rerun()

    if selected_sid != active_sid:
        st.session_state["perf_active_session_id"] = selected_sid
        st.session_state["perf_active_step_idx"] = 0
        st.rerun()

    active_session = next((s for s in sessions if s["id"] == selected_sid), None)
    if not active_session:
        st.warning("Session introuvable.")
        return

    steps = active_session.get("steps", [])
    if not steps:
        st.warning("Cette session ne contient pas d'étapes.")
        return

    total = len(steps)
    step_idx = int(st.session_state.get("perf_active_step_idx", 0))
    step_idx = max(0, min(step_idx, total - 1))
    step = steps[step_idx]
    sid = active_session["id"]
    step_key = f"perf-{sid}_step{step_idx}"

    # ── 1. TIP CARD (affiché EN PREMIER) ─────────────────────────────────────
    tip = active_session.get("tip", {})
    if tip:
        _render_tip_card(tip)

    # ── 2. LECTEUR AUDIO DU VRAI CD ──────────────────────────────────────────
    session_disc = active_session.get("disc", "")
    disc_info_active = MT_PERFECTIONNEMENT_DISCS.get(session_disc, {})
    folder = disc_info_active.get("folder", "")
    if folder:
        disc_folder_path = os.path.join(MT_PERFECTIONNEMENT_BASE_DIR, folder)
        if os.path.isdir(disc_folder_path):
            mp3_files = sorted(
                [f for f in os.listdir(disc_folder_path) if f.lower().endswith(".mp3")]
            )
            if mp3_files:
                st.markdown("#### 🎙️ Écouter le vrai CD Michel Thomas")
                st.caption(
                    "Écoute d'abord le Tip ci-dessus, puis le CD pour entendre Michel Thomas expliquer le concept."
                )
                selected_track = st.selectbox(
                    "Piste",
                    mp3_files,
                    key=f"perf-track-{sid}",
                )
                track_path = os.path.join(disc_folder_path, selected_track)
                with open(track_path, "rb") as af:
                    st.audio(af.read(), format="audio/mp3")

    st.markdown("---")

    # ── 3. PROGRESSION + ÉTAPE COURANTE ──────────────────────────────────────
    st.markdown(
        f"**Étape {step_idx + 1} / {total}** — {active_session.get('concept', '')}"
    )
    st.progress((step_idx + 1) / total)

    # Tip echo — mini-rappel de la formule pour cette étape
    tip_echo = step.get("tip_echo", "")
    if tip_echo:
        st.markdown(
            f"<div style='background:#1a0a00;padding:8px 14px;border-radius:6px;"
            f"border-left:3px solid #e67e22;margin-bottom:10px;color:#f39c12;font-size:14px;font-weight:600'>"
            f"🔑 {tip_echo}</div>",
            unsafe_allow_html=True,
        )

    # Build-ups scaffold
    build_ups = step.get("build_ups", [])
    if len(build_ups) > 1:
        with st.expander(
            "🪜 Aide progressive (construction étape par étape)", expanded=False
        ):
            st.caption(
                "Comme Michel Thomas — construis la phrase morceau par morceau :"
            )
            for bi, chunk in enumerate(build_ups):
                st.markdown(
                    f"<div style='background:#0d2440;padding:8px 14px;border-radius:6px;"
                    f"border-left:3px solid #4a90d9;margin-bottom:4px;color:#c9ddff;font-size:15px'>"
                    f"{'→ ' * bi}<strong>{chunk}</strong></div>",
                    unsafe_allow_html=True,
                )

    # Hint
    hint = step.get("hint", "")
    if hint:
        st.caption(f"💡 Indice : {hint}")

    # French sentence
    st.markdown(
        f"""
<div style="background:#1e3a5f;padding:18px 22px;border-radius:10px;border-left:5px solid #4a90d9;margin-bottom:6px">
  <span style="font-size:13px;color:#8ab4e8;font-weight:600;letter-spacing:1px">PHRASE EN FRANÇAIS</span><br/>
  <span style="font-size:22px;font-weight:700;color:#ffffff">{step.get('french','')}</span>
</div>
""",
        unsafe_allow_html=True,
    )

    # French audio button
    fr_audio_path = step.get("fr_audio_path")
    if fr_audio_path and os.path.exists(fr_audio_path):
        with open(fr_audio_path, "rb") as af:
            _audio_player_with_repeat(
                af.read(), "audio/wav", key=f"perf-fr-player-{step_key}"
            )
        if st.button(
            "🔄 Régénérer l'audio français",
            key=f"perf-fr-regen-{step_key}",
            use_container_width=True,
        ):
            with st.spinner("Génération audio français..."):
                ab, _, tts_err = text_to_speech_openrouter(
                    step.get("french", ""), voice=perf_voice, language_hint="fr"
                )
            if tts_err:
                st.error(tts_err)
            else:
                new_path = _save_mt_perf_step_fr_audio(sid, step_idx, ab)
                _update_perf_step_audio_path(
                    profile_id, sid, step_idx, "fr_audio_path", new_path
                )
                st.rerun()
    else:
        if st.button(
            "🔊 Écouter la phrase en français",
            key=f"perf-fr-gen-{step_key}",
            use_container_width=True,
            type="primary",
        ):
            with st.spinner("Génération audio français..."):
                ab, _, tts_err = text_to_speech_openrouter(
                    step.get("french", ""), voice=perf_voice, language_hint="fr"
                )
            if tts_err:
                st.error(tts_err)
            else:
                new_path = _save_mt_perf_step_fr_audio(sid, step_idx, ab)
                _update_perf_step_audio_path(
                    profile_id, sid, step_idx, "fr_audio_path", new_path
                )
                st.rerun()

    # ── 4. RÉPONSE & ÉVALUATION ───────────────────────────────────────────────
    attempt_key = f"perf-attempt-{step_key}"
    eval_key = f"perf-eval-{step_key}"
    reveal_key = f"perf-reveal-{step_key}"
    once_more_key = f"perf-once-more-{step_key}"
    stt_key = f"perf-stt-{step_key}"
    transcript_edit_key = f"perf-transcript-edit-{step_key}"

    answer_mode = st.radio(
        "Répondre par",
        ["🎙️ Audio (recommandé)", "⌨️ Texte"],
        horizontal=True,
        key=f"perf-answer-mode-{profile_id}",
    )

    audio_input = None
    if answer_mode.startswith("🎙️"):
        audio_input = st.audio_input(
            "Enregistre ta traduction en anglais",
            key=f"perf-audio-attempt-{step_key}",
            help="Réponds à voix haute, comme avec Michel Thomas.",
        )
        if st.session_state.get(stt_key):
            st.caption("Transcription (modifiable) :")
            st.text_area(
                "",
                value=st.session_state.get(stt_key, ""),
                key=transcript_edit_key,
                label_visibility="collapsed",
                height=90,
            )
        else:
            st.caption("La transcription apparaîtra ici après évaluation.")
    else:
        st.text_input(
            "Ta traduction en anglais :",
            key=attempt_key,
            placeholder="Type your English translation here...",
        )

    col_eval, col_en_audio, col_reveal = st.columns(3)
    with col_eval:
        eval_clicked = st.button(
            "✅ Évaluer ma traduction",
            key=f"perf-eval-btn-{step_key}",
            use_container_width=True,
        )
    with col_en_audio:
        listen_en_clicked = st.button(
            "🔊 Écouter la traduction",
            key=f"perf-listen-en-btn-{step_key}",
            use_container_width=True,
        )
    with col_reveal:
        if st.button(
            "👁 Voir la réponse",
            key=f"perf-reveal-btn-{step_key}",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state[reveal_key] = True

    if eval_clicked:
        attempt_text = ""
        if answer_mode.startswith("🎙️"):
            if audio_input is None:
                st.warning("Enregistre d'abord ta traduction avant d'évaluer.")
            else:
                audio_bytes = audio_input.getvalue()
                mime = getattr(audio_input, "type", "") or ""
                audio_format = "wav"
                if "mpeg" in mime or "mp3" in mime:
                    audio_format = "mp3"
                elif "webm" in mime:
                    audio_format = "opus"
                with st.spinner("Transcription de ton audio..."):
                    transcript, stt_err = transcribe_audio_with_openrouter(
                        audio_bytes, audio_format=audio_format
                    )
                if stt_err:
                    st.error(stt_err)
                else:
                    st.session_state[stt_key] = transcript
                    attempt_text = transcript
                    edited = st.session_state.get(transcript_edit_key)
                    if isinstance(edited, str) and edited.strip():
                        attempt_text = edited
        else:
            attempt_text = st.session_state.get(attempt_key, "")

        if attempt_text and attempt_text.strip():
            with st.spinner("Évaluation en cours..."):
                result, err = evaluate_mt_step(step, attempt_text)
            if err:
                st.error(f"Erreur : {err}")
            else:
                st.session_state[eval_key] = result
        elif not answer_mode.startswith("🎙️"):
            st.warning("Écris d'abord ta traduction avant de l'évaluer.")

    if listen_en_clicked:
        en_audio_check = step.get("audio_path")
        if not (en_audio_check and os.path.exists(en_audio_check)):
            with st.spinner("Génération de l'audio anglais..."):
                ab, _, tts_err = text_to_speech_openrouter(
                    step.get("english", ""), voice=perf_voice, language_hint="en"
                )
            if tts_err:
                st.error(tts_err)
            else:
                new_path = _save_mt_perf_step_audio(sid, step_idx, ab)
                _update_perf_step_audio_path(
                    profile_id, sid, step_idx, "audio_path", new_path
                )
                st.rerun()

    # Reload step after possible audio update
    sessions_fresh = load_mt_perf_sessions(profile_id)
    active_session_fresh = next(
        (s for s in sessions_fresh if s["id"] == sid), active_session
    )
    steps_fresh = active_session_fresh.get("steps", [])
    if step_idx < len(steps_fresh):
        step = steps_fresh[step_idx]

    # English audio player (once generated)
    en_audio_path = step.get("audio_path")
    if en_audio_path and os.path.exists(en_audio_path):
        st.markdown("**🔊 Traduction anglaise (audio) :**")
        with open(en_audio_path, "rb") as af:
            _audio_player_with_repeat(
                af.read(), "audio/wav", key=f"perf-en-player-{step_key}"
            )

    # Evaluation result
    eval_result = st.session_state.get(eval_key)
    if eval_result:
        score = eval_result.get("score", 0)
        correct = eval_result.get("correct", False)
        feedback = eval_result.get("feedback_fr", "")
        improved = eval_result.get("improved_answer", "")
        if correct and score >= 80:
            st.success(f"Score : {score}/100 — {feedback}")
        else:
            st.warning(f"Score : {score}/100 — {feedback}")
        if improved:
            st.markdown(
                f"""
<div style="background:#1a3320;padding:12px 18px;border-radius:8px;border-left:4px solid #4caf50;margin-top:8px">
  <span style="font-size:12px;color:#88c989;font-weight:600">VERSION AMÉLIORÉE</span><br/>
  <span style="font-size:18px;color:#e8f5e9">{improved}</span>
</div>
""",
                unsafe_allow_html=True,
            )
        correct_phrase = improved if improved else step.get("english", "")
        st.markdown("---")
        st.markdown(
            "<div style='background:#2a1f00;padding:10px 16px;border-radius:8px;border-left:4px solid #f0c040;margin-bottom:8px'>"
            "<span style='color:#f0c040;font-weight:700;font-size:13px'>🔁 ONCE MORE — Répète maintenant à voix haute puis écris la phrase :</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        once_more_input = st.text_input(
            "",
            key=f"perf-once-more-input-{step_key}",
            placeholder=f"Écris : {correct_phrase}",
            label_visibility="collapsed",
        )
        if once_more_input.strip().lower() == correct_phrase.strip().lower():
            st.session_state[once_more_key] = True
        if st.session_state.get(once_more_key):
            st.success("✓ Parfait ! La phrase est bien ancrée.")
        elif (
            once_more_input.strip()
            and once_more_input.strip().lower() != correct_phrase.strip().lower()
        ):
            st.warning(f"Pas tout à fait — la phrase exacte : *{correct_phrase}*")

    # ── 5. RÉPONSE RÉVÉLÉE ────────────────────────────────────────────────────
    revealed = st.session_state.get(reveal_key, False)
    if revealed:
        english = step.get("english", "")
        st.markdown(
            f"""
<div style="background:#1a3320;padding:18px 22px;border-radius:10px;border-left:5px solid #4caf50;margin-top:8px">
  <span style="font-size:13px;color:#88c989;font-weight:600;letter-spacing:1px">TRADUCTION ANGLAISE</span><br/>
  <span style="font-size:24px;font-weight:700;color:#e8f5e9">{english}</span>
</div>
""",
            unsafe_allow_html=True,
        )
        vocab = step.get("vocabulary", [])
        if vocab:
            st.markdown("#### Vocabulaire clé")
            for v in vocab:
                word = v.get("word", "")
                tip_v = v.get("tip", "")
                fr_v = v.get("french", "")
                st.markdown(
                    f"""
<div style="background:#2d2d2d;padding:10px 16px;border-radius:8px;margin-bottom:6px">
  <span style="font-size:16px;font-weight:700;color:#f0c040">🔑 {word}</span>
  {"<span style='color:#aaa;font-size:13px'> — " + fr_v + "</span>" if fr_v else ""}
  {"<br/><span style='color:#ccc;font-size:14px'>💡 " + tip_v + "</span>" if tip_v else ""}
</div>
""",
                    unsafe_allow_html=True,
                )

        grammar_note = step.get("grammar_note", "")
        if grammar_note:
            st.markdown("#### Note de grammaire")
            st.info(grammar_note)

        variations = step.get("practice_variations", [])
        if variations:
            st.markdown("#### Phrases d'entraînement")
            for vi, var_text in enumerate(variations):
                vcol_text, vcol_audio = st.columns([4, 1])
                with vcol_text:
                    st.markdown(f"**{vi + 1}.** *{var_text}*")
                with vcol_audio:
                    var_audio_key = f"perf-var-audio-{step_key}-{vi}"
                    if st.button(
                        "🔊",
                        key=f"perf-var-btn-{step_key}-{vi}",
                        help=f"Écouter : {var_text}",
                        use_container_width=True,
                    ):
                        with st.spinner("Génération..."):
                            ab, _, tts_err = text_to_speech_openrouter(
                                var_text, voice=perf_voice, language_hint="en"
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            st.session_state[var_audio_key] = ab
                    var_audio_bytes = st.session_state.get(var_audio_key)
                    if var_audio_bytes:
                        _audio_player_with_repeat(
                            var_audio_bytes,
                            "audio/wav",
                            key=f"perf-var-player-{step_key}-{vi}",
                        )

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("---")
    nav_prev, nav_counter, nav_next = st.columns([1, 2, 1])
    with nav_prev:
        if st.button(
            "Étape précédente",
            key=f"perf-prev-{step_key}",
            disabled=step_idx == 0,
            use_container_width=True,
        ):
            st.session_state["perf_active_step_idx"] = step_idx - 1
            st.rerun()
    with nav_counter:
        st.markdown(
            f"<div style='text-align:center;padding-top:8px;color:#888'>Étape {step_idx + 1} / {total}</div>",
            unsafe_allow_html=True,
        )
    with nav_next:
        if step_idx < total - 1:
            if st.button(
                "Étape suivante",
                key=f"perf-next-{step_key}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state["perf_active_step_idx"] = step_idx + 1
                st.rerun()
        else:
            st.success("Fin de la session ! Bravo. 🎉")

    # ── All steps overview ────────────────────────────────────────────────────
    with st.expander(f"Vue d'ensemble ({total} étapes)"):
        for i, s in enumerate(steps):
            is_current = i == step_idx
            marker = "▶️" if is_current else f"{i + 1}."
            fr_s = s.get("french", "")
            en_s = s.get("english", "")
            rev_i = st.session_state.get(f"perf-reveal-{sid}_step{i}", False)
            if rev_i:
                st.markdown(f"{marker} **FR:** {fr_s} → **EN:** {en_s}")
            else:
                st.markdown(f"{marker} **FR:** {fr_s} → *[non révélé]*")
            if not is_current:
                if st.button(
                    f"Aller à l'étape {i + 1}",
                    key=f"perf-goto-{i}",
                    use_container_width=True,
                ):
                    st.session_state["perf_active_step_idx"] = i
                    st.rerun()


# ── Leçons bilingues & Dialogues tab ─────────────────────────────────────────


def _render_mt_dialogue_tab(profile, profile_id):
    """Render the bilingual lessons + dialogue + flashcards tab."""
    st.write(
        "Génère une **leçon bilingue** (phrases clés EN + FR avec audio), "
        "puis écoute le dialogue en contexte, et entraîne-toi avec les **flashcards**."
    )

    # ── Settings ─────────────────────────────────────────────────────────────
    with st.expander("⚙️ Paramètres de la leçon", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            level_default = get_profile_module_level(profile, "michel_thomas")
            level = st.selectbox(
                "Niveau CEFR",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index(level_default),
                key=f"dial-level-{profile_id}",
            )
            themes_for_level = MT_THEMES_BY_LEVEL.get(level, MT_THEMES_BY_LEVEL["B1"])
            theme = st.selectbox(
                "Thème",
                themes_for_level,
                key=f"dial-theme-{profile_id}-{level}",
            )
        with col2:
            tenses_for_level = MT_TENSES_BY_LEVEL.get(level, MT_TENSES_BY_LEVEL["B1"])
            tense_focus = st.selectbox(
                "Temps / structure à pratiquer",
                ["🔀 Tout pratiquer (aléatoire)"] + tenses_for_level,
                key=f"dial-tense-{profile_id}-{level}",
            )
            phrase_count = st.slider(
                "Nombre de phrases clés",
                min_value=4,
                max_value=8,
                value=6,
                key="dial-phrase-count",
            )
        voice_label = st.selectbox(
            "Voix audio (TTS)",
            list(STORY_NARRATOR_VOICES.keys()),
            index=0,
            key="dial-voice",
        )
        dial_voice = STORY_NARRATOR_VOICES.get(voice_label, "alloy")

        if st.button(
            "📚 Générer la leçon bilingue",
            type="primary",
            use_container_width=True,
            key="dial-generate-btn",
        ):
            import random as _random

            effective_tense = (
                _random.choice(tenses_for_level)
                if tense_focus.startswith("🔀")
                else tense_focus
            )
            with st.spinner(f"Génération — {theme} | {effective_tense}..."):
                session, err = generate_mt_dialogue_session(
                    level=level,
                    theme=theme,
                    tense_focus=effective_tense,
                    phrase_count=phrase_count,
                    profile_id=profile_id,
                )
            if err:
                st.error(f"Erreur : {err}")
            else:
                sessions = load_mt_dialogue_sessions(profile_id)
                sessions.insert(0, session)
                save_mt_dialogue_sessions(sessions, profile_id)
                st.session_state["dial_active_session_id"] = session["id"]
                st.session_state["dial_active_tab"] = "lesson"
                st.success(
                    f"Leçon générée : {len(session['key_phrases'])} phrases — {theme}"
                )
                st.rerun()

    sessions = load_mt_dialogue_sessions(profile_id)
    if not sessions:
        st.info("Aucune leçon encore. Configurez et cliquez sur Générer.")
        return

    # ── Session selector ─────────────────────────────────────────────────────
    session_labels = {
        s["id"]: f"{s.get('level','?')} | {s.get('theme','?')} — {s.get('created_at','')[:10]}"
        for s in sessions
    }
    active_sid = st.session_state.get("dial_active_session_id", sessions[0]["id"])
    if active_sid not in session_labels:
        active_sid = sessions[0]["id"]
        st.session_state["dial_active_session_id"] = active_sid

    col_sel, col_del = st.columns([4, 1])
    with col_sel:
        selected_sid = st.selectbox(
            "Leçon active",
            list(session_labels.keys()),
            index=list(session_labels.keys()).index(active_sid),
            format_func=lambda sid: session_labels[sid],
            key="dial-session-selector",
        )
    with col_del:
        st.write("")
        st.write("")
        if st.button("🗑️ Supprimer", key="dial-delete", use_container_width=True):
            sessions = [s for s in sessions if s["id"] != selected_sid]
            save_mt_dialogue_sessions(sessions, profile_id)
            st.session_state.pop("dial_active_session_id", None)
            st.rerun()

    if selected_sid != active_sid:
        st.session_state["dial_active_session_id"] = selected_sid
        st.session_state["dial_active_tab"] = "lesson"
        st.rerun()

    active_session = next((s for s in sessions if s["id"] == selected_sid), None)
    if not active_session:
        return

    sid = active_session["id"]
    key_phrases = active_session.get("key_phrases", [])
    dialogue = active_session.get("dialogue", [])
    flashcards = active_session.get("flashcards", [])

    # Retrieve voice from session state
    voice_label_now = st.session_state.get("dial-voice", list(STORY_NARRATOR_VOICES.keys())[0])
    dial_voice = STORY_NARRATOR_VOICES.get(voice_label_now, "alloy")

    # Sub-tabs inside the dialogue tab
    sub_lesson, sub_dialogue, sub_flash = st.tabs(
        ["📖 Phrases clés", "💬 Dialogue", "🃏 Flashcards"]
    )

    # ─── Sub-tab 1: Phrases clés bilingues ───────────────────────────────────
    with sub_lesson:
        st.markdown(
            f"**{active_session.get('theme','')}** — "
            f"*{active_session.get('tense_focus','')}* "
            f"(niveau {active_session.get('level','')})"
        )
        st.markdown("---")
        # Reload to get fresh audio paths
        fresh_sessions = load_mt_dialogue_sessions(profile_id)
        fresh_active = next((s for s in fresh_sessions if s["id"] == sid), active_session)
        fresh_phrases = fresh_active.get("key_phrases", [])

        for pi, phrase in enumerate(fresh_phrases):
            en = phrase.get("english", "")
            fr = phrase.get("french", "")
            grammar = phrase.get("grammar_note", "")
            tip_txt = phrase.get("usage_tip", "")
            memory = phrase.get("memory_trick", "")
            phrase_key = f"dial-{sid}-p{pi}"

            # Phrase card
            st.markdown(
                f"""
<div style="background:#1e3a5f;padding:14px 20px;border-radius:10px;border-left:5px solid #4a90d9;margin-bottom:4px">
  <span style="font-size:12px;color:#8ab4e8;font-weight:600;letter-spacing:1px">ANGLAIS</span><br/>
  <span style="font-size:20px;font-weight:700;color:#ffffff">{en}</span>
</div>
<div style="background:#1a3320;padding:10px 20px;border-radius:10px;border-left:5px solid #4caf50;margin-bottom:8px">
  <span style="font-size:12px;color:#88c989;font-weight:600;letter-spacing:1px">FRANÇAIS</span><br/>
  <span style="font-size:17px;color:#e8f5e9">{fr}</span>
</div>
""",
                unsafe_allow_html=True,
            )

            # Audio buttons row
            col_en_audio, col_fr_audio = st.columns(2)
            with col_en_audio:
                en_audio_path = phrase.get("audio_path_en")
                if en_audio_path and os.path.exists(en_audio_path):
                    with open(en_audio_path, "rb") as af:
                        _audio_player_with_repeat(af.read(), "audio/wav", key=f"{phrase_key}-en-player")
                else:
                    if st.button(
                        "🔊 Écouter EN",
                        key=f"{phrase_key}-en-btn",
                        use_container_width=True,
                        type="primary",
                    ):
                        with st.spinner("Génération audio anglais..."):
                            ab, _, tts_err = text_to_speech_openrouter(
                                en, voice=dial_voice, language_hint="en"
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            new_path = _save_dial_phrase_audio(sid, pi, "en", ab)
                            _update_dial_phrase_audio(profile_id, sid, pi, "audio_path_en", new_path)
                            st.rerun()
            with col_fr_audio:
                fr_audio_path = phrase.get("audio_path_fr")
                if fr_audio_path and os.path.exists(fr_audio_path):
                    with open(fr_audio_path, "rb") as af:
                        _audio_player_with_repeat(af.read(), "audio/wav", key=f"{phrase_key}-fr-player")
                else:
                    if st.button(
                        "🔊 Écouter FR",
                        key=f"{phrase_key}-fr-btn",
                        use_container_width=True,
                    ):
                        with st.spinner("Génération audio français..."):
                            ab, _, tts_err = text_to_speech_openrouter(
                                fr, voice=dial_voice, language_hint="fr"
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            new_path = _save_dial_phrase_audio(sid, pi, "fr", ab)
                            _update_dial_phrase_audio(profile_id, sid, pi, "audio_path_fr", new_path)
                            st.rerun()

            # Grammar / tip / memory trick (collapsed)
            with st.expander("💡 Note & astuce", expanded=False):
                if grammar:
                    st.info(f"📝 **Grammaire :** {grammar}")
                if tip_txt:
                    st.success(f"✅ **Usage :** {tip_txt}")
                if memory:
                    st.markdown(
                        f"<div style='background:#1f1a00;padding:10px 14px;border-radius:8px;"
                        f"border-left:3px solid #f0c040'>"
                        f"<span style='color:#f0c040;font-weight:700'>🧠 Astuce mémoire : </span>"
                        f"<span style='color:#fff8dc'>{memory}</span></div>",
                        unsafe_allow_html=True,
                    )
            st.markdown("---")

    # ─── Sub-tab 2: Dialogue ─────────────────────────────────────────────────
    with sub_dialogue:
        st.markdown("#### 💬 Dialogue en contexte")
        st.caption("Lis le dialogue, écoute chaque réplique, puis essaie de le rejouer.")

        fresh_sessions2 = load_mt_dialogue_sessions(profile_id)
        fresh_active2 = next((s for s in fresh_sessions2 if s["id"] == sid), active_session)
        fresh_dialogue = fresh_active2.get("dialogue", [])

        for li, line in enumerate(fresh_dialogue):
            speaker = line.get("speaker", f"Speaker {li % 2 + 1}")
            line_en = line.get("line_en", "")
            line_fr = line.get("line_fr", "")
            line_key = f"dial-{sid}-line{li}"
            is_a = li % 2 == 0
            color_en = "#4a90d9" if is_a else "#4caf50"
            bg_en = "#1e3a5f" if is_a else "#1a3320"

            col_text, col_btn = st.columns([5, 1])
            with col_text:
                st.markdown(
                    f"""
<div style="background:{bg_en};padding:10px 16px;border-radius:8px;border-left:4px solid {color_en};margin-bottom:2px">
  <span style="font-size:11px;color:{color_en};font-weight:700">{speaker.upper()}</span><br/>
  <span style="font-size:16px;font-weight:700;color:#fff">{line_en}</span><br/>
  <span style="font-size:13px;color:#aaa;font-style:italic">{line_fr}</span>
</div>
""",
                    unsafe_allow_html=True,
                )
            with col_btn:
                audio_path_en = line.get("audio_path_en")
                if audio_path_en and os.path.exists(audio_path_en):
                    if st.button("🔊", key=f"{line_key}-play", use_container_width=True, help="Rejouer"):
                        pass  # audio player below will display
                    with open(audio_path_en, "rb") as af:
                        _audio_player_with_repeat(af.read(), "audio/wav", key=f"{line_key}-player")
                else:
                    if st.button(
                        "🔊",
                        key=f"{line_key}-gen",
                        use_container_width=True,
                        help="Générer l'audio de cette réplique",
                    ):
                        with st.spinner(""):
                            ab, _, tts_err = text_to_speech_openrouter(
                                line_en, voice=dial_voice, language_hint="en"
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            new_path = _save_dial_line_audio(sid, li, ab)
                            _update_dial_line_audio(profile_id, sid, li, new_path)
                            st.rerun()

        # Generate all audio button
        st.markdown("---")
        if st.button(
            "🔊 Générer l'audio de tout le dialogue",
            use_container_width=True,
            key="dial-gen-all-audio",
        ):
            progress = st.progress(0)
            total_lines = len(fresh_dialogue)
            for li, line in enumerate(fresh_dialogue):
                if not (line.get("audio_path_en") and os.path.exists(line.get("audio_path_en", ""))):
                    ab, _, tts_err = text_to_speech_openrouter(
                        line.get("line_en", ""), voice=dial_voice, language_hint="en"
                    )
                    if not tts_err:
                        new_path = _save_dial_line_audio(sid, li, ab)
                        _update_dial_line_audio(profile_id, sid, li, new_path)
                progress.progress((li + 1) / total_lines)
            st.rerun()

    # ─── Sub-tab 3: Flashcards ───────────────────────────────────────────────
    with sub_flash:
        if not flashcards:
            st.info("Pas de flashcards pour cette session.")
        else:
            st.markdown("#### 🃏 Flashcards — Français → Anglais")
            st.caption(
                "Lis la phrase française, essaie de la traduire mentalement, "
                "puis retourne la carte pour voir la réponse."
            )

            fc_idx_key = f"dial-fc-idx-{sid}"
            fc_revealed_key = f"dial-fc-rev-{sid}"
            fc_score_key = f"dial-fc-score-{sid}"

            if fc_idx_key not in st.session_state:
                st.session_state[fc_idx_key] = 0
            if fc_score_key not in st.session_state:
                st.session_state[fc_score_key] = {"correct": 0, "total": 0}

            total_fc = len(flashcards)
            fc_idx = min(int(st.session_state[fc_idx_key]), total_fc - 1)
            card = flashcards[fc_idx]

            score = st.session_state[fc_score_key]
            col_prog, col_score = st.columns([3, 1])
            with col_prog:
                st.progress((fc_idx + 1) / total_fc, text=f"Carte {fc_idx + 1} / {total_fc}")
            with col_score:
                st.metric("Score", f"{score['correct']}/{score['total']}")

            # Card face (French)
            st.markdown(
                f"""
<div style="background:linear-gradient(135deg,#1e3a5f,#0d2440);padding:32px 28px;border-radius:14px;
border:2px solid #4a90d9;margin:16px 0;text-align:center">
  <div style="font-size:12px;color:#8ab4e8;font-weight:700;letter-spacing:2px;margin-bottom:12px">
    🇫🇷 FRANÇAIS
  </div>
  <div style="font-size:24px;font-weight:800;color:#ffffff">{card['front_fr']}</div>
</div>
""",
                unsafe_allow_html=True,
            )

            # Reveal toggle
            revealed = st.session_state.get(fc_revealed_key, False)
            col_rev, col_know, col_no = st.columns([2, 1, 1])
            with col_rev:
                if st.button(
                    "👁 Voir la traduction anglaise",
                    key=f"dial-fc-reveal-{sid}-{fc_idx}",
                    use_container_width=True,
                    type="secondary",
                ):
                    st.session_state[fc_revealed_key] = True
                    st.rerun()

            if revealed:
                st.markdown(
                    f"""
<div style="background:linear-gradient(135deg,#1a3320,#0d2210);padding:28px 28px;border-radius:14px;
border:2px solid #4caf50;margin:8px 0;text-align:center">
  <div style="font-size:12px;color:#88c989;font-weight:700;letter-spacing:2px;margin-bottom:12px">
    🇬🇧 ANGLAIS
  </div>
  <div style="font-size:24px;font-weight:800;color:#e8f5e9">{card['back_en']}</div>
</div>
""",
                    unsafe_allow_html=True,
                )
                with col_know:
                    if st.button(
                        "✅ Je savais",
                        key=f"dial-fc-ok-{sid}-{fc_idx}",
                        use_container_width=True,
                        type="primary",
                    ):
                        score["correct"] += 1
                        score["total"] += 1
                        st.session_state[fc_score_key] = score
                        _advance_flashcard(sid, fc_idx, total_fc, fc_idx_key, fc_revealed_key)
                        st.rerun()
                with col_no:
                    if st.button(
                        "❌ À revoir",
                        key=f"dial-fc-no-{sid}-{fc_idx}",
                        use_container_width=True,
                    ):
                        score["total"] += 1
                        st.session_state[fc_score_key] = score
                        _advance_flashcard(sid, fc_idx, total_fc, fc_idx_key, fc_revealed_key)
                        st.rerun()

            # Navigation
            st.markdown("---")
            nav_p, nav_c, nav_n = st.columns([1, 2, 1])
            with nav_p:
                if st.button(
                    "← Précédente",
                    key=f"dial-fc-prev-{sid}-{fc_idx}",
                    disabled=fc_idx == 0,
                    use_container_width=True,
                ):
                    st.session_state[fc_idx_key] = fc_idx - 1
                    st.session_state[fc_revealed_key] = False
                    st.rerun()
            with nav_c:
                if st.button(
                    "🔄 Recommencer les flashcards",
                    key=f"dial-fc-reset-{sid}",
                    use_container_width=True,
                ):
                    st.session_state[fc_idx_key] = 0
                    st.session_state[fc_revealed_key] = False
                    st.session_state[fc_score_key] = {"correct": 0, "total": 0}
                    st.rerun()
            with nav_n:
                if st.button(
                    "Suivante →",
                    key=f"dial-fc-next-{sid}-{fc_idx}",
                    disabled=fc_idx >= total_fc - 1,
                    use_container_width=True,
                    type="primary",
                ):
                    st.session_state[fc_idx_key] = fc_idx + 1
                    st.session_state[fc_revealed_key] = False
                    st.rerun()


def _advance_flashcard(sid, current_idx, total, idx_key, revealed_key):
    if current_idx < total - 1:
        st.session_state[idx_key] = current_idx + 1
    st.session_state[revealed_key] = False


# ── Main entry point ──────────────────────────────────────────────────────────


def render_michel_thomas_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Méthode Michel Thomas — Construction progressive de phrases")
    st.caption(f"Profil actif : {profile.get('name', 'Profil principal')}")

    tab_ia, tab_perf, tab_dial = st.tabs(
        ["🤖 Session IA", "🎯 Perfectionnement CD 8–11", "📚 Leçons & Dialogues"]
    )

    with tab_ia:
        _render_mt_ia_tab(profile, profile_id)

    with tab_perf:
        _render_mt_perfectionnement_tab(profile, profile_id)

    with tab_dial:
        _render_mt_dialogue_tab(profile, profile_id)
