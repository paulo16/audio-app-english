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
from modules.real_english import (_list_real_english_lessons,
                                  _load_real_english_lesson,
                                  _load_real_english_progress,
                                  _mark_real_english_lesson_completed,
                                  _real_english_lesson_path,
                                  _save_real_english_lesson,
                                  _save_real_english_progress)
from modules.sessions import *
from modules.shadowing import *
from modules.stories import *
from modules.utils import *
from modules.utils import _audio_player_with_repeat
from modules.vocabulary import *


def render_real_english_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Lecons Anglais Reel — Mini-series americaines")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")
    st.info(
        "Ce module vous plonge dans **l'anglais americain de tous les jours** "
        "a travers des mini-series de la vie quotidienne. Chaque episode est un dialogue "
        "authentique avec du slang, des contractions et le rythme reel des conversations "
        "americaines — exactement ce que vous entendez dans les films et series."
    )

    progress = _load_real_english_progress(profile_id)
    all_lessons = _list_real_english_lessons(profile_id)

    tab_episodes, tab_listen, tab_vocab, tab_shadow, tab_progress = st.tabs(
        [
            "Episodes & Dialogues",
            "Ecouter la scene",
            "Vocabulaire, Chunks & Idioms",
            "Pratiquer (Shadowing)",
            "Ma progression",
        ]
    )

    # ── Tab 1: Episodes — Generate/browse mini-series ──────────────────────
    with tab_episodes:
        st.subheader("Choisissez une mini-serie et un episode")

        default_level = profile.get("target_cefr", "B1")
        if default_level not in CEFR_LEVELS:
            default_level = "B1"
        re_level = st.radio(
            "Niveau CEFR",
            CEFR_LEVELS,
            horizontal=True,
            index=CEFR_LEVELS.index(default_level),
            key="re_level",
        )

        series_names = list(REAL_ENGLISH_SERIES.keys())
        series_labels = [f"{REAL_ENGLISH_SERIES[s]['icon']} {s}" for s in series_names]
        selected_idx = st.selectbox(
            "Mini-serie",
            range(len(series_names)),
            format_func=lambda i: series_labels[i],
            key="re_series",
        )
        selected_series = series_names[selected_idx]
        series_info = REAL_ENGLISH_SERIES[selected_series]

        st.caption(series_info["description"])

        episodes = series_info["episodes"]
        selected_episode = st.selectbox(
            "Episode",
            episodes,
            key="re_episode",
        )

        # Check if this episode already exists
        episode_id = slugify(f"{selected_series}-{selected_episode}-{re_level}")

        existing_lesson = _load_real_english_lesson(profile_id, episode_id)
        is_completed = episode_id in progress.get("completed_lessons", [])

        if existing_lesson:
            st.success(
                "Cet episode est deja genere. Naviguez dans les onglets pour l'explorer."
            )
            if is_completed:
                st.markdown("✅ **Lecon terminee**")
            st.session_state["re_current_lesson"] = existing_lesson
            st.session_state["re_current_lesson_id"] = episode_id
        else:
            st.session_state.pop("re_current_lesson", None)
            st.session_state.pop("re_current_lesson_id", None)

        # ── Load saved lessons browser ───────────────────────────────
        if all_lessons:
            with st.expander(
                f"Mes episodes generes ({len(all_lessons)})", expanded=False
            ):
                for li, lesson in enumerate(all_lessons):
                    lid = lesson.get("id", "")
                    title = lesson.get("episode", "?")
                    series = lesson.get("series", "?")
                    level = lesson.get("level", "?")
                    done = lid in progress.get("completed_lessons", [])
                    icon = "✅" if done else "📺"
                    date = lesson.get("saved", "")[:10]
                    col_load, col_del = st.columns([4, 1])
                    with col_load:
                        if st.button(
                            f"{icon} {date} — {series} — {title} ({level})",
                            key=f"re_load_{li}",
                        ):
                            st.session_state["re_current_lesson"] = lesson
                            st.session_state["re_current_lesson_id"] = lid
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"re_del_{li}"):
                            path = _real_english_lesson_path(profile_id, lid)
                            if os.path.exists(path):
                                os.remove(path)
                            # Remove audio (both formats)
                            for ext in (".wav", ".mp3"):
                                audio_path = os.path.join(
                                    REAL_ENGLISH_AUDIO_DIR, f"{lid}{ext}"
                                )
                                if os.path.exists(audio_path):
                                    os.remove(audio_path)
                            if lid in progress.get("completed_lessons", []):
                                progress["completed_lessons"].remove(lid)
                                _save_real_english_progress(profile_id, progress)
                            if st.session_state.get("re_current_lesson_id") == lid:
                                st.session_state.pop("re_current_lesson", None)
                                st.session_state.pop("re_current_lesson_id", None)
                            st.rerun()

        custom_instr_re = st.text_area(
            "Instructions supplementaires (optionnel)",
            value="",
            height=80,
            placeholder="Ex: La scene se passe dans un bar sportif, inclure de l'argot californien, ajouter une dispute amicale...",
            key="re-custom-instr",
        )

        if st.button("Generer cet episode", key="re_generate"):
            with st.spinner("L'IA ecrit un dialogue authentique..."):
                level_instr = REAL_ENGLISH_LEVEL_INSTRUCTIONS.get(re_level, "")
                prompt = (
                    f"You are a scriptwriter for an American TV show. Write a REALISTIC, "
                    f"natural American English dialogue for this scene:\n\n"
                    f'Series: "{selected_series}"\n'
                    f'Episode scenario: "{selected_episode}"\n'
                    f"CEFR level for the learner: {re_level}\n\n"
                    f"Language level instructions: {level_instr}\n\n"
                    f"CRITICAL RULES — READ CAREFULLY:\n"
                    f"- This is NOT a textbook. NEVER write formal/academic English.\n"
                    f"- Write EXACTLY how Americans ACTUALLY speak in daily life.\n"
                    f"- Characters MUST use: gonna, wanna, gotta, kinda, dunno and other reductions.\n"
                    f"- Characters MUST use American idioms, chunks, and phrasal verbs — NOT single words.\n"
                    f"- Include filler words: like, you know, I mean, basically, honestly, um, right?\n"
                    f"- Include reactions: No way!, Seriously?, Dude!, Come on!, Oh my God!\n"
                    f"- Include interrupted sentences, self-corrections, and trailing off.\n"
                    f"- Greetings: Hey! / What's up? / How's it goin'? (NEVER 'Hello, how are you?')\n"
                    f"- 10-16 lines between 2 characters with American names\n"
                    f"- Keep the dialogue SHORT and PUNCHY — like a real quick conversation, not a screenplay.\n"
                    f"- Include [stage directions] for tone/action\n"
                    f"- Mini-story with beginning, middle, and end\n"
                    f"- If someone would say 'going to' in real life, write 'gonna' instead.\n"
                    f"- If someone would say 'want to', write 'wanna'. Same for gotta, kinda, etc.\n"
                    f"- EVERY line should sound like something you'd hear in Friends, The Office, or a podcast.\n\n"
                    f"DIALOGUE FORMAT RULES (VERY IMPORTANT):\n"
                    f"- Use ONLY 'A:' and 'B:' as speaker labels in the dialogue text.\n"
                    f"- NEVER write character names before each line (e.g. 'Jake: ...' is WRONG).\n"
                    f"- Use 'A:' for the first speaker and 'B:' for the second speaker.\n"
                    f"- Put the actual character names ONLY in the 'characters' field of the JSON.\n"
                    f"- Example: 'A: Hey, what's up?\\nB: Not much, just chillin'.' (CORRECT)\n"
                    f"- Example: 'Jake: Hey, what's up?\\nMike: Not much.' (WRONG — names will be read aloud by TTS)\n\n"
                    f"After the dialogue, provide:\n"
                    f"1. KEY_VOCABULARY: 6-10 important informal expressions, chunks, phrasal verbs, "
                    f"idioms, and reductions used in the dialogue. For each give: the expression, "
                    f"its standard/full form, the French translation, and the type "
                    f"(chunk/idiom/reduction/phrasal verb/slang).\n"
                    f"2. CULTURAL_NOTE: 2-3 sentences in French explaining any American cultural "
                    f"context in this dialogue.\n"
                    f"3. COMPREHENSION_QS: 3 quick comprehension questions about the dialogue "
                    f"(in English) with answers.\n\n"
                    f"{('Additional instructions from the learner:\n' + custom_instr_re + '\n\n') if custom_instr_re.strip() else ''}"
                    f"Format as JSON:\n"
                    f'{{"dialogue": "full dialogue text using A: and B: labels with [stage directions]", '
                    f'"characters": ["Name1", "Name2"], '
                    f'"vocabulary": ['
                    f'{{"expression": "...", "full_form": "...", "french": "...", "type": "chunk"}}, ...'
                    f"], "
                    f'"cultural_note": "...", '
                    f'"comprehension": ['
                    f'{{"question": "...", "answer": "..."}}, ...'
                    f"]}}"
                )
                response, err = openrouter_chat(
                    [{"role": "user", "content": prompt}],
                    model=CHAT_MODEL,
                    temperature=0.8,
                    max_tokens=2500,
                )
                if err:
                    st.error(f"Erreur: {err}")
                else:
                    try:
                        cleaned = response.strip()
                        if cleaned.startswith("```"):
                            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                            cleaned = re.sub(r"\s*```$", "", cleaned)
                        lesson_data = json.loads(cleaned)
                        lesson_data["series"] = selected_series
                        lesson_data["episode"] = selected_episode
                        lesson_data["level"] = re_level
                        lesson_data["series_icon"] = series_info["icon"]
                        _save_real_english_lesson(profile_id, episode_id, lesson_data)
                        st.session_state["re_current_lesson"] = lesson_data
                        st.session_state["re_current_lesson_id"] = episode_id
                        st.rerun()
                    except (json.JSONDecodeError, KeyError) as e:
                        st.error(f"Erreur de format IA: {e}")
                        st.code(response)

        # Display current lesson dialogue
        lesson = st.session_state.get("re_current_lesson")
        if lesson:
            st.markdown("---")
            st.markdown(
                f"### {lesson.get('series_icon', '📺')} {lesson.get('series', '')} — "
                f"*{lesson.get('episode', '')}*  ({lesson.get('level', '')})"
            )
            chars = lesson.get("characters", [])
            if chars:
                st.caption(f"Personnages: {', '.join(chars)}")
            st.text(lesson.get("dialogue", ""))

            # Cultural note
            cultural = lesson.get("cultural_note", "")
            if cultural:
                with st.expander("🇺🇸 Note culturelle"):
                    st.markdown(cultural)

            # Comprehension questions
            comp_qs = lesson.get("comprehension", [])
            if comp_qs:
                with st.expander("❓ Questions de comprehension"):
                    for qi, cq in enumerate(comp_qs):
                        st.markdown(f"**Q{qi+1}.** {cq.get('question', '')}")
                        if st.button(f"Voir la reponse Q{qi+1}", key=f"re_comp_{qi}"):
                            st.info(cq.get("answer", ""))

    # ── Tab 2: Ecouter la scene ──────────────────────────────────────────────
    with tab_listen:
        st.subheader("Ecouter le dialogue")

        tts_engine = get_tts_engine()

        # Voice selection — depends on TTS engine
        if tts_engine == "elevenlabs":
            st.caption("Moteur: **ElevenLabs** (voix americaines naturelles)")
            voice_pairs_re_el = ELEVENLABS_VOICE_PAIRS
            voice_choice_el = st.selectbox(
                "Voix du dialogue (ElevenLabs)",
                list(voice_pairs_re_el.keys()),
                key="re_voice_pair_el",
            )
            el_va, el_vb = voice_pairs_re_el[voice_choice_el]
            # Fallback OpenRouter voices (in case of engine switch)
            va, vb = "echo", "nova"
        else:
            st.caption("Moteur: **TTS par defaut** (OpenRouter)")
            el_va, el_vb = None, None
            voice_pairs_re = {
                "Homme / Femme (echo / nova)": ("echo", "nova"),
                "Femme / Homme (nova / echo)": ("nova", "echo"),
                "Homme / Homme (echo / onyx)": ("echo", "onyx"),
                "Femme / Femme (nova / shimmer)": ("nova", "shimmer"),
            }
            voice_choice = st.selectbox(
                "Voix du dialogue",
                list(voice_pairs_re.keys()),
                key="re_voice_pair",
            )
            va, vb = voice_pairs_re[voice_choice]

        # Audio file extension depends on engine
        audio_ext = ".mp3" if tts_engine == "elevenlabs" else ".wav"
        audio_mime = "audio/mpeg" if tts_engine == "elevenlabs" else "audio/wav"

        # ── Bibliotheque audio : tous les episodes avec audio deja genere ────
        audio_library = []
        for ls in all_lessons:
            lid = ls.get("id", "")
            # Check for both .wav and .mp3 audio files
            afp_wav = os.path.join(REAL_ENGLISH_AUDIO_DIR, f"{lid}.wav")
            afp_mp3 = os.path.join(REAL_ENGLISH_AUDIO_DIR, f"{lid}.mp3")
            if os.path.exists(afp_mp3):
                afp = afp_mp3
                has_audio = True
                af_mime = "audio/mpeg"
            elif os.path.exists(afp_wav):
                afp = afp_wav
                has_audio = True
                af_mime = "audio/wav"
            else:
                afp = afp_wav
                has_audio = False
                af_mime = "audio/wav"
            audio_library.append(
                {
                    "id": lid,
                    "series": ls.get("series", ""),
                    "episode": ls.get("episode", ""),
                    "level": ls.get("level", ""),
                    "icon": ls.get("series_icon", "📺"),
                    "has_audio": has_audio,
                    "audio_path": afp,
                    "audio_mime": af_mime,
                    "dialogue": ls.get("dialogue", ""),
                }
            )

        episodes_with_audio = [a for a in audio_library if a["has_audio"]]
        episodes_without_audio = [a for a in audio_library if not a["has_audio"]]

        if episodes_with_audio:
            st.markdown(f"### 🎧 Mes audios generes ({len(episodes_with_audio)})")
            st.caption("Cliquez pour reecouter un episode a tout moment.")
            for ai, ep in enumerate(episodes_with_audio):
                is_current = ep["id"] == st.session_state.get("re_current_lesson_id")
                marker = " ◀️ *en cours*" if is_current else ""
                with st.expander(
                    f"{ep['icon']} {ep['series']} — {ep['episode']} ({ep['level']}){marker}"
                ):
                    with open(ep["audio_path"], "rb") as af:
                        _audio_player_with_repeat(
                            af.read(),
                            mime_type=ep.get("audio_mime", "audio/wav"),
                            key=f"re_lib_audio_{ai}",
                        )

                    col_text, col_regen, col_select = st.columns([2, 1, 1])
                    with col_text:
                        if ep["dialogue"]:
                            with st.expander("Lire le texte"):
                                st.text(ep["dialogue"])
                    with col_regen:
                        if st.button("🔄 Regenerer", key=f"re_lib_regen_{ai}"):
                            if os.path.exists(ep["audio_path"]):
                                os.remove(ep["audio_path"])
                            with st.spinner("Regeneration audio..."):
                                ab, mime, err = generate_dual_voice_tts(
                                    ep["dialogue"], va, vb, language_hint="en"
                                )
                                if not err:
                                    os.makedirs(REAL_ENGLISH_AUDIO_DIR, exist_ok=True)
                                    with open(ep["audio_path"], "wb") as af:
                                        af.write(ab)
                            st.rerun()
                    with col_select:
                        if not is_current:
                            if st.button("📂 Charger", key=f"re_lib_load_{ai}"):
                                loaded = _load_real_english_lesson(profile_id, ep["id"])
                                if loaded:
                                    st.session_state["re_current_lesson"] = loaded
                                    st.session_state["re_current_lesson_id"] = ep["id"]
                                    st.rerun()

        st.markdown("---")

        # ── Episode actuel sans audio ────────────────────────────────────────
        lesson = st.session_state.get("re_current_lesson")
        lesson_id = st.session_state.get("re_current_lesson_id")

        if not lesson:
            if not episodes_with_audio:
                st.info(
                    "Generez ou selectionnez un episode dans l'onglet 'Episodes & Dialogues' d'abord."
                )
        else:
            audio_file_wav = os.path.join(REAL_ENGLISH_AUDIO_DIR, f"{lesson_id}.wav")
            audio_file_mp3 = os.path.join(REAL_ENGLISH_AUDIO_DIR, f"{lesson_id}.mp3")
            audio_exists = os.path.exists(audio_file_wav) or os.path.exists(
                audio_file_mp3
            )
            if not audio_exists:
                st.markdown(
                    f"### 🔊 Episode actuel sans audio : "
                    f"{lesson.get('series_icon', '📺')} {lesson.get('series', '')} — "
                    f"{lesson.get('episode', '')} ({lesson.get('level', '')})"
                )
                engine_label = (
                    "ElevenLabs" if tts_engine == "elevenlabs" else "OpenRouter"
                )
                if st.button(
                    f"🔊 Generer l'audio ({engine_label})", key="re_gen_audio"
                ):
                    with st.spinner("Generation audio 2 voix..."):
                        audio_bytes, mime, err = dual_voice_tts_smart(
                            lesson["dialogue"],
                            va,
                            vb,
                            el_voice_a=el_va,
                            el_voice_b=el_vb,
                            language_hint="en",
                        )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        else:
                            os.makedirs(REAL_ENGLISH_AUDIO_DIR, exist_ok=True)
                            out_ext = ".mp3" if tts_engine == "elevenlabs" else ".wav"
                            out_path = os.path.join(
                                REAL_ENGLISH_AUDIO_DIR, f"{lesson_id}{out_ext}"
                            )
                            with open(out_path, "wb") as af:
                                af.write(audio_bytes)
                            st.rerun()

        # ── Episodes sans audio (generation en attente) ──────────────────────
        if episodes_without_audio:
            with st.expander(
                f"📋 Episodes sans audio ({len(episodes_without_audio)})",
                expanded=False,
            ):
                st.caption(
                    "Ces episodes ont ete generes mais n'ont pas encore d'audio."
                )
                for wi, ep in enumerate(episodes_without_audio):
                    col_name, col_gen = st.columns([3, 1])
                    with col_name:
                        st.markdown(
                            f"{ep['icon']} {ep['series']} — {ep['episode']} ({ep['level']})"
                        )
                    with col_gen:
                        if st.button("🔊 Generer", key=f"re_lib_gen_{wi}"):
                            loaded = _load_real_english_lesson(profile_id, ep["id"])
                            if loaded:
                                with st.spinner("Generation audio..."):
                                    ab, mime, err = dual_voice_tts_smart(
                                        loaded.get("dialogue", ""),
                                        va,
                                        vb,
                                        el_voice_a=el_va,
                                        el_voice_b=el_vb,
                                        language_hint="en",
                                    )
                                    if not err:
                                        os.makedirs(
                                            REAL_ENGLISH_AUDIO_DIR, exist_ok=True
                                        )
                                        out_ext = (
                                            ".mp3"
                                            if tts_engine == "elevenlabs"
                                            else ".wav"
                                        )
                                        out_path = os.path.join(
                                            REAL_ENGLISH_AUDIO_DIR,
                                            f"{ep['id']}{out_ext}",
                                        )
                                        with open(out_path, "wb") as af:
                                            af.write(ab)
                                st.rerun()

        st.markdown(
            "💡 **Astuce**: Ecoutez d'abord **sans** lire le texte. "
            "Notez ce que vous comprenez. Puis reecoutez en lisant. "
            "Repetez jusqu'a comprendre chaque mot."
        )

    # ── Tab 3: Vocabulaire, Chunks & Idioms ──────────────────────────────────
    with tab_vocab:
        st.subheader("Vocabulaire, Chunks & Idioms de l'episode")
        lesson = st.session_state.get("re_current_lesson")

        if not lesson:
            st.info(
                "Generez ou selectionnez un episode dans l'onglet 'Episodes & Dialogues' d'abord."
            )
        else:
            vocab_items = lesson.get("vocabulary", [])
            if not vocab_items:
                st.warning("Aucun vocabulaire extrait pour cet episode.")
            else:
                st.markdown(
                    f"**{len(vocab_items)} expressions cles** de cet episode. "
                    "Ajoutez-les a vos flashcards pour les memoriser avec le systeme SRS."
                )

                vocab_entries = load_vocab(profile_id=profile_id)
                existing_terms = {
                    e.get("term", "").lower()
                    for e in vocab_entries
                    if isinstance(e, dict)
                }

                # Group by type
                type_icons = {
                    "chunk": "🧩",
                    "idiom": "💬",
                    "reduction": "🔗",
                    "phrasal verb": "🔀",
                    "slang": "🗣️",
                }

                for vi, item in enumerate(vocab_items):
                    expr = item.get("expression", "").strip()
                    full = item.get("full_form", "").strip()
                    french = item.get("french", "").strip()
                    vtype = item.get("type", "chunk").strip().lower()
                    if not expr:
                        continue

                    already = expr.lower() in existing_terms
                    icon = type_icons.get(vtype, "📝")

                    col_info, col_audio, col_btn = st.columns([3, 1, 1])
                    with col_info:
                        type_label = vtype.capitalize()
                        if already:
                            st.markdown(
                                f"✅ {icon} **{expr}** ({full}) → {french} "
                                f"[{type_label}] — *deja dans vos flashcards*"
                            )
                        else:
                            st.markdown(
                                f"{icon} **{expr}** ({full}) → {french} [{type_label}]"
                            )
                    with col_audio:
                        expr_audio_wav = os.path.join(
                            REAL_ENGLISH_AUDIO_DIR, f"vocab-{slugify(expr)}.wav"
                        )
                        expr_audio_mp3 = os.path.join(
                            REAL_ENGLISH_AUDIO_DIR, f"vocab-{slugify(expr)}.mp3"
                        )
                        if os.path.exists(expr_audio_mp3):
                            with open(expr_audio_mp3, "rb") as af:
                                _audio_player_with_repeat(
                                    af.read(), "audio/mpeg", key=f"re_voc_{vi}"
                                )
                        elif os.path.exists(expr_audio_wav):
                            with open(expr_audio_wav, "rb") as af:
                                _audio_player_with_repeat(
                                    af.read(), "audio/wav", key=f"re_voc_{vi}"
                                )
                        else:
                            if st.button("🔊", key=f"re_vocab_tts_{vi}"):
                                with st.spinner("Audio..."):
                                    ab, mime, err = tts_smart(
                                        expr,
                                        voice="echo",
                                        voice_elevenlabs_id=list(
                                            ELEVENLABS_VOICES.values()
                                        )[0],
                                        language_hint="en",
                                    )
                                    if not err:
                                        os.makedirs(
                                            REAL_ENGLISH_AUDIO_DIR, exist_ok=True
                                        )
                                        out_ext = (
                                            ".mp3"
                                            if get_tts_engine() == "elevenlabs"
                                            else ".wav"
                                        )
                                        out_path = os.path.join(
                                            REAL_ENGLISH_AUDIO_DIR,
                                            f"vocab-{slugify(expr)}{out_ext}",
                                        )
                                        with open(out_path, "wb") as af:
                                            af.write(ab)
                                        st.audio(ab, format=mime)
                                        st.rerun()
                    with col_btn:
                        if not already:
                            if st.button("📝 Flashcard", key=f"re_vocab_flash_{vi}"):
                                new_card = {
                                    "id": str(uuid.uuid4())[:8],
                                    "term": expr,
                                    "translation": french,
                                    "part_of_speech": vtype,
                                    "explanation": (
                                        f"Forme complete: {full}. Construisez une phrase avec '{expr}'."
                                        if full
                                        else f"Construisez une phrase avec '{expr}'."
                                    ),
                                    "examples": [],
                                    "synonyms": [],
                                    "cefr_level": lesson.get("level", "B1"),
                                    "added": now_iso(),
                                    "next_review": now_iso(),
                                    "interval": 1,
                                    "ease": 2.5,
                                    "repetitions": 0,
                                    "review_history": [],
                                    "source_lesson_id": f"real-{st.session_state.get('re_current_lesson_id', '')}",
                                    "profile_id": profile_id,
                                }
                                vocab_entries.append(new_card)
                                save_vocab(vocab_entries, profile_id=profile_id)
                                existing_terms.add(expr.lower())
                                st.success(f"Flashcard ajoutee: {expr}")

                # Bulk add button
                not_added = [
                    v
                    for v in vocab_items
                    if v.get("expression", "").strip()
                    and v.get("expression", "").strip().lower() not in existing_terms
                ]
                if len(not_added) > 1:
                    st.markdown("---")
                    if st.button(
                        f"📝 Ajouter les {len(not_added)} expressions aux flashcards",
                        key="re_vocab_flash_all",
                    ):
                        vocab_entries = load_vocab(profile_id=profile_id)
                        added = 0
                        for vi2, v2 in enumerate(not_added):
                            et = v2.get("expression", "").strip()
                            new_card = {
                                "id": str(uuid.uuid4())[:8],
                                "term": et,
                                "translation": v2.get("french", ""),
                                "part_of_speech": v2.get("type", "chunk"),
                                "explanation": (
                                    f"Forme complete: {v2.get('full_form', '')}. "
                                    f"Construisez une phrase avec '{et}'."
                                ),
                                "examples": [],
                                "synonyms": [],
                                "cefr_level": lesson.get("level", "B1"),
                                "added": now_iso(),
                                "next_review": now_iso(),
                                "interval": 1,
                                "ease": 2.5,
                                "repetitions": 0,
                                "review_history": [],
                                "source_lesson_id": f"real-{st.session_state.get('re_current_lesson_id', '')}",
                                "profile_id": profile_id,
                            }
                            vocab_entries.append(new_card)
                            added += 1
                        save_vocab(vocab_entries, profile_id=profile_id)
                        st.success(f"{added} flashcards ajoutees d'un coup !")

    # ── Tab 4: Pratiquer (Shadowing) ─────────────────────────────────────────
    with tab_shadow:
        st.subheader("Pratiquer ce dialogue en Shadowing")
        lesson = st.session_state.get("re_current_lesson")
        lesson_id = st.session_state.get("re_current_lesson_id")

        if not lesson:
            st.info(
                "Generez ou selectionnez un episode dans l'onglet 'Episodes & Dialogues' d'abord."
            )
        else:
            st.markdown(
                f"**{lesson.get('series_icon', '📺')} {lesson.get('series', '')} — "
                f"{lesson.get('episode', '')}** ({lesson.get('level', '')})"
            )
            st.markdown(
                "Envoyez ce dialogue vers le **Shadowing interactif** pour le pratiquer "
                "phrase par phrase. Vous ecouterez chaque replique et la repeterez."
            )

            # Show dialogue preview
            with st.expander("Apercu du dialogue"):
                st.text(lesson.get("dialogue", ""))

            # Extract chunk focus from vocabulary
            chunk_focus = [
                v.get("expression", "")
                for v in lesson.get("vocabulary", [])
                if v.get("expression", "")
            ]

            col_shadow_send, col_shadow_complete = st.columns(2)
            with col_shadow_send:
                if st.button(
                    "Envoyer vers le Shadowing interactif", key="re_to_shadowing"
                ):
                    added = register_shadowing_text(
                        profile_id=profile_id,
                        source_lesson_id=f"real-english-{lesson_id}",
                        lesson_kind="real_english",
                        theme_name=f"{lesson.get('series', '')} — {lesson.get('episode', '')}",
                        dialogue_text=lesson.get("dialogue", ""),
                        chunk_focus=chunk_focus,
                        cefr_level=lesson.get("level", "B1"),
                        lesson_title=f"[Real English] {lesson.get('series', '')} — {lesson.get('episode', '')}",
                    )
                    if added:
                        st.success(
                            "Dialogue ajoute au Shadowing interactif ! "
                            "Allez dans l'onglet 'Shadowing interactif' pour le pratiquer."
                        )
                    else:
                        st.info(
                            "Ce dialogue est deja dans votre liste de shadowing (mis a jour)."
                        )

            with col_shadow_complete:
                already_done = lesson_id in progress.get("completed_lessons", [])
                if already_done:
                    st.success("Cet episode est deja termine.")
                elif st.button(
                    "✅ Terminer cet episode", key="re_complete_from_shadow"
                ):
                    completion_result = _mark_real_english_lesson_completed(
                        profile_id=profile_id,
                        progress=progress,
                        lesson_id=lesson_id,
                        lesson=lesson,
                    )
                    added_cards = int(completion_result.get("added_flashcards", 0))
                    if added_cards > 0:
                        st.info(
                            f"{added_cards} flashcards ajoutees automatiquement depuis cette lecon."
                        )
                    st.success("Episode marque comme termine !")
                    st.rerun()

    # ── Tab 5: Ma progression ────────────────────────────────────────────────
    with tab_progress:
        st.subheader("Ma progression — Anglais reel")
        lesson = st.session_state.get("re_current_lesson")
        lesson_id = st.session_state.get("re_current_lesson_id")

        completed = progress.get("completed_lessons", [])
        total_episodes = sum(
            len(s["episodes"]) * len(CEFR_LEVELS) for s in REAL_ENGLISH_SERIES.values()
        )
        total_completed = len(completed)

        st.markdown(f"### Episodes termines: {total_completed}")
        if total_completed > 0:
            st.progress(min(total_completed / max(total_episodes, 1), 1.0))

        # Stats by series
        st.markdown("#### Par serie")
        for series_name, series_data in REAL_ENGLISH_SERIES.items():
            series_completed = [
                c for c in completed if c.startswith(slugify(series_name))
            ]
            total_series = len(series_data["episodes"]) * len(CEFR_LEVELS)
            icon = series_data["icon"]
            st.markdown(
                f"{icon} **{series_name}**: {len(series_completed)}/{total_series} episodes"
            )

        # Stats by level
        st.markdown("#### Par niveau")
        for level in CEFR_LEVELS:
            level_completed = [c for c in completed if c.endswith(f"-{level.lower()}")]
            badge = CEFR_DESCRIPTORS[level]["badge"]
            st.markdown(f"{badge}: {len(level_completed)} episodes termines")

        st.markdown("---")

        # Mark current lesson as completed
        if lesson and lesson_id:
            is_completed = lesson_id in completed
            if is_completed:
                st.success(f"✅ Cet episode est marque comme termine !")
                if st.button("Annuler (remettre en cours)", key="re_uncomplete"):
                    progress["completed_lessons"].remove(lesson_id)
                    progress.setdefault("lesson_history", []).append(
                        {
                            "action": "uncompleted",
                            "lesson_id": lesson_id,
                            "date": now_iso(),
                        }
                    )
                    _save_real_english_progress(profile_id, progress)
                    st.rerun()
            else:
                st.warning("Cet episode n'est pas encore marque comme termine.")
                if st.button("✅ Marquer comme termine", key="re_complete"):
                    completion_result = _mark_real_english_lesson_completed(
                        profile_id=profile_id,
                        progress=progress,
                        lesson_id=lesson_id,
                        lesson=lesson,
                    )
                    added_cards = int(completion_result.get("added_flashcards", 0))
                    if added_cards > 0:
                        st.info(
                            f"{added_cards} flashcards ajoutees automatiquement depuis cette lecon."
                        )

                    st.success("Episode marque comme termine !")
                    st.rerun()
        else:
            st.info(
                "Selectionnez un episode dans l'onglet 'Episodes & Dialogues' pour le marquer comme termine."
            )

        # Recent history
        history = progress.get("lesson_history", [])
        if history:
            with st.expander(f"Historique recent ({len(history)} actions)"):
                for h in reversed(history[-20:]):
                    action = (
                        "✅ Termine" if h.get("action") == "completed" else "↩️ Annule"
                    )
                    date = h.get("date", "")[:10]
                    series = h.get("series", "")
                    ep = h.get("episode", "")
                    lvl = h.get("level", "")
                    st.markdown(f"- {action} — {date} — {series} — {ep} ({lvl})")

                    action = (
                        "✅ Termine" if h.get("action") == "completed" else "↩️ Annule"
                    )
                    date = h.get("date", "")[:10]
                    series = h.get("series", "")
                    ep = h.get("episode", "")
                    lvl = h.get("level", "")
                    st.markdown(f"- {action} — {date} — {series} — {ep} ({lvl})")
