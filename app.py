"""English Audio Coach — entry point.

All logic lives in modules/ and views/.
"""

import time

import streamlit as st

from modules.ai_client import (
    _elevenlabs_quota_ok,
    get_last_stt_provider_used,
    get_stt_mode,
    get_stt_provider_options,
    get_tts_engine,
    set_stt_mode,
    transcribe_audio_with_openrouter,
)
from modules.config import *
from modules.profiles import create_or_update_profile, get_active_profile, load_profiles
from modules.utils import ensure_directories
from views.ai_lessons_page import render_ai_lessons_page
from views.history_page import render_history_page
from views.home_page import render_home
from views.lessons_page import render_lessons_page
from views.michel_thomas_page import render_michel_thomas_page
from views.natural_english_page import render_natural_english_page
from views.playlist_page import render_playlist_page
from views.podcast_page import render_podcast_page
from views.practice_page import initialize_state, render_practice_page
from views.real_english_page import render_real_english_page
from views.shadowing_page import render_shadowing_daily_page
from views.stories_page import render_stories_page
from views.vocabulary_page import render_vocabulary_page


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
            "Michel Thomas (Audio + Repetition)",
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

    with st.sidebar.expander("Transcription (STT)"):
        st.caption(
            "Mode Auto par défaut: OpenRouter, puis Google gratuit, puis Whisper local."
        )
        stt_options = get_stt_provider_options()
        stt_labels = [label for _, label in stt_options]
        stt_keys = [key for key, _ in stt_options]

        current_stt_mode = get_stt_mode()
        if current_stt_mode not in stt_keys:
            current_stt_mode = "auto"

        selected_stt_label = st.radio(
            "Choix du moteur STT",
            stt_labels,
            index=stt_keys.index(current_stt_mode),
            key="stt_mode_radio",
        )
        selected_stt_key = stt_keys[stt_labels.index(selected_stt_label)]
        if selected_stt_key != current_stt_mode:
            set_stt_mode(selected_stt_key)

        last_provider = get_last_stt_provider_used()
        if last_provider:
            st.caption(f"Dernier moteur utilise: {last_provider}")

        st.markdown("**Test rapide STT**")
        stt_test_audio = st.audio_input(
            "Enregistre un court message",
            key="stt_test_audio_input",
        )

        if st.button("Tester la transcription", key="stt_test_btn", width="stretch"):
            if not stt_test_audio:
                st.warning("Enregistre d'abord un audio de test.")
            else:
                with st.spinner("Test de transcription en cours..."):
                    test_text, test_err = transcribe_audio_with_openrouter(
                        stt_test_audio.getvalue(),
                        audio_format="wav",
                    )
                if test_err:
                    st.error(f"STT: {test_err}")
                else:
                    provider_now = get_last_stt_provider_used() or "inconnu"
                    st.success(f"Moteur actif: {provider_now}")
                    st.caption(f"Transcription: {test_text}")

        if st.button(
            "Comparer tous les moteurs", key="stt_compare_btn", width="stretch"
        ):
            if not stt_test_audio:
                st.warning("Enregistre d'abord un audio de test.")
            else:
                audio_bytes = stt_test_audio.getvalue()
                providers_to_test = [key for key, _ in stt_options if key != "auto"]
                rows = []

                with st.spinner(
                    "Comparaison STT en cours (OpenRouter / Google / Whisper)..."
                ):
                    for provider_key in providers_to_test:
                        t0 = time.perf_counter()
                        txt, err = transcribe_audio_with_openrouter(
                            audio_bytes,
                            audio_format="wav",
                            preferred_provider=provider_key,
                        )
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        transcript = (txt or "").strip()
                        words = len(transcript.split()) if transcript else 0

                        rows.append(
                            {
                                "moteur": provider_key,
                                "statut": "OK" if not err else "Erreur",
                                "latence_ms": elapsed_ms,
                                "mots": words,
                                "transcription": transcript if transcript else "-",
                                "erreur": err or "-",
                            }
                        )

                st.markdown("**Résultats comparatifs**")
                st.dataframe(rows, use_container_width=True)

                ok_rows = [r for r in rows if r["statut"] == "OK"]
                if ok_rows:
                    # Heuristic: prefer richer transcript first, then faster response.
                    best = sorted(ok_rows, key=lambda r: (-r["mots"], r["latence_ms"]))[
                        0
                    ]
                    st.success(
                        f"Recommandé pour cet audio: {best['moteur']} "
                        f"({best['mots']} mots, {best['latence_ms']} ms)"
                    )
                else:
                    st.error("Aucun moteur n'a réussi la transcription sur cet audio.")

    if page == "Accueil":
        render_home()
    elif page == "Lecons (Ecoute)":
        render_lessons_page()
    elif page == "Lecons basees sur echanges IA":
        render_ai_lessons_page()
    elif page == "Michel Thomas (Audio + Repetition)":
        render_michel_thomas_page()
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
