import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st

from modules.ai_client import openrouter_chat, openrouter_headers
from modules.config import *
from modules.lessons import load_lesson_pack, load_quick_variations
from modules.profiles import get_active_profile, load_profiles
from modules.real_english import _load_real_english_lesson
from modules.shadowing import _split_shadowing_chunks, load_shadowing_texts
from modules.utils import (
    _parse_iso,
    _seconds_between_iso,
    _seconds_since_iso,
    ext_from_mime,
    extract_json_from_text,
    now_iso,
    save_audio_bytes,
    slugify,
    utc_now,
)


def _normalize_translation_candidate(text):
    clean = str(text or "").strip()
    clean = re.sub(r"^[A-Za-z]\s*:\s*", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _is_valid_translation_candidate(text):
    clean = _normalize_translation_candidate(text)
    if not clean:
        return False
    # Reject truncated phrases ending with "..."
    if clean.endswith("..."):
        return False
    wc = len(clean.split())
    if wc < 4 or wc > 18:
        return False
    if re.search(r"https?://", clean, flags=re.IGNORECASE):
        return False
    return True


def _build_translation_targets(
    profile_id, lesson_context, max_total=36, max_per_lesson=6
):
    lesson_context = lesson_context or {}
    focus_items = lesson_context.get("focus_items", [])
    if not isinstance(focus_items, list) or not focus_items:
        return []

    shadowing_by_source = {
        str(item.get("source_id", "")).strip(): item
        for item in load_shadowing_texts(profile_id)
        if isinstance(item, dict) and str(item.get("source_id", "")).strip()
    }

    targets = []
    seen_expected = set()
    for item in focus_items:
        if not isinstance(item, dict):
            continue

        lesson_label = str(item.get("title") or item.get("theme") or "").strip()
        source_id = str(item.get("source_id", "")).strip()
        if not lesson_label:
            lesson_label = source_id or "Lecon"

        candidates = []
        dialogue_text_val = ""
        shadow_entry = shadowing_by_source.get(source_id)
        if shadow_entry:
            # Prefer full sentences (chunks) over key-phrase fragments (chunk_focus)
            candidates.extend(shadow_entry.get("chunks") or [])
            # Only add chunk_focus entries that are complete (not ending with "...")
            for cf in shadow_entry.get("chunk_focus") or []:
                if not str(cf or "").strip().endswith("..."):
                    candidates.append(cf)
            dialogue_text_val = shadow_entry.get("dialogue_text", "")
        elif source_id.startswith("real-english-"):
            lesson_id = source_id.replace("real-english-", "", 1)
            loaded = _load_real_english_lesson(profile_id, lesson_id)
            if isinstance(loaded, dict):
                candidates.extend(_split_shadowing_chunks(loaded.get("dialogue", "")))
                dialogue_text_val = loaded.get("dialogue", "")

        added_for_lesson = 0
        for raw in candidates:
            expected = _normalize_translation_candidate(raw)
            if not _is_valid_translation_candidate(expected):
                continue
            key = expected.lower()
            if key in seen_expected:
                continue

            targets.append(
                {
                    "lesson": lesson_label,
                    "expected_english": expected,
                    "source_id": source_id,
                    "dialogue_text": dialogue_text_val,
                }
            )
            seen_expected.add(key)
            added_for_lesson += 1

            if added_for_lesson >= max_per_lesson or len(targets) >= max_total:
                break

        if len(targets) >= max_total:
            break

    return targets


def _translation_target_key(target):
    source_id = str(target.get("source_id") or "").strip()
    expected = str(target.get("expected_english") or "").strip().lower()
    return f"{source_id}|{expected}"


def _translate_target_to_french(session_data, target):
    if not isinstance(target, dict):
        return ""

    expected = str(target.get("expected_english") or "").strip()
    if not expected:
        return ""

    cache = session_data.setdefault("translation_prompt_cache", {})
    cache_key = expected.lower()
    cached = cache.get(cache_key)
    if cached:
        return str(cached)

    prompt = (
        "Translate this English sentence into natural French. "
        "Keep the same meaning and everyday tone. "
        "Return ONLY the French sentence, no quotes, no explanation.\n"
        f"English: {expected}"
    )
    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.2,
        max_tokens=120,
    )
    if err or not text:
        return expected

    fr_sentence = str(text).strip()
    fr_sentence = re.sub(r"^```[a-z]*\n?|```$", "", fr_sentence, flags=re.MULTILINE)
    fr_sentence = fr_sentence.strip().strip('"').strip("'")
    fr_sentence = re.sub(r"\s+", " ", fr_sentence).strip()
    if not fr_sentence:
        return expected

    cache[cache_key] = fr_sentence
    return fr_sentence


def _select_next_translation_target(
    session_data, prefer_lesson=None, exclude_expected=None
):
    targets = session_data.get("translation_targets", [])
    if not isinstance(targets, list) or not targets:
        return None

    mastered = set(session_data.get("translation_mastered", []))
    exclude_expected_norm = str(exclude_expected or "").strip().lower()

    unresolved = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        key = _translation_target_key(target)
        if key in mastered:
            continue
        expected_norm = str(target.get("expected_english") or "").strip().lower()
        if exclude_expected_norm and expected_norm == exclude_expected_norm:
            continue
        unresolved.append(target)

    if not unresolved:
        return None

    selected_pool = unresolved
    if prefer_lesson:
        lesson_norm = str(prefer_lesson).strip().lower()
        lesson_matches = [
            t
            for t in unresolved
            if str(t.get("lesson") or "").strip().lower() == lesson_norm
        ]
        if lesson_matches:
            selected_pool = lesson_matches

    mode = str(session_data.get("mode", "guided")).lower()
    if mode == "free":
        idx = int(session_data.get("translation_next_idx", 0) or 0)
        picked = selected_pool[idx % len(selected_pool)]
        session_data["translation_next_idx"] = idx + 1
        return picked

    return selected_pool[0]


def _question_prompt_from_target(session_data, target, direction="fr_to_en"):
    expected_en = str(target.get("expected_english") or "").strip()
    if direction == "en_to_fr":
        return expected_en
    return _translate_target_to_french(session_data, target)


