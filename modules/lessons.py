import json
import os
import re

from modules.ai_client import (
    concatenate_wav_bytes,
    dual_voice_tts_smart,
    generate_dual_voice_tts,
    openrouter_chat,
    tts_smart,
)
from modules.config import *
from modules.profiles import _profile_storage_slug
from modules.real_english import _list_real_english_lessons, _load_real_english_progress
from modules.shadowing import load_shadowing_texts
from modules.utils import extract_json_from_text, now_iso, slugify
from modules.vocabulary import load_vocab, save_vocab


def generate_quick_variations_ai(theme_name, cefr_level="B1"):
    """Generate 10 realistic themed variations via OpenRouter AI at the given CEFR level."""
    cefr = CEFR_DESCRIPTORS[cefr_level]
    idiom_rule = (
        f"- Include at least 1 very common daily chunk suitable for {cefr_level} per dialogue"
        if cefr_level in {"A1", "A2"}
        else f"- Include at least 2 idiomatic expressions or chunks typical of {cefr_level} per dialogue"
    )
    situations_list = "\n".join(
        f"{i+1}. {s}" for i, s in enumerate(VARIATION_SITUATIONS)
    )
    prompt = f"""You are an American English conversation coach.
Generate a JSON array of exactly 10 short realistic dialogues about the theme: "{theme_name}".

Target CEFR level: {cefr_level} — {cefr['label']}
Language calibration for this level:
{cefr['english']}

Each dialogue targets a different daily-life situation listed below.
Requirements:
- 2 speakers: A and B
- 10 to 14 lines total per dialogue (more lines for higher levels)
- Natural American spoken English calibrated to {cefr_level}
{idiom_rule}
- Situations to cover (one per dialogue):
{situations_list}

Return ONLY valid JSON (no markdown, no explanation) with this exact schema:
[
  {{
    "id": 1,
    "cefr_level": "{cefr_level}",
    "title": "Variation 1: First-time conversation",
    "situation": "first-time conversation",
    "grammar_focus": "simple present + past simple",
    "chunk_focus": ["How's it going?", "I was just about to...", "Nice to meet you"],
    "dialogue": "A: ...\\nB: ..."
  }}
]""".strip()

    messages = [{"role": "user", "content": prompt}]
    text, err = openrouter_chat(messages, CHAT_MODEL, temperature=0.7, max_tokens=5000)
    if err:
        return None, err
    data = extract_json_from_text(text)
    if data is None or not isinstance(data, list):
        return None, "Reponse JSON invalide lors de la generation des variations."
    return data, None


def lesson_pack_path(theme_name, cefr_level="B1", profile_id="default"):
    profile_slug = _profile_storage_slug(profile_id)
    return os.path.join(
        LESSON_PACK_DIR,
        f"{slugify(theme_name)}-{cefr_level.lower()}-{profile_slug}.json",
    )


