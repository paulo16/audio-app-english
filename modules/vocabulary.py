import json
import os
from datetime import date, datetime, timedelta, timezone

import streamlit as st

from modules.ai_client import openrouter_chat, tts_smart
from modules.config import *
from modules.profiles import _profile_storage_slug
from modules.utils import now_iso
from modules.utils import _parse_iso
from modules.utils import utc_now, utc_iso

# ── Vocabulary / Flashcard / SRS helpers ─────────────────────────────────────


def vocab_file_path(profile_id=None):
    pid = profile_id or st.session_state.get("active_profile_id", "default")
    return os.path.join(VOCAB_DIR, f"vocab-{_profile_storage_slug(pid)}.json")


def _normalize_vocab_entries(entries, profile_id):
    normalized = []
    changed = False
    for item in entries:
        if not isinstance(item, dict):
            changed = True
            continue

        entry_profile = str(item.get("profile_id", "")).strip()
        if entry_profile and entry_profile != profile_id:
            changed = True
            continue

        if item.get("profile_id") != profile_id:
            item["profile_id"] = profile_id
            changed = True

        srs = item.get("srs")
        if not isinstance(srs, dict):
            item["srs"] = {
                "next_review": now_iso(),
                "interval": 1,
                "ease": 2.5,
                "repetitions": 0,
                "last_result": None,
            }
            changed = True

        normalized.append(item)
    return normalized, changed


def load_vocab(profile_id=None):
    """Return the vocabulary list from disk (list of dicts)."""
    pid = profile_id or st.session_state.get("active_profile_id", "default")
    path = vocab_file_path(profile_id=pid)
    if not os.path.exists(path):
        # Legacy fallback for default profile.
        if pid == "default" and os.path.exists(VOCAB_FILE):
            path = VOCAB_FILE
        else:
            return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    normalized, changed = _normalize_vocab_entries(data, pid)
    if changed:
        save_vocab(normalized, profile_id=pid)
    return normalized