def _generate_contextual_question(session_data, target, direction="fr_to_en"):
    """Generate a contextual translation question with a mini scenario instead of a bare phrase."""
    expected_en = str(target.get("expected_english") or "").strip()
    if not expected_en:
        return None

    cache = session_data.setdefault("contextual_question_cache", {})
    # Versioned cache key so stricter prompt/validation can invalidate older noisy items.
    cache_key = f"v5|{direction}|{expected_en.lower()}"
    cached = cache.get(cache_key)
    if cached:
        return str(cached)

    dialogue_context = str(target.get("dialogue_text") or "").strip()
    if dialogue_context and len(dialogue_context) > 600:
        dialogue_context = dialogue_context[:600] + "..."

    expected_fr = _translate_target_to_french(session_data, target)

    def _norm_for_match(text):
        txt = str(text or "").lower()
        txt = (
            txt.replace("«", '"').replace("»", '"').replace("“", '"').replace("”", '"')
        )
        txt = re.sub(r"\s+", " ", txt).strip()
        return txt

    if direction == "fr_to_en":
        # AI speaks FRENCH, user must translate to English
        phrase_to_translate = _translate_target_to_french(session_data, target)
        context_block = ""
        if dialogue_context:
            context_block = (
                "\n\nVoici le dialogue d'origine (utilise-le pour créer la mise en situation, "
                "sans dévoiler l'histoire) :\n"
                f'"""\n{dialogue_context}\n"""'
            )
        prompt = (
            "Tu es un professeur de langues. "
            "Génère une mise en situation concrète (2-3 phrases) ENTIÈREMENT EN FRANÇAIS "
            "puis demande à l'élève de traduire la phrase ci-dessous en anglais. "
            "Mets la phrase à traduire entre guillemets « ». "
            f"{context_block}\n\n"
            f"Phrase à traduire : « {phrase_to_translate} »\n\n"
            "Exemple :\n"
            "Tu retrouves un vieil ami au café après des années. Comment tu dis « Ça fait longtemps ! » en anglais ?\n\n"
            "RÈGLES STRICTES :\n"
            "- Écris TOUT en français (mise en situation + question)\n"
            "- Commence par un vrai contexte avant la question (pas seulement une question sèche)\n"
            "- Ce texte sera lu en audio: il doit être naturel en français\n"
            "- NE DONNE JAMAIS la traduction anglaise dans ta réponse\n"
            "- NE DONNE JAMAIS la réponse\n"
            "- N'ajoute PAS de section 'Réponse' ni 'Correction'\n"
            "- Retourne UNIQUEMENT la mise en situation + question, rien d'autre"
        )
        forbidden_language_markers = [
            "how do you",
            "howdo you",
            "how would you",
            "translate into",
            "in english",
            "in french",
            "answer:",
            "solution:",
        ]
        answer_to_block = expected_en
    else:
        # AI speaks ENGLISH, user must translate to French
        phrase_to_translate = expected_en
        context_block = ""
        if dialogue_context:
            context_block = (
                "\n\nHere is the original dialogue (use it to build the scenario, "
                "without revealing the full story):\n"
                f'"""\n{dialogue_context}\n"""'
            )
        prompt = (
            "You are a language teacher creating an English-to-French translation exercise. "
            "Generate a concrete short scenario (2-3 sentences) ENTIRELY IN ENGLISH, "
            "then ask the student to translate the English phrase below into French. "
            "Put the phrase to translate in double quotes. "
            f"{context_block}\n\n"
            f'English phrase to translate: "{phrase_to_translate}"\n\n'
            "Example:\n"
            'You\'re meeting someone new at work. How would you say "Nice to meet you" in French?\n\n'
            "STRICT RULES:\n"
            "- Write EVERYTHING in English — no French words allowed in the scenario or question\n"
            "- Do NOT use French words like 'tu', 'vous', 'dans', 'une', 'des', 'imagine que', etc.\n"
            "- Start with real English context before the question (not a bare question)\n"
            "- This text will be read aloud in English audio: it must sound natural in English\n"
            "- NEVER include the French translation in your response\n"
            "- NEVER give the answer\n"
            "- Do NOT add any 'Answer' or 'Correction' section\n"
            "- Return ONLY the English scenario + English question, nothing else"
        )
        forbidden_language_markers = [
            "comment dit-on",
            "traduis",
            "en anglais",
            "en français",
            "réponse",
            "correction",
            "solution",
        ]
        # Only block this when French translation differs from source sentence.
        answer_to_block = (
            expected_fr
            if _norm_for_match(expected_fr) != _norm_for_match(expected_en)
            else ""
        )

    phrase_norm = _norm_for_match(phrase_to_translate)
    answer_norm = _norm_for_match(answer_to_block)

    def _candidate_is_valid(candidate):
        text = str(candidate or "").strip()
        if len(text) < 10:
            return False

        norm = _norm_for_match(text)

        # Ensure the asked phrase is actually present in the question.
        if phrase_norm and phrase_norm not in norm:
            return False

        # Never leak the expected answer in the generated question.
        if answer_norm and answer_norm in norm:
            return False

        if re.search(r"\b(answer|réponse|solution|correction)\b", norm):
            return False

        # Force contextual style: one context clause + one question.
        if "?" not in text:
            return False
        if "." not in text and "!" not in text and ":" not in text:
            return False

        for marker in forbidden_language_markers:
            if marker in norm:
                return False

        if direction == "fr_to_en":
            # Reject English-framed question variants like "howdo you say ... in english".
            if re.search(r"\bhow\s*do\s*you\b|\bhowdo\s*you\b|\bin\s+english\b", norm):
                return False
            # Ensure clearly French framing.
            if not re.search(
                r"\b(comment|dans|situation|imagine|contexte|tu|vous|au|aux|le|la|les|un|une|des|en anglais)\b",
                norm,
            ):
                return False
        else:
            # Reject French-framed question variants (including French-specific pronouns/articles).
            if re.search(
                r"\bcomment\b|\ben\s+anglais\b|\btraduis\b"
                r"|\b(tu|vous|une|des|dans|aussi|donc|votre|notre|leur|voici|depuis)\b",
                norm,
            ):
                return False
            # Ensure clearly English framing (require unambiguous English words).
            if not re.search(
                r"\b(how|would|could|you|in french|say)\b",
                norm,
            ):
                return False

        return True

    # Try twice with a stricter second attempt if needed.
    for temp in (0.35, 0.2):
        raw, err = openrouter_chat(
            [{"role": "user", "content": prompt}],
            CHAT_MODEL,
            temperature=temp,
            max_tokens=140,
        )
        if err or not raw:
            continue

        result = str(raw).strip().strip('"').strip("'").strip()
        if _candidate_is_valid(result):
            cache[cache_key] = result
            return result

    # Deterministic fallback to guarantee language + no-answer leak.
    if direction == "en_to_fr":
        fallback = f'Imagine a real-life moment. In this situation, how would you say "{phrase_to_translate}" in French?'
    else:
        fallback = f"Imagine une scène de la vie quotidienne. Dans cette situation, comment dirais-tu « {phrase_to_translate} » en anglais ?"

    cache[cache_key] = fallback
    return fallback


