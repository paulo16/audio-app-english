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
from modules.utils import _audio_player_with_repeat
from modules.stories import _cover_image_url

def render_stories_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("📖 Histoires en anglais — écoute & immersion")
    st.write(
        "Génère des histoires complètes en anglais américain sur les thèmes qui te passionnent. "
        "Lis, écoute, et immerge-toi dans le récit."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    # ── Sidebar-style controls ────────────────────────────────────────────────
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Nouvelle histoire")

        category = st.selectbox(
            "Catégorie",
            list(STORY_CATEGORIES.keys()),
            key="story-cat",
        )

        suggestions = STORY_CATEGORIES[category]
        use_suggestion = st.toggle(
            "Utiliser un sujet suggéré", value=True, key="story-use-sug"
        )

        if use_suggestion:
            topic = st.selectbox("Sujet", suggestions, key="story-sug-pick")
        else:
            topic = st.text_input(
                "Ton propre sujet",
                placeholder="ex: The story of Genghis Khan...",
                key="story-custom-topic",
            )

        num_chapters = st.slider("Nombre de chapitres", 3, 6, 4, key="story-chapters")

        story_level_default = get_profile_module_level(profile, "stories")
        cefr_level = st.radio(
            "Niveau",
            CEFR_LEVELS,
            index=CEFR_LEVELS.index(story_level_default),
            horizontal=True,
            key=f"story-cefr-{profile_id}",
        )
        if cefr_level != story_level_default:
            set_profile_module_level(profile_id, "stories", cefr_level)
        badge = CEFR_DESCRIPTORS[cefr_level]["badge"]
        st.caption(f"{badge} — vocabulaire et style adaptés à ce niveau.")

        narrator_label = st.selectbox(
            "Voix narrateur",
            list(STORY_NARRATOR_VOICES.keys()),
            index=5,  # Fable
            key="story-voice",
        )
        narrator_voice = STORY_NARRATOR_VOICES[narrator_label]

        if st.button(
            "✨ Générer l'histoire",
            key="story-gen-btn",
            width="stretch",
            type="primary",
        ):
            if not topic or not topic.strip():
                st.warning("Entre un sujet pour générer l'histoire.")
            else:
                with st.spinner(
                    f"Génération de l'histoire ({num_chapters} chapitres, niveau {cefr_level})..."
                ):
                    story_data, err = generate_story_ai(
                        topic.strip(), category, num_chapters, cefr_level
                    )
                if err:
                    st.error(f"Erreur génération: {err}")
                else:
                    existing_titles = [
                        s["title"].strip().lower() for s in list_saved_stories()
                    ]
                    if story_data["title"].strip().lower() in existing_titles:
                        st.error(
                            f"Une histoire intitulée **{story_data['title']}** existe déjà. Supprime-la ou choisis un autre sujet."
                        )
                    else:
                        save_story(story_data)
                        st.session_state["story_active_id"] = story_data["id"]
                        st.success("Histoire générée !")
                        st.rerun()

        # ── Saved stories list ────────────────────────────────────────────────
        st.divider()
        st.subheader("Histoires sauvegardées")
        saved = list_saved_stories()
        if not saved:
            st.caption("Aucune histoire générée pour l'instant.")
        else:
            for s in saved:
                _cefr = s.get("cefr_level", "")
                label = f"{s.get('category','')[:2]} {s['title']}" + (
                    f" [{_cefr}]" if _cefr else ""
                )
                if st.button(label, key=f"story-load-{s['id']}", width="stretch"):
                    st.session_state["story_active_id"] = s["id"]
                    st.rerun()

    # ── Story display ─────────────────────────────────────────────────────────
    with col_right:
        active_id = st.session_state.get("story_active_id")
        if not active_id:
            st.info("Génère ou sélectionne une histoire pour l'afficher ici.")
            # Show category teaser images
            st.markdown("---")
            cols = st.columns(4)
            teasers = [
                ("🏯", "Manga & Anime", "Epic battles, destiny & honor"),
                ("👑", "Rois & Empires", "Rise and fall of great rulers"),
                ("🌍", "Pays & Nations", "How civilizations were born"),
                ("📜", "Documentaires", "History's greatest events"),
            ]
            for i, (em, name, desc) in enumerate(teasers):
                with cols[i]:
                    st.markdown(
                        f"<div style='text-align:center;padding:16px;background:#1e1e2e;"
                        f"border-radius:12px;'>"
                        f"<div style='font-size:2.5em'>{em}</div>"
                        f"<div style='font-weight:bold;color:#cba6f7;margin:4px 0'>{name}</div>"
                        f"<div style='font-size:.8em;color:#a6adc8'>{desc}</div></div>",
                        unsafe_allow_html=True,
                    )
            return

        story = load_story(active_id)
        if not story:
            st.error("Histoire introuvable.")
            return

        # ── Cover card ────────────────────────────────────────────────────────
        cover_url = _cover_image_url(story.get("cover_prompt", story["title"]))
        if cover_url:
            try:
                st.image(cover_url, width="stretch")
            except Exception:
                pass

        cat_icon = story.get("category", "")[:2]
        story_cefr = story.get("cefr_level", "")
        story_badge = CEFR_DESCRIPTORS.get(story_cefr, {}).get("badge", "")
        st.markdown(
            f"<h2 style='margin-top:8px'>{cat_icon} {story['title']}"
            f"{'&nbsp;&nbsp;<span style=\"font-size:.65em\">' + story_badge + '</span>' if story_badge else ''}</h2>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='color:#a6adc8;font-style:italic'>{story.get('summary','')}</p>",
            unsafe_allow_html=True,
        )

        # Vocabulary highlights
        vocab = story.get("vocabulary", [])
        if vocab:
            with st.expander("📚 Vocabulaire clé"):
                cols_v = st.columns(3)
                for i, word in enumerate(vocab):
                    with cols_v[i % 3]:
                        st.markdown(f"`{word}`")

        st.divider()

        # Delete story button
        if st.button("🗑️ Supprimer cette histoire", key=f"story-del-{active_id}"):
            path = story_path(active_id)
            if os.path.exists(path):
                os.remove(path)
            # Remove audio files
            for ch in story.get("chapters", []):
                ap = story_chapter_audio_path(active_id, ch["number"])
                if os.path.exists(ap):
                    os.remove(ap)
            st.session_state.pop("story_active_id", None)
            st.rerun()

        # ── Chapters ─────────────────────────────────────────────────────────
        for chapter in story.get("chapters", []):
            ch_num = chapter["number"]
            ch_title = chapter["title"]
            ch_content = chapter["content"]

            st.subheader(ch_title)
            st.write(ch_content)

            audio_key = f"story-audio-{active_id}-{ch_num}"

            # Load from disk if not in session_state
            if audio_key not in st.session_state:
                cached = load_story_chapter_audio(active_id, ch_num)
                if cached:
                    st.session_state[audio_key] = cached

            if audio_key in st.session_state:
                _audio_player_with_repeat(
                    st.session_state[audio_key],
                    "audio/wav",
                    key=f"story_{active_id}_{ch_num}",
                )
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button(
                        "🔄 Régénérer audio",
                        key=f"story-regen-{active_id}-{ch_num}",
                        width="stretch",
                    ):
                        with st.spinner(f"Régénération chapitre {ch_num}..."):
                            ab, _mime, err = generate_narrator_tts(
                                ch_content, voice=narrator_voice
                            )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        else:
                            save_story_chapter_audio(active_id, ch_num, ab)
                            st.session_state[audio_key] = ab
                            st.rerun()
                with c2:
                    if st.button(
                        "🗑️ Supprimer audio",
                        key=f"story-del-audio-{active_id}-{ch_num}",
                        width="stretch",
                    ):
                        ap = story_chapter_audio_path(active_id, ch_num)
                        if os.path.exists(ap):
                            os.remove(ap)
                        st.session_state.pop(audio_key, None)
                        st.rerun()
            else:
                if st.button(
                    f"🔊 Générer audio — {ch_title}",
                    key=f"story-gen-audio-{active_id}-{ch_num}",
                    width="stretch",
                ):
                    with st.spinner(
                        f"Synthèse vocale chapitre {ch_num} ({narrator_voice})..."
                    ):
                        ab, _mime, err = generate_narrator_tts(
                            ch_content, voice=narrator_voice
                        )
                    if err:
                        st.error(f"Erreur TTS: {err}")
                    else:
                        save_story_chapter_audio(active_id, ch_num, ab)
                        st.session_state[audio_key] = ab
                        st.rerun()

            st.divider()