def save_vocab(entries, profile_id=None):
    """Persist the vocabulary list to disk."""
    pid = profile_id or st.session_state.get("active_profile_id", "default")
    normalized, _changed = _normalize_vocab_entries(entries or [], pid)
    os.makedirs(VOCAB_DIR, exist_ok=True)
    with open(vocab_file_path(profile_id=pid), "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)


def _srs_update_rated(entry, rating: int):
    """
    SM-2-style update with 4 ratings:
      0 = À revoir  — interval=1, reps reset, ease -0.20
      1 = Difficile — short boost,     reps+1, ease -0.15
      2 = Bien      — standard SM-2,   reps+1
      3 = Facile    — bigger boost,    reps+1, ease +0.15
    """
    from datetime import timedelta

    ease = entry.get("ease", 2.5)
    interval = entry.get("interval", 1)
    reps = entry.get("repetitions", 0)

    if rating == 0:  # Again
        interval = 1
        reps = 0
        ease = max(1.3, ease - 0.2)
    elif rating == 1:  # Hard
        interval = max(1, round(interval * 1.2)) if reps > 1 else 1
        reps += 1
        ease = max(1.3, ease - 0.15)
    elif rating == 2:  # Good
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 3
        else:
            interval = round(interval * ease)
        reps += 1
    else:  # rating == 3, Easy
        if reps == 0:
            interval = 3
        elif reps == 1:
            interval = 7
        else:
            interval = round(interval * ease * 1.3)
        reps += 1
        ease = min(4.0, ease + 0.15)

    next_review = utc_iso(utc_now() + timedelta(days=interval))
    entry.update(
        {
            "interval": interval,
            "ease": ease,
            "repetitions": reps,
            "next_review": next_review,
        }
    )
    return entry


def _srs_update(entry, passed: bool):
    """Legacy 2-button wrapper — maps pass/fail to rating 2/0."""
    return _srs_update_rated(entry, rating=2 if passed else 0)


def get_due_cards(entries):
    """Return vocab entries whose next_review is <= now (due for review)."""
    now = utc_now()
    due = []
    for e in entries:
        srs = e.get("srs", {})
        nr_dt = _parse_iso(srs.get("next_review", "")) or now
        if nr_dt <= now:
            due.append(e)
    due.sort(key=lambda e: (_parse_iso(e.get("srs", {}).get("next_review", "")) or now))
    return due


def translate_and_explain(term: str, target_cefr: str = "B1"):
    """Ask the AI to translate and explain a word or chunk. Returns dict or (None, err)."""
    target = str(target_cefr or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"
    prompt = f"""You are an expert English teacher for French-speaking learners.
The learner gives you a word or chunk in English (or occasionally in French).
Target CEFR level for the output examples and explanations: {target}.
Return a JSON object with these exact keys:
- "term": the English word/chunk (normalized)
- "translation": concise translation IN FRENCH (mandatory: always in French, never Spanish or any other language)
- "part_of_speech": e.g. "idiom", "verb", "noun phrase", "phrasal verb" etc.
- "explanation": 2-3 sentence English explanation of meaning, register, and typical context
- "examples": array of exactly 3 English example sentences that show natural usage (no translation needed)
- "synonyms": array of 2-3 English synonyms or related expressions (can be empty array)
- "level": estimated CEFR level string, e.g. "B2"

IMPORTANT: The "translation" field MUST be in French. Example: for "to run out of" -> "manquer de", NOT "quedarse sin".

Respond with ONLY valid JSON, no markdown fences."""

    messages = [
        {
            "role": "system",
            "content": "You are a concise, expert English language teacher.",
        },
        {"role": "user", "content": f"Analyse this term: {term}\n\n{prompt}"},
    ]
    raw, err = openrouter_chat(messages, CHAT_MODEL, temperature=0.3, max_tokens=700)
    if err:
        return None, err
    try:
        # Strip possible markdown fences
        cleaned = re.sub(
            r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE
        ).strip()
        data = json.loads(cleaned)
        return data, None
    except json.JSONDecodeError:
        return None, f"Réponse JSON invalide: {raw[:200]}"


def evaluate_vocab_usage(term: str, context_explanation: str, user_text: str):
    """Ask the AI if the user's sentence correctly uses the vocab term."""
    messages = [
        {
            "role": "system",
            "content": "You are a strict but encouraging English teacher.",
        },
        {
            "role": "user",
            "content": (
                f"Vocabulary term: «{term}»\n"
                f"Meaning: {context_explanation}\n\n"
                f"The learner produced this sentence: «{user_text}»\n\n"
                "Evaluate whether the term is used CORRECTLY and NATURALLY in that sentence. "
                "Reply with a JSON object: "
                '{"correct": true/false, "score": 0-100, "feedback": "brief feedback in French"}'
                "\nRespond with ONLY valid JSON."
            ),
        },
    ]
    raw, err = openrouter_chat(messages, EVAL_MODEL, temperature=0.2, max_tokens=200)
    if err:
        return None, err
    try:
        cleaned = re.sub(
            r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE
        ).strip()
        return json.loads(cleaned), None
    except json.JSONDecodeError:
        return None, f"Réponse JSON invalide: {raw[:200]}"


# ── Vocabulary page ───────────────────────────────────────────────────────────


def _save_review_audio(
    entry_id: str, audio_bytes: bytes, profile_id: str = None
) -> str:
    """Persist flashcard review audio and return the file path."""
    os.makedirs(VOCAB_AUDIO_DIR, exist_ok=True)
    ts = utc_now().strftime("%Y%m%d-%H%M%S")
    profile_slug = _profile_storage_slug(
        profile_id or st.session_state.get("active_profile_id", "default")
    )
    path = os.path.join(VOCAB_AUDIO_DIR, f"{profile_slug}-{entry_id}_{ts}.wav")
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _save_example_audio(
    entry_id: str, example_idx: int, audio_bytes: bytes, profile_id: str = None
) -> str:
    """Persist example-sentence TTS audio and return the file path."""
    os.makedirs(VOCAB_AUDIO_DIR, exist_ok=True)
    profile_slug = _profile_storage_slug(
        profile_id or st.session_state.get("active_profile_id", "default")
    )
    path = os.path.join(
        VOCAB_AUDIO_DIR,
        f"{profile_slug}-{entry_id}_ex{example_idx}.wav",
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def evaluate_reverse_flashcard(term: str, user_text: str):
    """Check whether the user correctly identified the term from its definition."""
    messages = [
        {
            "role": "system",
            "content": "You are a strict but encouraging English teacher.",
        },
        {
            "role": "user",
            "content": (
                f"The correct answer was the English word/expression: \u00ab{term}\u00bb\n"
                f"The learner said or wrote: \u00ab{user_text}\u00bb\n\n"
                "Did the learner produce the correct term or a very close equivalent? "
                'Reply ONLY with valid JSON: {"correct": true/false, "score": 0-100, "feedback": "brief feedback in French"}'
            ),
        },
    ]
    raw, err = openrouter_chat(messages, EVAL_MODEL, temperature=0.1, max_tokens=150)
    if err:
        return None, err
    try:
        cleaned = re.sub(
            r"^```[a-z]*\n?|```$", "", raw.strip(), flags=re.MULTILINE
        ).strip()
        return json.loads(cleaned), None
    except json.JSONDecodeError:
        return None, f"R\u00e9ponse JSON invalide: {raw[:200]}"

        return None, f"R\u00e9ponse JSON invalide: {raw[:200]}"