def _format_translation_question(session_data, target, direction="fr_to_en"):
    """Return a contextual translation question, falling back to the classic format."""
    contextual = _generate_contextual_question(session_data, target, direction)
    if contextual:
        return contextual

    prompt_text = _question_prompt_from_target(session_data, target, direction)
    if direction == "en_to_fr":
        return f"How do you translate into French: « {prompt_text} » ?"
    return f"Comment dit-on en anglais : « {prompt_text} » ?"


def _extract_tts_narration(contextual_question, direction="fr_to_en"):
    """Extract the scenario/context portion and phrase from a contextual translation question.

    Returns (scenario, phrase_to_translate).
    """
    text = str(contextual_question or "").strip()
    if not text:
        return "", ""

    # Extract the phrase between « » or " "
    if direction == "fr_to_en":
        phrase_match = re.search(r'[«""]([^«»""]+)[»""]', text)
        split_pattern = r'(?:Comment\s+(?:dit-on|dirais-tu|tu\s+dis|diriez-vous)[^«»"]*[«"][^«»"]*[»"][^?]*\??)'
    else:
        phrase_match = re.search(r'["""]([^"""]+)["""]', text)
        split_pattern = r'(?:How\s+(?:would|do|could)\s+you\s+(?:say|translate)[^"""]*["""][^"""]*["""][^?]*\??)'

    phrase_to_translate = phrase_match.group(1).strip() if phrase_match else ""

    # Try to split: keep scenario, remove translation question
    match = re.search(split_pattern, text, re.IGNORECASE)
    if match:
        scenario = text[: match.start()].strip()
        if scenario:
            return scenario, phrase_to_translate

    # Fallback: split at last '?' — everything before it that looks like context
    last_q = text.rfind("?")
    if last_q > 0:
        before_q = text[:last_q]
        for sep in [". ", "! ", ".\n", "!\n"]:
            idx = before_q.rfind(sep)
            if idx > 0:
                scenario = text[: idx + 1].strip()
                if len(scenario) > 10:
                    return scenario, phrase_to_translate

    return "", phrase_to_translate


def _build_tts_text(contextual_question, phrase_to_translate, direction="fr_to_en"):
    """Build deterministic TTS text: scenario + fixed translation prompt.

    Always appends a clear 'Comment dirais-tu «xxx» en anglais ?'
    or 'How would you say "xxx" in French?' so TTS reads it verbatim.
    """
    scenario, extracted_phrase = _extract_tts_narration(contextual_question, direction)
    phrase = phrase_to_translate or extracted_phrase
    if not phrase:
        return str(contextual_question or "").strip()

    if direction == "fr_to_en":
        question = f"Comment dirais-tu « {phrase} » en anglais ?"
    else:
        question = f'How would you say "{phrase}" in French?'

    if scenario:
        return f"{scenario} {question}"
    return question


def _starter_translation_question_text(session_data):
    meta = session_data.get("starter_drill_meta")
    if not isinstance(meta, dict):
        return str(session_data.get("starter_ai_text") or "").strip()

    direction = str(meta.get("direction") or "fr_to_en")
    prompt_text = str(meta.get("prompt_text") or "").strip()
    if not prompt_text:
        return str(session_data.get("starter_ai_text") or "").strip()

    contextual = str(meta.get("contextual_question") or "").strip()
    if contextual:
        return contextual

    if direction == "en_to_fr":
        return f"How do you translate into French: {prompt_text} ?"
    return f"Comment dit-on en anglais : {prompt_text} ?"


