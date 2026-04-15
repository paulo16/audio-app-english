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

def render_history_page():
    profile = get_active_profile()
    st.header("Historique complet des sessions audio")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")
    sessions = load_all_sessions(profile_id=profile.get("id", "default"))
    if not sessions:
        st.info("Aucune session sauvegardee pour le moment.")
        return

    for session_data in sessions:
        with st.expander(
            f"{session_data.get('id')} | {session_data.get('mode')} | {session_data.get('theme')}"
        ):
            st.write(f"Creee le: {session_data.get('created_at', 'N/A')}")
            if session_data.get("evaluation"):
                st.markdown("**Derniere evaluation:**")
                st.markdown(session_data["evaluation"].get("text", ""))

            for turn in session_data.get("turns", []):
                st.markdown(f"**Vous:** {turn.get('user_text', '')}")
                user_audio_path = turn.get("user_audio_path")
                if user_audio_path and os.path.exists(user_audio_path):
                    st.audio(user_audio_path)

                st.markdown(f"**IA:** {turn.get('ai_text', '')}")
                ai_audio_path = turn.get("ai_audio_path")
                if ai_audio_path and os.path.exists(ai_audio_path):
                    st.audio(ai_audio_path)
                st.markdown("---")

