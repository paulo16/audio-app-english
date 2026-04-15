"""English Audio Coach — entry point.

All logic lives in modules/ and pages/.
"""
import streamlit as st
from modules.config import *
from modules.utils import ensure_directories
from modules.profiles import load_profiles, get_active_profile, create_or_update_profile
from modules.ai_client import get_tts_engine, _elevenlabs_quota_ok
from pages.home_page import render_home
from pages.lessons_page import render_lessons_page
from pages.ai_lessons_page import render_ai_lessons_page
from pages.natural_english_page import render_natural_english_page
from pages.real_english_page import render_real_english_page
from pages.stories_page import render_stories_page
from pages.playlist_page import render_playlist_page
from pages.podcast_page import render_podcast_page
from pages.practice_page import render_practice_page, initialize_state
from pages.shadowing_page import render_shadowing_daily_page
from pages.vocabulary_page import render_vocabulary_page
from pages.history_page import render_history_page


def main():
    ensure_directories()
    initialize_state()

    st.set_page_config(page_title="English Audio Coach", layout="wide")
    st.title("English Audio Coach (A1 -> C2)")

    if not OPENROUTER_API_KEY:
        st.error(
            "Ajoutez OPENROUTER_API_KEY dans le fichier .env pour activer les fonctions IA/audio."
        )

    st.sidebar.header("Profil")
    profiles = load_profiles()
    profile_ids = [p["id"] for p in profiles]
    if "profile_gate_passed" not in st.session_state:
        st.session_state["profile_gate_passed"] = False

    current_profile_id = st.session_state.get("active_profile_id", "")
    if current_profile_id not in profile_ids:
        current_profile_id = ""

    selectable_profiles = ["__choose__"] + profile_ids
    if current_profile_id:
        default_choice = current_profile_id
    else:
        default_choice = "__choose__"

    selected_profile_id = st.sidebar.selectbox(
        "Profil actif",
        selectable_profiles,
        index=selectable_profiles.index(default_choice),
        format_func=lambda pid: next(
            (
                f"{p.get('name', pid)} ({p.get('target_cefr', 'B1')})"
                for p in profiles
                if p.get("id") == pid
            ),
            "Choisir un profil...",
        ),
        key="active-profile-required-select",
    )

    if selected_profile_id in profile_ids:
        st.session_state["active_profile_id"] = selected_profile_id
        st.session_state["profile_gate_passed"] = True

    active_profile = None
    if st.session_state.get("profile_gate_passed"):
        active_profile = get_active_profile()
        st.sidebar.caption(
            f"Niveau lecons par defaut: {active_profile.get('target_cefr', 'B1')}"
        )

    with st.sidebar.expander("Ajouter / mettre a jour un profil"):
        st.caption(
            "Profils existants: " + ", ".join(p.get("name", "") for p in profiles)
        )
        with st.form("profile-create-form", clear_on_submit=True):
            new_profile_name = st.text_input("Nom du profil", key="profile-new-name")
            new_profile_level = st.selectbox(
                "Niveau de depart",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index("B1"),
                key="profile-new-level",
            )
            save_profile = st.form_submit_button(
                "Enregistrer le profil",
                width="stretch",
            )

        if save_profile:
            already_exists = any(
                p.get("name", "").lower() == new_profile_name.strip().lower()
                for p in profiles
            )
            created_profile, profile_err = create_or_update_profile(
                new_profile_name,
                target_cefr=new_profile_level,
            )
            if profile_err:
                st.warning(profile_err)
            else:
                st.session_state["active_profile_id"] = created_profile["id"]
                st.session_state["profile_gate_passed"] = True
                if already_exists:
                    st.success(f"Profil mis a jour: {created_profile['name']}")
                else:
                    st.success(f"Profil cree: {created_profile['name']}")
                st.rerun()

    if not st.session_state.get("profile_gate_passed"):
        st.warning("Choisissez un profil pour démarrer l'application.")
        st.stop()

    previous_profile_id = st.session_state.get("last_active_profile_id")
    current_active_profile_id = st.session_state.get("active_profile_id")
    if previous_profile_id and previous_profile_id != current_active_profile_id:
        st.session_state.active_session = None
        for k in list(st.session_state.keys()):
            if k.startswith("flash_") or k.startswith("flash-"):
                del st.session_state[k]
            if k.startswith("vocab_") or k.startswith("vocab-"):
                del st.session_state[k]
            if k.startswith("shadow_") or k.startswith("shadow-"):
                del st.session_state[k]
    st.session_state["last_active_profile_id"] = current_active_profile_id

    st.sidebar.header("Navigation")
    page = st.sidebar.radio(
        "Aller a",
        [
            "Accueil",
            "Lecons (Ecoute)",
            "Lecons basees sur echanges IA",
            "Anglais naturel",
            "Anglais reel (Mini-series)",
            "Histoires",
            "Playlist",
            "Podcasts",
            "Pratique avec l'IA",
            "Shadowing interactif",
            "Vocabulaire & Flashcards",
            "Historique",
        ],
    )

    with st.sidebar.expander("Modeles OpenRouter"):
        st.caption(f"STT: {STT_MODEL}")
        st.caption(f"Chat: {CHAT_MODEL}")
        st.caption(f"Evaluation: {EVAL_MODEL}")
        st.caption(f"TTS: {TTS_MODEL} ({TTS_VOICE})")

    # ── TTS Engine selector ──────────────────────────────────────────────
    with st.sidebar.expander("Moteur TTS"):
        tts_options = ["TTS par defaut (OpenRouter)"]
        if ELEVENLABS_API_KEY:
            tts_options.append("ElevenLabs (voix US naturelles)")
        tts_choice = st.radio(
            "Moteur de synthese vocale",
            tts_options,
            index=0 if get_tts_engine() != "elevenlabs" else 1,
            key="tts_engine_radio",
        )
        if "ElevenLabs" in tts_choice:
            st.session_state["tts_engine"] = "elevenlabs"
            ok, msg = _elevenlabs_quota_ok()
            if ok:
                st.success(msg)
            else:
                st.warning(msg)
        else:
            st.session_state["tts_engine"] = "default"

    if page == "Accueil":
        render_home()
    elif page == "Lecons (Ecoute)":
        render_lessons_page()
    elif page == "Lecons basees sur echanges IA":
        render_ai_lessons_page()
    elif page == "Anglais naturel":
        render_natural_english_page()
    elif page == "Anglais reel (Mini-series)":
        render_real_english_page()
    elif page == "Histoires":
        render_stories_page()
    elif page == "Playlist":
        render_playlist_page()
    elif page == "Podcasts":
        render_podcast_page()
    elif page == "Pratique avec l'IA":
        render_practice_page()
    elif page == "Shadowing interactif":
        render_shadowing_daily_page()
    elif page == "Vocabulaire & Flashcards":
        render_vocabulary_page()
    elif page == "Historique":
        render_history_page()


if __name__ == "__main__":
    main()