def _evaluate_translation_attempt(
    session_data,
    target,
    learner_text,
    direction="fr_to_en",
    target_cefr="B1",
):
    expected_en = str(target.get("expected_english") or "").strip()
    expected_fr = _translate_target_to_french(session_data, target)
    expected = expected_en if direction == "fr_to_en" else expected_fr
    learner = str(learner_text or "").strip()
    if not expected or not learner:
        return {
            "correct": False,
            "score": 0,
            "feedback": "Réponse vide ou incomplète.",
            "corrected_answer": expected,
            "expected_answer": expected,
        }

    target = str(target_cefr or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"

    if direction == "en_to_fr":
        prompt = (
            "Evaluate a learner English->French translation. "
            f"Target CEFR: {target}. "
            "IMPORTANT: The learner answer comes from AUDIO (speech-to-text), so IGNORE all punctuation issues "
            "(missing commas, periods, capitalization, apostrophes, etc.). "
            "The expected answer below is ONE possible translation, but the learner may give a DIFFERENT "
            "but equally valid translation. Accept ANY French translation that correctly conveys the same meaning, "
            "even if the wording, structure, or vocabulary is completely different from the expected answer. "
            "Only mark incorrect if the meaning is genuinely wrong or a key element is missing. "
            "If the learner's answer is valid but different, mark correct and mention the alternative in feedback. "
            "Return ONLY JSON with this schema: "
            '{"correct":true/false,"score":0-100,"feedback":"brief feedback in French","corrected_answer":"natural corrected French sentence"}.\n\n'
            f"Expected French (one possible answer): {expected}\n"
            f"Learner answer: {learner}"
        )
    else:
        prompt = (
            "Evaluate a learner French->English translation. "
            f"Target CEFR: {target}. "
            "IMPORTANT: The learner answer comes from AUDIO (speech-to-text), so IGNORE all punctuation issues "
            "(missing commas, periods, capitalization, apostrophes, etc.). "
            "The expected answer below is ONE possible translation, but the learner may give a DIFFERENT "
            "but equally valid translation. Accept ANY English translation that correctly conveys the same meaning, "
            "even if the wording, structure, or vocabulary is completely different from the expected answer. "
            "Only mark incorrect if the meaning is genuinely wrong or a key element is missing. "
            "If the learner's answer is valid but different, mark correct and mention the alternative in feedback. "
            "Return ONLY JSON with this schema: "
            '{"correct":true/false,"score":0-100,"feedback":"brief feedback in French","corrected_answer":"natural corrected English sentence"}.\n\n'
            f"Expected English (one possible answer): {expected}\n"
            f"Learner answer: {learner}"
        )
    raw, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        EVAL_MODEL,
        temperature=0.1,
        max_tokens=220,
    )

    if err:
        ratio = SequenceMatcher(None, expected.lower(), learner.lower()).ratio()
        score = int(round(ratio * 100))
        return {
            "correct": score >= 60,
            "score": score,
            "feedback": "Évaluation automatique (fallback).",
            "corrected_answer": expected,
            "expected_answer": expected,
        }

    parsed = extract_json_from_text(raw)
    if not isinstance(parsed, dict):
        ratio = SequenceMatcher(None, expected.lower(), learner.lower()).ratio()
        score = int(round(ratio * 100))
        return {
            "correct": score >= 60,
            "score": score,
            "feedback": "Évaluation automatique (fallback).",
            "corrected_answer": expected,
            "expected_answer": expected,
        }

    try:
        score = int(parsed.get("score", 0))
    except Exception:
        score = 0
    score = max(0, min(100, score))

    corrected = str(parsed.get("corrected_answer", "")).strip() or expected
    return {
        "correct": bool(parsed.get("correct", False)),
        "score": score,
        "feedback": str(parsed.get("feedback", "")).strip(),
        "corrected_answer": corrected,
        "expected_answer": expected,
    }


def _propose_translation_variation_target(
    session_data,
    base_target,
    learner_text,
    direction="fr_to_en",
):
    if not isinstance(base_target, dict):
        return None

    lesson_name = str(base_target.get("lesson") or "selected lesson").strip()
    expected_en = str(base_target.get("expected_english") or "").strip()
    if not expected_en:
        return None

    prompt = (
        "You are creating one slight translation retry variation for a lesson review. "
        "Keep the same lesson context and difficulty, but make the sentence slightly different. "
        'Return ONLY JSON with this schema: {"expected_english":"..."}.\n\n'
        f"Lesson: {lesson_name}\n"
        f"Current target English: {expected_en}\n"
        f"Learner answer (for context): {str(learner_text or '').strip()}\n"
        f"Direction mode: {direction}\n"
        "Constraints: 4-14 words, natural daily English, not identical to current target."
    )
    raw, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.45,
        max_tokens=120,
    )
    if err:
        return None

    data = extract_json_from_text(raw)
    if not isinstance(data, dict):
        return None

    candidate = _normalize_translation_candidate(data.get("expected_english", ""))
    if not _is_valid_translation_candidate(candidate):
        return None
    if candidate.lower() == expected_en.lower():
        return None

    return {
        "lesson": lesson_name,
        "source_id": str(base_target.get("source_id") or "").strip(),
        "expected_english": candidate,
        "mastery_key": str(
            base_target.get("mastery_key") or _translation_target_key(base_target)
        ),
    }


def build_tutor_system_prompt(
    mode,
    theme,
    objective,
    target_cefr="B1",
    training_mode="standard",
    training_settings=None,
    lesson_context=None,
):
    training_settings = training_settings or {}
    lesson_context = lesson_context or {}
    target = str(target_cefr or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"
    cefr = CEFR_DESCRIPTORS.get(target, CEFR_DESCRIPTORS["B1"])
    topic_instruction = (
        f"Current theme: {theme}. Keep the learner in-theme. If the learner drifts, gently redirect."
        if theme
        else "Pick one essential daily-life topic and keep the learner focused on it."
    )
    objective_instruction = (
        f"Current objective: {objective}"
        if objective
        else "Objective: improve fluency and naturalness."
    )

    lesson_context_instruction = ""
    focus_items = lesson_context.get("focus_items", [])
    if isinstance(focus_items, list) and focus_items:
        lines = []
        for item in focus_items[:8]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- [{item.get('status', 'en cours')}] {item.get('source_type', 'Lecon')}: "
                f"{item.get('title', item.get('theme', 'N/A'))}"
            )
        if lines:
            if mode == "free":
                lesson_context_instruction = (
                    "Lesson context pool for this free dialogue session (prioritize these topics):\n"
                    + "\n".join(lines)
                    + "\nIn free mode, rotate naturally across this pool while staying practical and coherent."
                )
            else:
                lesson_context_instruction = (
                    "Lesson context for this guided session:\n"
                    + "\n".join(lines)
                    + "\nStay anchored to this lesson context and recycle its chunks naturally."
                )

    stress_reply_seconds = int(training_settings.get("stress_reply_seconds", 10))
    target_tense = training_settings.get("target_tense", "present")
    if training_mode == "conversation_stress":
        training_instruction = (
            "Training drill: CONVERSATION STRESS. Keep your replies short (1-2 sentences), "
            f"ask direct follow-up questions, and maintain quick turn-taking. Target reply window: {stress_reply_seconds} seconds."
        )
    elif training_mode == "no_translation":
        training_instruction = (
            "Training drill: NO TRANSLATION. Keep everything in English. If the learner asks in French or gets stuck, "
            "guide them to paraphrase in simple English without giving French translations."
        )
    elif training_mode == "fr_to_en":
        _tr_direction = training_settings.get("translation_direction", "fr_to_en")
        if _tr_direction == "en_to_fr":
            training_instruction = (
                "Training drill: ENGLISH TO FRENCH CHALLENGE. Give one short everyday English sentence "
                "and explicitly ask the learner to translate it into natural French. , your voice should be in English but the learner's answer should be in French. "
                "After the learner answers, confirm or correct briefly in English and continue. "
                "Do not provide long grammar explanations during the live exchange."
            )
        else:
            training_instruction = (
                "Training drill: FRENCH TO ENGLISH CHALLENGE. Regularly give one short everyday sentence in French, "
                "then explicitly ask the learner to say it in natural American English.Your voice should be in French, but the learner's answer should be in English as well. "
                "After the learner answers, recast naturally in English and continue with one follow-up question. "
                "Do not provide long grammar explanations during the live exchange."
            )
    elif training_mode == "tense_switch":
        training_instruction = (
            f"Training drill: TENSE SWITCH. Keep the learner anchored in {target_tense} tense, "
            "then occasionally ask a short reformulation of the same idea in another tense."
        )
    elif training_mode == "word_rescue":
        training_instruction = (
            "Training drill: MISSING-WORD RESCUE. If the learner lacks a word, ask for paraphrase, synonym, "
            "or description in English, and keep the conversation moving."
        )
    else:
        training_instruction = "Training drill: STANDARD FLUENCY."

    return (
        f"You are a friendly American English conversation partner for a {target} learner. "
        f"Language calibration: {cefr['english']} "
        "Speak like a real native American — casual, natural, with contractions and fillers (yeah, totally, I mean, you know, right?). "
        "NEVER explicitly correct the learner. NEVER say 'you should say', 'the correct form is', 'actually it's', or anything that interrupts the flow. "
        "Instead, use IMPLICIT RECASTS only: if the learner makes a grammar or vocabulary mistake, simply use the correct form naturally in your reply without drawing attention to it. "
        "Example: learner says 'I goed to the store' → you reply 'Oh nice, you went to the store! What did you get?' — correction embedded, conversation continues. "
        "Your only job during the conversation is to keep talking naturally, ask follow-up questions, and model correct American English through your own speech. "
        "All detailed corrections and feedback are saved for the end-of-session evaluation — do NOT give them during the conversation. "
        "Do not introduce unrelated topics. Keep continuity with the learner's selected lesson context. "
        f"Mode: {mode}. {topic_instruction} {objective_instruction} {lesson_context_instruction} {training_instruction} "
        "Use natural chunking, rhythm, stress patterns, and fillers that American native speakers actually use."
    )


