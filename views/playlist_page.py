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
from modules.stories import _collect_tracks_for_slug, _render_audio_player
from modules.utils import *
from modules.vocabulary import *


def render_playlist_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Playlist audio — écoute en continu")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    playlist_level_default = get_profile_module_level(profile, "playlist")
    playlist_level = st.selectbox(
        "Filtrer par niveau",
        ["Tous"] + CEFR_LEVELS,
        index=0,
        key=f"playlist-level-{profile_id}",
    )
    if playlist_level in CEFR_LEVELS and playlist_level != playlist_level_default:
        set_profile_module_level(profile_id, "playlist", playlist_level)

    mode = st.radio(
        "Mode d'écoute",
        ["Un seul thème (tous niveaux)", "Mélange de thèmes"],
        horizontal=True,
        key="pl-mode",
    )

    tracks = []

    if mode == "Un seul thème (tous niveaux)":
        col_cat, col_theme = st.columns([1, 2])
        with col_cat:
            category = st.selectbox(
                "Catégorie", list(THEME_CATEGORIES.keys()), key="pl-cat"
            )
        with col_theme:
            filtered = [t for t in THEME_CATEGORIES[category] if t in ESSENTIAL_THEMES]
            theme_name = st.selectbox("Thème", filtered, key="pl-theme")

        tracks = _collect_tracks_for_slug(
            slugify(theme_name),
            theme_name,
            profile_id=profile_id,
            level_filter=playlist_level,
        )

        if not tracks:
            st.warning(
                f"Aucun audio généré pour **{theme_name}** (tous niveaux confondus). "
                "Rendez-vous dans **Leçons** pour générer les audios."
            )
            return

        st.success(f"{len(tracks)} audio(s) disponible(s) pour **{theme_name}**.")
        _render_audio_player(tracks, theme_name)

    else:  # Mélange de thèmes
        all_themes = list(ESSENTIAL_THEMES.keys())
        selected_themes = st.multiselect(
            "Thèmes à inclure dans la playlist",
            all_themes,
            key="pl-mix-themes",
            placeholder="Sélectionnez un ou plusieurs thèmes...",
        )

        if not selected_themes:
            st.info("Sélectionnez au moins un thème pour construire la playlist.")
            return

        for t in selected_themes:
            found = _collect_tracks_for_slug(
                slugify(t),
                t,
                profile_id=profile_id,
                level_filter=playlist_level,
            )
            tracks.extend(found)

        if not tracks:
            st.warning(
                "Aucun audio trouvé pour les thèmes sélectionnés. "
                "Générez d'abord les audios dans **Leçons**."
            )
            return

        # Summary per theme
        counts = {}
        for t in tracks:
            theme_label = t["label"].split(" · ")[0]
            counts[theme_label] = counts.get(theme_label, 0) + 1
        summary = " | ".join(f"{k}: {v}" for k, v in counts.items())
        st.success(f"{len(tracks)} audio(s) au total — {summary}")
        title_line = f"Mix — {len(selected_themes)} thème(s)"
        _render_audio_player(tracks, title_line)

        title_line = f"Mix — {len(selected_themes)} thème(s)"
        _render_audio_player(tracks, title_line)
