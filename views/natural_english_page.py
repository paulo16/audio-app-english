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
from modules.immersion import (
    _delete_generated_content,
    _list_generated_content,
    _load_generated_content,
    _load_immersion_progress,
    _save_generated_content,
    _save_immersion_progress,
)
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


def render_natural_english_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Anglais naturel & Immersion")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")
    st.info(
        "Ce module cible le **fosse entre l'anglais appris et l'anglais reel**. "
        "Ici vous travaillez les contractions, l'argot, les expressions de series, "
        "et l'ecoute rapide — exactement ce qui manque pour comprendre Friends, "
        "les podcasts natifs et les conversations americaines."
    )

    progress = _load_immersion_progress(profile_id)

    tab_cs, tab_slang, tab_dictation, tab_quiz, tab_sitcom, tab_speed = st.tabs(
        [
            "Parole liee (Connected Speech)",
            "Argot & Expressions TV",
            "Ecoute active (Dictee)",
            "Quiz de comprehension",
            "Dialogues style sitcom",
            "Controle de vitesse",
        ]
    )

    # ── Tab 1: Connected Speech ──────────────────────────────────────────────
    with tab_cs:
        st.subheader("Les reductions de l'anglais parle americain")

        with st.expander(
            "📋 **Comment utiliser ce module — Guide complet**", expanded=False
        ):
            st.markdown(
                """
**Pourquoi ce module ?**
Vous comprenez l'anglais ecrit et l'anglais "propre", mais les Americains parlent
avec des **contractions, de l'argot et des mots avales** qui n'apparaissent dans
aucun manuel. C'est pour ca que vous comprenez ~60% de Friends. Ce module comble ce fosse.

---

**Parcours recommande (dans l'ordre des onglets) :**

| Etape | Onglet | Duree | Quoi faire |
|-------|--------|-------|------------|
| **1** | **Parole liee** (ici) | 5-10 min | Apprenez 3-5 reductions par jour. Ecoutez l'audio, repetez a voix haute, cliquez "J'ai compris". |
| **2** | **Argot & Expressions TV** | 5 min | Parcourez 1 categorie. Ajoutez les expressions utiles a vos **flashcards SRS**. |
| **3** | **Ecoute active (Dictee)** | 5-10 min | Generez un exercice, ecoutez le dialogue, remplissez les trous. Visez 80%+. |
| **4** | **Quiz de comprehension** | 5 min | Testez votre comprehension des nuances et du sarcasme apres ecoute. |
| **5** | **Dialogues style sitcom** | 5-10 min | Ecoutez un dialogue rapide style Friends, lisez le vocabulaire extrait. |
| **6** | **Controle de vitesse** | 5 min | Entrainez votre oreille a des debits crescents (0.85x → 1.3x). |

---

**Routine quotidienne recommandee (15-20 min) :**
1. **3-5 nouvelles reductions** dans "Parole liee" (ecouter + repeter)
2. **1 exercice de dictee** dans "Ecoute active" (remplir les trous)
3. **1 quiz de comprehension** OU **1 dialogue sitcom**
4. **Revision flashcards** des expressions ajoutees (dans Vocabulaire & Flashcards)

**Routine hebdomadaire :**
- Lundi-Mercredi : focus **Parole liee** + **Dictee**
- Jeudi-Vendredi : focus **Argot TV** + **Quiz**
- Samedi : **Dialogue sitcom** + **Vitesse** en augmentant le debit
- Dimanche : revision des flashcards + reecoute des audios de la semaine

---

**Objectifs de progression :**
- **Semaine 1-2** : Maitriser les 30 reductions les plus courantes (gonna, wanna, gotta...)
- **Semaine 3-4** : Comprendre l'argot courant + atteindre 70%+ aux dictees
- **Semaine 5-6** : Quiz a 80%+ + dialogues sitcom a vitesse 1.15x
- **Semaine 7+** : Comprendre Friends avec sous-titres anglais a 85%+

**Conseil cle** : ne passez pas a l'onglet suivant tant que vous n'avez pas
maitrise au moins 50% du contenu de l'onglet en cours.
"""
            )

        st.markdown(
            "Quand les Americains parlent, ils **fusionnent et reduisent** les mots. "
            "C'est la raison principale pour laquelle vous ne comprenez pas tout dans les series.\n\n"
            "**Exercice**: ecoutez la forme reduite, repetez-la, puis utilisez-la dans une phrase."
        )

        cs_search = st.text_input("Filtrer les expressions", "", key="cs_filter")
        filtered_rules = CONNECTED_SPEECH_RULES
        if cs_search.strip():
            q = cs_search.lower().strip()
            filtered_rules = [
                r
                for r in CONNECTED_SPEECH_RULES
                if q in r["full"].lower() or q in r["reduced"].lower()
            ]

        reviewed_ids = set(progress.get("connected_speech_scores", {}).keys())
        st.caption(
            f"Progression: {len(reviewed_ids)}/{len(CONNECTED_SPEECH_RULES)} expressions travaillees"
        )
        pbar = st.progress(
            min(len(reviewed_ids) / max(len(CONNECTED_SPEECH_RULES), 1), 1.0)
        )

        for idx, rule in enumerate(filtered_rules):
            rule_id = slugify(rule["reduced"])
            is_done = rule_id in reviewed_ids
            icon = "✅" if is_done else "🔹"
            with st.expander(f"{icon} {rule['full']}  →  **{rule['reduced']}**"):
                col1, col2 = st.columns([1, 1])
                with col1:
                    st.markdown(f"**Forme complete:** {rule['full']}")
                    st.markdown(f"**Forme reduite:** `{rule['reduced']}`")
                    if rule.get("ipa"):
                        st.markdown(f"**Prononciation:** {rule['ipa']}")
                with col2:
                    st.markdown(f"**Exemple:** *{rule['example']}*")

                # Generate audio for the reduced form
                audio_key = f"cs-audio-{rule_id}"
                audio_file = os.path.join(CONNECTED_SPEECH_AUDIO_DIR, f"{rule_id}.wav")

                if os.path.exists(audio_file):
                    with open(audio_file, "rb") as af:
                        _audio_player_with_repeat(
                            af.read(), "audio/wav", key=f"cs_{rule_id}"
                        )
                else:
                    if st.button(f"🔊 Ecouter la prononciation", key=f"cs-tts-{idx}"):
                        with st.spinner("Generation audio..."):
                            tts_text = f"{rule['example']}"
                            audio_bytes, mime, err = text_to_speech_openrouter(
                                tts_text, voice="echo", language_hint="en"
                            )
                            if err:
                                st.error(f"Erreur TTS: {err}")
                            else:
                                os.makedirs(CONNECTED_SPEECH_AUDIO_DIR, exist_ok=True)
                                with open(audio_file, "wb") as af:
                                    af.write(audio_bytes)
                                st.audio(audio_bytes, format=mime)
                                st.rerun()

                col_done_cs, col_flash_cs = st.columns(2)
                with col_done_cs:
                    if st.button("✅ J'ai compris et repete", key=f"cs-done-{idx}"):
                        progress["connected_speech_scores"][rule_id] = {
                            "date": now_iso(),
                            "expression": rule["reduced"],
                        }
                        _save_immersion_progress(profile_id, progress)
                        st.rerun()
                with col_flash_cs:
                    if st.button("📝 Flashcard", key=f"cs-flash-{idx}"):
                        vocab_entries = load_vocab(profile_id=profile_id)
                        exists = any(
                            e.get("term", "").lower() == rule["reduced"].lower()
                            for e in vocab_entries
                        )
                        if exists:
                            st.info("Deja dans vos flashcards.")
                        else:
                            new_card = {
                                "id": str(uuid.uuid4())[:8],
                                "term": rule["reduced"],
                                "translation": rule["full"],
                                "part_of_speech": "connected speech",
                                "explanation": f"Contraction de '{rule['full']}'. Construisez une phrase avec '{rule['reduced']}'.",
                                "examples": [rule["example"]],
                                "synonyms": [],
                                "cefr_level": "B1",
                                "added": now_iso(),
                                "next_review": now_iso(),
                                "interval": 1,
                                "ease": 2.5,
                                "repetitions": 0,
                                "review_history": [],
                                "source_lesson_id": f"cs-{rule_id}",
                                "profile_id": profile_id,
                            }
                            vocab_entries.append(new_card)
                            save_vocab(vocab_entries, profile_id=profile_id)
                            st.success(f"Flashcard ajoutee: {rule['reduced']}")

    # ── Tab 2: Slang & Idioms TV ─────────────────────────────────────────────
    with tab_slang:
        st.subheader("Argot, expressions & references des series US")
        st.markdown(
            "Les expressions qu'on n'apprend pas dans les manuels mais qu'on entend "
            "**dans chaque episode** de Friends, The Office, etc."
        )

        slang_category = st.selectbox(
            "Categorie", list(SLANG_CATEGORIES.keys()), key="slang_cat"
        )
        items = SLANG_CATEGORIES[slang_category]
        reviewed_slang = set(progress.get("slang_reviewed", []))

        st.caption(
            f"{len([s for s in items if slugify(s['expression']) in reviewed_slang])}/{len(items)} maitrisees dans cette categorie"
        )

        for si, item in enumerate(items):
            sid = slugify(item["expression"])
            is_known = sid in reviewed_slang
            icon = "✅" if is_known else "💬"
            with st.expander(f"{icon} {item['expression']}"):
                st.markdown(f"**Traduction:** {item['meaning']}")
                st.markdown(f"**Contexte:** {item['context']}")
                st.markdown(f"**Exemple:** *\"{item['example']}\"*")

                # Audio
                slang_audio_file = os.path.join(
                    CONNECTED_SPEECH_AUDIO_DIR, f"slang-{sid}.wav"
                )
                if os.path.exists(slang_audio_file):
                    with open(slang_audio_file, "rb") as af:
                        _audio_player_with_repeat(
                            af.read(), "audio/wav", key=f"slang_{sid}"
                        )
                else:
                    if st.button("🔊 Ecouter", key=f"slang-tts-{si}"):
                        with st.spinner("Generation audio..."):
                            audio_bytes, mime, err = text_to_speech_openrouter(
                                item["example"], voice="nova", language_hint="en"
                            )
                            if err:
                                st.error(f"Erreur TTS: {err}")
                            else:
                                os.makedirs(CONNECTED_SPEECH_AUDIO_DIR, exist_ok=True)
                                with open(slang_audio_file, "wb") as af:
                                    af.write(audio_bytes)
                                st.audio(audio_bytes, format=mime)
                                st.rerun()

                # Add to flashcards
                col_flash, col_done = st.columns(2)
                with col_flash:
                    if st.button("📝 Ajouter aux flashcards", key=f"slang-flash-{si}"):
                        vocab_entries = load_vocab(profile_id=profile_id)
                        exists = any(
                            e.get("term", "").lower() == item["expression"].lower()
                            for e in vocab_entries
                        )
                        if exists:
                            st.info("Deja dans vos flashcards.")
                        else:
                            new_card = {
                                "id": str(uuid.uuid4())[:8],
                                "term": item["expression"],
                                "translation": item["meaning"],
                                "part_of_speech": "idiom / slang",
                                "explanation": f"{item['context']}. Construisez une phrase avec '{item['expression']}'.",
                                "examples": [item["example"]],
                                "synonyms": [],
                                "cefr_level": "B2",
                                "added": now_iso(),
                                "next_review": now_iso(),
                                "interval": 1,
                                "ease": 2.5,
                                "repetitions": 0,
                                "review_history": [],
                                "source_lesson_id": f"slang-{sid}",
                                "profile_id": profile_id,
                            }
                            vocab_entries.append(new_card)
                            save_vocab(vocab_entries, profile_id=profile_id)
                            st.success(f"Flashcard ajoutee: {item['expression']}")
                with col_done:
                    if st.button("✅ Maitrisee", key=f"slang-done-{si}"):
                        if sid not in progress.get("slang_reviewed", []):
                            progress.setdefault("slang_reviewed", []).append(sid)
                            _save_immersion_progress(profile_id, progress)
                        st.rerun()

    # ── Tab 3: Ecoute active (Dictee partielle) ─────────────────────────────
    with tab_dictation:
        st.subheader("Dictee partielle — Ecoute active")
        st.markdown(
            "L'IA genere un dialogue **base sur ce que vous avez deja appris** "
            "(reductions cochees + argot maitrise). Les trous portent sur ces expressions.\n\n"
            "Quand le dialogue contient des expressions **nouvelles**, vous pouvez "
            "les ajouter directement a vos flashcards."
        )

        default_level = profile.get("target_cefr", "B1")
        if default_level not in CEFR_LEVELS:
            default_level = "B1"
        dict_level = st.radio(
            "Niveau cible",
            CEFR_LEVELS,
            horizontal=True,
            index=CEFR_LEVELS.index(default_level),
            key="dict_level",
        )

        # ── Collect learned material ────────────────────────────────────────
        learned_cs = progress.get("connected_speech_scores", {})
        learned_slang_ids = set(progress.get("slang_reviewed", []))

        # Build list of learned reductions
        learned_reductions = []
        for rule in CONNECTED_SPEECH_RULES:
            rid = slugify(rule["reduced"])
            if rid in learned_cs:
                learned_reductions.append(f"{rule['reduced']} ({rule['full']})")
        # Build list of learned slang
        learned_expressions = []
        for cat_items in SLANG_CATEGORIES.values():
            for item in cat_items:
                sid = slugify(item["expression"])
                if sid in learned_slang_ids:
                    learned_expressions.append(item["expression"])

        total_learned = len(learned_reductions) + len(learned_expressions)

        if total_learned == 0:
            st.warning(
                "Vous n'avez pas encore valide d'expressions dans les onglets "
                "**Parole liee** et **Argot & Expressions TV**.\n\n"
                "Commencez par apprendre quelques expressions la-bas, puis revenez ici "
                "pour les pratiquer en contexte. En attendant, un dialogue general sera genere."
            )
            learned_summary = (
                "gonna, wanna, gotta, kinda, dunno, lemme, gimme, coulda, shoulda, prolly, "
                "'cause, y'all, tryna, gotcha, c'mon, no way, for real, my bad, I'm down, "
                "you know, I mean, like, right?, basically, hang out, figure out"
            )
        else:
            with st.expander(
                f"📚 Vos acquis utilises pour la dictee ({total_learned} expressions)"
            ):
                if learned_reductions:
                    st.markdown(
                        "**Reductions apprises:** "
                        + ", ".join(f"`{r}`" for r in learned_reductions[:20])
                    )
                    if len(learned_reductions) > 20:
                        st.caption(f"... et {len(learned_reductions)-20} de plus")
                if learned_expressions:
                    st.markdown(
                        "**Argot maitrise:** "
                        + ", ".join(f"`{e}`" for e in learned_expressions[:20])
                    )
                    if len(learned_expressions) > 20:
                        st.caption(f"... et {len(learned_expressions)-20} de plus")
            learned_summary = ", ".join(
                learned_reductions[:15] + learned_expressions[:15]
            )

        if "dictation_exercise" not in st.session_state:
            st.session_state["dictation_exercise"] = None

        # ── Load saved dictation exercises ───────────────────────────────
        saved_dicts = _list_generated_content(profile_id, "dictation")
        if saved_dicts:
            with st.expander(
                f"📂 Dictees sauvegardees ({len(saved_dicts)})", expanded=False
            ):
                for di, saved in enumerate(saved_dicts):
                    date = saved.get("saved", "?")[:10]
                    level = saved.get("level", "?")
                    score = saved.get("last_score", "—")
                    col_load, col_del = st.columns([4, 1])
                    with col_load:
                        if st.button(
                            f"📖 {date} — Niveau {level} — Score: {score}",
                            key=f"dict_load_{di}",
                        ):
                            st.session_state["dictation_exercise"] = saved.get(
                                "exercise"
                            )
                            st.session_state.pop("dictation_answers_submitted", None)
                            st.session_state.pop("dictation_audio_current", None)
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"dict_del_{di}"):
                            _delete_generated_content(
                                profile_id, "dictation", saved.get("id", "")
                            )
                            st.rerun()

        if st.button("Generer un exercice de dictee", key="gen_dictation"):
            with st.spinner("L'IA cree un dialogue base sur vos acquis..."):
                prompt = (
                    f"Create a short natural American English dialogue (8-10 lines) between two friends. "
                    f"CEFR level: {dict_level}.\n\n"
                    f"The dialogue MUST use these connected speech reductions and slang that the learner "
                    f"has already studied: {learned_summary}\n\n"
                    f"IMPORTANT: Use at least 6-8 of these learned expressions naturally in the dialogue. "
                    f"Also sprinkle in 2-3 NEW expressions the learner hasn't seen yet "
                    f"(common American reductions, phrasal verbs, or slang — different from the list above).\n\n"
                    f"Topic: casual everyday conversation.\n\n"
                    f"Provide:\n"
                    f"1. The FULL dialogue (complete text)\n"
                    f"2. A GAPPED version where 6-8 of the reduced/slang words are replaced by ___ (blanks). "
                    f"Mix learned expressions AND new ones in the gaps.\n"
                    f"3. The ANSWERS list (what goes in each blank, in order)\n"
                    f"4. A NEW_EXPRESSIONS list: the 2-3 expressions that are NEW for the learner "
                    f"(not in their learned list above). For each, give the expression, its full form, "
                    f"and a French translation.\n\n"
                    f"Format your response EXACTLY as JSON:\n"
                    f'{{"full_dialogue": "...", "gapped_dialogue": "...", '
                    f'"answers": ["word1", "word2", ...], '
                    f'"new_expressions": ['
                    f'{{"expression": "...", "full_form": "...", "french": "..."}}, ...'
                    f"], "
                    f'"vocabulary_notes": "brief French explanation of the reductions used"}}'
                )
                response, err = openrouter_chat(
                    [{"role": "user", "content": prompt}],
                    model=CHAT_MODEL,
                    temperature=0.7,
                    max_tokens=1800,
                )
                if err:
                    st.error(f"Erreur: {err}")
                else:
                    try:
                        cleaned = response.strip()
                        if cleaned.startswith("```"):
                            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                            cleaned = re.sub(r"\s*```$", "", cleaned)
                        exercise = json.loads(cleaned)
                        st.session_state["dictation_exercise"] = exercise
                        st.session_state["dictation_content_id"] = (
                            now_iso()[:19].replace(":", "-").replace("T", "-")
                        )
                        _save_generated_content(
                            profile_id,
                            "dictation",
                            st.session_state["dictation_content_id"],
                            {
                                "exercise": exercise,
                                "level": dict_level,
                                "last_score": "—",
                            },
                        )
                        st.session_state.pop("dictation_answers_submitted", None)
                        st.session_state.pop("dictation_audio_current", None)
                    except (json.JSONDecodeError, KeyError) as e:
                        st.error(f"Erreur de format IA: {e}")
                        st.code(response)

        exercise = st.session_state.get("dictation_exercise")
        if exercise:
            # Generate audio for full dialogue
            dict_audio_key = "dictation_audio_current"
            if dict_audio_key not in st.session_state:
                if st.button("🔊 Ecouter le dialogue", key="dict_listen"):
                    with st.spinner("Generation audio du dialogue..."):
                        audio_bytes, mime, err = generate_dual_voice_tts(
                            exercise["full_dialogue"],
                            "echo",
                            "nova",
                            language_hint="en",
                        )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        else:
                            st.session_state[dict_audio_key] = {
                                "bytes": audio_bytes,
                                "mime": mime,
                            }
                            st.rerun()
            else:
                _audio_player_with_repeat(
                    st.session_state[dict_audio_key]["bytes"],
                    st.session_state[dict_audio_key]["mime"],
                    key="dict_rpt",
                )

            st.markdown("**Remplissez les trous:**")
            st.code(exercise.get("gapped_dialogue", ""), language=None)

            answers = exercise.get("answers", [])
            user_answers = []
            cols = st.columns(min(max(len(answers), 1), 4))
            for ai, ans in enumerate(answers):
                with cols[ai % len(cols)]:
                    user_answers.append(
                        st.text_input(f"Trou {ai+1}", key=f"dict_ans_{ai}").strip()
                    )

            if st.button("Verifier mes reponses", key="dict_check"):
                correct = 0
                results_md = []
                for ai, (expected, given) in enumerate(zip(answers, user_answers)):
                    is_correct = given.lower().strip(
                        ".,!?'\""
                    ) == expected.lower().strip(".,!?'\"")
                    if is_correct:
                        correct += 1
                        results_md.append(f"✅ Trou {ai+1}: **{given}**")
                    else:
                        results_md.append(
                            f"❌ Trou {ai+1}: vous avez mis **{given or '(vide)'}** → reponse: **{expected}**"
                        )

                score = int(correct / max(len(answers), 1) * 100)
                if score >= 80:
                    st.success(
                        f"Score: {score}% ({correct}/{len(answers)}) — Excellent !"
                    )
                elif score >= 50:
                    st.warning(
                        f"Score: {score}% ({correct}/{len(answers)}) — Continuez !"
                    )
                else:
                    st.error(
                        f"Score: {score}% ({correct}/{len(answers)}) — Reecoutez et reessayez"
                    )

                for r in results_md:
                    st.markdown(r)

                if exercise.get("vocabulary_notes"):
                    st.info(f"**Notes:** {exercise['vocabulary_notes']}")

                # Show full dialogue
                with st.expander("Voir le dialogue complet"):
                    st.text(exercise["full_dialogue"])

                # ── New expressions discovered → propose flashcards ──────────
                new_exprs = exercise.get("new_expressions", [])
                if new_exprs:
                    st.markdown("---")
                    st.markdown("### 🆕 Nouvelles expressions decouvertes")
                    st.caption(
                        "Ces expressions sont apparues dans le dialogue mais ne font pas "
                        "partie de vos acquis. Ajoutez-les a vos flashcards pour les memoriser !"
                    )
                    vocab_entries = load_vocab(profile_id=profile_id)
                    existing_terms = {
                        e.get("term", "").lower()
                        for e in vocab_entries
                        if isinstance(e, dict)
                    }

                    for ni, new_expr in enumerate(new_exprs):
                        expr_text = new_expr.get("expression", "").strip()
                        full_form = new_expr.get("full_form", "").strip()
                        french = new_expr.get("french", "").strip()
                        if not expr_text:
                            continue

                        already_exists = expr_text.lower() in existing_terms

                        col_info, col_btn = st.columns([3, 1])
                        with col_info:
                            if already_exists:
                                st.markdown(
                                    f"✅ **{expr_text}** ({full_form}) → {french} — *deja dans vos flashcards*"
                                )
                            else:
                                st.markdown(
                                    f"💡 **{expr_text}** ({full_form}) → {french}"
                                )
                        with col_btn:
                            if not already_exists:
                                if st.button("📝 Ajouter", key=f"dict_flash_{ni}"):
                                    new_card = {
                                        "id": str(uuid.uuid4())[:8],
                                        "term": expr_text,
                                        "translation": french,
                                        "part_of_speech": "connected speech / slang",
                                        "explanation": (
                                            f"Forme complete: {full_form}. Construisez une phrase avec '{expr_text}'."
                                            if full_form
                                            else f"Construisez une phrase avec '{expr_text}'."
                                        ),
                                        "examples": [],
                                        "synonyms": [],
                                        "cefr_level": dict_level,
                                        "added": now_iso(),
                                        "next_review": now_iso(),
                                        "interval": 1,
                                        "ease": 2.5,
                                        "repetitions": 0,
                                        "review_history": [],
                                        "source_lesson_id": f"dictation-{now_iso()[:10]}-{ni}",
                                        "profile_id": profile_id,
                                    }
                                    vocab_entries.append(new_card)
                                    save_vocab(vocab_entries, profile_id=profile_id)
                                    existing_terms.add(expr_text.lower())
                                    st.success(f"Flashcard ajoutee: {expr_text}")

                    # Bulk add all new
                    not_yet_added = [
                        ne
                        for ne in new_exprs
                        if ne.get("expression", "").strip()
                        and ne.get("expression", "").strip().lower()
                        not in existing_terms
                    ]
                    if len(not_yet_added) > 1:
                        if st.button(
                            "📝 Ajouter toutes les nouvelles expressions",
                            key="dict_flash_all",
                        ):
                            vocab_entries = load_vocab(profile_id=profile_id)
                            added = 0
                            for ni2, ne2 in enumerate(not_yet_added):
                                expr2 = ne2.get("expression", "").strip()
                                new_card = {
                                    "id": str(uuid.uuid4())[:8],
                                    "term": expr2,
                                    "translation": ne2.get("french", ""),
                                    "part_of_speech": "connected speech / slang",
                                    "explanation": (
                                        f"Forme complete: {ne2.get('full_form', '')}. Construisez une phrase avec '{expr2}'."
                                        if ne2.get("full_form")
                                        else f"Construisez une phrase avec '{expr2}'."
                                    ),
                                    "examples": [],
                                    "synonyms": [],
                                    "cefr_level": dict_level,
                                    "added": now_iso(),
                                    "next_review": now_iso(),
                                    "interval": 1,
                                    "ease": 2.5,
                                    "repetitions": 0,
                                    "review_history": [],
                                    "source_lesson_id": f"dictation-{now_iso()[:10]}-bulk-{ni2}",
                                    "profile_id": profile_id,
                                }
                                vocab_entries.append(new_card)
                                added += 1
                            save_vocab(vocab_entries, profile_id=profile_id)
                            st.success(f"{added} flashcards ajoutees d'un coup !")

                # Save to progress
                progress.setdefault("dictation_history", []).append(
                    {
                        "date": now_iso(),
                        "score": score,
                        "level": dict_level,
                    }
                )
                if len(progress["dictation_history"]) > 50:
                    progress["dictation_history"] = progress["dictation_history"][-50:]
                _save_immersion_progress(profile_id, progress)

                # Update saved file with score
                dict_cid = st.session_state.get("dictation_content_id")
                if dict_cid:
                    saved_data = _load_generated_content(
                        profile_id, "dictation", dict_cid
                    )
                    if saved_data:
                        saved_data["last_score"] = f"{score}%"
                        _save_generated_content(
                            profile_id, "dictation", dict_cid, saved_data
                        )

    # ── Tab 4: Quiz de comprehension ─────────────────────────────────────────
    with tab_quiz:
        st.subheader("Quiz post-ecoute — Comprehension naturelle")
        st.markdown(
            "Ecoutez un dialogue genere par l'IA, puis repondez aux questions.\n"
            "Les questions portent sur les **nuances, les sous-entendus et le ton** "
            "— pas seulement les faits. C'est exactement ce qu'il faut comprendre dans Friends."
        )

        default_level = profile.get("target_cefr", "B1")
        if default_level not in CEFR_LEVELS:
            default_level = "B1"
        quiz_level = st.radio(
            "Niveau cible",
            CEFR_LEVELS,
            horizontal=True,
            index=CEFR_LEVELS.index(default_level),
            key="quiz_level",
        )

        quiz_topics = [
            "Two friends arguing about where to eat",
            "Roommates discussing chores and responsibilities",
            "A sarcastic conversation about a terrible date",
            "Friends planning a surprise birthday party",
            "Coworkers gossiping about office drama",
            "Two people debating which TV show is better",
            "A friend giving unsolicited advice about fashion",
            "Planning a road trip with disagreements",
        ]

        if "quiz_data" not in st.session_state:
            st.session_state["quiz_data"] = None

        # ── Load saved quizzes ───────────────────────────────────────────
        saved_quizzes = _list_generated_content(profile_id, "quiz")
        if saved_quizzes:
            with st.expander(
                f"📂 Quiz sauvegardes ({len(saved_quizzes)})", expanded=False
            ):
                for qi, saved in enumerate(saved_quizzes):
                    date = saved.get("saved", "?")[:10]
                    topic = saved.get("topic", "?")
                    score = saved.get("last_score", "—")
                    col_load, col_del = st.columns([4, 1])
                    with col_load:
                        if st.button(
                            f"📖 {date} — {topic} — Score: {score}",
                            key=f"quiz_load_{qi}",
                        ):
                            st.session_state["quiz_data"] = saved.get("quiz")
                            st.session_state.pop("quiz_submitted", None)
                            st.session_state.pop("quiz_audio", None)
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"quiz_del_{qi}"):
                            _delete_generated_content(
                                profile_id, "quiz", saved.get("id", "")
                            )
                            st.rerun()

        selected_topic = st.selectbox(
            "Sujet du dialogue", quiz_topics, key="quiz_topic"
        )

        if st.button("Generer le quiz", key="gen_quiz"):
            with st.spinner("L'IA cree un dialogue et des questions..."):
                prompt = (
                    f"Create a natural American English dialogue (12-15 lines) between two friends about: "
                    f"{selected_topic}. CEFR level: {quiz_level}.\n"
                    f"Use HEAVY connected speech (gonna, wanna, kinda, etc.), natural fillers, "
                    f"sarcasm, humor, and cultural references.\n\n"
                    f"Then create 5 comprehension questions that test:\n"
                    f"- Understanding of implied meaning (not just literal)\n"
                    f"- Tone and sarcasm detection\n"
                    f"- Vocabulary in context\n"
                    f"- What a character really means vs what they say\n\n"
                    f"Also extract 4-5 key informal expressions/chunks/reductions from the dialogue "
                    f"that are important to learn. For each, give the expression, its full/standard form, "
                    f"and a French translation.\n\n"
                    f"Format as JSON:\n"
                    f'{{"dialogue": "full dialogue text", '
                    f'"questions": ['
                    f'{{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], "correct": "A", "explanation_fr": "..."}}, '
                    f"...], "
                    f'"key_expressions": ['
                    f'{{"expression": "...", "full_form": "...", "french": "..."}}, ...'
                    f"]}}"
                )
                response, err = openrouter_chat(
                    [{"role": "user", "content": prompt}],
                    model=CHAT_MODEL,
                    temperature=0.7,
                    max_tokens=2000,
                )
                if err:
                    st.error(f"Erreur: {err}")
                else:
                    try:
                        cleaned = response.strip()
                        if cleaned.startswith("```"):
                            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                            cleaned = re.sub(r"\s*```$", "", cleaned)
                        quiz = json.loads(cleaned)
                        st.session_state["quiz_data"] = quiz
                        st.session_state.pop("quiz_submitted", None)
                        st.session_state.pop("quiz_audio", None)
                    except (json.JSONDecodeError, KeyError) as e:
                        st.error(f"Erreur format: {e}")
                        st.code(response)

        quiz = st.session_state.get("quiz_data")
        if quiz:
            # Audio
            if "quiz_audio" not in st.session_state:
                if st.button("🔊 Ecouter le dialogue", key="quiz_listen"):
                    with st.spinner("Generation audio..."):
                        audio_bytes, mime, err = generate_dual_voice_tts(
                            quiz["dialogue"], "echo", "nova", language_hint="en"
                        )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        else:
                            st.session_state["quiz_audio"] = {
                                "bytes": audio_bytes,
                                "mime": mime,
                            }
                            st.rerun()
            else:
                _audio_player_with_repeat(
                    st.session_state["quiz_audio"]["bytes"],
                    st.session_state["quiz_audio"]["mime"],
                    key="quiz_rpt",
                )

            with st.expander("Lire le dialogue (texte)"):
                st.text(quiz.get("dialogue", ""))

            st.markdown("---")
            questions = quiz.get("questions", [])
            user_quiz_answers = {}
            for qi, q in enumerate(questions):
                st.markdown(f"**Q{qi+1}.** {q['question']}")
                user_quiz_answers[qi] = st.radio(
                    f"Reponse Q{qi+1}",
                    q.get("options", []),
                    key=f"quiz_q_{qi}",
                    label_visibility="collapsed",
                )

            if st.button("Verifier mes reponses", key="quiz_check"):
                score = 0
                for qi, q in enumerate(questions):
                    selected = user_quiz_answers.get(qi, "")
                    correct_letter = q.get("correct", "")
                    is_correct = selected.startswith(correct_letter + ")")
                    if is_correct:
                        score += 1
                        st.success(f"Q{qi+1}: ✅ Correct !")
                    else:
                        st.error(
                            f"Q{qi+1}: ❌ Reponse: {correct_letter}) — {q.get('explanation_fr', '')}"
                        )

                total_pct = int(score / max(len(questions), 1) * 100)
                st.markdown(f"### Score final: {total_pct}% ({score}/{len(questions)})")

                if total_pct >= 80:
                    st.balloons()
                    st.success("Excellente comprehension !")
                elif total_pct >= 60:
                    st.info("Pas mal ! Reecoutez les passages difficiles.")
                else:
                    st.warning(
                        "Reecoutez le dialogue en lisant le texte, puis refaites le quiz."
                    )

                progress.setdefault("quiz_history", []).append(
                    {
                        "date": now_iso(),
                        "score": total_pct,
                        "topic": selected_topic,
                        "level": quiz_level,
                    }
                )
                if len(progress["quiz_history"]) > 50:
                    progress["quiz_history"] = progress["quiz_history"][-50:]
                _save_immersion_progress(profile_id, progress)

                # Update saved file with score
                quiz_cid = st.session_state.get("quiz_content_id")
                if quiz_cid:
                    saved_data = _load_generated_content(profile_id, "quiz", quiz_cid)
                    if saved_data:
                        saved_data["last_score"] = f"{total_pct}%"
                        _save_generated_content(
                            profile_id, "quiz", quiz_cid, saved_data
                        )

                # ── Key expressions → flashcards ─────────────────────
                key_exprs = quiz.get("key_expressions", [])
                if key_exprs:
                    st.markdown("---")
                    st.markdown("### 📝 Expressions cles du dialogue")
                    st.caption(
                        "Ajoutez ces expressions a vos flashcards pour les memoriser. "
                        "Lors de la revision, vous devrez construire une phrase correcte avec chaque expression."
                    )
                    vocab_entries = load_vocab(profile_id=profile_id)
                    existing_terms = {
                        e.get("term", "").lower()
                        for e in vocab_entries
                        if isinstance(e, dict)
                    }
                    for ki, kexpr in enumerate(key_exprs):
                        expr_text = kexpr.get("expression", "").strip()
                        full_form = kexpr.get("full_form", "").strip()
                        french = kexpr.get("french", "").strip()
                        if not expr_text:
                            continue
                        already = expr_text.lower() in existing_terms
                        col_i, col_b = st.columns([3, 1])
                        with col_i:
                            if already:
                                st.markdown(
                                    f"✅ **{expr_text}** ({full_form}) → {french} — *deja dans vos flashcards*"
                                )
                            else:
                                st.markdown(
                                    f"💡 **{expr_text}** ({full_form}) → {french}"
                                )
                        with col_b:
                            if not already:
                                if st.button("📝 Ajouter", key=f"quiz_flash_{ki}"):
                                    new_card = {
                                        "id": str(uuid.uuid4())[:8],
                                        "term": expr_text,
                                        "translation": french,
                                        "part_of_speech": "connected speech / slang",
                                        "explanation": f"Forme complete: {full_form}. Construisez une phrase avec '{expr_text}'.",
                                        "examples": [],
                                        "synonyms": [],
                                        "cefr_level": quiz_level,
                                        "added": now_iso(),
                                        "next_review": now_iso(),
                                        "interval": 1,
                                        "ease": 2.5,
                                        "repetitions": 0,
                                        "review_history": [],
                                        "source_lesson_id": f"quiz-{now_iso()[:10]}-{ki}",
                                        "profile_id": profile_id,
                                    }
                                    vocab_entries.append(new_card)
                                    save_vocab(vocab_entries, profile_id=profile_id)
                                    existing_terms.add(expr_text.lower())
                                    st.success(f"Flashcard ajoutee: {expr_text}")
                    not_added = [
                        ke
                        for ke in key_exprs
                        if ke.get("expression", "").strip()
                        and ke.get("expression", "").strip().lower()
                        not in existing_terms
                    ]
                    if len(not_added) > 1:
                        if st.button(
                            "📝 Ajouter toutes les expressions", key="quiz_flash_all"
                        ):
                            vocab_entries = load_vocab(profile_id=profile_id)
                            added = 0
                            for ki2, ke2 in enumerate(not_added):
                                et = ke2.get("expression", "").strip()
                                new_card = {
                                    "id": str(uuid.uuid4())[:8],
                                    "term": et,
                                    "translation": ke2.get("french", ""),
                                    "part_of_speech": "connected speech / slang",
                                    "explanation": f"Forme complete: {ke2.get('full_form', '')}. Construisez une phrase avec '{et}'.",
                                    "examples": [],
                                    "synonyms": [],
                                    "cefr_level": quiz_level,
                                    "added": now_iso(),
                                    "next_review": now_iso(),
                                    "interval": 1,
                                    "ease": 2.5,
                                    "repetitions": 0,
                                    "review_history": [],
                                    "source_lesson_id": f"quiz-{now_iso()[:10]}-bulk-{ki2}",
                                    "profile_id": profile_id,
                                }
                                vocab_entries.append(new_card)
                                added += 1
                            save_vocab(vocab_entries, profile_id=profile_id)
                            st.success(f"{added} flashcards ajoutees !")

    # ── Tab 5: Dialogues style sitcom ────────────────────────────────────────
    with tab_sitcom:
        st.subheader("Dialogues style sitcom americaine")
        st.markdown(
            "Des dialogues generes avec le rythme rapide, le sarcasme "
            "et les interruptions d'une sitcom comme **Friends** ou **The Office**.\n\n"
            "**5 variations** sont generees a chaque fois pour multiplier l'exposition. "
            "Choisissez les voix pour personnaliser l'ecoute."
        )

        default_level = profile.get("target_cefr", "B1")
        if default_level not in CEFR_LEVELS:
            default_level = "B1"
        sitcom_level = st.radio(
            "Niveau cible",
            CEFR_LEVELS,
            horizontal=True,
            index=CEFR_LEVELS.index(default_level),
            key="sitcom_level",
        )

        sitcom_scenarios = [
            "Roommates arguing about whose turn it is to do the dishes",
            "Two friends at a coffee shop judging everyone who walks in",
            "Someone accidentally sending a text to the wrong person",
            "Trying to split the bill at a restaurant and it goes wrong",
            "A friend who always shows up late with terrible excuses",
            "Helping a clueless friend prepare for a first date",
            "Debating an absurd topic way too seriously",
            "Trying to assemble furniture with zero instructions",
        ]

        sitcom_scenario = st.selectbox("Scenario", sitcom_scenarios, key="sitcom_scene")

        # ── Voice selection ──────────────────────────────────────────────
        VOICE_PAIRS = {
            "Homme / Femme": ("echo", "nova"),
            "Femme / Homme": ("nova", "echo"),
            "Homme / Homme": ("echo", "onyx"),
            "Femme / Femme": ("nova", "shimmer"),
            "Voix mixtes (alloy / fable)": ("alloy", "fable"),
        }
        voice_choice = st.selectbox(
            "Voix du dialogue (Alex / Jamie)",
            list(VOICE_PAIRS.keys()),
            key="sitcom_voice_pair",
        )
        voice_a, voice_b = VOICE_PAIRS[voice_choice]

        # ── Auto-load most recent saved sitcom on page reload ────────
        saved_sitcoms = _list_generated_content(profile_id, "sitcom")
        if "sitcom_variations" not in st.session_state:
            if saved_sitcoms:
                latest = saved_sitcoms[0]
                st.session_state["sitcom_variations"] = latest.get("variations", [])
                st.session_state["sitcom_var_idx"] = 0
                st.session_state["sitcom_content_id"] = latest.get("id", "")
            else:
                st.session_state["sitcom_variations"] = []
                st.session_state["sitcom_content_id"] = ""
        if "sitcom_var_idx" not in st.session_state:
            st.session_state["sitcom_var_idx"] = 0
        if saved_sitcoms:
            with st.expander(
                f"📂 Dialogues sauvegardes ({len(saved_sitcoms)})", expanded=False
            ):
                for si, saved in enumerate(saved_sitcoms):
                    scen = saved.get("scenario", "?")
                    date = saved.get("saved", "?")[:10]
                    nb = len(saved.get("variations", []))
                    col_load, col_del = st.columns([4, 1])
                    with col_load:
                        if st.button(
                            f"📖 {date} — {scen} ({nb} var.)", key=f"sitcom_load_{si}"
                        ):
                            st.session_state["sitcom_variations"] = saved.get(
                                "variations", []
                            )
                            st.session_state["sitcom_var_idx"] = 0
                            st.session_state["sitcom_content_id"] = saved.get("id", "")
                            for k in list(st.session_state.keys()):
                                if k.startswith("sitcom_audio_"):
                                    del st.session_state[k]
                            st.rerun()
                    with col_del:
                        if st.button("🗑️", key=f"sitcom_del_{si}"):
                            del_id = saved.get("id", "")
                            _delete_generated_content(profile_id, "sitcom", del_id)
                            # Also delete associated audio files
                            for _avi in range(10):
                                _afp = os.path.join(
                                    IMMERSION_GENERATED_DIR,
                                    f"sitcom-audio-{del_id}-{_avi}.mp3",
                                )
                                if os.path.exists(_afp):
                                    os.remove(_afp)
                            # Reset session if we deleted the currently loaded set
                            if st.session_state.get("sitcom_content_id") == del_id:
                                st.session_state.pop("sitcom_variations", None)
                                st.session_state.pop("sitcom_content_id", None)
                                st.session_state.pop("sitcom_var_idx", None)
                                for k in list(st.session_state.keys()):
                                    if k.startswith("sitcom_audio_"):
                                        del st.session_state[k]
                            st.rerun()

        if st.button("Generer 5 variations de dialogues", key="gen_sitcom"):
            variations = []
            progress_bar = st.progress(0, text="Generation des 5 variations...")
            for vi in range(5):
                progress_bar.progress(
                    (vi) / 5,
                    text=f"Generation de la variation {vi+1}/5...",
                )
                prompt = (
                    f"Write a hilarious American sitcom-style dialogue (15-20 lines) for this scenario: "
                    f"{sitcom_scenario}. CEFR level: {sitcom_level}.\n\n"
                    f"This is variation #{vi+1} of 5 — make each variation UNIQUE with different jokes, "
                    f"different angles on the scenario, and different expressions.\n\n"
                    f"Requirements:\n"
                    f"- Fast-paced, with interruptions, sarcasm, and running jokes\n"
                    f"- HEAVY use of connected speech: gonna, wanna, gotta, kinda, dunno, lemme, etc.\n"
                    f"- Natural fillers: 'I mean', 'like', 'you know', 'right?', 'dude', 'come on'\n"
                    f"- At least one dramatic pause or reaction\n"
                    f"- Chandler-style sarcasm or Joey-style obliviousness\n"
                    f"- Characters named Alex and Jamie\n\n"
                    f"Format (two speakers only, Alex: and Jamie:):\n"
                    f"Alex: line...\nJamie: line...\n\n"
                    f"After the dialogue, add:\n"
                    f"---VOCAB---\n"
                    f"List 5 key informal expressions used, with French translations, one per line as:\n"
                    f"expression | traduction"
                )
                response, err = openrouter_chat(
                    [{"role": "user", "content": prompt}],
                    model=CHAT_MODEL,
                    temperature=0.9,
                    max_tokens=1500,
                )
                if err:
                    st.error(f"Erreur variation {vi+1}: {err}")
                    continue
                parts = response.split("---VOCAB---")
                dialogue = parts[0].strip()
                vocab_notes = parts[1].strip() if len(parts) > 1 else ""
                variations.append(
                    {
                        "text": dialogue,
                        "vocab": vocab_notes,
                        "scenario": sitcom_scenario,
                    }
                )

            progress_bar.progress(1.0, text="Termine !")
            if variations:
                content_id = now_iso()[:19].replace(":", "-").replace("T", "-")
                _save_generated_content(
                    profile_id,
                    "sitcom",
                    content_id,
                    {
                        "scenario": sitcom_scenario,
                        "level": sitcom_level,
                        "variations": variations,
                    },
                )
                st.session_state["sitcom_variations"] = variations
                st.session_state["sitcom_var_idx"] = 0
                st.session_state["sitcom_content_id"] = content_id
                # Clear all cached audio
                for k in list(st.session_state.keys()):
                    if k.startswith("sitcom_audio_"):
                        del st.session_state[k]
                st.rerun()

        variations = st.session_state.get("sitcom_variations", [])
        if variations:
            # Navigation between variations
            var_idx = st.session_state.get("sitcom_var_idx", 0)
            st.markdown(f"### Variation {var_idx + 1} / {len(variations)}")
            nav_cols = st.columns([1, 1, 3])
            with nav_cols[0]:
                if st.button(
                    "⬅️ Precedente", key="sitcom_prev", disabled=(var_idx == 0)
                ):
                    st.session_state["sitcom_var_idx"] = var_idx - 1
                    st.rerun()
            with nav_cols[1]:
                if st.button(
                    "Suivante ➡️",
                    key="sitcom_next",
                    disabled=(var_idx >= len(variations) - 1),
                ):
                    st.session_state["sitcom_var_idx"] = var_idx + 1
                    st.rerun()

            sitcom = variations[var_idx]
            st.text(sitcom["text"])

            # Audio with selected voices — persisted to disk
            audio_key = f"sitcom_audio_{var_idx}"
            _sitcom_cid = st.session_state.get("sitcom_content_id", "")
            _sitcom_audio_fpath = (
                os.path.join(
                    IMMERSION_GENERATED_DIR, f"sitcom-audio-{_sitcom_cid}-{var_idx}.mp3"
                )
                if _sitcom_cid
                else ""
            )
            # Reload audio from disk if not in session
            if (
                audio_key not in st.session_state
                and _sitcom_audio_fpath
                and os.path.exists(_sitcom_audio_fpath)
            ):
                with open(_sitcom_audio_fpath, "rb") as _af:
                    st.session_state[audio_key] = {
                        "bytes": _af.read(),
                        "mime": "audio/mp3",
                    }
            if audio_key not in st.session_state:
                if st.button(
                    f"🔊 Ecouter ({voice_choice})", key=f"sitcom_listen_{var_idx}"
                ):
                    with st.spinner("Generation audio 2 voix..."):
                        audio_bytes, mime, err = generate_dual_voice_tts(
                            sitcom["text"], voice_a, voice_b, language_hint="en"
                        )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        else:
                            st.session_state[audio_key] = {
                                "bytes": audio_bytes,
                                "mime": mime,
                            }
                            # Persist audio to disk
                            if _sitcom_cid:
                                os.makedirs(IMMERSION_GENERATED_DIR, exist_ok=True)
                                with open(_sitcom_audio_fpath, "wb") as _af:
                                    _af.write(audio_bytes)
                            st.rerun()
            else:
                _audio_player_with_repeat(
                    st.session_state[audio_key]["bytes"],
                    st.session_state[audio_key]["mime"],
                    key=f"sitcom_rpt_{var_idx}",
                )
                if st.button(
                    "🔄 Regenerer l'audio avec d'autres voix",
                    key=f"sitcom_regen_audio_{var_idx}",
                ):
                    del st.session_state[audio_key]
                    # Delete old audio file so new one can be generated
                    if _sitcom_audio_fpath and os.path.exists(_sitcom_audio_fpath):
                        os.remove(_sitcom_audio_fpath)
                    st.rerun()

            if sitcom.get("vocab"):
                with st.expander("📝 Vocabulaire du dialogue — ajouter aux flashcards"):
                    vocab_lines = [
                        ln.strip() for ln in sitcom["vocab"].split("\n") if ln.strip()
                    ]
                    parsed_vocab = []
                    for line in vocab_lines:
                        if "|" in line:
                            parts = line.split("|", 1)
                            parsed_vocab.append(
                                {
                                    "expression": parts[0].strip().strip("-•* "),
                                    "french": parts[1].strip(),
                                }
                            )
                        elif line:
                            st.markdown(f"- {line}")

                    if parsed_vocab:
                        vocab_entries = load_vocab(profile_id=profile_id)
                        existing_terms = {
                            e.get("term", "").lower()
                            for e in vocab_entries
                            if isinstance(e, dict)
                        }

                        for vi, pv in enumerate(parsed_vocab):
                            expr = pv["expression"]
                            french = pv["french"]
                            already = expr.lower() in existing_terms
                            col_i, col_b = st.columns([3, 1])
                            with col_i:
                                if already:
                                    st.markdown(
                                        f"✅ **{expr}** → {french} — *deja dans vos flashcards*"
                                    )
                                else:
                                    st.markdown(f"💡 **{expr}** → {french}")
                            with col_b:
                                if not already:
                                    if st.button(
                                        "📝 Ajouter",
                                        key=f"sitcom_flash_{var_idx}_{vi}",
                                    ):
                                        new_card = {
                                            "id": str(uuid.uuid4())[:8],
                                            "term": expr,
                                            "translation": french,
                                            "part_of_speech": "idiom / slang",
                                            "explanation": f"Expression de sitcom US. Construisez une phrase avec '{expr}'.",
                                            "examples": [],
                                            "synonyms": [],
                                            "cefr_level": sitcom_level,
                                            "added": now_iso(),
                                            "next_review": now_iso(),
                                            "interval": 1,
                                            "ease": 2.5,
                                            "repetitions": 0,
                                            "review_history": [],
                                            "source_lesson_id": f"sitcom-{now_iso()[:10]}-v{var_idx}-{vi}",
                                            "profile_id": profile_id,
                                        }
                                        vocab_entries.append(new_card)
                                        save_vocab(vocab_entries, profile_id=profile_id)
                                        existing_terms.add(expr.lower())
                                        st.success(f"Flashcard ajoutee: {expr}")

                        not_added = [
                            pv
                            for pv in parsed_vocab
                            if pv["expression"].lower() not in existing_terms
                        ]
                        if len(not_added) > 1:
                            if st.button(
                                "📝 Ajouter tout le vocabulaire",
                                key=f"sitcom_flash_all_{var_idx}",
                            ):
                                vocab_entries = load_vocab(profile_id=profile_id)
                                added = 0
                                for vi2, pv2 in enumerate(not_added):
                                    new_card = {
                                        "id": str(uuid.uuid4())[:8],
                                        "term": pv2["expression"],
                                        "translation": pv2["french"],
                                        "part_of_speech": "idiom / slang",
                                        "explanation": f"Expression de sitcom US. Construisez une phrase avec '{pv2['expression']}'.",
                                        "examples": [],
                                        "synonyms": [],
                                        "cefr_level": sitcom_level,
                                        "added": now_iso(),
                                        "next_review": now_iso(),
                                        "interval": 1,
                                        "ease": 2.5,
                                        "repetitions": 0,
                                        "review_history": [],
                                        "source_lesson_id": f"sitcom-{now_iso()[:10]}-v{var_idx}-bulk-{vi2}",
                                        "profile_id": profile_id,
                                    }
                                    vocab_entries.append(new_card)
                                    added += 1
                                save_vocab(vocab_entries, profile_id=profile_id)
                                st.success(f"{added} flashcards ajoutees !")

    # ── Tab 6: Controle de vitesse ───────────────────────────────────────────
    with tab_speed:
        st.subheader("Controle de vitesse — Entrainement progressif")
        st.markdown(
            "Les Americains parlent a un debit d'environ **150-180 mots/min**. "
            "Les series comme Friends montent a **180-220 mots/min**.\n\n"
            "Entrez ou collez un texte anglais, choisissez un debit, et ecoutez.\n"
            "Commencez lent (0.85x) et montez progressivement."
        )

        speed = st.slider(
            "Vitesse de parole",
            min_value=0.7,
            max_value=1.5,
            value=1.0,
            step=0.05,
            format="%.2fx",
            key="speed_control",
        )

        speed_labels = {
            0.7: "Tres lent",
            0.85: "Lent",
            1.0: "Normal",
            1.15: "Rapide (sitcom)",
            1.3: "Tres rapide",
            1.5: "Defi natif",
        }
        closest = min(speed_labels.keys(), key=lambda x: abs(x - speed))
        st.caption(f"Debit: **{speed_labels.get(closest, '')}**")

        speed_voice = st.selectbox(
            "Voix",
            ["echo", "nova", "alloy", "onyx", "shimmer", "fable"],
            key="speed_voice",
        )

        speed_text = st.text_area(
            "Texte a lire (anglais)",
            value="Hey, you know what? I've been thinking about it, and honestly, "
            "I'm kinda done with this whole situation. Like, I dunno, "
            "it's just not worth the stress anymore, you know what I mean? "
            "I'm gonna take a step back and figure things out. "
            "Maybe I shoulda done that a long time ago.",
            height=150,
            key="speed_text",
        )

        if st.button("🔊 Generer l'audio a cette vitesse", key="speed_gen"):
            if not speed_text.strip():
                st.warning("Entrez un texte d'abord.")
            else:
                with st.spinner(f"Generation audio a {speed:.2f}x..."):
                    # We use standard TTS and note that OpenAI TTS has a speed parameter
                    # but OpenRouter may not support it directly, so we generate normally
                    # and inform the user about the speed concept
                    audio_bytes, mime, err = text_to_speech_openrouter(
                        speed_text, voice=speed_voice, language_hint="en"
                    )
                    if err:
                        st.error(f"Erreur TTS: {err}")
                    else:
                        st.session_state["speed_audio"] = {
                            "bytes": audio_bytes,
                            "mime": mime,
                            "speed": speed,
                        }
                        st.rerun()

        if "speed_audio" in st.session_state:
            sa = st.session_state["speed_audio"]
            _audio_player_with_repeat(sa["bytes"], sa["mime"], key="speed_rpt")
            st.caption(
                "💡 **Astuce**: utilisez les commandes de vitesse de votre lecteur "
                "multimedia pour ajuster la vitesse de lecture (la plupart des navigateurs "
                "supportent 0.5x a 2x via clic droit sur le lecteur audio)."
            )

        st.markdown("---")

        # ── Extraire les expressions cles du texte ───────────────────────
        st.markdown("#### 📝 Extraire les expressions a apprendre")
        st.caption(
            "Analysez le texte ci-dessus pour identifier les contractions, "
            "chunks et expressions informelles. Ajoutez-les a vos flashcards."
        )
        if st.button(
            "🔍 Analyser le texte et proposer des flashcards", key="speed_extract"
        ):
            if not speed_text.strip():
                st.warning("Entrez un texte d'abord.")
            else:
                with st.spinner("Analyse des expressions..."):
                    extract_prompt = (
                        f"Analyze this American English text and extract ALL connected speech reductions, "
                        f"contractions, chunks, slang, and informal expressions worth learning:\n\n"
                        f'"{speed_text}"\n\n'
                        f"For each expression, give:\n"
                        f"- expression: the informal/reduced form\n"
                        f"- full_form: the standard/complete form\n"
                        f"- french: French translation\n\n"
                        f"Return ONLY a JSON array:\n"
                        f'[{{"expression": "...", "full_form": "...", "french": "..."}}, ...]'
                    )
                    resp, err = openrouter_chat(
                        [{"role": "user", "content": extract_prompt}],
                        model=CHAT_MODEL,
                        temperature=0.3,
                        max_tokens=1000,
                    )
                    if err:
                        st.error(f"Erreur: {err}")
                    else:
                        try:
                            cleaned = resp.strip()
                            if cleaned.startswith("```"):
                                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                                cleaned = re.sub(r"\s*```$", "", cleaned)
                            extracted = json.loads(cleaned)
                            st.session_state["speed_extracted"] = extracted
                        except (json.JSONDecodeError, KeyError) as e:
                            st.error(f"Erreur format: {e}")
                            st.code(resp)

        extracted = st.session_state.get("speed_extracted", [])
        if extracted:
            vocab_entries = load_vocab(profile_id=profile_id)
            existing_terms = {
                e.get("term", "").lower() for e in vocab_entries if isinstance(e, dict)
            }
            for ei, ext in enumerate(extracted):
                expr = ext.get("expression", "").strip()
                full = ext.get("full_form", "").strip()
                french = ext.get("french", "").strip()
                if not expr:
                    continue
                already = expr.lower() in existing_terms
                col_i, col_b = st.columns([3, 1])
                with col_i:
                    if already:
                        st.markdown(
                            f"✅ **{expr}** ({full}) → {french} — *deja dans vos flashcards*"
                        )
                    else:
                        st.markdown(f"💡 **{expr}** ({full}) → {french}")
                with col_b:
                    if not already:
                        if st.button("📝 Ajouter", key=f"speed_flash_{ei}"):
                            new_card = {
                                "id": str(uuid.uuid4())[:8],
                                "term": expr,
                                "translation": french,
                                "part_of_speech": "connected speech / slang",
                                "explanation": f"Forme complete: {full}. Construisez une phrase avec '{expr}'.",
                                "examples": [],
                                "synonyms": [],
                                "cefr_level": "B2",
                                "added": now_iso(),
                                "next_review": now_iso(),
                                "interval": 1,
                                "ease": 2.5,
                                "repetitions": 0,
                                "review_history": [],
                                "source_lesson_id": f"speed-{now_iso()[:10]}-{ei}",
                                "profile_id": profile_id,
                            }
                            vocab_entries.append(new_card)
                            save_vocab(vocab_entries, profile_id=profile_id)
                            existing_terms.add(expr.lower())
                            st.success(f"Flashcard ajoutee: {expr}")
            not_added = [
                ex
                for ex in extracted
                if ex.get("expression", "").strip()
                and ex.get("expression", "").strip().lower() not in existing_terms
            ]
            if len(not_added) > 1:
                if st.button(
                    "📝 Ajouter toutes les expressions", key="speed_flash_all"
                ):
                    vocab_entries = load_vocab(profile_id=profile_id)
                    added = 0
                    for ei2, ex2 in enumerate(not_added):
                        et = ex2.get("expression", "").strip()
                        new_card = {
                            "id": str(uuid.uuid4())[:8],
                            "term": et,
                            "translation": ex2.get("french", ""),
                            "part_of_speech": "connected speech / slang",
                            "explanation": f"Forme complete: {ex2.get('full_form', '')}. Construisez une phrase avec '{et}'.",
                            "examples": [],
                            "synonyms": [],
                            "cefr_level": "B2",
                            "added": now_iso(),
                            "next_review": now_iso(),
                            "interval": 1,
                            "ease": 2.5,
                            "repetitions": 0,
                            "review_history": [],
                            "source_lesson_id": f"speed-{now_iso()[:10]}-bulk-{ei2}",
                            "profile_id": profile_id,
                        }
                        vocab_entries.append(new_card)
                        added += 1
                    save_vocab(vocab_entries, profile_id=profile_id)
                    st.success(f"{added} flashcards ajoutees !")

        st.markdown("---")
        st.markdown(
            "**Progression recommandee:**\n"
            "| Semaine | Vitesse | Objectif |\n"
            "|---------|---------|----------|\n"
            "| 1-2 | 0.85x | Comprendre chaque mot |\n"
            "| 3-4 | 1.0x | Comprendre le sens general |\n"
            "| 5-6 | 1.15x | Suivre une conversation naturelle |\n"
            "| 7+ | 1.3x+ | Comprendre Friends sans sous-titres |"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# LECONS ANGLAIS REEL — Mini-series americaines (A1 -> C2)
# ═══════════════════════════════════════════════════════════════════════════════