def choose_theme_with_ai(choices=None):
    choices = choices or list(ESSENTIAL_THEMES.keys())
    choices = [str(item).strip() for item in choices if str(item).strip()]
    if not choices:
        choices = list(ESSENTIAL_THEMES.keys())
    prompt = (
        "Choose one theme for today's speaking session from this exact list and return only the theme name:\n"
        + "\n".join(f"- {item}" for item in choices)
    )
    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.4,
        max_tokens=30,
    )
    if err or not text:
        return choices[0]
    selected = text.strip().split("\n")[0]
    for item in choices:
        if item.lower() in selected.lower():
            return item
    return choices[0]


def new_session(
    mode,
    theme,
    objective,
    target_cefr=None,
    training_mode="standard",
    training_settings=None,
    lesson_context=None,
):
    training_settings = training_settings or {}
    lesson_context = lesson_context or {}
    translation_targets = []
    if training_mode == "fr_to_en":
        raw_targets = lesson_context.get("translation_targets", [])
        if isinstance(raw_targets, list):
            translation_targets = [t for t in raw_targets if isinstance(t, dict)]
    profile = get_active_profile()
    session_target_cefr = str(target_cefr or profile.get("target_cefr", "B1")).upper()
    if session_target_cefr not in CEFR_LEVELS:
        session_target_cefr = "B1"
    session_id = f"session-{utc_now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    data = {
        "id": session_id,
        "created_at": now_iso(),
        "started_at": now_iso(),
        "mode": mode,
        "theme": theme,
        "objective": objective,
        "profile_id": profile.get("id", "default"),
        "profile_name": profile.get("name", "Profil principal"),
        "target_cefr": session_target_cefr,
        "training_mode": training_mode,
        "training_settings": training_settings,
        "lesson_context": lesson_context,
        "translation_targets": translation_targets,
        "translation_next_idx": 0,
        "translation_mastered": [],
        "pending_translation_target": None,
        "translation_attempt_log": [],
        "translation_prompt_cache": {},
        "starter_ai_text": "",
        "starter_drill_meta": None,
        "starter_ai_audio_path": "",
        "starter_ai_audio_mime": "audio/wav",
        "starter_ai_audio_played": False,
        "final_timeout_turn_done": False,
        "messages": [
            {
                "role": "system",
                "content": build_tutor_system_prompt(
                    mode=mode,
                    theme=theme,
                    objective=objective,
                    target_cefr=session_target_cefr,
                    training_mode=training_mode,
                    training_settings=training_settings,
                    lesson_context=lesson_context,
                ),
            }
        ],
        "turns": [],
        "evaluation": None,
    }

    if training_mode == "fr_to_en" and translation_targets:
        direction = str(training_settings.get("translation_direction", "fr_to_en"))
        first_target = _select_next_translation_target(data)
        if first_target:
            data["pending_translation_target"] = first_target
            prompt_text = _question_prompt_from_target(data, first_target, direction)
            total_unique = len(
                {_translation_target_key(t) for t in translation_targets}
            )
            question_line = _format_translation_question(data, first_target, direction)

            if direction == "en_to_fr":
                data["starter_ai_text"] = question_line
            else:
                data["starter_ai_text"] = question_line

            if direction == "en_to_fr":
                _starter_intro = "Translation drill started."
                _starter_progress = f"Lesson progress: 0/{max(total_unique, 1)}"
            else:
                _starter_intro = "Mode traduction guidée activé."
                _starter_progress = f"Progression leçon: 0/{max(total_unique, 1)}"

            data["starter_drill_meta"] = {
                "drill": "fr_to_en",
                "direction": direction,
                "lesson": str(first_target.get("lesson") or "").strip(),
                "source_id": str(first_target.get("source_id") or "").strip(),
                "expected_english": str(
                    first_target.get("expected_english") or ""
                ).strip(),
                "prompt_text": prompt_text,
                "contextual_question": question_line,
                "feedback_blocks": [_starter_intro],
                "progress_line": _starter_progress,
            }

    save_session(data)
    return data


