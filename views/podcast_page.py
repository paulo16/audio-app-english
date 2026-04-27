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
from modules.stories import *
from modules.utils import *
from modules.utils import _audio_player_with_repeat
from modules.vocabulary import *


def render_podcast_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("🎙️ Podcasts du jour")
    st.write(
        "3 podcasts générés chaque jour sur vos sujets favoris : "
        "**News, IA, Football, Manga**. "
        "Écoutez-les en anglais américain au niveau de votre profil."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    podcast_level_default = get_profile_module_level(profile, "podcasts", "C1")
    podcast_level = st.radio(
        "Niveau cible podcasts",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(podcast_level_default),
        horizontal=True,
        key=f"podcast-level-{profile_id}",
    )
    if podcast_level != podcast_level_default:
        set_profile_module_level(profile_id, "podcasts", podcast_level)

    col_date, col_dur = st.columns([2, 1])
    with col_date:
        date_selected = st.date_input(
            "Date",
            value=utc_now().date(),
        ).strftime("%Y-%m-%d")
    with col_dur:
        duration = st.slider(
            "Durée cible (min)",
            min_value=5,
            max_value=10,
            value=7,
            help="Durée approximative de chaque podcast",
        )

    interest_filter = st.multiselect(
        "Filtrer par intérêt",
        USER_INTERESTS,
        default=USER_INTERESTS,
    )

    podcast_voice_pair = st.selectbox(
        "Paire de voix (Host A / Host B)",
        list(VOICE_PAIRS.keys()),
        key="podcast_voice_pair",
        index=0,
    )
    podcast_voice_a, podcast_voice_b = VOICE_PAIRS[podcast_voice_pair]

    podcasts = load_podcasts_for_date(date_selected)

    col_gen, col_regen = st.columns([3, 1])
    with col_gen:
        if st.button(
            "🎙️ Générer 3 podcasts du jour",
            type="primary",
            width="stretch",
            disabled=(podcasts is not None),
        ):
            with st.spinner("Génération des 3 podcasts en cours (30-60 secondes)..."):
                generated, err = generate_podcast_scripts(
                    date_selected,
                    USER_INTERESTS,
                    duration_minutes=duration,
                    target_cefr=podcast_level,
                )
            if err:
                st.error(f"Erreur génération podcasts: {err}")
            else:
                save_podcasts_for_date(date_selected, generated)
                st.success("3 podcasts générés et sauvegardés !")
                st.rerun()
    with col_regen:
        if podcasts and st.button("🔄 Régénérer", width="stretch"):
            path = podcast_file_path(date_selected)
            if os.path.exists(path):
                os.remove(path)
            # Clear audio cache keys for this date
            for key in list(st.session_state.keys()):
                if key.startswith(f"podcast-audio-{date_selected}"):
                    del st.session_state[key]
            st.rerun()

    if not podcasts:
        st.info(
            "Aucun podcast pour cette date. Cliquez sur 'Générer 3 podcasts du jour'."
        )
        st.markdown("**Vos centres d'intérêt configurés :**")
        for interest in USER_INTERESTS:
            st.markdown(f"- {interest}")
        return

    displayed = [
        p
        for p in podcasts
        if not interest_filter or p.get("interest") in interest_filter
    ]

    if not displayed:
        st.warning("Aucun podcast correspond à votre filtre.")
        return

    for podcast in displayed:
        pid = podcast.get("id", 1)
        interest = podcast.get("interest", "")
        audio_cache_key = f"podcast-audio-{date_selected}-{pid}"

        # Load from disk into session_state if not already there
        if audio_cache_key not in st.session_state:
            cached = load_podcast_audio_bytes(date_selected, pid)
            if cached:
                st.session_state[audio_cache_key] = {
                    "bytes": cached,
                    "mime": "audio/wav",
                }

        with st.container(border=True):
            col_title, col_badge = st.columns([5, 1])
            with col_title:
                st.subheader(f"🎧 {podcast.get('title', 'Podcast')}")
            with col_badge:
                interest_icons = {
                    "World News & Current Affairs": "🌍",
                    "Artificial Intelligence & Technology": "🤖",
                    "Football (Soccer)": "⚽",
                    "Manga & Anime": "🇯🇵",
                }
                icon = interest_icons.get(interest, "🎙️")
                st.markdown(f"**{icon} {interest}**")

            st.caption(podcast.get("summary", ""))
            st.caption(
                f"⏱️ ~{podcast.get('estimated_minutes', duration)} min  |  {CEFR_DESCRIPTORS.get(podcast_level, {}).get('badge', podcast_level)}  |  📅 {date_selected}"
            )

            if podcast.get("vocabulary_highlights"):
                st.markdown(
                    "**Vocabulaire clé :** "
                    + "  ".join(f"`{v}`" for v in podcast["vocabulary_highlights"])
                )

            with st.expander("📖 Lire le script complet"):
                st.text(podcast.get("script", ""))

            if audio_cache_key in st.session_state:
                _audio_player_with_repeat(
                    st.session_state[audio_cache_key]["bytes"],
                    st.session_state[audio_cache_key]["mime"],
                    key=f"pod_{audio_cache_key}",
                )
                col_regen_pod, col_del_pod = st.columns([1, 1])
                with col_regen_pod:
                    if st.button(
                        "🔄 Régénérer audio",
                        key=f"regen-podcast-audio-{date_selected}-{pid}",
                        width="stretch",
                    ):
                        script = podcast.get("script", "")
                        script_norm = re.sub(r"\bHost A\s*:", "A:", script)
                        script_norm = re.sub(r"\bHost B\s*:", "B:", script_norm)
                        with st.spinner("Régénération audio podcast (2 voix)..."):
                            ab, mime, err = dual_voice_tts_smart(
                                script_norm,
                                podcast_voice_a,
                                podcast_voice_b,
                                language_hint="en",
                            )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        elif ab:
                            save_podcast_audio_bytes(date_selected, pid, ab)
                            st.session_state[audio_cache_key] = {
                                "bytes": ab,
                                "mime": "audio/wav",
                            }
                            st.rerun()
                with col_del_pod:
                    if st.button(
                        "🗑️ Supprimer audio",
                        key=f"del-podcast-audio-{date_selected}-{pid}",
                        width="stretch",
                    ):
                        fname = podcast_audio_file_name(date_selected, pid)
                        path = os.path.join(PODCAST_AUDIO_DIR, fname)
                        if os.path.exists(path):
                            os.remove(path)
                        st.session_state.pop(audio_cache_key, None)
                        st.rerun()
            else:
                if st.button(
                    f"🔊 Générer audio ({podcast_voice_a} / {podcast_voice_b})",
                    key=f"btn-podcast-audio-{date_selected}-{pid}",
                    width="stretch",
                ):
                    script = podcast.get("script", "")
                    script_norm = re.sub(r"\bHost A\s*:", "A:", script)
                    script_norm = re.sub(r"\bHost B\s*:", "B:", script_norm)
                    with st.spinner("Synthèse vocale du podcast (2 voix)..."):
                        ab, mime, err = dual_voice_tts_smart(
                            script_norm,
                            podcast_voice_a,
                            podcast_voice_b,
                            language_hint="en",
                        )
                    if err:
                        st.error(f"Erreur TTS: {err}")
                    elif ab:
                        save_podcast_audio_bytes(date_selected, pid, ab)
                        st.session_state[audio_cache_key] = {
                            "bytes": ab,
                            "mime": "audio/wav",
                        }
                        st.rerun()

            st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# ANGLAIS NATUREL — Phase 2 : combler le fosse avec l'anglais reel
# ═══════════════════════════════════════════════════════════════════════════════

# ANGLAIS NATUREL — Phase 2 : combler le fosse avec l'anglais reel
# ═══════════════════════════════════════════════════════════════════════════════
