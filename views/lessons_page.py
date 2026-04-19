import io
import json
import os
import re
import uuid
from datetime import date, datetime, timedelta, timezone

import requests
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit_autorefresh import st_autorefresh

from modules.ai_client import *
from modules.ai_lessons import *
from modules.config import *
from modules.immersion import *
from modules.lessons import *
from modules.lessons import _lesson_source_id
from modules.podcasts import *
from modules.profiles import *
from modules.profiles import _profile_storage_slug
from modules.real_english import *
from modules.sessions import *
from modules.shadowing import *
from modules.stories import *
from modules.utils import *
from modules.utils import _audio_player_with_repeat
from modules.vocabulary import *


def render_lessons_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")
    profile_slug = _profile_storage_slug(profile_id)
    profile_vocab_entries = load_vocab(profile_id=profile_id)
    lesson_sources_done = {
        str(e.get("source_lesson_id"))
        for e in profile_vocab_entries
        if isinstance(e, dict) and e.get("source_lesson_id")
    }

    st.header("Lecons audio: ecouter et repeter")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    # ── Niveau CEFR ──────────────────────────────────────────────────────────
    default_level = profile.get("target_cefr", "B1")
    if default_level not in CEFR_LEVELS:
        default_level = "B1"
    cefr_level = st.radio(
        "Niveau cible",
        CEFR_LEVELS,
        horizontal=True,
        index=CEFR_LEVELS.index(default_level),
        help="Les dialogues seront générés avec le vocabulaire, la grammaire et les chunks adaptés à ce niveau.",
    )
    if cefr_level != default_level:
        update_profile_target_cefr(profile_id, cefr_level)
        st.session_state["active_profile_target_cefr"] = cefr_level

    desc = CEFR_DESCRIPTORS[cefr_level]
    st.markdown(
        f"{desc['badge']} **{desc['label']}** — dialogues calibrés sur ce niveau."
    )

    # ── Catégorie + thème ─────────────────────────────────────────────────────
    col_cat, col_theme = st.columns([1, 2])
    with col_cat:
        category = st.selectbox("Catégorie", list(THEME_CATEGORIES.keys()))
    with col_theme:
        filtered = THEME_CATEGORIES[category]
        # Guard: if somehow filtered themes are missing from ESSENTIAL_THEMES skip them
        filtered = [t for t in filtered if t in ESSENTIAL_THEMES]
        theme_name = st.selectbox("Thème", filtered)
    st.caption(ESSENTIAL_THEMES[theme_name])

    voice_pair_label = st.selectbox(
        "Paire de voix pour les audios (Personne A / Personne B)",
        list(VOICE_PAIRS.keys()),
        key=f"voice-pair-{profile_slug}-{slugify(theme_name)}-{cefr_level}",
    )
    voice_a, voice_b = VOICE_PAIRS[voice_pair_label]

    quick_tab, pack_tab = st.tabs(["10 variations rapides", "Pack 5 x 5 minutes"])

    with quick_tab:
        st.subheader("10 variations entre 2 personnes")
        st.info(
            "**Comment utiliser cette section ?**\n\n"
            "Chaque variation est un mini-dialogue (10-14 lignes) entre deux Americains "
            "dans une situation differente du theme choisi.\n"
            "1. Lisez le dialogue une fois.\n"
            "2. Cliquez **Generer audio US** pour entendre l'accent americain.\n"
            "3. Ecoutez et repetez chaque replique a voix haute (shadowing).\n"
            "4. Recommencez jusqu'a ce que le rythme soit naturel.\n"
            "5. Cliquez **Lecon terminee** pour ajouter automatiquement des flashcards (max 10).\n"
            "**Objectif:** internaliser les chunks, les liaisons et le rythme americain."
        )

        var_cache_key = (
            f"quick-variations-ai-{profile_slug}-{slugify(theme_name)}-{cefr_level}"
        )

        # Load from disk into session_state on first render of this theme+level
        if var_cache_key not in st.session_state:
            saved_vars = load_quick_variations(
                theme_name,
                cefr_level,
                profile_id=profile_id,
            )
            if saved_vars:
                st.session_state[var_cache_key] = saved_vars

        col_btn, col_del = st.columns([3, 1])
        custom_instr_var = st.text_area(
            "Instructions supplementaires (optionnel)",
            value="",
            height=80,
            placeholder="Ex: Inclure du vocabulaire medical, ajouter un contexte professionnel, utiliser des expressions du Sud des USA...",
            key=f"custom-instr-var-{slugify(theme_name)}-{cefr_level}",
        )
        with col_btn:
            if st.button(
                "Generer les 10 variations par IA (dialogues realistes)",
                key=f"gen-variations-{slugify(theme_name)}-{cefr_level}",
            ):
                with st.spinner("Generation des 10 dialogues par IA..."):
                    ai_variations, err = generate_quick_variations_ai(
                        theme_name,
                        cefr_level=cefr_level,
                        custom_instructions=custom_instr_var,
                    )
                if err:
                    st.error(f"Erreur generation variations: {err}")
                else:
                    save_quick_variations(
                        theme_name,
                        ai_variations,
                        cefr_level,
                        profile_id=profile_id,
                    )
                    st.session_state[var_cache_key] = ai_variations
                    st.success("10 variations generees et sauvegardees.")
                    st.rerun()
        with col_del:
            if st.session_state.get(var_cache_key) and st.button(
                "Regenerer", key=f"regen-variations-{slugify(theme_name)}-{cefr_level}"
            ):
                with st.spinner("Regeneration des 10 dialogues par IA..."):
                    ai_variations, err = generate_quick_variations_ai(
                        theme_name,
                        cefr_level=cefr_level,
                        custom_instructions=custom_instr_var,
                    )
                if err:
                    st.error(f"Erreur generation variations: {err}")
                else:
                    save_quick_variations(
                        theme_name,
                        ai_variations,
                        cefr_level,
                        profile_id=profile_id,
                    )
                    st.session_state[var_cache_key] = ai_variations
                    st.success("10 variations regenerees et sauvegardees.")
                    st.rerun()

        variations = st.session_state.get(var_cache_key)
        if not variations:
            st.caption(
                "Cliquez sur le bouton ci-dessus pour obtenir des dialogues realistes generes par IA. "
                "Ils seront adaptes exactement au theme choisi et aux 10 situations."
            )
        else:
            for item in variations:
                with st.expander(item["title"]):
                    # CEFR badge
                    item_level = item.get("cefr_level", cefr_level)
                    badge = CEFR_DESCRIPTORS.get(item_level, {}).get(
                        "badge", item_level
                    )
                    st.markdown(f"**Niveau:** {badge}")
                    if item.get("grammar_focus"):
                        st.markdown(f"**Focus grammaire:** `{item['grammar_focus']}`")
                    st.markdown(
                        "**Chunks cibles:** "
                        + ", ".join(f"`{c}`" for c in item.get("chunk_focus", []))
                    )
                    st.text(item["dialogue"])

                    audio_key = f"quick-audio-{profile_slug}-{slugify(theme_name)}-{cefr_level}-{item['id']}"
                    audio_disk_file = (
                        f"var-{profile_slug}-{slugify(theme_name)}-"
                        f"{cefr_level.lower()}-{item['id']}.wav"
                    )

                    # Load from disk if not already in session_state
                    if audio_key not in st.session_state:
                        cached = load_lesson_audio(audio_disk_file)
                        if cached:
                            st.session_state[audio_key] = {
                                "bytes": cached,
                                "mime": "audio/wav",
                            }

                    if audio_key in st.session_state:
                        source_lesson_id = _lesson_source_id(
                            "quick",
                            theme_name,
                            cefr_level,
                            item.get("id"),
                        )
                        _audio_player_with_repeat(
                            st.session_state[audio_key]["bytes"],
                            st.session_state[audio_key]["mime"],
                            key=f"rpt_{audio_key}",
                        )
                        col_regen_v, col_del_v, col_done_v = st.columns([1, 1, 1.4])
                        with col_regen_v:
                            if st.button(
                                "🔄 Régénérer",
                                key=f"regen-{audio_key}",
                                width="stretch",
                            ):
                                with st.spinner(
                                    f"Régénération ({voice_a} / {voice_b})..."
                                ):
                                    audio_bytes, mime_type, err = (
                                        generate_dual_voice_tts(
                                            item["dialogue"],
                                            voice_a,
                                            voice_b,
                                            language_hint="en",
                                        )
                                    )
                                if err:
                                    st.error(f"Erreur TTS: {err}")
                                else:
                                    save_lesson_audio(audio_disk_file, audio_bytes)
                                    st.session_state[audio_key] = {
                                        "bytes": audio_bytes,
                                        "mime": mime_type,
                                    }
                                    st.rerun()
                        with col_del_v:
                            if st.button(
                                "🗑️ Supprimer",
                                key=f"del-{audio_key}",
                                width="stretch",
                            ):
                                disk_path = lesson_audio_path(audio_disk_file)
                                if os.path.exists(disk_path):
                                    os.remove(disk_path)
                                st.session_state.pop(audio_key, None)
                                st.rerun()
                        with col_done_v:
                            if source_lesson_id in lesson_sources_done:
                                st.caption("Flashcards deja ajoutees pour cette lecon.")
                            if st.button(
                                "✅ Lecon terminee",
                                key=f"done-{audio_key}",
                                width="stretch",
                            ):
                                added_to_shadowing = register_shadowing_text(
                                    profile_id=profile_id,
                                    source_lesson_id=source_lesson_id,
                                    lesson_kind="quick",
                                    theme_name=theme_name,
                                    dialogue_text=item.get("dialogue", ""),
                                    chunk_focus=item.get("chunk_focus", []),
                                    cefr_level=item.get("cefr_level", cefr_level),
                                    lesson_title=item.get("title", ""),
                                )
                                with st.spinner(
                                    "Ajout automatique des flashcards en arriere-plan..."
                                ):
                                    result = auto_add_lesson_flashcards(
                                        profile_id=profile_id,
                                        source_lesson_id=source_lesson_id,
                                        lesson_kind="quick",
                                        theme_name=theme_name,
                                        dialogue_text=item.get("dialogue", ""),
                                        chunk_focus=item.get("chunk_focus", []),
                                        cefr_level=item.get("cefr_level", cefr_level),
                                        max_cards=LESSON_FLASHCARD_LIMIT,
                                    )
                                if result.get("already_done"):
                                    st.info(
                                        "Les flashcards de cette lecon sont deja presentes."
                                    )
                                    if added_to_shadowing:
                                        st.success(
                                            "Texte ajoute au menu Shadowing interactif quotidien."
                                        )
                                elif result.get("added", 0) > 0:
                                    st.success(
                                        f"{result['added']} flashcards ajoutees (max {LESSON_FLASHCARD_LIMIT})."
                                    )
                                    if added_to_shadowing:
                                        st.success(
                                            "Texte ajoute au menu Shadowing interactif quotidien."
                                        )
                                    if result.get("error") and result.get(
                                        "used_fallback"
                                    ):
                                        st.warning(
                                            "Extraction IA indisponible: fallback applique depuis les chunks de la lecon."
                                        )
                                    st.rerun()
                                elif result.get("error"):
                                    st.error(
                                        f"Erreur ajout flashcards: {result['error']}"
                                    )
                                else:
                                    st.info(
                                        "Aucune nouvelle flashcard ajoutee (deja existantes)."
                                    )
                    else:
                        if st.button(
                            "🔊 Générer audio US (2 voix)",
                            key=f"btn-{audio_key}",
                            width="stretch",
                        ):
                            with st.spinner(
                                f"Generation audio 2 voix ({voice_a} / {voice_b})..."
                            ):
                                audio_bytes, mime_type, err = generate_dual_voice_tts(
                                    item["dialogue"],
                                    voice_a,
                                    voice_b,
                                )
                            if err:
                                st.error(f"Erreur TTS: {err}")
                            else:
                                save_lesson_audio(audio_disk_file, audio_bytes)
                                st.session_state[audio_key] = {
                                    "bytes": audio_bytes,
                                    "mime": mime_type,
                                }
                                st.rerun()

    with pack_tab:
        st.subheader("Pack de 5 conversations longues (~5 min chacune)")
        pack = load_lesson_pack(theme_name, cefr_level, profile_id=profile_id)

        if pack is None:
            st.info(
                "Aucun pack genere pour ce theme/niveau. Cliquez pour le creer avec OpenRouter."
            )
            custom_instr_pack = st.text_area(
                "Instructions supplementaires (optionnel)",
                value="",
                height=80,
                placeholder="Ex: Inclure du vocabulaire medical, ajouter un contexte professionnel, utiliser des expressions du Sud des USA...",
                key=f"custom-instr-pack-{slugify(theme_name)}-{cefr_level}",
            )
            if st.button(
                "Generer le pack complet",
                key=f"pack-{slugify(theme_name)}-{cefr_level}",
            ):
                with st.spinner("Creation de 5 conversations en cours..."):
                    generated, err = generate_five_minute_pack(
                        theme_name,
                        cefr_level=cefr_level,
                        custom_instructions=custom_instr_pack,
                    )
                if err:
                    st.error(f"Erreur generation pack: {err}")
                else:
                    save_lesson_pack(
                        theme_name,
                        generated,
                        cefr_level,
                        profile_id=profile_id,
                    )
                    st.success("Pack genere et sauvegarde.")
                    st.rerun()
        else:
            custom_instr_pack = st.text_area(
                "Instructions supplementaires (optionnel)",
                value="",
                height=80,
                placeholder="Ex: Inclure du vocabulaire medical, ajouter un contexte professionnel, utiliser des expressions du Sud des USA...",
                key=f"custom-instr-pack-regen-{slugify(theme_name)}-{cefr_level}",
            )
            if st.button(
                "Regenerer le pack complet",
                key=f"pack-regen-{slugify(theme_name)}-{cefr_level}",
            ):
                with st.spinner("Regeneration de 5 conversations en cours..."):
                    generated, err = generate_five_minute_pack(
                        theme_name,
                        cefr_level=cefr_level,
                        custom_instructions=custom_instr_pack,
                    )
                if err:
                    st.error(f"Erreur generation pack: {err}")
                else:
                    save_lesson_pack(
                        theme_name,
                        generated,
                        cefr_level,
                        profile_id=profile_id,
                    )
                    st.success("Pack regenere et sauvegarde.")
                    st.rerun()
            for idx, lesson in enumerate(pack, start=1):
                with st.expander(
                    f"Conversation {idx}: {lesson.get('title', 'Untitled')}"
                ):
                    item_level = lesson.get("cefr_level", cefr_level)
                    badge = CEFR_DESCRIPTORS.get(item_level, {}).get(
                        "badge", item_level
                    )
                    st.markdown(f"**Niveau:** {badge}")
                    if lesson.get("grammar_focus"):
                        st.markdown(f"**Focus grammaire:** `{lesson['grammar_focus']}`")
                    st.write(f"Objectif: {lesson.get('objective', 'N/A')}")
                    st.write(
                        f"Duree estimee: {lesson.get('estimated_minutes', 5)} minutes"
                    )
                    st.text(lesson.get("dialogue", ""))

                    btn_key = (
                        f"pack-audio-{profile_slug}-{slugify(theme_name)}-"
                        f"{cefr_level}-{idx}"
                    )
                    audio_disk_file = (
                        f"pack-{profile_slug}-{slugify(theme_name)}-"
                        f"{cefr_level.lower()}-{idx}.wav"
                    )

                    # Load from disk if not already in session_state
                    if btn_key not in st.session_state:
                        cached = load_lesson_audio(audio_disk_file)
                        if cached:
                            st.session_state[btn_key] = {
                                "bytes": cached,
                                "mime": "audio/wav",
                            }

                    if btn_key in st.session_state:
                        source_lesson_id = _lesson_source_id(
                            "pack",
                            theme_name,
                            cefr_level,
                            idx,
                        )
                        _audio_player_with_repeat(
                            st.session_state[btn_key]["bytes"],
                            st.session_state[btn_key]["mime"],
                            key=f"rpt_{btn_key}",
                        )
                        col_regen_p, col_del_p, col_done_p = st.columns([1, 1, 1.4])
                        with col_regen_p:
                            if st.button(
                                "🔄 Régénérer",
                                key=f"regen-{btn_key}",
                                width="stretch",
                            ):
                                with st.spinner(
                                    f"Régénération ({voice_a} / {voice_b})..."
                                ):
                                    audio_bytes, mime_type, err = (
                                        generate_dual_voice_tts(
                                            lesson.get("dialogue", ""),
                                            voice_a,
                                            voice_b,
                                            language_hint="en",
                                        )
                                    )
                                if err:
                                    st.error(f"Erreur TTS: {err}")
                                else:
                                    save_lesson_audio(audio_disk_file, audio_bytes)
                                    st.session_state[btn_key] = {
                                        "bytes": audio_bytes,
                                        "mime": mime_type,
                                    }
                                    st.rerun()
                        with col_del_p:
                            if st.button(
                                "🗑️ Supprimer",
                                key=f"del-{btn_key}",
                                width="stretch",
                            ):
                                disk_path = lesson_audio_path(audio_disk_file)
                                if os.path.exists(disk_path):
                                    os.remove(disk_path)
                                st.session_state.pop(btn_key, None)
                                st.rerun()
                        with col_done_p:
                            if source_lesson_id in lesson_sources_done:
                                st.caption("Flashcards deja ajoutees pour cette lecon.")
                            if st.button(
                                "✅ Lecon terminee",
                                key=f"done-{btn_key}",
                                width="stretch",
                            ):
                                added_to_shadowing = register_shadowing_text(
                                    profile_id=profile_id,
                                    source_lesson_id=source_lesson_id,
                                    lesson_kind="pack",
                                    theme_name=theme_name,
                                    dialogue_text=lesson.get("dialogue", ""),
                                    chunk_focus=lesson.get("chunk_focus", []),
                                    cefr_level=lesson.get("cefr_level", cefr_level),
                                    lesson_title=lesson.get("title", ""),
                                )
                                with st.spinner(
                                    "Ajout automatique des flashcards en arriere-plan..."
                                ):
                                    result = auto_add_lesson_flashcards(
                                        profile_id=profile_id,
                                        source_lesson_id=source_lesson_id,
                                        lesson_kind="pack",
                                        theme_name=theme_name,
                                        dialogue_text=lesson.get("dialogue", ""),
                                        chunk_focus=lesson.get("chunk_focus", []),
                                        cefr_level=lesson.get("cefr_level", cefr_level),
                                        max_cards=LESSON_FLASHCARD_LIMIT,
                                    )
                                if result.get("already_done"):
                                    st.info(
                                        "Les flashcards de cette lecon sont deja presentes."
                                    )
                                    if added_to_shadowing:
                                        st.success(
                                            "Texte ajoute au menu Shadowing interactif quotidien."
                                        )
                                elif result.get("added", 0) > 0:
                                    st.success(
                                        f"{result['added']} flashcards ajoutees (max {LESSON_FLASHCARD_LIMIT})."
                                    )
                                    if added_to_shadowing:
                                        st.success(
                                            "Texte ajoute au menu Shadowing interactif quotidien."
                                        )
                                    if result.get("error") and result.get(
                                        "used_fallback"
                                    ):
                                        st.warning(
                                            "Extraction IA indisponible: fallback applique depuis les chunks de la lecon."
                                        )
                                    st.rerun()
                                elif result.get("error"):
                                    st.error(
                                        f"Erreur ajout flashcards: {result['error']}"
                                    )
                                else:
                                    st.info(
                                        "Aucune nouvelle flashcard ajoutee (deja existantes)."
                                    )
                    else:
                        if st.button(
                            "🔊 Générer audio US (2 voix)",
                            key=f"btn-{btn_key}",
                            width="stretch",
                        ):
                            with st.spinner(
                                f"Generation audio 2 voix ({voice_a} / {voice_b})..."
                            ):
                                audio_bytes, mime_type, err = generate_dual_voice_tts(
                                    lesson.get("dialogue", ""),
                                    voice_a,
                                    voice_b,
                                    language_hint="en",
                                )
                            if err:
                                st.error(f"Erreur TTS: {err}")
                            else:
                                save_lesson_audio(audio_disk_file, audio_bytes)
                                st.session_state[btn_key] = {
                                    "bytes": audio_bytes,
                                    "mime": mime_type,
                                }
                                st.rerun()