def session_file_path(session_id):
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def save_session(session_data):
    with open(session_file_path(session_data["id"]), "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)


def load_all_sessions(profile_id=None):
    if profile_id is None:
        profile_id = st.session_state.get("active_profile_id", "default")

    sessions = []
    for file_name in os.listdir(SESSIONS_DIR):
        if not file_name.endswith(".json"):
            continue
        path = os.path.join(SESSIONS_DIR, file_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        sid = data.get("profile_id")
        if sid and sid != profile_id:
            continue
        if not sid and profile_id != "default":
            continue

        sessions.append(data)

    sessions.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return sessions


def get_elapsed_seconds(session_data):
    """Return seconds elapsed since the session started."""
    started = session_data.get("started_at") or session_data.get("created_at")
    if not started:
        return 0
    try:
        started_dt = _parse_iso(started)
        if not started_dt:
            return 0
        return int((utc_now() - started_dt).total_seconds())
    except Exception:
        return 0


def get_ai_reply(session_data, user_text, elapsed_seconds=0):
    training_mode = session_data.get("training_mode", "standard")
    training_settings = session_data.get("training_settings", {})
    lesson_context = session_data.get("lesson_context") or {}
    drill_meta = None

    if training_mode == "fr_to_en":
        target_cefr = str(session_data.get("target_cefr", "B1")).upper()
        if target_cefr not in CEFR_LEVELS:
            target_cefr = "B1"
        direction = str(training_settings.get("translation_direction", "fr_to_en"))

        pending = session_data.get("pending_translation_target")
        eval_result = None
        if isinstance(pending, dict):
            asked_prompt = _question_prompt_from_target(
                session_data, pending, direction
            )
            eval_result = _evaluate_translation_attempt(
                session_data,
                pending,
                user_text,
                direction=direction,
                target_cefr=target_cefr,
            )

            attempt_log = session_data.setdefault("translation_attempt_log", [])
            attempt_log.append(
                {
                    "date": now_iso(),
                    "direction": direction,
                    "lesson": pending.get("lesson", ""),
                    "source_id": pending.get("source_id", ""),
                    "prompt_text": asked_prompt,
                    "expected_english": pending.get("expected_english", ""),
                    "expected_answer": eval_result.get("expected_answer", ""),
                    "learner_text": user_text,
                    "score": eval_result.get("score", 0),
                    "correct": bool(eval_result.get("correct", False)),
                    "feedback": eval_result.get("feedback", ""),
                    "corrected_answer": eval_result.get("corrected_answer", ""),
                }
            )

            if eval_result.get("correct"):
                mastered = session_data.setdefault("translation_mastered", [])
                pkey = str(
                    pending.get("mastery_key") or _translation_target_key(pending)
                )
                if pkey not in mastered:
                    mastered.append(pkey)

        all_targets = [
            t
            for t in session_data.get("translation_targets", [])
            if isinstance(t, dict)
        ]
        total_unique = len({_translation_target_key(t) for t in all_targets})
        mastered_count = len(set(session_data.get("translation_mastered", [])))

        # Keep lesson continuity: if wrong, retry with a slight variation from the same lesson.
        if isinstance(pending, dict) and eval_result and not eval_result.get("correct"):
            next_target = _propose_translation_variation_target(
                session_data,
                pending,
                user_text,
                direction=direction,
            )
            if not next_target:
                next_target = _select_next_translation_target(
                    session_data,
                    prefer_lesson=pending.get("lesson"),
                    exclude_expected=pending.get("expected_english"),
                )
            if not next_target:
                next_target = pending
        else:
            next_target = _select_next_translation_target(session_data)

        if not next_target:
            attempts = session_data.get("translation_attempt_log", [])
            avg_score = (
                round(
                    sum(float(a.get("score", 0) or 0) for a in attempts)
                    / max(len(attempts), 1),
                    1,
                )
                if attempts
                else 0.0
            )
            session_data["pending_translation_target"] = None
            if direction == "en_to_fr":
                done_msg = (
                    "🎉 Translation lesson complete!\n"
                    f"Provisional score: {avg_score}/100 ({mastered_count}/{max(total_unique, 1)} points mastered).\n"
                    "You can click Evaluate for the final detailed score."
                )
            else:
                done_msg = (
                    "🎉 Leçon de traduction terminée !\n"
                    f"Score provisoire: {avg_score}/100 ({mastered_count}/{max(total_unique, 1)} points maîtrisés).\n"
                    "Tu peux cliquer sur Évaluer pour le score final détaillé."
                )
            return done_msg, None, None

        session_data["pending_translation_target"] = next_target
        prompt_text = _question_prompt_from_target(session_data, next_target, direction)
        contextual_question = _format_translation_question(
            session_data, next_target, direction
        )

        drill_meta = {
            "drill": "fr_to_en",
            "direction": direction,
            "lesson": str(next_target.get("lesson") or "").strip(),
            "expected_english": str(next_target.get("expected_english") or "").strip(),
            "source_id": str(next_target.get("source_id") or "").strip(),
            "prompt_text": prompt_text,
            "contextual_question": contextual_question,
            "tts_text": "",
            "feedback_blocks": [],
            "progress_line": "",
        }

        # Build deterministic TTS text: scenario + fixed "Comment dirais-tu..." prompt
        drill_meta["tts_text"] = _build_tts_text(
            contextual_question, prompt_text, direction
        )

        feedback_blocks = []
        if isinstance(pending, dict) and eval_result:
            score = int(eval_result.get("score", 0) or 0)
            feedback = str(eval_result.get("feedback") or "").strip()
            corrected = str(eval_result.get("corrected_answer") or "").strip()

            if direction == "en_to_fr":
                if eval_result.get("correct"):
                    feedback_blocks.append(
                        f"✅ Well done ({score}/100). {feedback}".strip()
                    )
                    if corrected:
                        feedback_blocks.append(f"Natural form: {corrected}")
                else:
                    feedback_blocks.append(
                        f"❌ Not quite ({score}/100). {feedback}".strip()
                    )
                    if corrected:
                        feedback_blocks.append(f"Correction: {corrected}")
                    feedback_blocks.append(
                        "Here's a variation from the same lesson to try again."
                    )
            else:
                if eval_result.get("correct"):
                    feedback_blocks.append(
                        f"✅ Bien joué ({score}/100). {feedback}".strip()
                    )
                    if corrected:
                        feedback_blocks.append(f"Forme naturelle: {corrected}")
                else:
                    feedback_blocks.append(
                        f"❌ Pas tout à fait ({score}/100). {feedback}".strip()
                    )
                    if corrected:
                        feedback_blocks.append(f"Correction: {corrected}")
                    feedback_blocks.append(
                        "Je te propose une variante pour réessayer dans la même leçon."
                    )

        if direction == "en_to_fr":
            progress_line = f"Lesson progress: {mastered_count}/{max(total_unique, 1)}"
        else:
            progress_line = (
                f"Progression leçon: {mastered_count}/{max(total_unique, 1)}"
            )

        drill_meta["feedback_blocks"] = feedback_blocks
        drill_meta["progress_line"] = progress_line

        # ai_text = ONLY the question (matches what TTS reads)
        return contextual_question, None, drill_meta

    messages = list(session_data["messages"])

    topic_pool = lesson_context.get("topic_pool", [])
    if isinstance(topic_pool, list) and topic_pool:
        short_pool = [
            str(topic).strip() for topic in topic_pool[:8] if str(topic).strip()
        ]
        if short_pool:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "SESSION CONTEXT REMINDER: stay anchored to these learner lessons/topics when possible: "
                        + ", ".join(short_pool)
                    ),
                }
            )

    if training_mode == "conversation_stress":
        messages.append(
            {
                "role": "system",
                "content": (
                    "DRILL ACTIVE: Conversation stress. Reply in 1-2 short sentences max and always end with one direct question."
                ),
            }
        )
    elif training_mode == "tense_switch":
        target_tense = training_settings.get("target_tense", "present")
        messages.append(
            {
                "role": "system",
                "content": (
                    f"DRILL ACTIVE: Tense switch. Keep the learner mostly in {target_tense} tense and occasionally ask a reformulation in another tense."
                ),
            }
        )
    elif training_mode == "no_translation":
        messages.append(
            {
                "role": "system",
                "content": (
                    "DRILL ACTIVE: No translation. Keep the learner in English and push paraphrasing when vocabulary is missing."
                ),
            }
        )
    elif training_mode == "word_rescue":
        messages.append(
            {
                "role": "system",
                "content": (
                    "DRILL ACTIVE: Missing-word rescue. If the learner lacks a word, coach circumlocution and keep flow."
                ),
            }
        )

    if elapsed_seconds >= 200:
        messages.append(
            {
                "role": "system",
                "content": (
                    "IMPORTANT: Less than 40 seconds remain in this 4-minute session. "
                    "Wrap up your response naturally in 1-2 short sentences and gently "
                    "suggest to the learner to click 'Obtenir la note de fin de session'."
                ),
            }
        )
    messages.append({"role": "user", "content": user_text})
    text, err = openrouter_chat(messages, CHAT_MODEL, temperature=0.6, max_tokens=350)
    if err:
        return None, err, drill_meta
    return text, None, drill_meta


