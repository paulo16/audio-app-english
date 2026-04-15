import json
import os

from modules.ai_client import (
    dual_voice_tts_smart,
    generate_dual_voice_tts,
    openrouter_chat,
)
from modules.config import *
from modules.utils import extract_json_from_text, now_iso

# ── Podcast persistence & generation ─────────────────────────────────────────


def podcast_file_path(date_str):
    return os.path.join(PODCAST_DIR, f"podcasts-{date_str}.json")


def load_podcasts_for_date(date_str):
    path = podcast_file_path(date_str)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_podcasts_for_date(date_str, podcasts):
    with open(podcast_file_path(date_str), "w", encoding="utf-8") as f:
        json.dump(podcasts, f, ensure_ascii=False, indent=2)


def podcast_audio_file_name(date_str, podcast_id):
    return f"podcast-{date_str}-{podcast_id}.wav"


def load_podcast_audio_bytes(date_str, podcast_id):
    fname = podcast_audio_file_name(date_str, podcast_id)
    path = os.path.join(PODCAST_AUDIO_DIR, fname)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def save_podcast_audio_bytes(date_str, podcast_id, audio_bytes):
    fname = podcast_audio_file_name(date_str, podcast_id)
    path = os.path.join(PODCAST_AUDIO_DIR, fname)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def generate_podcast_scripts(date_str, interests, duration_minutes=7, target_cefr="C1"):
    """Generate 3 podcast discussions (one per interest category) via OpenRouter AI."""
    target = str(target_cefr or "C1").upper()
    if target not in CEFR_LEVELS:
        target = "C1"
    cefr = CEFR_DESCRIPTORS[target]
    vocab_rule = (
        "- Keep vocabulary high-frequency and practical; avoid advanced idioms."
        if target in {"A1", "A2"}
        else f"- Use rich {target} vocabulary naturally embedded in conversation."
    )
    interests_list = "\n".join(f"- {i}" for i in interests)
    prompt = f"""Today's date: {date_str}.

You are a podcast producer creating engaging English-learning content for an American English learner targeting {target} ({cefr['label']}).

Language calibration:
{cefr['english']}

Generate exactly 3 podcast episodes as a JSON array, one for each of these interest areas:
{interests_list}

For each podcast, write a lively, natural discussion between 2 American hosts (Host A and Host B).

Requirements:
- Each podcast should last approximately {duration_minutes} minutes when read aloud (~{duration_minutes * 130} words per script).
- Use natural American conversational English: contractions, fillers (you know, I mean, right, totally, absolutely, kind of, sort of), natural interruptions and overlaps.
- Both hosts share opinions, debate facts, make jokes, and disagree sometimes — like a real podcast.
- Base topics on plausible current events, recent trends, or hot discussions related to today's date ({date_str}) in that interest area.
{vocab_rule}
- Format speaker lines as "Host A: ..." and "Host B: ..." on separate lines.

Return ONLY a valid JSON array with this exact schema (no markdown, no comments):
[
  {{
    "id": 1,
    "date": "{date_str}",
    "interest": "World News & Current Affairs",
    "title": "A catchy podcast episode title",
    "summary": "Two sentences describing what this episode covers.",
    "estimated_minutes": {duration_minutes},
    "vocabulary_highlights": ["chunk or idiom 1", "chunk or idiom 2", "chunk or idiom 3", "chunk or idiom 4", "chunk or idiom 5"],
    "script": "Host A: ...\\nHost B: ..."
  }}
]""".strip()

    messages = [{"role": "user", "content": prompt}]
    text, err = openrouter_chat(messages, CHAT_MODEL, temperature=0.75, max_tokens=9000)
    if err:
        return None, err
    data = extract_json_from_text(text)
    if data is None or not isinstance(data, list):
        return None, "La generation des podcasts n'a pas retourne un JSON valide."
    return data, None

    return data, None
