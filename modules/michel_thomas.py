import json
import os
import uuid

from modules.ai_client import openrouter_chat, tts_smart
from modules.config import (
    CEFR_DESCRIPTORS,
    CEFR_LEVELS,
    CHAT_MODEL,
    EVAL_MODEL,
    LESSON_DEEP_MODEL,
    MICHEL_THOMAS_AUDIO_DIR,
    MICHEL_THOMAS_DIR,
    MT_DIALOGUE_SESSION_DIR,
    MT_LESSON_SESSION_DIR,
    MT_PERFECTIONNEMENT_SESSION_DIR,
    MT_TENSES_BY_LEVEL,
    MT_THEMED_DIALOGUE_DIR,
    MT_THEMES_BY_LEVEL,
    STORY_NARRATOR_VOICES,
)
from modules.profiles import _profile_storage_slug
from modules.utils import extract_json_from_text, now_iso, utc_now

# ── Storage helpers ──────────────────────────────────────────────────────────


def mt_sessions_file_path(profile_id="default"):
    slug = _profile_storage_slug(profile_id)
    os.makedirs(MICHEL_THOMAS_DIR, exist_ok=True)
    return os.path.join(MICHEL_THOMAS_DIR, f"mt-sessions-{slug}.json")


def load_mt_sessions(profile_id="default"):
    path = mt_sessions_file_path(profile_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_mt_sessions(sessions, profile_id="default"):
    os.makedirs(MICHEL_THOMAS_DIR, exist_ok=True)
    with open(mt_sessions_file_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def _save_mt_step_audio(session_id: str, step_idx: int, audio_bytes: bytes) -> str:
    """Save English TTS audio for a step."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(MICHEL_THOMAS_AUDIO_DIR, f"{session_id}_step{step_idx}_en.wav")
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _save_mt_step_fr_audio(session_id: str, step_idx: int, audio_bytes: bytes) -> str:
    """Save French TTS audio for a step."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(MICHEL_THOMAS_AUDIO_DIR, f"{session_id}_step{step_idx}_fr.wav")
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


# ── Generation ───────────────────────────────────────────────────────────────


def generate_mt_session(
    level: str,
    theme: str,
    tense_focus: str,
    step_count: int = 7,
    profile_id: str = "default",
):
    """Generate a Michel Thomas-style session: progressive French → English steps.

    Returns (session_dict, error_str).
    """
    target = str(level or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"
    cefr = CEFR_DESCRIPTORS[target]

    prompt = f"""
You are an expert English language teacher using the Michel Thomas Method.
Your learner speaks French natively and is at CEFR level {target} ({cefr['label']}).

Theme: {theme}
Grammar focus (tense/structure): {tense_focus}

Generate exactly {step_count} progressive steps in the Michel Thomas style. The progression must be:
- Step 1: very short, simple sentence using the target structure
- Each subsequent step adds ONE element of complexity: a new word, a negation, a question form, a time expression, a subordinate clause, etc.
- The FINAL step should be a rich, natural, complex sentence using the full target structure

CRITICAL Michel Thomas principles to follow:
1. Every step builds on the previous — no sudden jumps.
2. "build_ups": show 2-3 intermediate chunks that scaffold the learner toward the full sentence.
   Example for "I didn't have the time to do it because I was too busy":
   build_ups = ["I didn't have the time.", "I didn't have the time to do it.", "...because I was too busy."]
3. "pattern_link": explicitly connect the new grammar structure to something already familiar to the learner.
   Example: "Même principe que 'je ne savais pas' → 'I didn't know' : on utilise didn't + base verb."
   This is the KEY Michel Thomas technique — always anchor new patterns to known ones.
4. Vocabulary tips: etymology, cognates, false friends, memory tricks — explain WHY.
5. Grammar notes: 1-2 sentences max, practical, no jargon.
6. Practice variations: 2 short sentences the learner can try immediately.
7. English sentences must be natural American English, appropriate for {cefr['label']}.

Return ONLY a valid JSON array with this exact schema (no markdown, no explanation):
[
  {{
    "idx": 0,
    "french": "Je travaille.",
    "english": "I work.",
    "build_ups": ["I work."],
    "pattern_link": "Pas de lien encore — c'est la structure de base : sujet + verbe.",
    "vocabulary": [
      {{"word": "work", "tip": "Same root as French 'travail' via Latin — easy to remember!", "french": "travailler / travail"}}
    ],
    "grammar_note": "In English, Present Simple = subject + base verb. No auxiliary needed for affirmative.",
    "practice_variations": ["You work.", "She works."]
  }}
]
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.4,
        max_tokens=3000,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, list) or not data:
        return (
            None,
            "Generation invalide : la reponse IA n'est pas un tableau JSON exploitable.",
        )

    session_id = f"mt-{utc_now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6]}"

    steps = []
    for raw in data[:step_count]:
        if not isinstance(raw, dict):
            continue
        vocab = []
        for v in raw.get("vocabulary", []):
            if isinstance(v, dict) and v.get("word"):
                vocab.append(
                    {
                        "word": str(v.get("word", "")).strip(),
                        "tip": str(v.get("tip", "")).strip(),
                        "french": str(v.get("french", "")).strip(),
                    }
                )
        build_ups = [
            str(x).strip()
            for x in raw.get("build_ups", [])
            if isinstance(x, str) and str(x).strip()
        ]
        variations = [
            str(x).strip()
            for x in raw.get("practice_variations", [])
            if isinstance(x, str) and str(x).strip()
        ]
        steps.append(
            {
                "idx": len(steps),
                "french": str(raw.get("french", "")).strip(),
                "english": str(raw.get("english", "")).strip(),
                "build_ups": build_ups,
                "pattern_link": str(raw.get("pattern_link", "")).strip(),
                "vocabulary": vocab,
                "grammar_note": str(raw.get("grammar_note", "")).strip(),
                "practice_variations": variations[:3],
                "audio_path": None,
                "fr_audio_path": None,
            }
        )

    if not steps:
        return None, "Aucune etape valide n'a ete generee."

    session = {
        "id": session_id,
        "profile_id": profile_id,
        "level": target,
        "theme": theme,
        "tense_focus": tense_focus,
        "created_at": now_iso(),
        "steps": steps,
    }
    return session, None


# ── Evaluation ───────────────────────────────────────────────────────────────


def evaluate_mt_step(step: dict, user_text: str):
    """Evaluate the learner's translation attempt for a single Michel Thomas step.

    Returns (eval_dict, error_str).
    eval_dict keys: score (0-100), correct (bool), feedback_fr (str), improved_answer (str).
    """
    if not user_text.strip():
        return None, "Reponse vide."

    french = step.get("french", "")
    expected = step.get("english", "")
    grammar_note = step.get("grammar_note", "")

    prompt = f"""
You are a kind, encouraging English coach evaluating a French-speaking learner.

The learner was shown this French sentence and asked to translate it into English:
French: {french}
Expected English: {expected}
Grammar note: {grammar_note}

Learner's answer: {user_text}

Evaluation rules:
- Accept minor spelling errors (do not penalize heavily).
- Accept paraphrases that convey the same meaning with correct grammar.
- Award full marks (100) if the grammar structure and meaning are both correct.
- Penalize incorrect tense usage more than vocabulary choice.
- Give feedback IN FRENCH, encouraging and practical (2-3 sentences max).
- Suggest an improved version only if the learner's answer had errors.

Return ONLY valid JSON:
{{
  "score": 85,
  "correct": true,
  "feedback_fr": "Tres bien ! Tu as utilise le bon temps. Juste un petit mot manquant.",
  "improved_answer": "I have worked here for 3 years."
}}
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        EVAL_MODEL,
        temperature=0.2,
        max_tokens=300,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, dict):
        return None, "Evaluation invalide : reponse JSON non reconnue."
    return data, None


# ── Perfectionnement (CD 8-11) — Storage ─────────────────────────────────────


def mt_perf_sessions_file_path(profile_id="default"):
    slug = _profile_storage_slug(profile_id)
    os.makedirs(MT_PERFECTIONNEMENT_SESSION_DIR, exist_ok=True)
    return os.path.join(MT_PERFECTIONNEMENT_SESSION_DIR, f"mt-perf-{slug}.json")


def load_mt_perf_sessions(profile_id="default"):
    path = mt_perf_sessions_file_path(profile_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_mt_perf_sessions(sessions, profile_id="default"):
    os.makedirs(MT_PERFECTIONNEMENT_SESSION_DIR, exist_ok=True)
    with open(mt_perf_sessions_file_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def _save_mt_perf_step_audio(session_id: str, step_idx: int, audio_bytes: bytes) -> str:
    """Save English TTS audio for a Perfectionnement step."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(
        MICHEL_THOMAS_AUDIO_DIR, f"perf-{session_id}_step{step_idx}_en.wav"
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _save_mt_perf_step_fr_audio(
    session_id: str, step_idx: int, audio_bytes: bytes
) -> str:
    """Save French TTS audio for a Perfectionnement step."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(
        MICHEL_THOMAS_AUDIO_DIR, f"perf-{session_id}_step{step_idx}_fr.wav"
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _update_perf_step_audio_path(profile_id, sid, step_idx, field_name, new_path):
    """Persist an audio path update for a single step in the Perfectionnement JSON store."""
    all_sessions = load_mt_perf_sessions(profile_id)
    for s in all_sessions:
        if s["id"] == sid and step_idx < len(s.get("steps", [])):
            s["steps"][step_idx][field_name] = new_path
            break
    save_mt_perf_sessions(all_sessions, profile_id)


# ── Perfectionnement — Generation ────────────────────────────────────────────


def generate_mt_perfectionnement_session(
    disc_name: str,
    concept: str,
    step_count: int = 7,
    profile_id: str = "default",
):
    """Generate a Michel Thomas Perfectionnement session with a Tip block + N progressive steps.

    Returns (session_dict, error_str).
    """
    prompt = f"""
You are an expert English language teacher specializing in the Michel Thomas Method.
Your learner speaks French natively and is at CEFR level B2.

Disc: {disc_name}
Grammatical concept to teach: {concept}

Michel Thomas's core pedagogical technique:
- He ALWAYS explains the concept FIRST in simple terms BEFORE asking the student to practice.
- He shows HOW the concept maps directly from French to English (analogies, cognates, parallel structures).
- Classic tip example: "En anglais, pour dire 'je voudrais que tu fasses quelque chose pour moi', on dit
  'I would like you to + base verb'. Si je dis 'I would like you to come', comment diriez-vous
  'je voudrais que tu partes' ?"

Generate EXACTLY {step_count} progressive steps PLUS an introductory TIP block.

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{{
  "tip": {{
    "title_fr": "Titre court du concept (ex: Le 2nd Conditionnel)",
    "explanation_fr": "Explication en français, style Michel Thomas : simple, mémorable, avec analogie FR↔EN. 3-4 phrases max. Commence par la structure clé, puis montre le parallèle avec le français.",
    "example_given_en": "La phrase exemple que Michel Thomas donne à l'apprenant (en anglais)",
    "example_given_fr": "Sa traduction française",
    "analogy_fr": "L'analogie clé FR→EN en 1-2 phrases (ex: 'would = votre -rais/-rait en français')"
  }},
  "steps": [
    {{
      "idx": 0,
      "tip_echo": "Mini-rappel de la formule (1 ligne max, ex: 'If + past → would + base verb')",
      "french": "La phrase française à traduire",
      "english": "La traduction anglaise attendue",
      "hint": "Indice discret (verbe irrégulier, faux-ami, préposition piège) — chaîne vide si pas nécessaire",
      "build_ups": ["Chunk 1", "Chunk 1 + 2", "Phrase complète"],
      "vocabulary": [
        {{"word": "mot", "tip": "astuce mémo / étymologie / faux-ami", "french": "traduction FR"}}
      ],
      "grammar_note": "Note grammaticale pratique, 1-2 phrases max",
      "practice_variations": ["Phrase 1 d'entraînement.", "Phrase 2 d'entraînement."]
    }}
  ]
}}

Critical rules:
1. Steps must progress in difficulty: step 1 = very short & simple, final step = rich natural complex sentence.
2. Each step adds EXACTLY ONE new element vs the previous.
3. tip_echo is a compact formula reminder — not a repetition of the full explanation.
4. build_ups must have 2-3 intermediate chunks scaffolding toward the complete sentence.
5. Vocabulary tips: etymology, cognates, false friends, memory tricks.
6. English must be natural B2-level American English.
7. All explanations (tip, feedback, notes) in French.
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.4,
        max_tokens=4000,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, dict) or "tip" not in data or "steps" not in data:
        return (
            None,
            "Génération invalide : la réponse IA n'a pas la structure tip + steps attendue.",
        )

    tip = data.get("tip", {})
    raw_steps = data.get("steps", [])

    steps = []
    for raw in raw_steps[:step_count]:
        if not isinstance(raw, dict):
            continue
        vocab = [
            {
                "word": str(v.get("word", "")).strip(),
                "tip": str(v.get("tip", "")).strip(),
                "french": str(v.get("french", "")).strip(),
            }
            for v in raw.get("vocabulary", [])
            if isinstance(v, dict) and v.get("word")
        ]
        build_ups = [
            str(x).strip()
            for x in raw.get("build_ups", [])
            if isinstance(x, str) and str(x).strip()
        ]
        variations = [
            str(x).strip()
            for x in raw.get("practice_variations", [])
            if isinstance(x, str) and str(x).strip()
        ]
        steps.append(
            {
                "idx": len(steps),
                "tip_echo": str(raw.get("tip_echo", "")).strip(),
                "french": str(raw.get("french", "")).strip(),
                "english": str(raw.get("english", "")).strip(),
                "hint": str(raw.get("hint", "")).strip(),
                "build_ups": build_ups,
                "vocabulary": vocab,
                "grammar_note": str(raw.get("grammar_note", "")).strip(),
                "practice_variations": variations[:3],
                "audio_path": None,
                "fr_audio_path": None,
            }
        )

    if not steps:
        return None, "Aucune étape valide n'a été générée."

    session_id = f"mt-perf-{utc_now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6]}"
    session = {
        "id": session_id,
        "profile_id": profile_id,
        "disc": disc_name,
        "concept": concept,
        "tip": {
            "title_fr": str(tip.get("title_fr", concept)).strip(),
            "explanation_fr": str(tip.get("explanation_fr", "")).strip(),
            "example_given_en": str(tip.get("example_given_en", "")).strip(),
            "example_given_fr": str(tip.get("example_given_fr", "")).strip(),
            "analogy_fr": str(tip.get("analogy_fr", "")).strip(),
        },
        "created_at": now_iso(),
        "steps": steps,
    }
    return session, None


# ── Leçons bilingues & Dialogues — Storage ───────────────────────────────────


def mt_dialogue_sessions_file_path(profile_id="default"):
    slug = _profile_storage_slug(profile_id)
    os.makedirs(MT_DIALOGUE_SESSION_DIR, exist_ok=True)
    return os.path.join(MT_DIALOGUE_SESSION_DIR, f"mt-dial-{slug}.json")


def load_mt_dialogue_sessions(profile_id="default"):
    path = mt_dialogue_sessions_file_path(profile_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_mt_dialogue_sessions(sessions, profile_id="default"):
    os.makedirs(MT_DIALOGUE_SESSION_DIR, exist_ok=True)
    with open(mt_dialogue_sessions_file_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


# ── Leçons bilingues & Dialogues — Generation ────────────────────────────────


def generate_mt_dialogue_session(
    level: str,
    theme: str,
    tense_focus: str,
    phrase_count: int = 6,
    profile_id: str = "default",
):
    """Generate a bilingual lesson (key phrases EN+FR) + a short dialogue + flashcards.

    Returns (session_dict, error_str).
    """
    target = str(level or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"
    cefr = CEFR_DESCRIPTORS[target]

    prompt = f"""
You are an expert bilingual English–French language coach using the Michel Thomas Method.
The learner speaks French natively and is at CEFR level {target} ({cefr['label']}).

Theme: {theme}
Grammar focus: {tense_focus}

Generate a bilingual lesson with:
1. {phrase_count} KEY PHRASES — each with the English sentence, its French translation,
   a practical grammar note, a usage tip, and a memory trick.
2. A SHORT DIALOGUE (8–10 lines) between two speakers (A and B) that naturally uses
   these key phrases in a realistic context related to the theme.
   Each line must have both an English and a French version.
3. FLASHCARDS — one per key phrase (French front → English back).

Rules:
- English must be natural {cefr['label']}-level American English.
- Grammar notes and tips must be in FRENCH (clear, practical, no jargon).
- Memory tricks must link the English to something French-speakers already know.
- The dialogue must feel natural, not contrived.
- Speakers in the dialogue can be named (e.g. Sophie & Tom, or Client & Serveur).

Return ONLY valid JSON (no markdown, no explanation) with this exact structure:
{{
  "theme": "{theme}",
  "tense_focus": "{tense_focus}",
  "key_phrases": [
    {{
      "english": "I've been working here for three years.",
      "french": "Je travaille ici depuis trois ans.",
      "grammar_note": "Present Perfect avec 'for' pour exprimer une durée qui dure encore.",
      "usage_tip": "Utilise cette structure pour dire depuis combien de temps tu fais quelque chose.",
      "memory_trick": "Pense à 'for' comme 'pendant/depuis' pour les durées : for 3 years = depuis 3 ans."
    }}
  ],
  "dialogue": [
    {{"speaker": "Sophie", "line_en": "How long have you been working here?", "line_fr": "Depuis combien de temps travailles-tu ici ?"}},
    {{"speaker": "Tom", "line_en": "I've been here for about three years.", "line_fr": "Je suis ici depuis environ trois ans."}}
  ],
  "flashcards": [
    {{"id": 0, "front_fr": "Je travaille ici depuis trois ans.", "back_en": "I've been working here for three years."}}
  ]
}}
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.45,
        max_tokens=3500,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, dict) or not data.get("key_phrases"):
        return None, "Génération invalide : structure JSON incorrecte."

    # Normalise key_phrases
    key_phrases = []
    for kp in data.get("key_phrases", [])[:phrase_count]:
        if not isinstance(kp, dict):
            continue
        key_phrases.append(
            {
                "english": str(kp.get("english", "")).strip(),
                "french": str(kp.get("french", "")).strip(),
                "grammar_note": str(kp.get("grammar_note", "")).strip(),
                "usage_tip": str(kp.get("usage_tip", "")).strip(),
                "memory_trick": str(kp.get("memory_trick", "")).strip(),
                "audio_path_en": None,
                "audio_path_fr": None,
            }
        )

    # Normalise dialogue
    dialogue = []
    for line in data.get("dialogue", []):
        if not isinstance(line, dict):
            continue
        dialogue.append(
            {
                "speaker": str(line.get("speaker", "")).strip(),
                "line_en": str(line.get("line_en", "")).strip(),
                "line_fr": str(line.get("line_fr", "")).strip(),
                "audio_path_en": None,
            }
        )

    # Normalise flashcards
    flashcards = []
    for i, fc in enumerate(data.get("flashcards", [])):
        if not isinstance(fc, dict):
            continue
        flashcards.append(
            {
                "id": i,
                "front_fr": str(fc.get("front_fr", "")).strip(),
                "back_en": str(fc.get("back_en", "")).strip(),
            }
        )

    if not key_phrases:
        return None, "Aucune phrase clé valide générée."

    session_id = f"mt-dial-{utc_now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6]}"
    session = {
        "id": session_id,
        "profile_id": profile_id,
        "level": target,
        "theme": theme,
        "tense_focus": tense_focus,
        "created_at": now_iso(),
        "key_phrases": key_phrases,
        "dialogue": dialogue,
        "flashcards": flashcards,
    }
    return session, None


def _save_dial_phrase_audio(
    session_id: str, phrase_idx: int, lang: str, audio_bytes: bytes
) -> str:
    """Persist audio for a key phrase (lang = 'en' or 'fr')."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(
        MICHEL_THOMAS_AUDIO_DIR,
        f"dial-{session_id}_phrase{phrase_idx}_{lang}.wav",
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _save_dial_line_audio(session_id: str, line_idx: int, audio_bytes: bytes) -> str:
    """Persist audio for a dialogue line (English)."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(
        MICHEL_THOMAS_AUDIO_DIR,
        f"dial-{session_id}_line{line_idx}_en.wav",
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _update_dial_phrase_audio(profile_id, sid, phrase_idx, field, new_path):
    all_sessions = load_mt_dialogue_sessions(profile_id)
    for s in all_sessions:
        if s["id"] == sid and phrase_idx < len(s.get("key_phrases", [])):
            s["key_phrases"][phrase_idx][field] = new_path
            break
    save_mt_dialogue_sessions(all_sessions, profile_id)


def _update_dial_line_audio(profile_id, sid, line_idx, new_path):
    all_sessions = load_mt_dialogue_sessions(profile_id)
    for s in all_sessions:
        if s["id"] == sid and line_idx < len(s.get("dialogue", [])):
            s["dialogue"][line_idx]["audio_path_en"] = new_path
            break
    save_mt_dialogue_sessions(all_sessions, profile_id)


# ═══════════════════════════════════════════════════════════════════════════════
# LESSON SESSIONS — Leçons bilingues structurées avec pratique EN↔FR
# ═══════════════════════════════════════════════════════════════════════════════


def mt_lesson_sessions_file_path(profile_id="default"):
    slug = _profile_storage_slug(profile_id)
    os.makedirs(MT_LESSON_SESSION_DIR, exist_ok=True)
    return os.path.join(MT_LESSON_SESSION_DIR, f"lessons-{slug}.json")


def load_mt_lesson_sessions(profile_id="default"):
    path = mt_lesson_sessions_file_path(profile_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_mt_lesson_sessions(sessions, profile_id="default"):
    os.makedirs(MT_LESSON_SESSION_DIR, exist_ok=True)
    with open(mt_lesson_sessions_file_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def generate_lesson_session(
    concept: str,
    level: str,
    profile_id: str = "default",
):
    """Generate a full bilingual lesson: explanation + examples + FR↔EN practice pairs.

    Returns (session_dict, error_str).
    """
    target = str(level or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"
    cefr = CEFR_DESCRIPTORS[target]

    prompt = f"""
You are an expert bilingual English-French language teacher focused on real American usage.
Generate a complete structured lesson on: "{concept}" for CEFR level {target} ({cefr['label']}).
The learner speaks French natively. ALL explanations MUST be in FRENCH.

Return ONLY valid JSON (no markdown, no commentary) with this exact structure:
{{
  "title_fr": "Titre de la leçon en français (ex: Le 2ème Conditionnel — Hypothèses irréelles)",
  "situation_fr": "Une situation TRÈS concrète et vivante (3-4 phrases) qui décrit EXACTEMENT quand un Américain utilise cette structure — comme si tu racontais une scène de film ou de vie réelle. Exemple pour le Present Perfect: 'Tu rentres chez toi, ton ami te dit: Have you seen Inception? Il ne te demande pas QUAND tu l'as vu — il veut juste savoir si tu l'as vu ou non, si cette expérience fait partie de ta vie. Répondre I saw it yesterday serait bizarre — le moment précis n'a aucune importance ici.'",
  "decision_binaire_fr": "Une règle de décision BINAIRE ultra-simple, style arbre de décision. Format:\n✅ Utilise [STRUCTURE] si: [condition claire]\n❌ N'utilise PAS [STRUCTURE] si: [contre-condition]\nExemple pour Present Perfect vs Simple Past:\n✅ Utilise Present Perfect si: tu penses à l'expérience ou au résultat (pas au moment précis)\n❌ N'utilise PAS Present Perfect si: tu mentionnes quand c'est arrivé (yesterday, in 2020, last week...)",
  "chunks": [
    "chunk mémorisable 1 — phrase complète naturelle à réutiliser telle quelle",
    "chunk mémorisable 2",
    "chunk mémorisable 3",
    "chunk mémorisable 4",
    "chunk mémorisable 5",
    "chunk mémorisable 6"
  ],
  "what_is_it_fr": "Explication concrète (3-4 phrases) de CE QUE LES AMÉRICAINS VEULENT EXPRIMER avec cette structure dans la vie réelle, puis lien rapide avec le français naturel.",
  "when_to_use_fr": "Liste de 4 situations américaines concrètes (daily life, travail, amis, service client, etc.) séparées par \\n, chaque ligne commençant par •",
  "structure": {{
    "affirmative": "formule affirmative (ex: If + Past Simple, would + base verb)",
    "negative": "formule négative (ex: If ... didn't + verb, wouldn't + base verb)",
    "question": "formule interrogative (ex: What would you do if + Past Simple?)"
  }},
  "analogy_fr": "L'analogie clé FR→EN en 1-2 phrases très concrètes (ex: 'C'est exactement comme en français : Si j'avais... je ferais... = If I had... I would...')",
  "key_points_fr": [
    "Point clé ou erreur fréquente #1 (pratique, pas trop technique)",
    "Point clé ou erreur fréquente #2",
    "Point clé ou erreur fréquente #3"
  ],
  "examples": [
        {{
            "english": "phrase anglaise naturelle",
            "french": "traduction française naturelle",
            "us_context_fr": "Contexte typique aux USA où cette phrase sonne naturelle",
            "intention_fr": "Nuance voulue par le locuteur américain (insister sur la durée, résultat visible, habitude, etc.)",
            "compare_fr": "Comparaison FR: comment on le dirait spontanément en français"
        }},
        {{"english": "...", "french": "...", "us_context_fr": "...", "intention_fr": "...", "compare_fr": "..."}},
        {{"english": "...", "french": "...", "us_context_fr": "...", "intention_fr": "...", "compare_fr": "..."}},
        {{"english": "...", "french": "...", "us_context_fr": "...", "intention_fr": "...", "compare_fr": "..."}},
        {{"english": "...", "french": "...", "us_context_fr": "...", "intention_fr": "...", "compare_fr": "..."}}
  ],
  "practice_pairs": [
        {{"direction": "fr_to_en", "prompt": "phrase française à traduire en anglais", "answer": "traduction anglaise attendue", "hint": "", "usage_note_fr": "Pourquoi cette forme est utilisée par un Américain dans ce contexte"}},
        {{"direction": "fr_to_en", "prompt": "...", "answer": "...", "hint": "indice si nécessaire, sinon chaîne vide", "usage_note_fr": "..."}},
        {{"direction": "fr_to_en", "prompt": "...", "answer": "...", "hint": "", "usage_note_fr": "..."}},
        {{"direction": "fr_to_en", "prompt": "...", "answer": "...", "hint": "", "usage_note_fr": "..."}},
        {{"direction": "fr_to_en", "prompt": "...", "answer": "...", "hint": "", "usage_note_fr": "..."}},
        {{"direction": "fr_to_en", "prompt": "...", "answer": "...", "hint": "", "usage_note_fr": "..."}},
        {{"direction": "en_to_fr", "prompt": "English sentence to translate into French", "answer": "traduction française attendue", "hint": "", "usage_note_fr": "..."}},
        {{"direction": "en_to_fr", "prompt": "...", "answer": "...", "hint": "", "usage_note_fr": "..."}},
        {{"direction": "en_to_fr", "prompt": "...", "answer": "...", "hint": "", "usage_note_fr": "..."}},
        {{"direction": "en_to_fr", "prompt": "...", "answer": "...", "hint": "", "usage_note_fr": "..."}}
  ]
}}

Critical rules:
1. Exactly 5 examples ordered by complexity (simple → complex).
2. Exactly 10 practice pairs: first 6 FR→EN, last 4 EN→FR.
3. Exactly 6 chunks: short, complete, natural sentences an American would actually say — ready to memorize and reuse verbatim.
4. situation_fr must be vivid and concrete — paint a real scene, not a grammar rule.
5. decision_binaire_fr must be immediately actionable — 2 lines max, a real binary filter.
6. Practice pairs must vary: affirmative, negative, question forms, different subjects.
7. English sentences must be natural {cefr['label']}-level American English.
8. Avoid abstract grammar lecture tone; prioritize real situations, intention, and meaning in context.
9. Use practical French comparisons (what French speakers naturally say) instead of literal/awkward translations.
10. Hints should be empty strings unless genuinely helpful (e.g., irregular verb warning).
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        LESSON_DEEP_MODEL,
        temperature=1,
        max_tokens=8000,
        reasoning=True,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, dict) or not data.get("examples"):
        return None, "Génération invalide : structure JSON incorrecte."

    # Normalise examples
    examples = []
    for ex in data.get("examples", [])[:5]:
        if not isinstance(ex, dict):
            continue
        examples.append(
            {
                "english": str(ex.get("english", "")).strip(),
                "french": str(ex.get("french", "")).strip(),
                "us_context_fr": str(ex.get("us_context_fr", "")).strip(),
                "intention_fr": str(ex.get("intention_fr", "")).strip(),
                "compare_fr": str(ex.get("compare_fr", "")).strip(),
                "audio_path_en": None,
                "audio_path_fr": None,
            }
        )

    # Normalise practice_pairs
    practice_pairs = []
    for pp in data.get("practice_pairs", [])[:10]:
        if not isinstance(pp, dict):
            continue
        practice_pairs.append(
            {
                "direction": str(pp.get("direction", "fr_to_en")),
                "prompt": str(pp.get("prompt", "")).strip(),
                "answer": str(pp.get("answer", "")).strip(),
                "hint": str(pp.get("hint", "")).strip(),
                "usage_note_fr": str(pp.get("usage_note_fr", "")).strip(),
            }
        )

    session_id = f"mt-lesson-{utc_now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6]}"
    session = {
        "id": session_id,
        "profile_id": profile_id,
        "level": target,
        "concept": concept,
        "created_at": now_iso(),
        "lesson": {
            "title_fr": str(data.get("title_fr", concept)).strip(),
            "situation_fr": str(data.get("situation_fr", "")).strip(),
            "decision_binaire_fr": str(data.get("decision_binaire_fr", "")).strip(),
            "chunks": [
                str(c).strip()
                for c in data.get("chunks", [])
                if isinstance(c, str) and str(c).strip()
            ][:6],
            "what_is_it_fr": str(data.get("what_is_it_fr", "")).strip(),
            "when_to_use_fr": str(data.get("when_to_use_fr", "")).strip(),
            "structure": {
                "affirmative": str(
                    data.get("structure", {}).get("affirmative", "")
                ).strip(),
                "negative": str(data.get("structure", {}).get("negative", "")).strip(),
                "question": str(data.get("structure", {}).get("question", "")).strip(),
            },
            "analogy_fr": str(data.get("analogy_fr", "")).strip(),
            "key_points_fr": [
                str(kp).strip()
                for kp in data.get("key_points_fr", [])
                if isinstance(kp, str) and kp.strip()
            ],
            "examples": examples,
        },
        "practice_pairs": practice_pairs,
    }
    return session, None


def _save_lesson_example_audio(
    session_id: str, example_idx: int, lang: str, audio_bytes: bytes
) -> str:
    """Persist TTS audio for a lesson example (lang = 'en' or 'fr')."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(
        MICHEL_THOMAS_AUDIO_DIR,
        f"lesson-{session_id}_ex{example_idx}_{lang}.wav",
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _update_lesson_example_audio(profile_id, sid, example_idx, field, new_path):
    all_sessions = load_mt_lesson_sessions(profile_id)
    for s in all_sessions:
        if s["id"] == sid:
            examples = s.get("lesson", {}).get("examples", [])
            if example_idx < len(examples):
                examples[example_idx][field] = new_path
            break
    save_mt_lesson_sessions(all_sessions, profile_id)


def _save_lesson_practice_audio(
    session_id: str, pair_idx: int, role: str, audio_bytes: bytes
) -> str:
    """Persist TTS audio for a practice pair (role = 'prompt' or 'answer')."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(
        MICHEL_THOMAS_AUDIO_DIR,
        f"lesson-{session_id}_pair{pair_idx}_{role}.wav",
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _update_lesson_practice_audio(profile_id, sid, pair_idx, field, new_path):
    all_sessions = load_mt_lesson_sessions(profile_id)
    for s in all_sessions:
        if s["id"] == sid:
            pairs = s.get("practice_pairs", [])
            if pair_idx < len(pairs):
                pairs[pair_idx][field] = new_path
            break
    save_mt_lesson_sessions(all_sessions, profile_id)


def build_lesson_narration_script(lesson: dict) -> str:
    """Build a spoken narration script of the full lesson in a natural teacher style.

    Structure: examples FIRST (Michel Thomas method), then explanation, then tips.
    Returns a plain text string suitable for TTS.
    """
    parts = []
    title = lesson.get("title_fr", "")
    examples = lesson.get("examples", [])
    what = lesson.get("what_is_it_fr", "")
    analogy = lesson.get("analogy_fr", "")
    struct = lesson.get("structure", {})
    affirmative = struct.get("affirmative", "")
    negative = struct.get("negative", "")
    question = struct.get("question", "")
    when_raw = lesson.get("when_to_use_fr", "")
    when_lines = [
        l.lstrip("•- ").strip() for l in when_raw.split("\n") if l.strip().lstrip("•- ")
    ]
    kp = lesson.get("key_points_fr", [])

    # ── Introduction ───────────────────────────────────────────────────────
    if title:
        parts.append(f"Bienvenue dans cette leçon sur : {title}.")
        parts.append("")

    # ── Step 1 : examples FIRST, without explanation (Michel Thomas method) ─
    listen_examples = [ex for ex in examples if ex.get("english")][:3]
    if listen_examples:
        parts.append(
            "Avant que j'explique quoi que ce soit, écoute d'abord ces phrases en anglais. "
            "Essaie de sentir ce qui se passe, même si tu ne comprends pas encore tout."
        )
        parts.append("")
        for ex in listen_examples:
            parts.append(ex["english"] + ".")
            parts.append("")
        parts.append(
            "Tu as senti quelque chose ? Ces phrases ont toutes quelque chose en commun. "
            "On va maintenant comprendre exactement ce que c'est."
        )
        parts.append("")

    # ── Step 2 : explanation ───────────────────────────────────────────────
    if what:
        parts.append(what)
        parts.append("")

    if analogy:
        parts.append("Voici une façon simple de t'en souvenir :")
        parts.append(analogy)
        parts.append("")

    # ── Step 3 : structure ─────────────────────────────────────────────────
    if affirmative or negative or question:
        parts.append("Voyons maintenant comment construire cette structure.")
        if affirmative:
            parts.append(f"Pour la forme affirmative, c'est : {affirmative}.")
        if negative:
            parts.append(f"Pour la forme négative : {negative}.")
        if question:
            parts.append(f"Et pour poser une question : {question}.")
        parts.append("")

    # ── Step 4 : when to use ───────────────────────────────────────────────
    if when_lines:
        parts.append("Quand est-ce qu'on utilise ça concrètement ?")
        for line in when_lines:
            parts.append(line + ".")
        parts.append("")

    # ── Step 5 : all examples WITH translations ────────────────────────────
    if examples:
        parts.append(
            "Maintenant, reprenons tous les exemples — cette fois avec la traduction en français. "
            "Écoute bien la structure en anglais."
        )
        parts.append("")
        for i, ex in enumerate(examples, 1):
            en = ex.get("english", "")
            fr = ex.get("french", "")
            us_context = ex.get("us_context_fr", "")
            intention = ex.get("intention_fr", "")
            compare_fr = ex.get("compare_fr", "")
            if not en:
                continue
            intro = [
                "Premier exemple.",
                "Deuxième exemple.",
                "Troisième exemple.",
                "Quatrième exemple.",
                "Cinquième exemple.",
            ]
            parts.append(intro[i - 1] if i <= 5 else f"Exemple {i}.")
            parts.append(en + ".")
            if fr:
                parts.append(f"Ce qui veut dire en français : {fr}.")
            if us_context:
                parts.append(f"Contexte américain typique : {us_context}.")
            if intention:
                parts.append(f"Ce que ça exprime ici : {intention}.")
            if compare_fr:
                parts.append(f"En français naturel, on dira plutôt : {compare_fr}.")
            parts.append("")

    # ── Step 6 : tips & common mistakes ───────────────────────────────────
    if kp:
        parts.append(
            "Avant de passer à la pratique, voici les points clés à garder en tête."
        )
        parts.append("")
        for i, point in enumerate(kp, 1):
            intros = [
                "Première chose importante :",
                "Deuxième chose à retenir :",
                "Troisième astuce :",
                "Et enfin :",
            ]
            label = intros[i - 1] if i <= len(intros) else f"Point {i} :"
            parts.append(f"{label} {point}.")
            parts.append("")

    # ── Closing ───────────────────────────────────────────────────────────
    parts.append(
        "Voilà pour la leçon ! Tu as maintenant tout ce qu'il faut pour t'entraîner. "
        "Passe à la partie pratique et essaie de traduire les phrases par toi-même. Allez, on y va !"
    )
    return "\n".join(parts)


def _save_lesson_course_audio(session_id: str, audio_bytes: bytes) -> str:
    """Persist the full course narration TTS audio."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(MICHEL_THOMAS_AUDIO_DIR, f"lesson-{session_id}_course.wav")
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _update_lesson_course_audio_path(profile_id, sid, new_path):
    all_sessions = load_mt_lesson_sessions(profile_id)
    for s in all_sessions:
        if s["id"] == sid:
            s.setdefault("lesson", {})["course_audio_path"] = new_path
            break
    save_mt_lesson_sessions(all_sessions, profile_id)


def evaluate_practice_pair(pair: dict, user_text: str):
    """Evaluate a FR→EN or EN→FR practice pair.

    Returns (eval_dict, error_str).
    eval_dict keys: score (0-100), correct (bool), feedback_fr (str), improved_answer (str).
    """
    if not user_text.strip():
        return None, "Réponse vide."

    direction = pair.get("direction", "fr_to_en")
    prompt_shown = pair.get("prompt", "")
    expected = pair.get("answer", "")

    if direction == "fr_to_en":
        source_lang, target_lang = "français", "anglais"
    else:
        source_lang, target_lang = "anglais", "français"

    prompt = f"""
You are a kind, encouraging bilingual English-French language coach.

Direction: translate from {source_lang} to {target_lang}
Sentence shown: {prompt_shown}
Expected answer: {expected}
Learner's answer: {user_text}

Evaluation rules:
- Accept minor spelling errors (do not penalize heavily).
- Accept paraphrases that convey the same meaning with correct grammar.
- Award full marks (100) if grammar structure AND meaning are both correct.
- Penalize incorrect grammar more than minor vocabulary differences.
- IMPORTANT tense nuance for duration expressions:
    - If the meaning is an action still true now (French often uses "depuis"), accept correct equivalents such as
        English present perfect OR present perfect continuous (e.g. "has studied" / "has been studying").
    - For EN->FR, prefer natural French present with "depuis" for ongoing duration (e.g. "Elle etudie ... depuis 3 ans").
    - Do NOT prefer unnatural French like "a etudie ... depuis 3 ans" when the action is still ongoing.
- Give feedback IN FRENCH, encouraging and practical (2-3 sentences max).
- Suggest an improved version only if the learner's answer had errors.

Return ONLY valid JSON:
{{
  "score": 85,
  "correct": true,
  "feedback_fr": "Très bien ! ...",
  "improved_answer": ""
}}
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        EVAL_MODEL,
        temperature=0.2,
        max_tokens=300,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, dict):
        return None, "Évaluation invalide : réponse JSON non reconnue."
    return data, None


# ═══════════════════════════════════════════════════════════════════════════════
# THEMED DIALOGUES — Dialogues par thème de vie + focus grammatical
# ═══════════════════════════════════════════════════════════════════════════════


def mt_themed_dialogue_file_path(profile_id="default"):
    slug = _profile_storage_slug(profile_id)
    os.makedirs(MT_THEMED_DIALOGUE_DIR, exist_ok=True)
    return os.path.join(MT_THEMED_DIALOGUE_DIR, f"tdial-{slug}.json")


def load_mt_themed_dialogues(profile_id="default"):
    path = mt_themed_dialogue_file_path(profile_id)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_mt_themed_dialogues(sessions, profile_id="default"):
    os.makedirs(MT_THEMED_DIALOGUE_DIR, exist_ok=True)
    with open(mt_themed_dialogue_file_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)


def generate_themed_dialogue(
    theme: str,
    grammar_focus: str,
    level: str,
    profile_id: str = "default",
):
    """Generate a realistic themed dialogue that naturally embeds a grammar focus.

    Returns (session_dict, error_str).
    """
    target = str(level or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"
    cefr = CEFR_DESCRIPTORS[target]

    prompt = f"""
You are an expert bilingual English-French language coach.
Generate a realistic dialogue for:
- Theme: {theme}
- Grammar focus: {grammar_focus} (must appear naturally 3-4 times in the dialogue)
- CEFR Level: {target} ({cefr['label']})

The dialogue must feel like a real conversation between two people, NOT an artificial exercise.
It should naturally use the target grammar structure in context.
Each line needs both English and French versions.

Return ONLY valid JSON (no markdown, no commentary) with this exact structure:
{{
  "title": "Short descriptive title of the dialogue (in English)",
  "context_fr": "Description du contexte en français : où ça se passe, qui parle, de quoi. 2-3 phrases.",
  "speakers": [
    {{"name": "Prénom", "role": "Rôle (ex: Client, Serveur, Collègue...)"}},
    {{"name": "Prénom", "role": "Rôle"}}
  ],
  "lines": [
    {{
      "speaker": "Prénom (identique à speakers)",
      "line_en": "Natural English line",
      "line_fr": "Traduction française naturelle",
      "grammar_tag": "{grammar_focus}" if this line uses the target grammar, else ""
    }},
    ... exactly 12 lines alternating between the two speakers
  ],
  "grammar_spotlight": [
    {{
      "structure": "Formule clé extraite du dialogue (ex: If I had..., I would...)",
      "example_from_dialogue": "The exact line from the dialogue that uses it",
      "explanation_fr": "Courte explication en français (1-2 phrases)"
    }}
  ],
  "vocabulary_fr": [
    {{"word": "English word or phrase", "french": "traduction française", "tip": "astuce ou contexte d'usage"}}
  ]
}}

Critical rules:
1. Exactly 12 dialogue lines, alternating speakers.
2. The target grammar ({grammar_focus}) must appear in at least 3-4 lines (mark them with grammar_tag).
3. Dialogue must feel natural — characters have real motivations and emotions.
4. English must be natural {cefr['label']}-level American English.
5. Include 3-4 grammar_spotlight entries and 4-6 vocabulary items.
""".strip()

    text, err = openrouter_chat(
        [{"role": "user", "content": prompt}],
        CHAT_MODEL,
        temperature=0.5,
        max_tokens=4000,
    )
    if err:
        return None, err

    data = extract_json_from_text(text)
    if not isinstance(data, dict) or not data.get("lines"):
        return None, "Génération invalide : structure JSON incorrecte."

    # Normalise lines
    lines = []
    for line in data.get("lines", [])[:14]:
        if not isinstance(line, dict):
            continue
        lines.append(
            {
                "speaker": str(line.get("speaker", "")).strip(),
                "line_en": str(line.get("line_en", "")).strip(),
                "line_fr": str(line.get("line_fr", "")).strip(),
                "grammar_tag": str(line.get("grammar_tag", "")).strip(),
                "audio_path_en": None,
            }
        )

    grammar_spotlight = [
        {
            "structure": str(gs.get("structure", "")).strip(),
            "example_from_dialogue": str(gs.get("example_from_dialogue", "")).strip(),
            "explanation_fr": str(gs.get("explanation_fr", "")).strip(),
        }
        for gs in data.get("grammar_spotlight", [])
        if isinstance(gs, dict)
    ]

    vocabulary_fr = [
        {
            "word": str(v.get("word", "")).strip(),
            "french": str(v.get("french", "")).strip(),
            "tip": str(v.get("tip", "")).strip(),
        }
        for v in data.get("vocabulary_fr", [])
        if isinstance(v, dict) and v.get("word")
    ]

    speakers = [
        {"name": str(s.get("name", "")).strip(), "role": str(s.get("role", "")).strip()}
        for s in data.get("speakers", [])
        if isinstance(s, dict)
    ]

    session_id = f"mt-tdial-{utc_now().strftime('%Y%m%d%H%M')}-{uuid.uuid4().hex[:6]}"
    session = {
        "id": session_id,
        "profile_id": profile_id,
        "level": target,
        "theme": theme,
        "grammar_focus": grammar_focus,
        "created_at": now_iso(),
        "title": str(data.get("title", theme)).strip(),
        "context_fr": str(data.get("context_fr", "")).strip(),
        "speakers": speakers,
        "lines": lines,
        "grammar_spotlight": grammar_spotlight,
        "vocabulary_fr": vocabulary_fr,
    }
    return session, None


def _save_themed_dialogue_line_audio(
    session_id: str, line_idx: int, audio_bytes: bytes
) -> str:
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(
        MICHEL_THOMAS_AUDIO_DIR,
        f"tdial-{session_id}_line{line_idx}_en.wav",
    )
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _update_themed_dialogue_line_audio(profile_id, sid, line_idx, new_path):
    all_sessions = load_mt_themed_dialogues(profile_id)
    for s in all_sessions:
        if s["id"] == sid and line_idx < len(s.get("lines", [])):
            s["lines"][line_idx]["audio_path_en"] = new_path
            break
    save_mt_themed_dialogues(all_sessions, profile_id)


def _save_dialogue_full_audio(session_id: str, audio_bytes: bytes) -> str:
    """Persist the full concatenated dialogue audio."""
    os.makedirs(MICHEL_THOMAS_AUDIO_DIR, exist_ok=True)
    path = os.path.join(MICHEL_THOMAS_AUDIO_DIR, f"tdial-{session_id}_full.wav")
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _update_dialogue_full_audio(profile_id, sid, new_path):
    all_sessions = load_mt_themed_dialogues(profile_id)
    for s in all_sessions:
        if s["id"] == sid:
            s["full_audio_path"] = new_path
            break
    save_mt_themed_dialogues(all_sessions, profile_id)