def load_lesson_pack(theme_name, cefr_level="B1", profile_id="default"):
    path = lesson_pack_path(theme_name, cefr_level, profile_id=profile_id)
    if not os.path.exists(path):
        legacy_paths = [
            os.path.join(
                LESSON_PACK_DIR, f"{slugify(theme_name)}-{cefr_level.lower()}.json"
            )
        ]
        if cefr_level.upper() == "B1":
            legacy_paths.append(
                os.path.join(LESSON_PACK_DIR, f"{slugify(theme_name)}.json")
            )
        for legacy_path in legacy_paths:
            if os.path.exists(legacy_path):
                with open(legacy_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_lesson_pack(theme_name, pack_data, cefr_level="B1", profile_id="default"):
    with open(
        lesson_pack_path(theme_name, cefr_level, profile_id=profile_id),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(pack_data, f, ensure_ascii=False, indent=2)


# ── Variations persistence ────────────────────────────────────────────────────


def variations_path(theme_name, cefr_level="B1", profile_id="default"):
    profile_slug = _profile_storage_slug(profile_id)
    return os.path.join(
        VARIATIONS_DIR,
        f"{slugify(theme_name)}-{cefr_level.lower()}-{profile_slug}_variations.json",
    )


def load_quick_variations(theme_name, cefr_level="B1", profile_id="default"):
    path = variations_path(theme_name, cefr_level, profile_id=profile_id)
    if not os.path.exists(path):
        legacy_paths = [
            os.path.join(
                VARIATIONS_DIR,
                f"{slugify(theme_name)}-{cefr_level.lower()}_variations.json",
            )
        ]
        if cefr_level.upper() == "B1":
            legacy_paths.append(
                os.path.join(VARIATIONS_DIR, f"{slugify(theme_name)}_variations.json")
            )
        for legacy_path in legacy_paths:
            if os.path.exists(legacy_path):
                with open(legacy_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_quick_variations(
    theme_name, variations, cefr_level="B1", profile_id="default"
):
    with open(
        variations_path(theme_name, cefr_level, profile_id=profile_id),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(variations, f, ensure_ascii=False, indent=2)


# ── Lesson audio persistence ──────────────────────────────────────────────────


def lesson_audio_path(file_name):
    return os.path.join(LESSON_AUDIO_DIR, file_name)


def save_lesson_audio(file_name, audio_bytes):
    path = lesson_audio_path(file_name)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def load_lesson_audio(file_name):
    path = lesson_audio_path(file_name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def generate_five_minute_pack(theme_name, cefr_level="B1"):
    cefr = CEFR_DESCRIPTORS[cefr_level]
    idiom_rule = (
        f"- Prefer very common daily chunks and avoid advanced idioms for {cefr_level}."
        if cefr_level in {"A1", "A2"}
        else f"- Include realistic chunks and idiomatic phrases appropriate for {cefr_level}."
    )
    prompt = f"""
Generate a JSON array with exactly 5 lesson conversations for an English learner targeting {cefr_level} ({cefr['label']}), American English.
Theme: {theme_name}

Language calibration for {cefr_level}:
{cefr['english']}

Constraints:
- Exactly 5 conversations.
- Each conversation should be around 5 minutes of speaking time (roughly 550-700 words).
- Exactly 2 speakers: A and B.
- Natural American spoken English calibrated to {cefr_level}.
- Practical daily-life context directly related to the theme.
{idiom_rule}
- Each conversation targets a different sub-situation within the theme.

Return only valid JSON in this schema:
[
  {{
    "title": "...",
    "objective": "...",
    "cefr_level": "{cefr_level}",
    "grammar_focus": "...",
    "estimated_minutes": 5,
    "dialogue": "A: ...\\nB: ..."
  }}
]
""".strip()

    messages = [{"role": "user", "content": prompt}]
    text, err = openrouter_chat(messages, CHAT_MODEL, temperature=0.7, max_tokens=7000)
    if err:
        return None, err

    data = extract_json_from_text(text)
    if data is None:
        return None, "La generation du pack n'a pas retourne un JSON valide."

    if not isinstance(data, list) or len(data) < 3:
        return (
            None,
            f"Le pack genere est incomplet ({len(data) if isinstance(data, list) else 0} conversations recues).",
        )

    return data, None


def _lesson_source_id(lesson_kind, theme_name, cefr_level, lesson_uid):
    return (
        f"{lesson_kind}:{slugify(theme_name)}:{str(cefr_level).lower()}:"
        f"{str(lesson_uid).strip()}"
    )


def _sanitize_lesson_flashcards(raw_cards, cefr_level="B1", max_cards=10):
    level_default = str(cefr_level or "B1").upper()
    if level_default not in CEFR_LEVELS:
        level_default = "B1"

    cleaned = []
    seen = set()
    for item in raw_cards:
        if not isinstance(item, dict):
            continue

        term = str(item.get("term", "")).strip()
        if not term:
            continue

        term_key = term.lower()
        if term_key in seen:
            continue
        seen.add(term_key)

        examples = []
        for ex in item.get("examples", []):
            if isinstance(ex, str) and ex.strip():
                examples.append(ex.strip())
            if len(examples) >= 3:
                break

        synonyms = []
        for syn in item.get("synonyms", []):
            if isinstance(syn, str) and syn.strip():
                synonyms.append(syn.strip())
            if len(synonyms) >= 4:
                break

        lvl = str(item.get("level", level_default)).upper()
        if lvl not in CEFR_LEVELS:
            lvl = level_default

        cleaned.append(
            {
                "term": term,
                "translation": str(item.get("translation", "")).strip(),
                "part_of_speech": str(item.get("part_of_speech", "")).strip(),
                "explanation": str(item.get("explanation", "")).strip(),
                "examples": examples,
                "synonyms": synonyms,
                "level": lvl,
            }
        )
        if len(cleaned) >= max_cards:
            break
    return cleaned


def _fallback_lesson_flashcards(chunk_focus, cefr_level="B1", max_cards=10):
    cards = []
    seen = set()
    for chunk in chunk_focus or []:
        if not isinstance(chunk, str):
            continue
        clean = chunk.strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        cards.append(
            {
                "term": clean,
                "translation": "",
                "part_of_speech": "chunk",
                "explanation": "Expression importante extraite de la lecon.",
                "examples": [],
                "synonyms": [],
                "level": str(cefr_level or "B1").upper(),
            }
        )
        if len(cards) >= max_cards:
            break
    return cards


def generate_lesson_flashcards_ai(
    theme_name,
    dialogue_text,
    chunk_focus=None,
    cefr_level="B1",
    max_cards=10,
):
    target = str(cefr_level or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"

    chunks = [
        c.strip() for c in (chunk_focus or []) if isinstance(c, str) and c.strip()
    ]
    chunks_text = "\n".join(f"- {c}" for c in chunks[:20]) or "- None"

    prompt = f"""You are an English teacher creating flashcards for a French-speaking learner.

Theme: {theme_name}
Target CEFR: {target}

Dialogue:
{dialogue_text}

Priority chunks from lesson metadata:
{chunks_text}

Task:
- Extract the most useful vocabulary and chunks from this lesson.
- Return at most {max_cards} flashcards.
- Prefer high-frequency, practical expressions the learner can reuse immediately.
- Keep level appropriate for {target}.
- The "translation" field MUST be in French (never Spanish or any other language).

Return ONLY valid JSON array with objects using this schema:
[
  {{
    "term": "...",
    "translation": "traduction en francais ici",
    "part_of_speech": "chunk|verb|noun phrase|idiom|phrasal verb|...",
    "explanation": "1 short English explanation",
    "examples": ["example 1", "example 2"],
    "synonyms": ["optional", "optional"],
    "level": "{target}"
  }}
]
"""

    messages = [
        {
            "role": "system",
            "content": "You are a precise English pedagogy assistant.",
        },
        {"role": "user", "content": prompt},
    ]
    text, err = openrouter_chat(messages, CHAT_MODEL, temperature=0.2, max_tokens=1800)
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, list):
        return None, "Extraction IA invalide pour les flashcards de lecon."

    cards = _sanitize_lesson_flashcards(data, cefr_level=target, max_cards=max_cards)
    if not cards:
        return None, "Aucune flashcard valide extraite depuis la lecon."

    return cards, None


def auto_add_lesson_flashcards(
    profile_id,
    source_lesson_id,
    lesson_kind,
    theme_name,
    dialogue_text,
    chunk_focus=None,
    cefr_level="B1",
    max_cards=10,
):
    result = {
        "added": 0,
        "skipped": 0,
        "already_done": False,
        "used_fallback": False,
        "error": None,
    }

    entries = load_vocab(profile_id=profile_id)
    if any(e.get("source_lesson_id") == source_lesson_id for e in entries):
        result["already_done"] = True
        return result

    cards, err = generate_lesson_flashcards_ai(
        theme_name=theme_name,
        dialogue_text=dialogue_text,
        chunk_focus=chunk_focus,
        cefr_level=cefr_level,
        max_cards=max_cards,
    )
    if err:
        cards = _fallback_lesson_flashcards(
            chunk_focus,
            cefr_level=cefr_level,
            max_cards=max_cards,
        )
        if not cards:
            result["error"] = err
            return result
        result["used_fallback"] = True
        result["error"] = err

    existing_terms = {
        str(e.get("term", "")).strip().lower()
        for e in entries
        if str(e.get("term", "")).strip()
    }

    for card in cards[:max_cards]:
        term = str(card.get("term", "")).strip()
        if not term:
            continue
        term_key = term.lower()
        if term_key in existing_terms:
            result["skipped"] += 1
            continue

        entry_id = str(uuid.uuid4())[:8]
        examples_with_audio = [
            {"text": ex, "audio_path": None} for ex in card.get("examples", [])
        ]
        entries.append(
            {
                "id": entry_id,
                "profile_id": profile_id,
                "term": term,
                "created_at": now_iso(),
                "translation": card.get("translation", ""),
                "part_of_speech": card.get("part_of_speech", ""),
                "explanation": card.get("explanation", ""),
                "examples": examples_with_audio,
                "synonyms": card.get("synonyms", []),
                "level": card.get("level", str(cefr_level or "B1").upper()),
                "source_lesson_id": source_lesson_id,
                "source_lesson_kind": lesson_kind,
                "source_theme": theme_name,
                "source_auto": True,
                "srs": {
                    "next_review": now_iso(),
                    "interval": 1,
                    "ease": 2.5,
                    "repetitions": 0,
                    "last_result": None,
                },
                "review_history": [],
            }
        )
        existing_terms.add(term_key)
        result["added"] += 1

    if result["added"] > 0:
        save_vocab(entries, profile_id=profile_id)

    return result


def _theme_label_from_slug(theme_slug):
    target_slug = str(theme_slug or "").strip()
    if not target_slug:
        return ""
    for theme_name in ESSENTIAL_THEMES.keys():
        if slugify(theme_name) == target_slug:
            return theme_name
    return target_slug.replace("-", " ").strip().title()


def _extract_theme_slug_from_variation_file_name(file_name, profile_slug):
    name = str(file_name or "")
    profile_slug_esc = re.escape(profile_slug)
    patterns = [
        rf"^(?P<slug>.+)-(a1|a2|b1|b2|c1|c2)-{profile_slug_esc}_variations\.json$",
        r"^(?P<slug>.+)-(a1|a2|b1|b2|c1|c2)_variations\.json$",
        r"^(?P<slug>.+)_variations\.json$",
    ]
    for pattern in patterns:
        match = re.match(pattern, name, flags=re.IGNORECASE)
        if match:
            return str(match.group("slug")).strip().lower()
    return ""


def _extract_theme_slug_from_pack_file_name(file_name, profile_slug):
    name = str(file_name or "")
    profile_slug_esc = re.escape(profile_slug)
    patterns = [
        rf"^(?P<slug>.+)-(a1|a2|b1|b2|c1|c2)-{profile_slug_esc}\.json$",
        r"^(?P<slug>.+)-(a1|a2|b1|b2|c1|c2)\.json$",
        r"^(?P<slug>.+)\.json$",
    ]
    for pattern in patterns:
        match = re.match(pattern, name, flags=re.IGNORECASE)
        if match:
            return str(match.group("slug")).strip().lower()
    return ""


def _collect_generated_lesson_themes(profile_id):
    profile_slug = _profile_storage_slug(profile_id)
    known_theme_by_slug = {
        slugify(theme_name): theme_name for theme_name in ESSENTIAL_THEMES.keys()
    }
    found_slugs = set()

    if os.path.exists(VARIATIONS_DIR):
        for fname in os.listdir(VARIATIONS_DIR):
            slug = _extract_theme_slug_from_variation_file_name(fname, profile_slug)
            if slug in known_theme_by_slug:
                found_slugs.add(slug)

    if os.path.exists(LESSON_PACK_DIR):
        for fname in os.listdir(LESSON_PACK_DIR):
            slug = _extract_theme_slug_from_pack_file_name(fname, profile_slug)
            if slug in known_theme_by_slug:
                found_slugs.add(slug)

    ordered = []
    for theme_name in ESSENTIAL_THEMES.keys():
        if slugify(theme_name) in found_slugs:
            ordered.append(theme_name)
    return ordered


def _collect_practice_lesson_catalog(profile_id):
    status_rank = {"en cours": 1, "terminee": 2}
    catalog_map = {}

    profile_vocab_entries = load_vocab(profile_id=profile_id)
    completed_regular_ids = {
        str(entry.get("source_lesson_id", "")).strip()
        for entry in profile_vocab_entries
        if isinstance(entry, dict)
        and str(entry.get("source_lesson_id", ""))
        .strip()
        .startswith(("quick:", "pack:"))
    }

    real_progress = _load_real_english_progress(profile_id)
    completed_real_ids = {
        str(lesson_id).strip()
        for lesson_id in real_progress.get("completed_lessons", [])
        if str(lesson_id).strip()
    }

    def _upsert_item(item):
        key = item.get("key")
        if not key:
            return
        current = catalog_map.get(key)
        if not current:
            catalog_map[key] = item
            return
        if status_rank.get(item.get("status", "en cours"), 0) > status_rank.get(
            current.get("status", "en cours"), 0
        ):
            catalog_map[key] = item

    shadowing_items = load_shadowing_texts(profile_id)
    for entry in shadowing_items:
        if not isinstance(entry, dict):
            continue
        source_id = str(entry.get("source_id", "")).strip()
        if not source_id:
            continue
        lesson_kind = str(entry.get("lesson_kind", "")).strip().lower()
        theme_name = str(entry.get("theme_name", "")).strip()
        title = str(entry.get("lesson_title") or theme_name or source_id).strip()
        level = str(entry.get("cefr_level") or "B1").upper()

        source_type = "Lecons audio"
        status = "en cours"
        if lesson_kind in {"quick", "pack"}:
            status = "terminee" if source_id in completed_regular_ids else "en cours"
            if not theme_name and ":" in source_id:
                parts = source_id.split(":")
                if len(parts) >= 2:
                    theme_name = _theme_label_from_slug(parts[1])
        elif lesson_kind == "real_english":
            source_type = "Anglais reel"
            raw_id = source_id.replace("real-english-", "", 1)
            status = "terminee" if raw_id in completed_real_ids else "en cours"

        if not theme_name:
            theme_name = title

        _upsert_item(
            {
                "key": source_id,
                "source_id": source_id,
                "source_type": source_type,
                "status": status,
                "theme": theme_name,
                "title": title,
                "level": level,
                "lesson_kind": lesson_kind,
            }
        )

    for lesson in _list_real_english_lessons(profile_id):
        if not isinstance(lesson, dict):
            continue
        lesson_id = str(lesson.get("id", "")).strip()
        if not lesson_id:
            continue
        source_id = f"real-english-{lesson_id}"
        series = str(lesson.get("series", "")).strip()
        episode = str(lesson.get("episode", "")).strip()
        title = f"{series} - {episode}".strip(" -")
        if not title:
            title = lesson_id
        status = "terminee" if lesson_id in completed_real_ids else "en cours"
        _upsert_item(
            {
                "key": source_id,
                "source_id": source_id,
                "source_type": "Anglais reel",
                "status": status,
                "theme": title,
                "title": title,
                "level": str(lesson.get("level") or "B1").upper(),
                "lesson_kind": "real_english",
            }
        )

    existing_audio_themes = {
        str(item.get("theme", "")).strip()
        for item in catalog_map.values()
        if item.get("source_type") == "Lecons audio"
    }
    for generated_theme in _collect_generated_lesson_themes(profile_id):
        if generated_theme in existing_audio_themes:
            continue
        _upsert_item(
            {
                "key": f"generated-theme:{slugify(generated_theme)}",
                "source_id": "",
                "source_type": "Lecons audio",
                "status": "en cours",
                "theme": generated_theme,
                "title": generated_theme,
                "level": "",
                "lesson_kind": "generated",
            }
        )

    items = list(catalog_map.values())
    items.sort(
        key=lambda item: (
            0 if item.get("status") == "terminee" else 1,
            0 if item.get("source_type") == "Lecons audio" else 1,
            str(item.get("theme", "")).lower(),
            str(item.get("title", "")).lower(),
        )
    )

    topic_pool = []
    seen_topics = set()
    for item in items:
        topic = str(item.get("title") or item.get("theme") or "").strip()
        if topic and topic.lower() not in seen_topics:
            topic_pool.append(topic)
            seen_topics.add(topic.lower())

    completed_count = sum(1 for item in items if item.get("status") == "terminee")
    in_progress_count = sum(1 for item in items if item.get("status") == "en cours")
    return {
        "items": items,
        "completed_count": completed_count,
        "in_progress_count": in_progress_count,
        "topic_pool": topic_pool,
    }


def _practice_catalog_item_label(item):
    status_icon = "✅" if item.get("status") == "terminee" else "🟡"
    level = str(item.get("level") or "").strip()
    level_part = f" ({level})" if level else ""
    return (
        f"{status_icon} {item.get('source_type', 'Lecon')} - "
        f"{item.get('title', item.get('theme', 'N/A'))}{level_part}"
    )
