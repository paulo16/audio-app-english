import json
import os

import streamlit as st

from modules.ai_client import openrouter_chat, tts_smart
from modules.config import *
from modules.profiles import _profile_storage_slug
from modules.sessions import load_all_sessions
from modules.utils import extract_json_from_text, now_iso, utc_now


def ai_lesson_file_path(profile_id="default"):
    profile_slug = _profile_storage_slug(profile_id)
    return os.path.join(AI_LESSON_DIR, f"lessons-{profile_slug}.json")


def load_ai_lessons(profile_id="default"):
    path = ai_lesson_file_path(profile_id)
    if not os.path.exists(path):
        if profile_id == "default" and os.path.exists(AI_LESSON_FILE):
            path = AI_LESSON_FILE
        else:
            return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_ai_lessons(lessons, profile_id="default"):
    os.makedirs(AI_LESSON_DIR, exist_ok=True)
    with open(ai_lesson_file_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(lessons, f, ensure_ascii=False, indent=2)


def _save_ai_lesson_example_audio(lesson_id: str, example_idx: int, audio_bytes: bytes):
    os.makedirs(AI_LESSON_AUDIO_DIR, exist_ok=True)
    path = os.path.join(AI_LESSON_AUDIO_DIR, f"{lesson_id}_ex{example_idx}.wav")
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _recent_practice_sessions(limit=12):
    sessions = [s for s in load_all_sessions() if s.get("mode") in {"guided", "free"}]
    return sessions[:limit]


def generate_ai_lessons_from_sessions(
    session_limit=12, lesson_count=4, target_cefr="B1", custom_instructions=""
):
    sessions = _recent_practice_sessions(limit=session_limit)
    if not sessions:
        return None, "Aucune session IA trouvee dans l'historique."

    target = str(target_cefr or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"
    cefr = CEFR_DESCRIPTORS[target]

    chunks = []
    used_ids = []
    for sess in reversed(sessions):
        sid = sess.get("id", "unknown")
        used_ids.append(sid)
        theme = sess.get("theme", "General")
        chunks.append(f"Session {sid} | Theme: {theme}")
        for turn in sess.get("turns", [])[-10:]:
            user_text = (turn.get("user_text") or "").strip()
            ai_text = (turn.get("ai_text") or "").strip()
            if user_text:
                chunks.append(f"Learner: {user_text}")
            if ai_text:
                chunks.append(f"Partner: {ai_text}")
        chunks.append("---")

    transcript = "\n".join(chunks)
    if len(transcript) > 16000:
        transcript = transcript[-16000:]

    prompt = f"""
You are an expert American English speaking coach.

Analyze the learner transcript below (B2 listening, around B1 speaking).
Target CEFR for the generated practice material: {target} ({cefr['label']}).
Language calibration:
{cefr['english']}
Create exactly {lesson_count} practical lessons to improve daily conversation fluency.
{f'''
Additional instructions from the learner:
{custom_instructions}''' if custom_instructions.strip() else ''}

Return ONLY valid JSON array with this exact schema:
[
  {{
    "focus": "short lesson title",
    "concept": "what to study and why",
    "common_mistakes": ["mistake pattern 1", "mistake pattern 2", "mistake pattern 3"],
    "tips_to_remember": ["tip 1", "tip 2", "tip 3"],
    "example_sentences": ["example 1", "example 2", "example 3", "example 4"],
    "mini_task": {{
      "instruction": "2-minute speaking task instruction",
      "success_checklist": ["check 1", "check 2", "check 3"],
      "target_time_seconds": 120
    }}
  }}
]

Transcript:
{transcript}
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.35,
        max_tokens=2600,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, list) or not data:
        return None, "Generation invalide: JSON de lecons non reconnu."

    lessons = []
    for idx, item in enumerate(data[:lesson_count]):
        if not isinstance(item, dict):
            continue
        lesson_id = (
            f"ai-lesson-{utc_now().strftime('%Y%m%d')}-{idx+1}-{uuid.uuid4().hex[:4]}"
        )
        examples_raw = item.get("example_sentences") or []
        examples = []
        for ex in examples_raw[:6]:
            if isinstance(ex, str) and ex.strip():
                examples.append({"text": ex.strip(), "audio_path": None})

        mini_task = (
            item.get("mini_task") if isinstance(item.get("mini_task"), dict) else {}
        )
        lessons.append(
            {
                "id": lesson_id,
                "created_at": now_iso(),
                "source_session_ids": used_ids,
                "focus": item.get("focus", f"Lesson {idx + 1}"),
                "concept": item.get("concept", ""),
                "common_mistakes": item.get("common_mistakes", []),
                "tips_to_remember": item.get("tips_to_remember", []),
                "examples": examples,
                "mini_task": {
                    "instruction": mini_task.get(
                        "instruction", "Speak for 2 minutes on this topic."
                    ),
                    "success_checklist": mini_task.get("success_checklist", []),
                    "target_time_seconds": int(
                        mini_task.get("target_time_seconds", 120) or 120
                    ),
                },
            }
        )

    if not lessons:
        return None, "Aucune lecon exploitable n'a ete produite."

    return lessons, None


def evaluate_ai_lesson_mini_task(lesson, user_text):
    if not user_text.strip():
        return None, "Reponse vide."

    concept = lesson.get("concept", "")
    instruction = lesson.get("mini_task", {}).get("instruction", "")
    checks = lesson.get("mini_task", {}).get("success_checklist", [])
    checks_text = "\n".join(f"- {x}" for x in checks)

    prompt = f"""
You are an English speaking evaluator for a French-speaking learner.

Lesson concept:
{concept}

Mini-task instruction:
{instruction}

Expected checklist:
{checks_text}

Learner answer:
{user_text}

Return ONLY valid JSON:
{{
  "score": 0,
  "correct": false,
  "feedback_fr": "brief French feedback",
  "improved_answer": "short improved English answer"
}}
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        EVAL_MODEL,
        temperature=0.2,
        max_tokens=350,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, dict):
        return None, "Evaluation invalide: JSON non reconnu."
    return data, None

    return data, None
