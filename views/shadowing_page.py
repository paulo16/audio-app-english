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
from modules.config import *
from modules.immersion import *
from modules.lessons import *
from modules.podcasts import *
from modules.profiles import *
from modules.real_english import *
from modules.sessions import *
from modules.shadowing import *
from modules.shadowing import (
    _audio_duration_seconds,
    _render_shadowing_phrase_detail,
    _shadowing_day_entry_to_state,
    _shadowing_mismatch_feedback,
    _shadowing_record_seconds,
    _shadowing_records_summary,
    _shadowing_score_label,
    _shadowing_score_scales,
    _split_shadowing_chunks,
)
from modules.stories import *
from modules.utils import *
from modules.utils import _audio_player_with_repeat
from modules.vocabulary import *


def render_shadowing_daily_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Shadowing interactif quotidien")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    texts = load_shadowing_texts(profile_id)
    if not texts:
        st.info(
            "Aucun texte disponible pour le shadowing. "
            "Dans Lecons (Ecoute), termine une lecon pour alimenter ce menu."
        )
        return

    # ── Choice: daily random or manual pick ────────────────────────────────
    mode_key = f"shadow-mode-{profile_id}"
    mode = st.radio(
        "Mode de selection",
        ["Texte du jour (automatique)", "Choisir une lecon"],
        horizontal=True,
        key=mode_key,
    )

    texts_by_id = {str(t.get("source_id")): t for t in texts if t.get("source_id")}

    if mode == "Choisir une lecon":
        labels = {}
        for t in texts:
            sid = str(t.get("source_id", ""))
            title = str(t.get("lesson_title") or t.get("theme_name") or sid)
            level = str(t.get("cefr_level", ""))
            labels[sid] = f"{title} ({level})" if level else title

        chosen_sid = st.selectbox(
            "Lecon a travailler",
            list(labels.keys()),
            format_func=lambda sid: labels.get(sid, sid),
            key=f"shadow-pick-{profile_id}",
        )
        if chosen_sid not in texts_by_id:
            st.warning("Lecon introuvable.")
            return
        chosen_text = texts_by_id[chosen_sid]
        day_key = utc_now().date().isoformat()
    else:
        chosen_text, day_key = pick_daily_shadowing_text(profile_id, texts)
        if not chosen_text:
            st.warning("Impossible de selectionner un texte du jour.")
            return

    daily_text = chosen_text

    assignments = load_shadowing_daily_assignments()
    profile_map = assignments.get(profile_id, {})
    if not isinstance(profile_map, dict):
        profile_map = {}
    day_state = _shadowing_day_entry_to_state(profile_map.get(day_key))
    completed_today_ids = [
        sid for sid in day_state.get("completed_source_ids", []) if str(sid).strip()
    ]

    if completed_today_ids:
        with st.expander("Textes deja valides aujourd'hui", expanded=False):
            shown_ids = list(reversed(completed_today_ids[-10:]))
            for sid in shown_ids:
                item = texts_by_id.get(str(sid), {})
                title = str(item.get("lesson_title") or item.get("theme_name") or sid)
                runs = get_shadowing_run_history(profile_id, day_key, sid)
                last_run = runs[-1] if runs else {}
                avg_score = float(last_run.get("avg_score", 0) or 0)
                scales = _shadowing_score_scales(avg_score)
                st.markdown(
                    f"- {title}: **{scales['on_100']}/100** "
                    f"({scales['on_20']}/20, {scales['on_10']}/10)"
                )

    source_id = str(daily_text.get("source_id", ""))
    full_text = str(daily_text.get("dialogue_text", "")).strip()
    chunks = daily_text.get("chunks") or _split_shadowing_chunks(full_text)
    if not chunks:
        st.warning("Le texte du jour ne contient pas de phrases exploitables.")
        return

    text_title = str(
        daily_text.get("lesson_title") or daily_text.get("theme_name") or "N/A"
    )
    st.markdown(f"### {text_title}")
    st.caption(
        f"Date: {day_key} | Theme: {daily_text.get('theme_name', 'N/A')} | "
        f"Niveau: {daily_text.get('cefr_level', 'B1')}"
    )
    st.text(full_text)

    voice_label = st.selectbox(
        "Voix pour les phrases",
        list(STORY_NARRATOR_VOICES.keys()),
        index=0,
        key=f"shadowing-voice-{profile_id}",
    )
    voice = STORY_NARRATOR_VOICES.get(voice_label, "alloy")

    records = get_shadowing_session_records(profile_id, day_key, source_id)
    next_idx = get_next_shadowing_chunk_index(records, len(chunks))
    scores = [int(r.get("score", 0)) for r in records]
    avg_score_100 = round(sum(scores) / len(scores), 1) if scores else 0
    avg_scales = _shadowing_score_scales(avg_score_100)
    source_slug = slugify(source_id)
    run_history = get_shadowing_run_history(profile_id, day_key, source_id)

    m1, m2, m3 = st.columns(3)
    m1.metric("Phrases total", len(chunks))
    m2.metric("Phrases notees", len(records))
    m3.metric("Moyenne (/100)", avg_scales["on_100"])
    st.caption(
        f"La note principale est sur /100. Les formats /20 et /10 sont la meme note convertie "
        f"({avg_scales['on_20']}/20 et {avg_scales['on_10']}/10)."
    )

    with st.expander("Comment la note est calculee", expanded=False):
        st.markdown(
            "- Une seule note de base est calculee par phrase: **qualite de repetition sur 100**.\n"
            "- Cette qualite repose sur la **fidelite au texte cible** et la **fluidite**.\n"
            "- Le mode actuel est **sans chrono**: tu peux envoyer quand tu veux.\n"
            "- Les formats **/20** et **/10** sont juste des conversions de la note /100.\n"
            "- Reperes rapides: 85-100 tres bon, 70-84 bon, 55-69 moyen, <55 a retravailler."
        )

    # ── Helper: render recommencer + run history ──
    def _render_recommencer_and_history():
        if st.button(
            "Recommencer ce texte (garder mon historique)",
            key=f"shadow-restart-{profile_id}-{day_key}-{source_slug}",
            width="stretch",
        ):
            reset_shadowing_session_keep_history(
                profile_id=profile_id,
                day_key=day_key,
                source_id=source_id,
                chunk_count=len(chunks),
            )
            state_prefix = f"shadow-{profile_id}-{day_key}-{source_slug}-"
            for state_key in list(st.session_state.keys()):
                if str(state_key).startswith(state_prefix):
                    st.session_state.pop(state_key, None)
            st.session_state.pop("shadow_last_autoplay_chunk", None)
            st.rerun()

        if run_history:
            with st.expander("Historique de mes tentatives", expanded=False):
                shown = list(reversed(run_history[-10:]))
                for i, run in enumerate(shown, start=1):
                    archived_at = str(run.get("archived_at", ""))
                    archived_label = (
                        archived_at.replace("T", " ")[:19] if archived_at else "N/A"
                    )
                    avg_s = run.get("avg_score", 0)
                    avg_sc = _shadowing_score_scales(avg_s)
                    avg_lb = _shadowing_score_label(avg_s)
                    pdone = int(run.get("phrases_done", 0))
                    cc = int(run.get("chunk_count", len(chunks)))
                    st.markdown(
                        f"- Tentative {i} ({archived_label}) - moyenne: **{avg_sc['on_100']}/100** "
                        f"({avg_sc['on_20']}/20, {avg_sc['on_10']}/10) "
                        f"- {avg_lb} ({pdone}/{cc} phrases)"
                    )

    # ── Session complete: full-width detail ──
    if next_idx >= len(chunks):
        if records:
            with st.expander("Detail par phrase", expanded=True):
                _render_shadowing_phrase_detail(records)

        _render_recommencer_and_history()

        completed_summary = _shadowing_records_summary(records, len(chunks))
        avg_done = float(completed_summary.get("avg_score", 0) or 0)
        if maybe_advance_shadowing_daily_text(
            profile_id=profile_id,
            day_key=day_key,
            source_id=source_id,
            texts=texts,
            avg_score=avg_done,
        ):
            st.success(
                "Bravo, moyenne >= 80/100. Nouveau texte charge pour aujourd'hui; "
                "le precedent a ete historise."
            )
            st.session_state.pop("shadow_last_autoplay_chunk", None)
            st.rerun()

        st.success(
            "Session du jour terminee. Demain, un autre texte sera propose automatiquement."
        )
        return

    # ── Session in progress: side-by-side layout ──
    current_chunk = str(chunks[next_idx]).strip()
    record_limit = _shadowing_record_seconds(current_chunk)

    col_active, col_detail = st.columns([3, 2])

    with col_active:
        st.markdown("### Shadowing actif")
        st.markdown(f"**Phrase {next_idx + 1} / {len(chunks)}**")
        st.write(current_chunk)
        st.caption(
            "Mode libre: pas de chrono. "
            "Repete la phrase puis envoie quand tu es pret."
        )

        chunk_audio_path, audio_err = ensure_shadowing_chunk_audio(
            profile_id=profile_id,
            source_id=source_id,
            chunk_idx=next_idx,
            chunk_text=current_chunk,
            voice=voice,
        )
        if audio_err:
            st.warning(f"Audio phrase indisponible: {audio_err}")
        elif chunk_audio_path and os.path.exists(chunk_audio_path):
            autoplay_chunk_marker = f"{profile_id}:{day_key}:{source_id}:{next_idx}"
            autoplay_state_key = "shadow_last_autoplay_chunk"
            if st.session_state.get(autoplay_state_key) != autoplay_chunk_marker:
                try:
                    with open(chunk_audio_path, "rb") as _af:
                        _ab64 = base64.b64encode(_af.read()).decode("utf-8")
                    st.html(
                        (
                            '<audio id="shadow_autoplay" autoplay style="display:none">'
                            f'<source src="data:audio/wav;base64,{_ab64}">'
                            "</audio>"
                            "<script>"
                            "(function(){"
                            '  var a=document.getElementById("shadow_autoplay");'
                            '  if(a && "mediaSession" in navigator){'
                            '    navigator.mediaSession.metadata=new MediaMetadata({title:"Shadowing",artist:"AI Tutor",album:"Shadowing Session"});'
                            '    navigator.mediaSession.playbackState="playing";'
                            '    a.addEventListener("pause",function(){navigator.mediaSession.playbackState="paused";});'
                            '    a.addEventListener("play",function(){navigator.mediaSession.playbackState="playing";});'
                            "  }"
                            "})();"
                            "</script>"
                        ),
                        unsafe_allow_javascript=True,
                    )
                    st.session_state[autoplay_state_key] = autoplay_chunk_marker
                except Exception:
                    pass
            with open(chunk_audio_path, "rb") as _af:
                _audio_player_with_repeat(
                    _af.read(), "audio/wav", key=f"shd_{source_slug}_{next_idx}"
                )

        run_key = f"shadow-{profile_id}-{day_key}-{source_slug}-{next_idx}"
        blob_key = f"{run_key}-blob"
        widget_key = f"{run_key}-widget"

        # ── Audio input FIRST so bytes are captured before button click ──
        fmt_key = f"{run_key}-fmt"
        user_audio_widget = st.audio_input(
            "Enregistre ta repetition ici",
            key=widget_key,
        )
        if user_audio_widget is not None:
            raw_bytes = user_audio_widget.getvalue()
            if raw_bytes and len(raw_bytes) > 44:
                st.session_state[blob_key] = raw_bytes
                # Detect format from widget MIME type
                mime = getattr(user_audio_widget, "type", "") or ""
                if "webm" in mime:
                    st.session_state[fmt_key] = "webm"
                elif "ogg" in mime:
                    st.session_state[fmt_key] = "ogg"
                elif "mp3" in mime or "mpeg" in mime:
                    st.session_state[fmt_key] = "mp3"
                else:
                    st.session_state[fmt_key] = "wav"

        has_audio = bool(st.session_state.get(blob_key))
        if has_audio:
            st.success("Audio capture - pret a envoyer!", icon="✅")

        def _finalize_chunk():
            audio_bytes = st.session_state.get(blob_key)
            audio_fmt = st.session_state.get(fmt_key, "wav")
            if not audio_bytes:
                w = st.session_state.get(widget_key)
                if w is not None:
                    try:
                        raw = w.getvalue()
                        if raw and len(raw) > 44:
                            audio_bytes = raw
                            mime = getattr(w, "type", "") or ""
                            if "webm" in mime:
                                audio_fmt = "webm"
                            elif "ogg" in mime:
                                audio_fmt = "ogg"
                    except Exception:
                        audio_bytes = None
            duration_sec = 0.0
            user_text = ""
            score = 0
            feedback = ""

            if audio_bytes:
                duration = _audio_duration_seconds(audio_bytes)
                if duration is not None:
                    duration_sec = float(duration)

                with st.spinner("Transcription et notation..."):
                    user_text, stt_err = transcribe_audio_with_openrouter(
                        audio_bytes,
                        audio_format=audio_fmt,
                    )
                if stt_err:
                    score = 30
                    feedback = f"Transcription indisponible: {stt_err}"
                    user_text = ""
                else:
                    eval_data = evaluate_shadowing_chunk(
                        current_chunk,
                        user_text,
                        cefr_level=daily_text.get("cefr_level", "B1"),
                    )
                    score = int(eval_data.get("score", 0))
                    feedback = str(eval_data.get("feedback", "")).strip()
                    mismatch_msg = _shadowing_mismatch_feedback(
                        current_chunk, user_text
                    )
                    if mismatch_msg:
                        feedback = (
                            f"{feedback} {mismatch_msg}".strip()
                            if feedback
                            else mismatch_msg
                        )
            else:
                score = 0
                feedback = (
                    "Aucun audio detecte. Enregistre d'abord puis clique Envoyer."
                )

            save_shadowing_chunk_result(
                profile_id=profile_id,
                day_key=day_key,
                source_id=source_id,
                chunk_idx=next_idx,
                chunk_text=current_chunk,
                score=score,
                feedback=feedback,
                user_text=user_text,
                duration_sec=duration_sec,
                chunk_count=len(chunks),
            )

            st.session_state.pop(blob_key, None)
            st.session_state.pop(widget_key, None)
            st.session_state.pop(fmt_key, None)
            st.rerun()

        btn1, btn2 = st.columns(2)
        with btn1:
            send_disabled = not has_audio
            if st.button(
                "Envoyer maintenant",
                key=f"{run_key}-send-btn",
                width="stretch",
                disabled=send_disabled,
            ):
                _finalize_chunk()
        with btn2:
            if st.button("Passer", key=f"{run_key}-skip-btn", width="stretch"):
                save_shadowing_chunk_result(
                    profile_id=profile_id,
                    day_key=day_key,
                    source_id=source_id,
                    chunk_idx=next_idx,
                    chunk_text=current_chunk,
                    score=0,
                    feedback="Phrase passee manuellement.",
                    user_text="",
                    duration_sec=0.0,
                    chunk_count=len(chunks),
                )
                st.session_state.pop(blob_key, None)
                st.session_state.pop(widget_key, None)
                st.session_state.pop(fmt_key, None)
                st.rerun()

        if not has_audio:
            st.info("Enregistre ton audio ci-dessus, puis clique Envoyer.")

    with col_detail:
        st.markdown("### Resultats phrase par phrase")
        # Reload records from disk to reflect the latest save
        records_fresh = get_shadowing_session_records(profile_id, day_key, source_id)
        detail_container = st.container(height=500)
        with detail_container:
            if records_fresh:
                _render_shadowing_phrase_detail(records_fresh)
            else:
                st.info("Les resultats apparaitront ici au fur et a mesure.")

    # ── Recommencer + run history (full width, below columns) ──
    _render_recommencer_and_history()