def _collect_fr_to_en_pairs(turns):
    pairs = []
    if not isinstance(turns, list):
        return pairs
    for idx in range(len(turns) - 1):
        current = turns[idx] if isinstance(turns[idx], dict) else {}
        nxt = turns[idx + 1] if isinstance(turns[idx + 1], dict) else {}
        drill_meta = current.get("drill_meta")
        if not isinstance(drill_meta, dict):
            continue
        if drill_meta.get("drill") != "fr_to_en":
            continue

        expected = str(drill_meta.get("expected_english") or "").strip()
        learner = str(nxt.get("user_text") or "").strip()
        if not expected or not learner:
            continue

        pairs.append(
            {
                "lesson": str(drill_meta.get("lesson") or "").strip(),
                "expected_english": expected,
                "learner_text": learner,
            }
        )
    return pairs


def _evaluate_fr_to_en_pairs(pairs, target_cefr):
    if not pairs:
        return {
            "pair_count": 0,
            "avg_score": None,
            "summary": "Aucun exercice FR->EN exploitable dans cette session.",
            "details": [],
        }

    pair_lines = []
    for idx, pair in enumerate(pairs, start=1):
        pair_lines.append(
            f"{idx}) Lesson: {pair.get('lesson', '')}\n"
            f"Expected English: {pair.get('expected_english', '')}\n"
            f"Learner answer: {pair.get('learner_text', '')}"
        )

    prompt = (
        "You are an English examiner. Evaluate French-to-English translation attempts. "
        f"Target CEFR: {target_cefr}. "
        "For each pair, score accuracy from 0 to 100 (meaning preservation + grammar + naturalness). "
        "Return ONLY JSON with this schema: "
        '{"overall_score":0-100,"summary":"...","items":[{"index":1,"score":0-100,"comment":"..."}]}.\n\n'
        "Pairs:\n" + "\n\n".join(pair_lines)
    )

    raw, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        EVAL_MODEL,
        temperature=0.1,
        max_tokens=900,
    )

    if err:
        scored = []
        for pair in pairs:
            ratio = SequenceMatcher(
                None,
                pair.get("expected_english", "").lower(),
                pair.get("learner_text", "").lower(),
            ).ratio()
            score = int(round(ratio * 100))
            scored.append(
                {
                    "lesson": pair.get("lesson", ""),
                    "expected_english": pair.get("expected_english", ""),
                    "learner_text": pair.get("learner_text", ""),
                    "score": score,
                    "comment": "Estimation automatique (fallback) basee sur similarite textuelle.",
                }
            )
        avg = round(sum(item["score"] for item in scored) / len(scored), 1)
        return {
            "pair_count": len(scored),
            "avg_score": avg,
            "summary": f"Score moyen FR->EN (fallback): {avg}/100.",
            "details": scored,
        }

    parsed = extract_json_from_text(raw)
    if not isinstance(parsed, dict):
        scored = []
        for pair in pairs:
            ratio = SequenceMatcher(
                None,
                pair.get("expected_english", "").lower(),
                pair.get("learner_text", "").lower(),
            ).ratio()
            score = int(round(ratio * 100))
            scored.append(
                {
                    "lesson": pair.get("lesson", ""),
                    "expected_english": pair.get("expected_english", ""),
                    "learner_text": pair.get("learner_text", ""),
                    "score": score,
                    "comment": "Estimation automatique (fallback) basee sur similarite textuelle.",
                }
            )
        avg = round(sum(item["score"] for item in scored) / len(scored), 1)
        return {
            "pair_count": len(scored),
            "avg_score": avg,
            "summary": f"Score moyen FR->EN (fallback): {avg}/100.",
            "details": scored,
        }

    raw_items = parsed.get("items", [])
    details = []
    for idx, pair in enumerate(pairs, start=1):
        item = raw_items[idx - 1] if idx - 1 < len(raw_items) else {}
        try:
            score = int(item.get("score", 0))
        except Exception:
            score = 0
        score = max(0, min(100, score))
        details.append(
            {
                "lesson": pair.get("lesson", ""),
                "expected_english": pair.get("expected_english", ""),
                "learner_text": pair.get("learner_text", ""),
                "score": score,
                "comment": str(item.get("comment", "")).strip(),
            }
        )

    avg_score = parsed.get("overall_score")
    try:
        avg_score = float(avg_score)
    except Exception:
        avg_score = (
            round(sum(item["score"] for item in details) / len(details), 1)
            if details
            else None
        )

    return {
        "pair_count": len(details),
        "avg_score": avg_score,
        "summary": str(parsed.get("summary", "")).strip(),
        "details": details,
    }


