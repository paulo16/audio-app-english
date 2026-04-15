import io
import json
import os
import wave
from datetime import date, datetime, timedelta, timezone

import streamlit as st

from modules.ai_client import (
    concatenate_wav_bytes,
    openrouter_chat,
    text_to_speech_openrouter,
    tts_smart,
)
from modules.config import *
from modules.profiles import _profile_storage_slug
from modules.utils import extract_json_from_text, now_iso, slugify, utc_now


def shadowing_texts_path(profile_id):
    return os.path.join(
        SHADOWING_DIR,
        f"texts-{_profile_storage_slug(profile_id)}.json",
    )


def shadowing_progress_path(profile_id):
    return os.path.join(
        SHADOWING_DIR,
        f"progress-{_profile_storage_slug(profile_id)}.json",
    )


def load_shadowing_texts(profile_id):
    path = shadowing_texts_path(profile_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_shadowing_texts(profile_id, items):
    os.makedirs(SHADOWING_DIR, exist_ok=True)
    with open(shadowing_texts_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def _split_shadowing_chunks(text):
    raw = str(text or "").replace("\r", "\n")
    lines = []
    for line in raw.split("\n"):
        clean = line.strip()
        if not clean:
            continue
        clean = re.sub(r"^[A-Za-z]\s*:\s*", "", clean)
        if clean:
            lines.append(clean)
    merged = " ".join(lines).strip()
    if not merged:
        return []

    base_sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", merged) if s.strip()
    ]

    chunks = []
    for sentence in base_sentences:
        words = sentence.split()
        if len(words) <= 12:
            chunks.append(sentence)
            continue

        pieces = [
            p.strip()
            for p in re.split(
                r"(?<=[,;:])\s+|\s+(?=(?:and|but|so|because|then)\b)",
                sentence,
                flags=re.IGNORECASE,
            )
            if p.strip()
        ]
        if len(pieces) <= 1:
            pieces = [" ".join(words[i : i + 10]) for i in range(0, len(words), 10)]

        for piece in pieces:
            piece_words = piece.split()
            if len(piece_words) <= 12:
                chunks.append(piece)
            else:
                for i in range(0, len(piece_words), 10):
                    sub = " ".join(piece_words[i : i + 10]).strip()
                    if sub:
                        chunks.append(sub)

    return [c for c in chunks if c]


def register_shadowing_text(
    profile_id,
    source_lesson_id,
    lesson_kind,
    theme_name,
    dialogue_text,
    chunk_focus=None,
    cefr_level="B1",
    lesson_title="",
):
    text = str(dialogue_text or "").strip()
    if not text:
        return False

    chunks = _split_shadowing_chunks(text)
    if not chunks:
        return False

    items = load_shadowing_texts(profile_id)
    for item in items:
        if item.get("source_id") == source_lesson_id:
            item["theme_name"] = theme_name
            item["cefr_level"] = str(cefr_level or "B1").upper()
            item["lesson_kind"] = lesson_kind
            item["lesson_title"] = lesson_title
            item["dialogue_text"] = text
            item["chunks"] = chunks
            item["chunk_focus"] = chunk_focus or []
            item["updated_at"] = now_iso()
            save_shadowing_texts(profile_id, items)
            return False

    items.append(
        {
            "source_id": source_lesson_id,
            "profile_id": profile_id,
            "theme_name": theme_name,
            "cefr_level": str(cefr_level or "B1").upper(),
            "lesson_kind": lesson_kind,
            "lesson_title": lesson_title,
            "dialogue_text": text,
            "chunks": chunks,
            "chunk_focus": chunk_focus or [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    )
    save_shadowing_texts(profile_id, items)
    return True


def load_shadowing_daily_assignments():
    if not os.path.exists(SHADOWING_DAILY_FILE):
        return {}
    try:
        with open(SHADOWING_DAILY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_shadowing_daily_assignments(data):
    os.makedirs(SHADOWING_DIR, exist_ok=True)
    with open(SHADOWING_DAILY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _shadowing_day_entry_to_state(entry):
    if isinstance(entry, str):
        return {
            "current_source_id": entry,
            "completed_source_ids": [],
        }
    if not isinstance(entry, dict):
        return {
            "current_source_id": "",
            "completed_source_ids": [],
        }

    current_source_id = str(entry.get("current_source_id", "") or "")
    completed_source_ids = entry.get("completed_source_ids", [])
    if not isinstance(completed_source_ids, list):
        completed_source_ids = []
    completed_source_ids = [
        str(sid) for sid in completed_source_ids if str(sid or "").strip()
    ]

    return {
        "current_source_id": current_source_id,
        "completed_source_ids": completed_source_ids,
    }


def _shadowing_save_day_state(
    profile_id, day_key, current_source_id, completed_source_ids
):
    assignments = load_shadowing_daily_assignments()
    profile_map = assignments.get(profile_id, {})
    if not isinstance(profile_map, dict):
        profile_map = {}

    profile_map[day_key] = {
        "current_source_id": str(current_source_id or ""),
        "completed_source_ids": [
            str(sid) for sid in completed_source_ids if str(sid or "").strip()
        ][-30:],
        "updated_at": now_iso(),
    }
    assignments[profile_id] = profile_map
    save_shadowing_daily_assignments(assignments)


def archive_shadowing_session_run(
    profile_id, day_key, source_id, chunk_count, reason="completed"
):
    data = load_shadowing_progress(profile_id)
    key = _shadowing_progress_key(day_key, source_id)
    session = data.get(key)
    if not isinstance(session, dict):
        return False

    records = session.get("records", [])
    if not isinstance(records, list):
        records = []
    records = [r for r in records if isinstance(r, dict)]
    if not records:
        return False

    run_history = session.get("run_history", [])
    if not isinstance(run_history, list):
        run_history = []

    summary = _shadowing_records_summary(records, chunk_count)
    run_history.append(
        {
            "archived_at": now_iso(),
            "started_at": session.get("started_at"),
            "completed_at": session.get("completed_at"),
            "avg_score": summary["avg_score"],
            "min_score": summary["min_score"],
            "max_score": summary["max_score"],
            "phrases_done": summary["phrases_done"],
            "chunk_count": summary["chunk_count"],
            "reason": str(reason or "completed"),
        }
    )

    session["run_history"] = run_history[-30:]
    session["records"] = []
    session["chunk_count"] = int(chunk_count)
    session["started_at"] = now_iso()
    session["completed_at"] = None
    session["auto_advanced_count"] = int(session.get("auto_advanced_count", 0)) + 1

    data[key] = session
    save_shadowing_progress(profile_id, data)
    return True


def maybe_advance_shadowing_daily_text(
    profile_id, day_key, source_id, texts, avg_score
):
    if float(avg_score or 0) < 80.0:
        return False

    texts_by_id = {str(t.get("source_id")): t for t in texts if t.get("source_id")}
    current_source_id = str(source_id or "")
    if current_source_id not in texts_by_id:
        return False

    assignments = load_shadowing_daily_assignments()
    profile_map = assignments.get(profile_id, {})
    if not isinstance(profile_map, dict):
        profile_map = {}

    state = _shadowing_day_entry_to_state(profile_map.get(day_key))
    completed_ids = [sid for sid in state.get("completed_source_ids", []) if sid]
    if current_source_id not in completed_ids:
        completed_ids.append(current_source_id)

    all_ids = sorted(texts_by_id.keys())
    excluded = set(completed_ids)
    candidate_ids = [sid for sid in all_ids if sid not in excluded]
    if not candidate_ids:
        return False

    seed_num = int(
        hashlib.sha1(
            f"{profile_id}:{day_key}:{current_source_id}:{len(completed_ids)}".encode(
                "utf-8"
            )
        ).hexdigest(),
        16,
    )
    next_source_id = candidate_ids[seed_num % len(candidate_ids)]

    archive_shadowing_session_run(
        profile_id=profile_id,
        day_key=day_key,
        source_id=current_source_id,
        chunk_count=len(texts_by_id[current_source_id].get("chunks") or []),
        reason="avg>=80 auto-next",
    )

    _shadowing_save_day_state(
        profile_id=profile_id,
        day_key=day_key,
        current_source_id=next_source_id,
        completed_source_ids=completed_ids,
    )
    return True


def pick_daily_shadowing_text(profile_id, texts):
    if not texts:
        return None, None

    texts_by_id = {str(t.get("source_id")): t for t in texts if t.get("source_id")}
    if not texts_by_id:
        return None, None

    today_date = utc_now().date()
    today = today_date.isoformat()
    yesterday = (today_date - timedelta(days=1)).isoformat()

    assignments = load_shadowing_daily_assignments()
    profile_map = assignments.get(profile_id, {})
    if not isinstance(profile_map, dict):
        profile_map = {}

    today_state = _shadowing_day_entry_to_state(profile_map.get(today))
    assigned_source = today_state.get("current_source_id")
    if assigned_source in texts_by_id:
        return texts_by_id[assigned_source], today

    all_ids = sorted(texts_by_id.keys())
    previous_state = _shadowing_day_entry_to_state(profile_map.get(yesterday))
    previous = previous_state.get("current_source_id")
    candidate_ids = [sid for sid in all_ids if sid != previous] or all_ids

    seed_num = int(
        hashlib.sha1(f"{profile_id}:{today}".encode("utf-8")).hexdigest(),
        16,
    )
    chosen_id = candidate_ids[seed_num % len(candidate_ids)]
    profile_map[today] = chosen_id

    min_keep = today_date - timedelta(days=120)
    for key in list(profile_map.keys()):
        try:
            key_date = datetime.fromisoformat(key).date()
        except Exception:
            continue
        if key_date < min_keep:
            del profile_map[key]

    assignments[profile_id] = profile_map
    save_shadowing_daily_assignments(assignments)
    return texts_by_id[chosen_id], today


def _shadowing_progress_key(day_key, source_id):
    return f"{day_key}::{source_id}"


def load_shadowing_progress(profile_id):
    path = shadowing_progress_path(profile_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_shadowing_progress(profile_id, data):
    os.makedirs(SHADOWING_DIR, exist_ok=True)
    with open(shadowing_progress_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_shadowing_session_records(profile_id, day_key, source_id):
    data = load_shadowing_progress(profile_id)
    session = data.get(_shadowing_progress_key(day_key, source_id), {})
    records = session.get("records", [])
    if not isinstance(records, list):
        return []
    records = [r for r in records if isinstance(r, dict)]
    records.sort(key=lambda r: int(r.get("chunk_idx", 10**6)))
    return records


def get_shadowing_session(profile_id, day_key, source_id):
    data = load_shadowing_progress(profile_id)
    session = data.get(_shadowing_progress_key(day_key, source_id), {})
    return session if isinstance(session, dict) else {}


def _render_shadowing_phrase_detail(records):
    """Render per-phrase detail results (used in both column and full-width contexts)."""
    for rec in reversed(records):
        idx = int(rec.get("chunk_idx", 0)) + 1
        score = int(rec.get("score", 0))
        score_scales = _shadowing_score_scales(score)
        score_label = _shadowing_score_label(score)
        feedback = rec.get("feedback", "")
        user_said = rec.get("user_text", "")
        target_text = rec.get("chunk_text", "")

        if score >= 85:
            score_color = "green"
        elif score >= 55:
            score_color = "orange"
        else:
            score_color = "red"

        st.markdown("---")
        st.markdown(
            f"**Phrase {idx}** — :{score_color}[**{score_scales['on_100']}/100**] "
            f"({score_scales['on_20']}/20) — {score_label}"
        )
        st.markdown(f"**Attendu:** {target_text}")
        if user_said:
            st.markdown(f"**Tu as dit:** {user_said}")
        elif score > 0:
            st.markdown("**Tu as dit:** *(transcription indisponible)*")
        else:
            st.markdown("**Tu as dit:** *(non enregistre)*")
        if feedback:
            st.caption(f"Conseil: {feedback}")


def _shadowing_records_summary(records, chunk_count):
    valid = [r for r in records if isinstance(r, dict)]
    if not valid:
        return {
            "avg_score": 0,
            "min_score": 0,
            "max_score": 0,
            "phrases_done": 0,
            "chunk_count": int(chunk_count),
        }

    scores = [int(r.get("score", 0)) for r in valid]
    return {
        "avg_score": round(sum(scores) / len(scores), 1),
        "min_score": min(scores),
        "max_score": max(scores),
        "phrases_done": len(valid),
        "chunk_count": int(chunk_count),
    }


def _shadowing_score_scales(score_100):
    score = float(score_100 or 0.0)
    return {
        "on_100": round(score, 1),
        "on_20": round(score / 5.0, 1),
        "on_10": round(score / 10.0, 1),
    }


def _shadowing_score_label(score_100):
    score = float(score_100 or 0.0)
    if score >= 85:
        return "Tres bon (fidele et fluide)"
    if score >= 70:
        return "Bon (quelques ajustements)"
    if score >= 55:
        return "Moyen (manque de precision)"
    return "A retravailler"


def get_shadowing_run_history(profile_id, day_key, source_id):
    session = get_shadowing_session(profile_id, day_key, source_id)
    history = session.get("run_history", [])
    if not isinstance(history, list):
        return []
    return [h for h in history if isinstance(h, dict)]


def reset_shadowing_session_keep_history(profile_id, day_key, source_id, chunk_count):
    data = load_shadowing_progress(profile_id)
    key = _shadowing_progress_key(day_key, source_id)
    session = data.get(key)
    if not isinstance(session, dict):
        session = {
            "profile_id": profile_id,
            "day": day_key,
            "source_id": source_id,
            "chunk_count": int(chunk_count),
            "records": [],
            "run_history": [],
            "restart_count": 0,
            "started_at": now_iso(),
            "completed_at": None,
        }

    records = session.get("records", [])
    if not isinstance(records, list):
        records = []
    run_history = session.get("run_history", [])
    if not isinstance(run_history, list):
        run_history = []

    if records:
        summary = _shadowing_records_summary(records, chunk_count)
        run_history.append(
            {
                "archived_at": now_iso(),
                "started_at": session.get("started_at"),
                "completed_at": session.get("completed_at"),
                "avg_score": summary["avg_score"],
                "min_score": summary["min_score"],
                "max_score": summary["max_score"],
                "phrases_done": summary["phrases_done"],
                "chunk_count": summary["chunk_count"],
            }
        )

    session["run_history"] = run_history[-30:]
    session["records"] = []
    session["chunk_count"] = int(chunk_count)
    session["restart_count"] = int(session.get("restart_count", 0)) + 1
    session["started_at"] = now_iso()
    session["completed_at"] = None

    data[key] = session
    save_shadowing_progress(profile_id, data)
    return session


def save_shadowing_chunk_result(
    profile_id,
    day_key,
    source_id,
    chunk_idx,
    chunk_text,
    score,
    feedback,
    user_text,
    duration_sec,
    chunk_count,
):
    data = load_shadowing_progress(profile_id)
    key = _shadowing_progress_key(day_key, source_id)
    session = data.get(key)
    if not isinstance(session, dict):
        session = {
            "profile_id": profile_id,
            "day": day_key,
            "source_id": source_id,
            "chunk_count": chunk_count,
            "records": [],
            "started_at": now_iso(),
            "completed_at": None,
        }

    session["chunk_count"] = chunk_count
    records = session.get("records", [])
    if not isinstance(records, list):
        records = []

    payload = {
        "chunk_idx": int(chunk_idx),
        "chunk_text": chunk_text,
        "score": int(max(0, min(100, int(score)))),
        "feedback": str(feedback or ""),
        "user_text": str(user_text or ""),
        "duration_sec": float(duration_sec or 0.0),
        "saved_at": now_iso(),
    }

    replaced = False
    for i, rec in enumerate(records):
        if int(rec.get("chunk_idx", -1)) == int(chunk_idx):
            records[i] = payload
            replaced = True
            break
    if not replaced:
        records.append(payload)

    records.sort(key=lambda r: int(r.get("chunk_idx", 10**6)))
    session["records"] = records

    if len(records) >= int(chunk_count):
        session["completed_at"] = now_iso()

    data[key] = session
    save_shadowing_progress(profile_id, data)
    return payload


def get_next_shadowing_chunk_index(records, chunk_count):
    done = {int(r.get("chunk_idx", -1)) for r in records if isinstance(r, dict)}
    for idx in range(int(chunk_count)):
        if idx not in done:
            return idx
    return int(chunk_count)


def _shadowing_record_seconds(chunk_text):
    words = max(1, len(str(chunk_text or "").split()))
    base = 1.2 + (words * 0.22)
    return round(min(SHADOWING_MAX_RECORD_SECONDS, max(1.6, base)), 1)


def _audio_duration_seconds(audio_bytes):
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate() or 1
            return frames / float(rate)
    except Exception:
        return None


def _normalize_compare_text(text):
    return re.sub(r"[^a-z0-9\s']+", " ", str(text or "").lower()).strip()


def _shadowing_mismatch_feedback(reference_text, user_text, max_points=5):
    ref_words = re.findall(r"[a-z0-9']+", _normalize_compare_text(reference_text))
    usr_words = re.findall(r"[a-z0-9']+", _normalize_compare_text(user_text))
    if not ref_words or not usr_words:
        return ""

    points = []
    matcher = SequenceMatcher(None, ref_words, usr_words)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        ref_part = " ".join(ref_words[i1:i2]).strip()
        usr_part = " ".join(usr_words[j1:j2]).strip()

        if tag == "replace" and ref_part and usr_part:
            points.append(f'au lieu de "{ref_part}", tu as dit "{usr_part}"')
        elif tag == "delete" and ref_part:
            points.append(f'il manque "{ref_part}"')
        elif tag == "insert" and usr_part:
            points.append(f'mot en trop: "{usr_part}"')

        if len(points) >= int(max_points):
            break

    if not points:
        return ""
    return "Points a corriger: " + " ; ".join(points) + "."


def _score_shadowing_chunk_fallback(reference_text, user_text):
    ref = _normalize_compare_text(reference_text)
    usr = _normalize_compare_text(user_text)
    if not usr:
        return {
            "score": 0,
            "feedback": "Aucun audio exploitable. Reessaie en parlant plus clairement.",
        }

    ratio = SequenceMatcher(None, ref, usr).ratio()
    score = int(round(ratio * 100))
    if score >= 90:
        feedback = "Excellent. Continue ce rythme et garde la precision."
    elif score >= 75:
        feedback = (
            "Bon resultat. Ameliore les petits mots de liaison pour gagner des points."
        )
    elif score >= 60:
        feedback = (
            "Correct, mais il manque des mots. Reecoute puis repete plus lentement."
        )
    else:
        feedback = (
            "A retravailler. Coupe la phrase en petits groupes et articule chaque mot."
        )
    return {"score": score, "feedback": feedback}


def evaluate_shadowing_chunk(reference_text, user_text, cefr_level="B1"):
    target = str(cefr_level or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"

    messages = [
        {
            "role": "system",
            "content": (
                "You are an English pronunciation and speaking coach. "
                "Compare the learner's transcribed sentence to the target sentence. "
                "Evaluate: 1) Fidelity (missing/added/wrong words), "
                "2) Pronunciation clues (words likely mispronounced based on transcript differences), "
                "3) Fluency (natural rhythm). "
                "Give a score from 0 to 100 and detailed coaching feedback IN FRENCH. "
                "In the feedback, ALWAYS specify: which exact words differ, "
                "what the learner said vs what was expected, and a concrete tip to improve."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Target CEFR: {target}\n"
                f"Target sentence: {reference_text}\n"
                f"Learner transcript: {user_text}\n\n"
                'Return ONLY JSON: {"score": 0-100, "feedback": "detailed coaching feedback in French with specific word-level corrections"}'
            ),
        },
    ]

    raw, err = openrouter_chat(messages, EVAL_MODEL, temperature=0.1, max_tokens=350)
    if err:
        return _score_shadowing_chunk_fallback(reference_text, user_text)

    data = extract_json_from_text(raw)
    if not isinstance(data, dict):
        return _score_shadowing_chunk_fallback(reference_text, user_text)

    try:
        score = int(data.get("score", 0))
    except Exception:
        score = 0
    score = max(0, min(100, score))
    feedback = str(data.get("feedback", "")).strip()
    if not feedback:
        feedback = _score_shadowing_chunk_fallback(reference_text, user_text)[
            "feedback"
        ]
    return {"score": score, "feedback": feedback}


def shadowing_chunk_audio_path(profile_id, source_id, chunk_idx, chunk_text):
    source_slug = slugify(str(source_id).replace(":", "-")) or "source"
    chunk_hash = hashlib.sha1(str(chunk_text).encode("utf-8")).hexdigest()[:10]
    file_name = f"{_profile_storage_slug(profile_id)}-{source_slug}-{int(chunk_idx)}-{chunk_hash}.wav"
    return os.path.join(SHADOWING_AUDIO_DIR, file_name)


def ensure_shadowing_chunk_audio(profile_id, source_id, chunk_idx, chunk_text, voice):
    path = shadowing_chunk_audio_path(profile_id, source_id, chunk_idx, chunk_text)
    if os.path.exists(path):
        return path, None
    audio_bytes, _, err = text_to_speech_openrouter(chunk_text, voice=voice)
    if err:
        return None, err
    os.makedirs(SHADOWING_AUDIO_DIR, exist_ok=True)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path, None