def evaluate_session(session_data):
    user_lines = [
        turn["user_text"] for turn in session_data["turns"] if turn.get("user_text")
    ]
    if not user_lines:
        return "Pas assez de contenu a evaluer.", None

    training_mode = session_data.get("training_mode", "standard")
    target_cefr = str(session_data.get("target_cefr", "B1")).upper()
    if target_cefr not in CEFR_LEVELS:
        target_cefr = "B1"
    target_tense = session_data.get("training_settings", {}).get("target_tense", "-")
    latencies = [
        turn.get("response_latency_seconds")
        for turn in session_data.get("turns", [])
        if isinstance(turn.get("response_latency_seconds"), (int, float))
    ]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else None
    slow_replies = sum(1 for v in latencies if v >= 8)
    self_repair_pattern = r"\b(i mean|sorry|let me rephrase|or rather|what i mean is)\b"
    self_repairs = sum(
        1 for line in user_lines if re.search(self_repair_pattern, line.lower())
    )

    translation_pairs = []
    translation_eval = {
        "pair_count": 0,
        "avg_score": None,
        "summary": "",
        "details": [],
    }
    translation_direction = str(
        session_data.get("training_settings", {}).get(
            "translation_direction", "fr_to_en"
        )
    )
    if training_mode == "fr_to_en":
        attempts = [
            a
            for a in session_data.get("translation_attempt_log", [])
            if isinstance(a, dict)
            and str(a.get("learner_text", "")).strip()
            and str(a.get("expected_answer", "")).strip()
        ]
        if attempts:
            avg_score = round(
                sum(float(a.get("score", 0) or 0) for a in attempts)
                / max(len(attempts), 1),
                1,
            )
            translation_pairs = attempts
            translation_eval = {
                "pair_count": len(attempts),
                "avg_score": avg_score,
                "summary": (
                    f"{len(attempts)} tentatives, moyenne {avg_score}/100, "
                    f"direction {translation_direction}."
                ),
                "details": attempts,
            }

    telemetry_lines = [
        f"- Active training mode: {training_mode}",
        f"- Target tense: {target_tense}",
        f"- Average response latency (seconds): {avg_latency if avg_latency is not None else 'N/A'}",
        f"- Number of slow replies (>=8s): {slow_replies}",
        f"- Detected self-repair markers: {self_repairs}",
    ]

    if training_mode == "fr_to_en":
        telemetry_lines.append(
            f"- Translation challenges answered: {translation_eval.get('pair_count', 0)}"
        )
        telemetry_lines.append(
            f"- Translation average accuracy (/100): {translation_eval.get('avg_score', 'N/A')}"
        )
        telemetry_lines.append(f"- Translation direction: {translation_direction}")
        telemetry_lines.append(
            f"- Translation summary: {translation_eval.get('summary', '')}"
        )

    translation_block = ""
    if training_mode == "fr_to_en" and translation_pairs:
        lines = []
        for idx, detail in enumerate(translation_eval.get("details", [])[:12], start=1):
            lines.append(
                f"{idx}) Lesson: {detail.get('lesson', '')}\n"
                f"Prompt asked: {detail.get('prompt_text', '')}\n"
                f"Expected answer: {detail.get('expected_answer', detail.get('expected_english', ''))}\n"
                f"Learner: {detail.get('learner_text', '')}\n"
                f"Score: {detail.get('score', 0)}/100\n"
                f"Comment: {detail.get('comment', detail.get('feedback', ''))}"
            )
        translation_block = "\n\nTranslation evidence:\n" + "\n\n".join(lines)

    prompt = f"""
Evaluate this learner's spoken English targeting CEFR {target_cefr} ({CEFR_DESCRIPTORS[target_cefr]['label']}) in American English.

Give a score from 1 to 10 for:
- Grammar
- Chunks/Vocabulary
- Fluency
- Naturalness
- Tense consistency
- Recovery strategy when missing words
- Translation accuracy for the configured direction (if drill was fr_to_en)

Then provide:
1) Strong points
2) Priority corrections (with corrected examples)
3) What to practice next week
4) Fluency drill metrics interpretation:
   - Explain response latency pattern
   - Explain tense consistency issues
   - Explain if self-repair strategy is effective
    - If drill was fr_to_en, explain translation strengths and errors clearly for the active direction

Session telemetry:
{chr(10).join(telemetry_lines)}

Conversation transcript (learner only):
{chr(10).join(user_lines)}
{translation_block}
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        EVAL_MODEL,
        temperature=0.2,
        max_tokens=900,
    )
    if err:
        return None, err
    return text, None

    if err:
        return None, err
    return text, None
