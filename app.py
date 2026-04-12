import base64
import hashlib
import io
import json
import os
import re
import uuid
import wave
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests
import streamlit as st
import streamlit.components.v1 as st_components
from dotenv import load_dotenv
from streamlit_autorefresh import st_autorefresh

load_dotenv()


def _cfg(key, default=""):
    """Read config: .env / os.environ first (local), then st.secrets (Streamlit Cloud)."""
    # os.environ is populated by load_dotenv() locally — always prefer it
    env_val = os.getenv(key)
    if env_val is not None:
        return env_val
    # Fallback: Streamlit Cloud secrets (no .env file on cloud)
    try:
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return default


OPENROUTER_API_KEY = _cfg("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
YOUR_SITE_URL = _cfg("YOUR_SITE_URL", "http://localhost:8501")

STT_MODEL = _cfg("OPENROUTER_STT_MODEL", "google/gemini-2.5-flash")
CHAT_MODEL = _cfg("OPENROUTER_CHAT_MODEL", "openai/gpt-4o-mini")
EVAL_MODEL = _cfg("OPENROUTER_EVAL_MODEL", "openai/gpt-4o")
TTS_MODEL = _cfg("OPENROUTER_TTS_MODEL", "openai/gpt-4o-audio-preview")
TTS_VOICE = _cfg("OPENROUTER_TTS_VOICE", "alloy")
TTS_AUDIO_FORMAT = _cfg("OPENROUTER_TTS_AUDIO_FORMAT", "pcm16")
TTS_PCM_SAMPLE_RATE = int(_cfg("OPENROUTER_TTS_PCM_SAMPLE_RATE", "24000"))
TTS_FALLBACK_MODELS = [
    item.strip()
    for item in _cfg("OPENROUTER_TTS_FALLBACK_MODELS", "").split(",")
    if item.strip()
]
TTS_FALLBACK_VOICES = [
    item.strip()
    for item in _cfg("OPENROUTER_TTS_FALLBACK_VOICES", "").split(",")
    if item.strip()
]

DATA_DIR = "data"
LESSON_PACK_DIR = os.path.join(DATA_DIR, "lesson_packs")
LESSON_AUDIO_DIR = os.path.join(DATA_DIR, "lesson_audio")
VARIATIONS_DIR = os.path.join(DATA_DIR, "variations")
USER_CONVERSATIONS_DIR = "user_conversations"
SESSIONS_DIR = os.path.join(USER_CONVERSATIONS_DIR, "sessions")
AUDIO_DIR = os.path.join(USER_CONVERSATIONS_DIR, "audio")
PROFILES_DIR = os.path.join(USER_CONVERSATIONS_DIR, "profiles")
PROFILES_FILE = os.path.join(PROFILES_DIR, "profiles.json")
LESSON_FLASHCARD_LIMIT = 10
SHADOWING_DIR = os.path.join(USER_CONVERSATIONS_DIR, "shadowing")
SHADOWING_AUDIO_DIR = os.path.join(SHADOWING_DIR, "audio")
SHADOWING_DAILY_FILE = os.path.join(SHADOWING_DIR, "daily_assignments.json")
SHADOWING_MAX_RECORD_SECONDS = 3.0
SHADOWING_SUBMIT_GRACE_SECONDS = 4.0
SHADOWING_PREP_SECONDS = 2.0

ESSENTIAL_THEMES = {
    # — Daily Life & Basics —
    "Introductions & small talk": "Meet new people, build rapport, and keep a conversation going naturally.",
    "Daily routines & habits": "Talk about your morning, weekly schedule, and personal organization.",
    "Weather & seasons": "Discuss weather, seasonal changes, and how they affect daily life.",
    "Time & scheduling": "Ask about availability, set appointments, manage conflicting plans.",
    # — Food & Drink —
    "Restaurants & coffee shops": "Order food, ask for recommendations, and handle special requests politely.",
    "Grocery shopping & markets": "Find items, ask staff, compare products, discuss prices and ingredients.",
    "Cooking & recipes": "Describe dishes, share recipes, discuss food preferences and dietary needs.",
    "Bars & nightlife": "Order drinks, socialize at events, handle American bar culture confidently.",
    # — Housing & Neighborhood —
    "Housing & renting apartments": "Discuss rent, lease terms, repairs, and tenant-landlord relationships.",
    "Home repairs & maintenance": "Describe problems, hire contractors, discuss quotes and timelines.",
    "Neighbors & community": "Handle neighborhood issues, introduce yourself, discuss local events.",
    "Moving & relocation": "Organize a move, discuss neighborhoods, hire movers, change address.",
    # — Shopping & Services —
    "Clothing & fashion shopping": "Find sizes, try things on, describe style preferences, make returns.",
    "Electronics & tech products": "Ask about specs, compare products, handle warranties and returns.",
    "Online shopping & delivery": "Track orders, handle damaged deliveries, contact customer service.",
    "Salons & personal services": "Book appointments, describe what you want, handle service issues.",
    # — Transportation —
    "Driving & cars": "Discuss car problems, ask for directions, talk about road trips.",
    "Public transportation": "Use subway, bus, and train systems confidently in American cities.",
    "Rideshare & taxis": "Use Uber/Lyft, communicate with drivers, handle trip issues.",
    "Airports & flights": "Check in, handle delays, navigate airports, talk to airline staff.",
    # — Health & Wellness —
    "Doctor visits & symptoms": "Describe health issues, understand medical instructions, ask questions.",
    "Pharmacy & medication": "Ask about prescriptions, over-the-counter meds, dosage instructions.",
    "Fitness & gym": "Discuss workouts, ask gym staff for help, talk about health goals.",
    "Mental health & stress": "Discuss stress, burnout, emotions, and seeking help — naturally.",
    "Dentist & specialist visits": "Handle appointments, describe concerns, understand treatment plans.",
    # — Work & Professional —
    "Job interviews": "Answer common questions, sell your skills, ask smart closing questions.",
    "Office & workplace dynamics": "Discuss tasks, deadlines, teamwork, and professional relationships.",
    "Meetings & presentations": "Lead or participate in meetings, present ideas clearly and confidently.",
    "Networking & professional events": "Start conversations, exchange contacts, make lasting impressions.",
    "Remote work & work-from-home": "Discuss tools, video calls, productivity, and work-life balance.",
    "Conflict at work": "Handle disagreements professionally, give feedback, resolve misunderstandings.",
    "Phone calls & customer service": "Resolve problems effectively and stay calm on support calls.",
    # — Education —
    "University & college life": "Discuss courses, professors, campus life, and academic challenges.",
    "Online learning & certifications": "Talk about MOOCs, certifications, skill development online.",
    "Study strategies & tutoring": "Discuss learning methods, study groups, time management.",
    # — Finance & Admin —
    "Banking & money management": "Handle payments, fees, subscriptions, accounts, and budgeting.",
    "Taxes & government forms": "Discuss filing taxes, understand basic American tax concepts.",
    "Insurance": "Handle health, car, and home insurance policies and claims.",
    "Loans & credit": "Discuss mortgages, credit cards, debt, and personal finance choices.",
    # — Technology & Digital —
    "Social media & content creation": "Discuss platforms, trends, digital culture, and online presence.",
    "Tech support & troubleshooting": "Describe computer problems, work with tech support, find solutions.",
    "Privacy & cybersecurity": "Talk about online safety, passwords, scams, and data privacy.",
    "Streaming & entertainment apps": "Discuss Netflix, Spotify, podcasts, and digital subscriptions.",
    # — Social Life & Relationships —
    "Friendship & social plans": "Make plans, cancel gracefully, maintain friendships authentically.",
    "Dating & relationships": "Talk about dating culture, relationships, and personal boundaries.",
    "Family & household": "Discuss family dynamics, parenting, and household responsibilities.",
    "Parties & social gatherings": "Navigate social events, make conversation, American party culture.",
    "Giving & receiving compliments": "Accept praise naturally, give genuine compliments, handle awkward moments.",
    # — Hobbies, Sports & Leisure —
    "Sports & watching games": "Discuss American football, basketball, baseball — fan culture, scores.",
    "Outdoor activities & adventures": "Hiking, camping, road trips — plan and discuss adventures.",
    "Arts, museums & culture": "Discuss exhibitions, movies, books, and cultural experiences.",
    "Music & concerts": "Talk about genres, artists, live music, and events.",
    "Video games & gaming culture": "Discuss gaming, esports, game recommendations.",
    # — Travel & Tourism —
    "Hotels & accommodation": "Check in/out, request amenities, handle hotel problems.",
    "Sightseeing & tourism": "Ask for recommendations, describe attractions, plan a day out.",
    "Vacation planning": "Discuss destinations, budgets, packing, and itinerary.",
    # — Emergencies & Formal —
    "Emergencies & accidents": "Call 911, describe emergencies, stay calm under pressure.",
    "Lost items & theft": "Report theft, describe lost items, work with police or staff.",
    "Legal situations basics": "Understand basic rights, work with a lawyer, sign contracts.",
    # — American Culture & Advanced —
    "American holidays & traditions": "Discuss Thanksgiving, 4th of July, Halloween, cultural customs.",
    "American humor & sarcasm": "Understand jokes, irony, and casual American banter.",
    "Debates & expressing opinions": "Argue a point respectfully, back opinions with evidence.",
    "Storytelling & anecdotes": "Tell engaging stories, use narrative tenses, keep listeners interested.",
    "Negotiations & persuasion": "Bargain, persuade, and reach agreements in everyday contexts.",
    "Apologizing & forgiving": "Apologize sincerely in different contexts, accept or reject apologies.",
}

THEME_CATEGORIES = {
    "Tout afficher": list(ESSENTIAL_THEMES.keys()),
    "Vie quotidienne": [
        "Introductions & small talk",
        "Daily routines & habits",
        "Weather & seasons",
        "Time & scheduling",
    ],
    "Nourriture & Boissons": [
        "Restaurants & coffee shops",
        "Grocery shopping & markets",
        "Cooking & recipes",
        "Bars & nightlife",
    ],
    "Logement & Quartier": [
        "Housing & renting apartments",
        "Home repairs & maintenance",
        "Neighbors & community",
        "Moving & relocation",
    ],
    "Shopping & Services": [
        "Clothing & fashion shopping",
        "Electronics & tech products",
        "Online shopping & delivery",
        "Salons & personal services",
    ],
    "Transport": [
        "Driving & cars",
        "Public transportation",
        "Rideshare & taxis",
        "Airports & flights",
    ],
    "Santé & Bien-être": [
        "Doctor visits & symptoms",
        "Pharmacy & medication",
        "Fitness & gym",
        "Mental health & stress",
        "Dentist & specialist visits",
    ],
    "Travail & Professionnel": [
        "Job interviews",
        "Office & workplace dynamics",
        "Meetings & presentations",
        "Networking & professional events",
        "Remote work & work-from-home",
        "Conflict at work",
        "Phone calls & customer service",
    ],
    "Education": [
        "University & college life",
        "Online learning & certifications",
        "Study strategies & tutoring",
    ],
    "Finance & Admin": [
        "Banking & money management",
        "Taxes & government forms",
        "Insurance",
        "Loans & credit",
    ],
    "Technologie & Digital": [
        "Social media & content creation",
        "Tech support & troubleshooting",
        "Privacy & cybersecurity",
        "Streaming & entertainment apps",
    ],
    "Vie sociale & Relations": [
        "Friendship & social plans",
        "Dating & relationships",
        "Family & household",
        "Parties & social gatherings",
        "Giving & receiving compliments",
    ],
    "Hobbies, Sports & Loisirs": [
        "Sports & watching games",
        "Outdoor activities & adventures",
        "Arts, museums & culture",
        "Music & concerts",
        "Video games & gaming culture",
    ],
    "Voyages & Tourisme": [
        "Hotels & accommodation",
        "Sightseeing & tourism",
        "Vacation planning",
    ],
    "Urgences & Formalités": [
        "Emergencies & accidents",
        "Lost items & theft",
        "Legal situations basics",
    ],
    "Culture américaine & Avancé": [
        "American holidays & traditions",
        "American humor & sarcasm",
        "Debates & expressing opinions",
        "Storytelling & anecdotes",
        "Negotiations & persuasion",
        "Apologizing & forgiving",
    ],
}

CEFR_DESCRIPTORS = {
    "A1": {
        "label": "A1 — Débutant",
        "badge": "⚪ A1",
        "english": (
            "Use very simple everyday words and short sentences. "
            "Prefer present simple and basic question forms. "
            "Keep ideas concrete and direct with frequent repetition. "
            "Prioritize clarity over complexity."
        ),
    },
    "A2": {
        "label": "A2 — Élémentaire",
        "badge": "🟡 A2",
        "english": (
            "Use common vocabulary for daily routines, family, shopping, and work basics. "
            "Use short linked sentences with simple past/future forms when needed. "
            "Ask and answer practical questions clearly. "
            "Minor grammar mistakes are acceptable if meaning stays clear."
        ),
    },
    "B1": {
        "label": "B1 — Intermédiaire",
        "badge": "🔵 B1",
        "english": (
            "Use high-frequency vocabulary and simple phrasal verbs. "
            "Stick to present/past/future tenses, basic conditionals (if + will), and simple modals. "
            "Short connected sentences with natural hesitations (um, let me think, well...). "
            "Occasional grammar mistakes are natural. Focus on getting the message across clearly."
        ),
    },
    "B2": {
        "label": "B2 — Intermédiaire supérieur",
        "badge": "🟢 B2",
        "english": (
            "Use a wider vocabulary range, some common idioms, and discourse markers "
            "(however, although, as a result, that being said). "
            "Include passive voice, reported speech, real and unreal conditionals. "
            "Ideas are well connected. Some idiomatic expressions. Minor grammar slips occasionally."
        ),
    },
    "C1": {
        "label": "C1 — Avancé",
        "badge": "🟠 C1",
        "english": (
            "Use sophisticated vocabulary, nuanced expressions, and phrasal verbs naturally. "
            "Include complex subordination, cleft sentences, advanced modals, and inversion. "
            "Fluent, precise, handles ambiguity well. Natural American hesitation patterns "
            "(I mean, you know, come to think of it). Near-native accuracy. Rich in idioms."
        ),
    },
    "C2": {
        "label": "C2 — Maîtrise",
        "badge": "🔴 C2",
        "english": (
            "Completely native-like American English. Perfect collocations, natural slang, "
            "humor, sarcasm, and cultural references. All grammatical structures used flawlessly. "
            "Register shifts naturally (formal to casual mid-conversation). "
            "Complex argumentation. Completely effortless flow."
        ),
    },
}

CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

VARIATION_SITUATIONS = [
    "first-time conversation",
    "problem-solving discussion",
    "quick decision under time pressure",
    "polite disagreement",
    "making a request",
    "follow-up after a misunderstanding",
    "planning for tomorrow",
    "asking for advice",
    "comparing two options",
    "wrapping up and next steps",
]

# Available OpenAI voices on OpenRouter audio-preview:
#   alloy (neutral), echo (male), fable (narrative), onyx (deep male),
#   nova (female), shimmer (soft female)
VOICE_PAIRS = {
    "Homme + Femme  (echo + nova)": ("echo", "nova"),
    "Femme + Homme  (nova + echo)": ("nova", "echo"),
    "Homme + Homme  (echo + onyx)": ("echo", "onyx"),
    "Femme + Femme  (nova + shimmer)": ("nova", "shimmer"),
    "Neutre + Femme (alloy + nova)": ("alloy", "nova"),
}

PODCAST_DIR = os.path.join(DATA_DIR, "podcasts")
PODCAST_AUDIO_DIR = os.path.join(DATA_DIR, "podcast_audio")

USER_INTERESTS = [
    "World News & Current Affairs",
    "Artificial Intelligence & Technology",
    "Football (Soccer)",
    "Manga & Anime",
]

STORY_DIR = os.path.join(DATA_DIR, "stories")
STORY_AUDIO_DIR = os.path.join(DATA_DIR, "story_audio")
AI_LESSON_DIR = os.path.join(DATA_DIR, "ai_lessons")
AI_LESSON_FILE = os.path.join(AI_LESSON_DIR, "lessons.json")
AI_LESSON_AUDIO_DIR = os.path.join(DATA_DIR, "ai_lessons_audio")

VOCAB_DIR = os.path.join(DATA_DIR, "vocabulary")
VOCAB_FILE = os.path.join(VOCAB_DIR, "vocab.json")
VOCAB_AUDIO_DIR = os.path.join(DATA_DIR, "vocab_audio")

STORY_CATEGORIES = {
    "🏯 Manga & Anime": [
        "Epic samurai clan war — betrayal and redemption",
        "Young ninja discovers a forbidden bloodline power",
        "Fantasy kingdom torn apart by a dragon god awakening",
        "Rival pirates racing for a legendary lost island",
        "Magical academy — the outcast student saves the world",
        "Post-apocalyptic Japan — last warriors vs machine empire",
        "Demon hunter falls in love with the demon queen",
    ],
    "👑 Rois & Empires": [
        "The rise and fall of the Roman Empire's greatest emperor",
        "A Viking king unites the warring Norse clans",
        "The last Aztec emperor fights Spanish conquistadors",
        "A Tang dynasty empress seizes the Dragon Throne",
        "The Mongol warlord who conquered half the world",
        "Medieval French king builds the most powerful court in Europe",
        "An African king defends his gold kingdom from European invaders",
    ],
    "🌍 Pays & Nations": [
        "The birth of the United States — 13 colonies rise up",
        "Japan's transformation from samurai era to industrial power",
        "Brazil — from Portuguese colony to vast independent nation",
        "South Korea's rise from rubble to tech superpower",
        "Cuba's revolution — poverty, cigars and Cold War tension",
        "The founding of Israel — a nation born from conflict",
        "India gains independence — Gandhi's non-violent revolution",
    ],
    "🏛️ Présidents & Leaders": [
        "Abraham Lincoln — saving the Union during Civil War",
        "Nelson Mandela — 27 years in prison to president",
        "John F. Kennedy — the assassination no one forgets",
        "Napoleon Bonaparte — from Corsican soldier to Emperor of Europe",
        "Winston Churchill — Britain alone against Hitler",
        "Cleopatra — the queen who seduced two Roman generals",
        "George Washington — the reluctant first president",
    ],
    "📜 Documentaires historiques": [
        "The construction of the Great Pyramid of Giza",
        "The Black Death — how the plague reshaped medieval Europe",
        "The Space Race — USA vs USSR in the cosmos",
        "The Silk Road — merchants, spies and empires connected",
        "Titanic — the night the unsinkable ship sank",
        "World War II resistance — secret agents behind enemy lines",
        "The Cold War — spies, nukes and the Berlin Wall",
    ],
    "⚔️ Guerres & Batailles": [
        "D-Day — soldiers storm the beaches of Normandy",
        "The Battle of Thermopylae — 300 Spartans vs a million Persians",
        "Stalingrad — the brutal winter battle that turned WWII",
        "The American Civil War — brothers against brothers",
        "The Crusades — knights march to the Holy Land",
        "The Hundred Years' War — Joan of Arc leads France",
        "The Battle of Waterloo — Napoleon's final defeat",
    ],
    "🔬 Sciences & Découvertes": [
        "Marie Curie — the woman who discovered radioactivity",
        "The race to decode DNA — Watson, Crick and Rosalind Franklin",
        "The Apollo 11 moon landing — 8 days to eternity",
        "Charles Darwin's voyage on the Beagle — evolution discovered",
        "Nikola Tesla vs Edison — the war of currents",
        "The discovery of penicillin — a mold that saved millions",
        "Einstein's theory of relativity — rewriting physics forever",
    ],
    "🌿 Nature & Exploration": [
        "Ernest Shackleton — trapped in Antarctic ice for 634 days",
        "Christopher Columbus — three ships and an impossible gamble",
        "Marco Polo — from Venice to the court of Kublai Khan",
        "James Cook — mapping the Pacific and finding Australia",
        "The Amazon rainforest — secrets of the world's lungs",
        "Deep ocean — scientists descend to the darkest trench on Earth",
        "Lewis and Clark — crossing untamed America to the Pacific",
    ],
}

STORY_NARRATOR_VOICES = {
    "Alloy (neutre)": "alloy",
    "Echo (masculin)": "echo",
    "Onyx (grave masculin)": "onyx",
    "Nova (féminin)": "nova",
    "Shimmer (doux féminin)": "shimmer",
    "Fable (narrateur)": "fable",
}

PRACTICE_DRILL_MODES = {
    "Standard fluency": {
        "key": "standard",
        "description": "Natural conversation with implicit recasts.",
    },
    "Conversation stress": {
        "key": "conversation_stress",
        "description": "Short answers, quick turn-taking, and direct follow-ups.",
    },
    "No translation": {
        "key": "no_translation",
        "description": "English-only reformulation when a word is missing.",
    },
    "Tense switch": {
        "key": "tense_switch",
        "description": "Practice one tense target and reformulate across tenses.",
    },
    "Missing-word rescue": {
        "key": "word_rescue",
        "description": "Train paraphrasing instead of stopping when vocabulary is missing.",
    },
}


def ensure_directories():
    for path in [
        DATA_DIR,
        LESSON_PACK_DIR,
        LESSON_AUDIO_DIR,
        VARIATIONS_DIR,
        USER_CONVERSATIONS_DIR,
        PROFILES_DIR,
        SHADOWING_DIR,
        SHADOWING_AUDIO_DIR,
        SESSIONS_DIR,
        AUDIO_DIR,
        PODCAST_DIR,
        PODCAST_AUDIO_DIR,
        STORY_DIR,
        STORY_AUDIO_DIR,
        AI_LESSON_DIR,
        AI_LESSON_AUDIO_DIR,
        VOCAB_DIR,
        VOCAB_AUDIO_DIR,
        CONNECTED_SPEECH_DIR,
        CONNECTED_SPEECH_AUDIO_DIR,
        SLANG_DIR,
        IMMERSION_GENERATED_DIR,
        REAL_ENGLISH_DIR,
        REAL_ENGLISH_AUDIO_DIR,
    ]:
        os.makedirs(path, exist_ok=True)


def now_iso():
    return utc_iso(utc_now())


def utc_now():
    return datetime.now(timezone.utc)


def utc_iso(dt):
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def slugify(value):
    value = value.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def _profile_storage_slug(profile_id):
    return slugify(profile_id or "default") or "default"


def save_profiles(profiles):
    os.makedirs(PROFILES_DIR, exist_ok=True)
    with open(PROFILES_FILE, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, indent=2)


def load_profiles():
    if not os.path.exists(PROFILES_FILE):
        default_profiles = [
            {
                "id": "default",
                "name": "Profil principal",
                "target_cefr": "B1",
                "module_levels": {},
                "created_at": now_iso(),
            }
        ]
        save_profiles(default_profiles)
        return default_profiles

    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = []

    profiles = []
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            pid = str(item.get("id", "")).strip() or f"profile-{slugify(name)}"
            pid = _profile_storage_slug(pid)
            target = str(item.get("target_cefr", "B1")).upper()
            if target not in CEFR_LEVELS:
                target = "B1"
            module_levels_raw = item.get("module_levels", {})
            module_levels = {}
            if isinstance(module_levels_raw, dict):
                for k, v in module_levels_raw.items():
                    vv = str(v).upper()
                    if vv in CEFR_LEVELS:
                        module_levels[str(k)] = vv
            profiles.append(
                {
                    "id": pid,
                    "name": name,
                    "target_cefr": target,
                    "module_levels": module_levels,
                    "created_at": item.get("created_at") or now_iso(),
                }
            )

    if not profiles:
        profiles = [
            {
                "id": "default",
                "name": "Profil principal",
                "target_cefr": "B1",
                "module_levels": {},
                "created_at": now_iso(),
            }
        ]

    if not any(p.get("id") == "default" for p in profiles):
        profiles.insert(
            0,
            {
                "id": "default",
                "name": "Profil principal",
                "target_cefr": "B1",
                "module_levels": {},
                "created_at": now_iso(),
            },
        )

    save_profiles(profiles)
    return profiles


def create_or_update_profile(name, target_cefr="B1"):
    clean_name = str(name or "").strip()
    if not clean_name:
        return None, "Le nom du profil est obligatoire."

    target = str(target_cefr or "B1").upper()
    if target not in CEFR_LEVELS:
        target = "B1"

    profiles = load_profiles()
    existing = next(
        (p for p in profiles if p.get("name", "").lower() == clean_name.lower()), None
    )
    if existing:
        existing["target_cefr"] = target
        save_profiles(profiles)
        return existing, None

    profile_id = _profile_storage_slug(f"profile-{slugify(clean_name)}")
    if any(p.get("id") == profile_id for p in profiles):
        profile_id = _profile_storage_slug(f"{profile_id}-{uuid.uuid4().hex[:6]}")

    profile = {
        "id": profile_id,
        "name": clean_name,
        "target_cefr": target,
        "module_levels": {},
        "created_at": now_iso(),
    }
    profiles.append(profile)
    save_profiles(profiles)
    return profile, None


def update_profile_target_cefr(profile_id, target_cefr):
    target = str(target_cefr or "B1").upper()
    if target not in CEFR_LEVELS:
        return

    profiles = load_profiles()
    changed = False
    for p in profiles:
        if p.get("id") == profile_id and p.get("target_cefr") != target:
            p["target_cefr"] = target
            changed = True
            break
    if changed:
        save_profiles(profiles)


def get_active_profile():
    profiles = load_profiles()
    active_id = st.session_state.get("active_profile_id")
    active = next((p for p in profiles if p.get("id") == active_id), None)
    if not active:
        active = profiles[0]
        st.session_state["active_profile_id"] = active["id"]
    st.session_state["active_profile_name"] = active.get("name", "Profil principal")
    st.session_state["active_profile_target_cefr"] = active.get("target_cefr", "B1")
    return active


def get_profile_module_level(profile, module_key, fallback_level=None):
    fallback = str(fallback_level or profile.get("target_cefr", "B1")).upper()
    if fallback not in CEFR_LEVELS:
        fallback = "B1"

    levels = profile.get("module_levels", {})
    if not isinstance(levels, dict):
        return fallback
    level = str(levels.get(module_key, fallback)).upper()
    if level not in CEFR_LEVELS:
        return fallback
    return level


def set_profile_module_level(profile_id, module_key, level):
    new_level = str(level or "").upper()
    if new_level not in CEFR_LEVELS:
        return

    profiles = load_profiles()
    changed = False
    for p in profiles:
        if p.get("id") != profile_id:
            continue
        levels = p.get("module_levels")
        if not isinstance(levels, dict):
            levels = {}
            p["module_levels"] = levels
        if levels.get(module_key) != new_level:
            levels[module_key] = new_level
            changed = True
        break
    if changed:
        save_profiles(profiles)


def openrouter_headers(title="English Audio Coach"):
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": YOUR_SITE_URL,
        "X-Title": title,
    }


def openrouter_chat(messages, model, temperature=0.4, max_tokens=1200):
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY manquante."

    response = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers=openrouter_headers(),
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=120,
    )

    if response.status_code != 200:
        return None, response.text

    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        content = "\n".join([p for p in text_parts if p]).strip()
    return content, None


def transcribe_audio_with_openrouter(audio_bytes, audio_format="wav"):
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY manquante."

    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
    messages = [
        {
            "role": "system",
            "content": "You are a precise transcription assistant. Return only the transcript text in English.",
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Transcribe this audio. Keep punctuation simple and return plain text only.",
                },
                {
                    "type": "input_audio",
                    "input_audio": {"data": b64_audio, "format": audio_format},
                },
            ],
        },
    ]

    text, err = openrouter_chat(messages, STT_MODEL, temperature=0.0, max_tokens=400)
    if err:
        return None, err
    return text.strip(), None


def _mime_for_audio_format(audio_format):
    mapping = {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "flac": "audio/flac",
        "opus": "audio/opus",
        "pcm16": "audio/wav",
    }
    return mapping.get(audio_format.lower(), "audio/wav")


def pcm16_to_wav_bytes(
    pcm_bytes, sample_rate=TTS_PCM_SAMPLE_RATE, channels=1, sample_width=2
):
    """Wrap raw PCM16 bytes into a WAV container so Streamlit can play it."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def _dedup_preserve_order(items):
    seen = set()
    output = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _extract_provider_error(raw_text):
    try:
        payload = json.loads(raw_text)
        error_obj = payload.get("error", {})
        message = error_obj.get("message")
        metadata = error_obj.get("metadata", {})
        provider = metadata.get("provider_name")
        if provider and message:
            return f"{provider}: {message}"
        if message:
            return message
    except Exception:
        pass
    return raw_text


def _stream_tts_once(text, model, voice, requested_format, tone_hint=None):
    max_retries = 3
    last_conn_err = None
    # Build system prompt — add tone/emotion guidance when available
    base_system = (
        "You are a text-to-speech narrator with a natural American accent. "
        "Your only job is to read the text provided by the user EXACTLY as written, "
        "word for word. Do NOT respond to the content, do NOT add commentary, "
        "do NOT answer questions in the text. "
        "NEVER read speaker names, labels like 'A:' or 'B:', or character names followed by colons. "
        "NEVER read stage directions such as (laughs), [sighs], *whispers* or similar annotations. "
        "Read only the actual spoken words."
    )
    if tone_hint:
        base_system += f" Deliver this line {tone_hint}."
    for attempt in range(max_retries):
        if attempt > 0:
            import time

            time.sleep(2**attempt)
        try:
            response = requests.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers={
                    **openrouter_headers(),
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": base_system,
                        },
                        {
                            "role": "user",
                            "content": f"Read this text aloud exactly as written:\n\n{text}",
                        },
                    ],
                    "modalities": ["text", "audio"],
                    "audio": {"voice": voice, "format": requested_format},
                    "stream": True,
                },
                stream=True,
                timeout=120,
            )
            break
        except requests.exceptions.ConnectionError as conn_err:
            last_conn_err = conn_err
            continue
    else:
        return (
            None,
            None,
            f"[{model}/{voice}] Connexion interrompue après {max_retries} tentatives: {last_conn_err}",
        )

    if response.status_code != 200:
        return (
            None,
            None,
            f"[{model}/{voice}] {_extract_provider_error(response.text)}",
        )

    audio_chunks_b64 = []
    try:
        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8", errors="ignore")
            if not decoded.startswith("data: "):
                continue

            data = decoded[len("data: ") :]
            if data.strip() == "[DONE]":
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue

            if "error" in chunk:
                err_obj = chunk.get("error", {})
                return (
                    None,
                    None,
                    f"[{model}/{voice}] {err_obj.get('message', 'Erreur streaming audio')}",
                )

            choices = chunk.get("choices", [])
            if not choices:
                continue

            delta = choices[0].get("delta", {})
            audio_delta = delta.get("audio", {})
            audio_b64 = audio_delta.get("data")
            if audio_b64:
                audio_chunks_b64.append(audio_b64)
    except requests.exceptions.ConnectionError as stream_err:
        return (
            None,
            None,
            f"[{model}/{voice}] Connexion interrompue pendant le streaming: {stream_err}",
        )

    if not audio_chunks_b64:
        return (
            None,
            None,
            f"[{model}/{voice}] Aucun chunk audio recu (modele/voix/format non compatibles).",
        )

    try:
        full_audio_b64 = "".join(audio_chunks_b64)
        audio_bytes = base64.b64decode(full_audio_b64)
    except Exception as exc:
        return None, None, f"[{model}/{voice}] Erreur decodage audio: {exc}"

    if requested_format == "pcm16":
        try:
            audio_bytes = pcm16_to_wav_bytes(audio_bytes)
            return audio_bytes, "audio/wav", None
        except Exception as exc:
            return None, None, f"[{model}/{voice}] Erreur conversion PCM16->WAV: {exc}"

    return audio_bytes, _mime_for_audio_format(requested_format), None


def text_to_speech_openrouter(text, voice=TTS_VOICE, audio_format=TTS_AUDIO_FORMAT, tone_hint=None):
    if not OPENROUTER_API_KEY:
        return None, None, "OPENROUTER_API_KEY manquante."

    requested_format = audio_format.lower()
    # OpenAI providers on OpenRouter require pcm16 for stream=true.
    if requested_format == "wav":
        requested_format = "pcm16"

    models_to_try = _dedup_preserve_order([TTS_MODEL] + TTS_FALLBACK_MODELS)
    voices_to_try = _dedup_preserve_order([voice] + TTS_FALLBACK_VOICES)

    attempts = []
    for model in models_to_try:
        for candidate_voice in voices_to_try:
            audio_bytes, mime_type, err = _stream_tts_once(
                text=text,
                model=model,
                voice=candidate_voice,
                requested_format=requested_format,
                tone_hint=tone_hint,
            )
            if not err:
                return audio_bytes, mime_type, None
            attempts.append(err)

    if attempts:
        # Keep message concise while still showing the latest provider feedback.
        return None, None, " | ".join(attempts[-3:])
    return None, None, "Aucune tentative TTS n'a pu etre executee."


def concatenate_wav_bytes(wav_bytes_list):
    """Concatenate a list of WAV byte-strings (same sample rate/channels) into one WAV."""
    params = None
    pcm_parts = []
    for wb in wav_bytes_list:
        buf = io.BytesIO(wb)
        with wave.open(buf, "rb") as wf:
            if params is None:
                params = wf.getparams()
            pcm_parts.append(wf.readframes(wf.getnframes()))
    out_buf = io.BytesIO()
    with wave.open(out_buf, "wb") as wf:
        wf.setparams(params)
        for data in pcm_parts:
            wf.writeframes(data)
    return out_buf.getvalue()


def _clean_dialogue_line_for_tts(text):
    """Remove stage directions and extract emotional tone from a dialogue line.
    Strips parenthetical cues like (laughs), [sighs], *rire*, etc.
    Returns (cleaned_text, tone_hint) where tone_hint is a short emotion description or None.
    """
    # Collect stage directions to infer tone
    tone_cues = []
    # Match (laughs), (rire), [sighs], *chuckles*, etc.
    for m in re.finditer(r"[\(\[\*]([^\)\]\*]+)[\)\]\*]", text):
        cue = m.group(1).strip().lower()
        if cue:
            tone_cues.append(cue)
    # Remove all stage directions: (laughs), [sighs], *rire*
    cleaned = re.sub(r"\s*[\(\[]\s*[^\)\]]*[\)\]]\s*", " ", text)
    cleaned = re.sub(r"\s*\*[^\*]+\*\s*", " ", cleaned)
    # Remove stray speaker-name-only fragments (e.g. leftover "Sam," or "Lisa:")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # Map common cues to tone hints
    _TONE_MAP = {
        "laughs": "warmly amused, with a light laugh in the voice",
        "laughing": "warmly amused, with a light laugh in the voice",
        "rire": "warmly amused, with a light laugh in the voice",
        "chuckles": "softly amused, gentle chuckle",
        "sighs": "with a gentle sigh, reflective",
        "soupire": "with a gentle sigh, reflective",
        "whispers": "in a soft whisper",
        "chuchote": "in a soft whisper",
        "excited": "enthusiastic and excited",
        "excitedly": "enthusiastic and excited",
        "sadly": "with a sad, subdued tone",
        "triste": "with a sad, subdued tone",
        "angry": "with frustration in the voice",
        "surprised": "with genuine surprise",
        "hesitant": "hesitant, slightly uncertain",
        "sarcastically": "with dry sarcasm",
        "nervously": "slightly nervous",
        "smiling": "warm and smiling",
        "sourit": "warm and smiling",
        "pauses": "with a thoughtful pause",
    }
    tone_hint = None
    for cue in tone_cues:
        for key, hint in _TONE_MAP.items():
            if key in cue:
                tone_hint = hint
                break
        if tone_hint:
            break
    return cleaned, tone_hint


def parse_dialogue_to_turns(dialogue_text):
    """Parse 'SpeakerName: ...' lines into [{speaker, text, tone}, ...] dicts.
    The first distinct speaker name maps to 'A', the second to 'B'.
    Speaker labels are stripped from the text so they are never read aloud by TTS.
    Stage directions like (laughs), *rire* are removed and converted to tone hints.
    """
    turns = []
    current_speaker = None
    current_lines = []
    speaker_map = {}
    for line in dialogue_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z][\w\s]{0,20}?):\s*(.+)$", line)
        if m:
            raw_name = m.group(1).strip()
            if raw_name not in speaker_map:
                if len(speaker_map) == 0:
                    speaker_map[raw_name] = "A"
                else:
                    speaker_map[raw_name] = "B"
            mapped = speaker_map.get(raw_name, "A")
            if current_speaker is not None and current_lines:
                turns.append(
                    {"speaker": current_speaker, "text": " ".join(current_lines)}
                )
            current_speaker = mapped
            current_lines = [m.group(2)]
        elif current_speaker is not None:
            current_lines.append(line)
    if current_speaker is not None and current_lines:
        turns.append({"speaker": current_speaker, "text": " ".join(current_lines)})
    # Clean stage directions and extract tone for each turn
    for turn in turns:
        cleaned, tone = _clean_dialogue_line_for_tts(turn["text"])
        turn["text"] = cleaned
        turn["tone"] = tone
    return turns


def generate_dual_voice_tts(dialogue_text, voice_a, voice_b):
    """Generate dialogue audio giving voice_a to speaker A and voice_b to speaker B.
    Parses turns FIRST, then splits long individual turns — never pre-splits the full
    script so that speaker labels are never lost.
    """
    turns = parse_dialogue_to_turns(dialogue_text)
    if not turns:
        # no A:/B: labels found – fall back to single voice
        sub_chunks = split_text_for_tts(dialogue_text, max_chars=1200)
        wav_parts = []
        for chunk in sub_chunks:
            ab, _, err = text_to_speech_openrouter(chunk, voice=voice_a)
            if err:
                return None, None, err
            wav_parts.append(ab)
        if not wav_parts:
            return None, None, "Aucun audio genere."
        if len(wav_parts) == 1:
            return wav_parts[0], "audio/wav", None
        return concatenate_wav_bytes(wav_parts), "audio/wav", None

    wav_parts = []
    for turn in turns:
        voice = voice_a if turn["speaker"] == "A" else voice_b
        tone = turn.get("tone")
        # Split long individual turns — keeps speaker context intact
        sub_chunks = split_text_for_tts(turn["text"], max_chars=1200)
        for chunk in sub_chunks:
            audio_bytes, _, err = text_to_speech_openrouter(chunk, voice=voice, tone_hint=tone)
            if err:
                return None, None, f"Erreur voix {turn['speaker']}: {err}"
            wav_parts.append(audio_bytes)

    if not wav_parts:
        return None, None, "Aucun audio genere."
    if len(wav_parts) == 1:
        return wav_parts[0], "audio/wav", None
    try:
        final_wav = concatenate_wav_bytes(wav_parts)
        return final_wav, "audio/wav", None
    except Exception as exc:
        return None, None, f"Erreur concatenation audio: {exc}"


def split_text_for_tts(text, max_chars=1200):
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = []
    size = 0
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if size + len(sentence) > max_chars and current:
            chunks.append(" ".join(current))
            current = [sentence]
            size = len(sentence)
        else:
            current.append(sentence)
            size += len(sentence)
    if current:
        chunks.append(" ".join(current))
    return chunks


def extract_json_from_text(text):
    """Extract a JSON object/array from text that may be wrapped in markdown code blocks."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"(\[[\s\S]+\])", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"(\{[\s\S]+\})", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


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


def build_tutor_system_prompt(
    mode,
    theme,
    objective,
    target_cefr="B1",
    training_mode="standard",
    training_settings=None,
):
    training_settings = training_settings or {}
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
        f"Mode: {mode}. {topic_instruction} {objective_instruction} {training_instruction} "
        "Use natural chunking, rhythm, stress patterns, and fillers that American native speakers actually use."
    )


def choose_theme_with_ai():
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
):
    training_settings = training_settings or {}
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
                ),
            }
        ],
        "turns": [],
        "evaluation": None,
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


def save_audio_bytes(file_name, audio_bytes):
    path = os.path.join(AUDIO_DIR, file_name)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def ext_from_mime(mime_type):
    mapping = {
        "audio/wav": "wav",
        "audio/mpeg": "mp3",
        "audio/flac": "flac",
        "audio/opus": "opus",
    }
    return mapping.get((mime_type or "").lower(), "wav")


def _parse_iso(iso_text):
    if not iso_text:
        return None
    try:
        parsed = datetime.fromisoformat(str(iso_text).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _seconds_between_iso(start_iso, end_iso):
    start_dt = _parse_iso(start_iso)
    end_dt = _parse_iso(end_iso)
    if not start_dt or not end_dt:
        return None
    return max(0, int((end_dt - start_dt).total_seconds()))


def _seconds_since_iso(iso_text):
    dt = _parse_iso(iso_text)
    if not dt:
        return 0
    return max(0, int((utc_now() - dt).total_seconds()))


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
    messages = list(session_data["messages"])
    training_mode = session_data.get("training_mode", "standard")
    training_settings = session_data.get("training_settings", {})

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
        return None, err
    return text, None


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

    telemetry_lines = [
        f"- Active training mode: {training_mode}",
        f"- Target tense: {target_tense}",
        f"- Average response latency (seconds): {avg_latency if avg_latency is not None else 'N/A'}",
        f"- Number of slow replies (>=8s): {slow_replies}",
        f"- Detected self-repair markers: {self_repairs}",
    ]

    prompt = f"""
Evaluate this learner's spoken English targeting CEFR {target_cefr} ({CEFR_DESCRIPTORS[target_cefr]['label']}) in American English.

Give a score from 1 to 10 for:
- Grammar
- Chunks/Vocabulary
- Fluency
- Naturalness
- Tense consistency
- Recovery strategy when missing words

Then provide:
1) Strong points
2) Priority corrections (with corrected examples)
3) What to practice next week
4) Fluency drill metrics interpretation:
   - Explain response latency pattern
   - Explain tense consistency issues
   - Explain if self-repair strategy is effective

Session telemetry:
{chr(10).join(telemetry_lines)}

Conversation transcript (learner only):
{chr(10).join(user_lines)}
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
    session_limit=12, lesson_count=4, target_cefr="B1"
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


def render_ai_lessons_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Lecons basees sur vos echanges IA")
    st.write(
        "Ces lecons sont generees depuis vos conversations IA pour corriger vos vrais points faibles a l'oral."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    ai_level_default = get_profile_module_level(profile, "ai_lessons")
    ai_level = st.radio(
        "Niveau cible des lecons",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(ai_level_default),
        horizontal=True,
        key=f"ai-lessons-level-{profile_id}",
    )
    if ai_level != ai_level_default:
        set_profile_module_level(profile_id, "ai_lessons", ai_level)

    voice_label = st.selectbox(
        "Voix audio des exemples",
        list(STORY_NARRATOR_VOICES.keys()),
        index=0,
        key="ai-lessons-voice",
    )
    lesson_voice = STORY_NARRATOR_VOICES.get(voice_label, "alloy")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        session_limit = st.slider(
            "Nombre de sessions IA a analyser",
            min_value=3,
            max_value=30,
            value=12,
            key="ai-lessons-session-limit",
        )
    with col_b:
        lesson_count = st.slider(
            "Nombre de lecons",
            min_value=2,
            max_value=8,
            value=4,
            key="ai-lessons-count",
        )

    if st.button(
        "Generer / Regenerer mes lecons personnalisees",
        type="primary",
        width="stretch",
        key="ai-lessons-generate",
    ):
        with st.spinner("Analyse des conversations et generation des lecons..."):
            lessons, err = generate_ai_lessons_from_sessions(
                session_limit=session_limit,
                lesson_count=lesson_count,
                target_cefr=ai_level,
            )
        if err:
            st.error(f"Erreur generation lecons: {err}")
        else:
            save_ai_lessons(lessons, profile_id=profile_id)
            st.success(f"{len(lessons)} lecon(s) personnalisee(s) creee(s).")
            st.rerun()

    lessons = load_ai_lessons(profile_id=profile_id)
    if not lessons:
        st.info(
            "Aucune lecon personnalisee pour l'instant. Generez-les depuis vos echanges IA."
        )
        return

    st.caption(f"{len(lessons)} lecon(s) disponible(s)")
    for lesson in lessons:
        lid = lesson.get("id", uuid.uuid4().hex[:8])
        with st.expander(f"🎯 {lesson.get('focus', 'Lecon personnalisee')}"):
            st.markdown(f"**Concept a etudier :** {lesson.get('concept', '')}")

            mistakes = lesson.get("common_mistakes", [])
            if mistakes:
                st.markdown("**Points a corriger observes :**")
                for m in mistakes:
                    st.markdown(f"- {m}")

            tips = lesson.get("tips_to_remember", [])
            if tips:
                st.markdown("**Tips a retenir :**")
                for t in tips:
                    st.markdown(f"- {t}")

            examples = lesson.get("examples", [])
            st.markdown("**Phrases d'exemple (avec audio) :**")
            if not examples:
                st.caption("Pas d'exemple disponible.")
            if examples and st.button(
                "🔊 Generer tous les audios des exemples",
                key=f"ai-lesson-gen-all-{lid}",
                width="stretch",
            ):
                with st.spinner("Generation de tous les audios des exemples..."):
                    all_lessons = load_ai_lessons(profile_id=profile_id)
                    target = next((l for l in all_lessons if l.get("id") == lid), None)
                    if not target:
                        st.error("Lecon introuvable.")
                    else:
                        for ex_idx, ex_item in enumerate(target.get("examples", [])):
                            text = (
                                ex_item.get("text", "")
                                if isinstance(ex_item, dict)
                                else str(ex_item)
                            )
                            if not text.strip():
                                continue
                            ab, _, tts_err = text_to_speech_openrouter(
                                text,
                                voice=lesson_voice,
                            )
                            if tts_err:
                                continue
                            new_path = _save_ai_lesson_example_audio(lid, ex_idx, ab)
                            if isinstance(target["examples"][ex_idx], dict):
                                target["examples"][ex_idx]["audio_path"] = new_path
                        save_ai_lessons(all_lessons, profile_id=profile_id)
                st.rerun()
            for ex_idx, ex_item in enumerate(examples):
                text = (
                    ex_item.get("text", "")
                    if isinstance(ex_item, dict)
                    else str(ex_item)
                )
                audio_path = (
                    ex_item.get("audio_path") if isinstance(ex_item, dict) else None
                )
                st.markdown(f"**{ex_idx + 1}.** {text}")
                if audio_path and os.path.exists(audio_path):
                    st.audio(audio_path, format="audio/wav")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "🔄 Regenerer audio",
                            key=f"ai-lesson-regen-{lid}-{ex_idx}",
                            width="stretch",
                        ):
                            with st.spinner("Generation audio..."):
                                ab, _, tts_err = text_to_speech_openrouter(
                                    text,
                                    voice=lesson_voice,
                                )
                            if tts_err:
                                st.error(tts_err)
                            else:
                                new_path = _save_ai_lesson_example_audio(
                                    lid, ex_idx, ab
                                )
                                all_lessons = load_ai_lessons(profile_id=profile_id)
                                for l in all_lessons:
                                    if l.get("id") == lid and ex_idx < len(
                                        l.get("examples", [])
                                    ):
                                        l["examples"][ex_idx]["audio_path"] = new_path
                                        break
                                save_ai_lessons(all_lessons, profile_id=profile_id)
                                st.rerun()
                    with c2:
                        if st.button(
                            "🗑 Supprimer audio",
                            key=f"ai-lesson-del-{lid}-{ex_idx}",
                            width="stretch",
                        ):
                            if audio_path and os.path.exists(audio_path):
                                os.remove(audio_path)
                            all_lessons = load_ai_lessons(profile_id=profile_id)
                            for l in all_lessons:
                                if l.get("id") == lid and ex_idx < len(
                                    l.get("examples", [])
                                ):
                                    l["examples"][ex_idx]["audio_path"] = None
                                    break
                            save_ai_lessons(all_lessons, profile_id=profile_id)
                            st.rerun()
                else:
                    if st.button(
                        "🔊 Generer audio",
                        key=f"ai-lesson-gen-{lid}-{ex_idx}",
                        width="stretch",
                    ):
                        with st.spinner("Generation audio..."):
                            ab, _, tts_err = text_to_speech_openrouter(
                                text,
                                voice=lesson_voice,
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            new_path = _save_ai_lesson_example_audio(lid, ex_idx, ab)
                            all_lessons = load_ai_lessons(profile_id=profile_id)
                            for l in all_lessons:
                                if l.get("id") == lid and ex_idx < len(
                                    l.get("examples", [])
                                ):
                                    l["examples"][ex_idx]["audio_path"] = new_path
                                    break
                            save_ai_lessons(all_lessons, profile_id=profile_id)
                            st.rerun()

            st.markdown("---")
            mini_task = lesson.get("mini_task", {})
            target_seconds = int(mini_task.get("target_time_seconds", 120) or 120)
            st.markdown(
                f"**Mini-task ({target_seconds} sec) :** {mini_task.get('instruction', '')}"
            )
            checklist = mini_task.get("success_checklist", [])
            if checklist:
                st.markdown("**Checklist de reussite :**")
                for item in checklist:
                    st.markdown(f"- {item}")

            start_key = f"ai-mini-start-{lid}"
            eval_key = f"ai-mini-eval-{lid}"
            answer_key = f"ai-mini-answer-{lid}"
            audio_key = f"ai-mini-audio-{lid}"
            active_key = "ai-mini-active-lesson"

            cstart, cretry = st.columns(2)
            with cstart:
                if st.button(
                    "▶️ Demarrer / Redemarrer le chrono",
                    key=f"ai-mini-start-btn-{lid}",
                    width="stretch",
                ):
                    st.session_state[start_key] = now_iso()
                    st.session_state[active_key] = lid
                    st.session_state.pop(eval_key, None)
                    st.rerun()
            with cretry:
                if st.button(
                    "♻️ Recommencer la mini-task",
                    key=f"ai-mini-retry-btn-{lid}",
                    width="stretch",
                ):
                    st.session_state[start_key] = now_iso()
                    st.session_state[active_key] = lid
                    st.session_state[answer_key] = ""
                    st.session_state.pop(audio_key, None)
                    st.session_state.pop(eval_key, None)
                    st.rerun()

            started_at = st.session_state.get(start_key)
            if started_at:
                elapsed = _seconds_since_iso(started_at)
                remaining = max(0, target_seconds - elapsed)
                st.progress(
                    min(1.0, elapsed / max(1, target_seconds)),
                    text=f"Temps ecoule: {elapsed}s  |  Temps restant cible: {remaining}s",
                )
                if st.session_state.get(active_key) == lid and remaining > 0:
                    st_autorefresh(
                        interval=1000,
                        key=f"ai-mini-refresh-{lid}",
                    )
                if remaining == 0 and st.session_state.get(active_key) == lid:
                    st.session_state.pop(active_key, None)
                    st.info(
                        "⏰ 2 minutes terminees. Soumets ton audio ou ton texte pour evaluation."
                    )

            st.markdown("**🎤 Reponse audio (optionnel) :**")
            mini_audio_widget = st.audio_input(
                "Enregistre ta mini-task puis clique pour soumettre",
                key=audio_key,
            )
            col_transc, col_submit_audio = st.columns(2)
            with col_transc:
                transcribe_clicked = st.button(
                    "📝 Transcrire mon audio",
                    key=f"ai-mini-transcribe-btn-{lid}",
                    width="stretch",
                )
            with col_submit_audio:
                submit_audio_clicked = st.button(
                    "🎤 Soumettre audio",
                    key=f"ai-mini-submit-audio-btn-{lid}",
                    width="stretch",
                    type="primary",
                )

            if transcribe_clicked:
                if not mini_audio_widget:
                    st.warning("Enregistre d'abord ton audio pour la mini-task.")
                else:
                    with st.spinner("Transcription de l'audio..."):
                        transcribed, terr = transcribe_audio_with_openrouter(
                            mini_audio_widget.getvalue(),
                            audio_format="wav",
                        )
                    if terr:
                        st.error(f"Erreur transcription: {terr}")
                    else:
                        st.session_state[answer_key] = transcribed
                        st.success("Transcription ajoutee dans le champ texte.")
                        st.rerun()

            if submit_audio_clicked:
                if not mini_audio_widget:
                    st.warning("Enregistre d'abord ton audio pour soumettre.")
                else:
                    with st.spinner("Transcription + evaluation de l'audio..."):
                        transcribed, terr = transcribe_audio_with_openrouter(
                            mini_audio_widget.getvalue(),
                            audio_format="wav",
                        )
                    if terr:
                        st.error(f"Erreur transcription: {terr}")
                    else:
                        st.session_state[answer_key] = transcribed
                        eval_result, eval_err = evaluate_ai_lesson_mini_task(
                            lesson, transcribed
                        )
                        if eval_err:
                            st.error(f"Erreur evaluation: {eval_err}")
                        else:
                            st.session_state[eval_key] = eval_result

            answer = st.text_area(
                "Ta reponse (texte libre ou transcription de ton oral)",
                key=answer_key,
                placeholder="Ecris ici ta production pour verifier si tu as compris le concept...",
                height=120,
            )
            if st.button(
                "✅ Verifier ma mini-task",
                key=f"ai-mini-eval-btn-{lid}",
                width="stretch",
            ):
                with st.spinner("Evaluation de ta mini-task..."):
                    eval_result, eval_err = evaluate_ai_lesson_mini_task(lesson, answer)
                if eval_err:
                    st.error(f"Erreur evaluation: {eval_err}")
                else:
                    st.session_state[eval_key] = eval_result

            mini_eval = st.session_state.get(eval_key)
            if mini_eval:
                score = mini_eval.get("score", 0)
                correct = mini_eval.get("correct", False)
                feedback = mini_eval.get("feedback_fr", "")
                improved = mini_eval.get("improved_answer", "")
                if correct:
                    st.success(f"Score: {score}/100 — {feedback}")
                else:
                    st.warning(f"Score: {score}/100 — {feedback}")
                if improved:
                    st.markdown(f"**Version amelioree suggeree :** {improved}")


def render_home():
    st.header("Objectif: A1 -> C2 American English")
    st.write(
        "Cette application combine ecoute intensive, repetition et conversations audio instantanees avec l'IA."
    )
    st.markdown(
        """
- **Lecons**: 10 variations par theme + packs 5x5 min
- **Pratique IA**: conversation audio corrigee en continu (recasts implicites)
- **Vocabulaire & Flashcards**: memoire long terme et reactivation quotidienne
- **Podcasts / Histoires**: comprehension et exposition naturelle a l'anglais US
- **Historique**: suivi de progression et reecoute des sessions
"""
    )

    st.subheader("Comment devenir fluent avec 15 a 30 minutes par jour")
    st.markdown(
        """
**Principe simple:** chaque jour, faire **Input -> Repetition -> Output -> Feedback**.

**Schema 15 minutes (minimum efficace):**
1. **Lecons (5 min)**: choisis 1 variation et ecoute/repete 2-3 fois (shadowing).
2. **Pratique IA (6 min)**: fais une mini session sur le meme theme et parle sans traduire.
3. **Vocabulaire (4 min)**: ajoute 2-3 chunks de la session + fais les flashcards du jour.

**Schema 30 minutes (progression rapide):**
1. **Lecons (10 min)**: 2 variations + 1 audio de pack (5 min).
2. **Pratique IA (10 min)**: session guidee avec objectif clair (fluidite, temps, vocabulaire).
3. **Vocabulaire (5 min)**: revision SRS + 3 nouvelles expressions utiles.
4. **Podcast ou Histoire (5 min)**: ecoute active et note 3 expressions a reutiliser.
"""
    )

    st.info(
        "Routine conseillee: garde le meme theme 2-3 jours, puis change. "
        "Objectif quotidien: reutiliser au moins 5 expressions dans ta session IA."
    )

    st.markdown(
        """
**Plan quotidien concret:**
1. Regle ton **niveau CEFR** selon ton profil.
2. Fais tes **Lecons audio** d'abord (oreille + prononciation).
3. Enchaine avec **Pratique IA** (production orale immediate).
4. Termine par **Vocabulaire** (memorisation) et, si possible, **Podcast/Histoire**.
5. 1-2 fois par semaine, relis l'**Historique** pour verifier les erreurs recurrentes.
"""
    )


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
        with col_btn:
            if st.button(
                "Generer les 10 variations par IA (dialogues realistes)",
                key=f"gen-variations-{slugify(theme_name)}-{cefr_level}",
            ):
                with st.spinner("Generation des 10 dialogues par IA..."):
                    ai_variations, err = generate_quick_variations_ai(
                        theme_name, cefr_level=cefr_level
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
                del st.session_state[var_cache_key]
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
                        st.audio(
                            st.session_state[audio_key]["bytes"],
                            format=st.session_state[audio_key]["mime"],
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
                                            item["dialogue"], voice_a, voice_b
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
                                    item["dialogue"], voice_a, voice_b
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
            if st.button(
                "Generer le pack complet",
                key=f"pack-{slugify(theme_name)}-{cefr_level}",
            ):
                with st.spinner("Creation de 5 conversations en cours..."):
                    generated, err = generate_five_minute_pack(
                        theme_name, cefr_level=cefr_level
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
                        st.audio(
                            st.session_state[btn_key]["bytes"],
                            format=st.session_state[btn_key]["mime"],
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
                                            lesson.get("dialogue", ""), voice_a, voice_b
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
                                    lesson.get("dialogue", ""), voice_a, voice_b
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


def render_shadowing_daily_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Shadowing interactif quotidien")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    texts = load_shadowing_texts(profile_id)
    if not texts:
        st.info(
            "Aucun texte disponible pour le shadowing. "
            "Dans Lecons (Ecoute), termine une lecon pour alimenter ce menu."
        )
        return

    # ── Choice: daily random or manual pick ────────────────────────────────
    mode_key = f"shadow-mode-{profile_id}"
    mode = st.radio(
        "Mode de selection",
        ["Texte du jour (automatique)", "Choisir une lecon"],
        horizontal=True,
        key=mode_key,
    )

    texts_by_id = {str(t.get("source_id")): t for t in texts if t.get("source_id")}

    if mode == "Choisir une lecon":
        labels = {}
        for t in texts:
            sid = str(t.get("source_id", ""))
            title = str(t.get("lesson_title") or t.get("theme_name") or sid)
            level = str(t.get("cefr_level", ""))
            labels[sid] = f"{title} ({level})" if level else title

        chosen_sid = st.selectbox(
            "Lecon a travailler",
            list(labels.keys()),
            format_func=lambda sid: labels.get(sid, sid),
            key=f"shadow-pick-{profile_id}",
        )
        if chosen_sid not in texts_by_id:
            st.warning("Lecon introuvable.")
            return
        chosen_text = texts_by_id[chosen_sid]
        day_key = utc_now().date().isoformat()
    else:
        chosen_text, day_key = pick_daily_shadowing_text(profile_id, texts)
        if not chosen_text:
            st.warning("Impossible de selectionner un texte du jour.")
            return

    daily_text = chosen_text

    assignments = load_shadowing_daily_assignments()
    profile_map = assignments.get(profile_id, {})
    if not isinstance(profile_map, dict):
        profile_map = {}
    day_state = _shadowing_day_entry_to_state(profile_map.get(day_key))
    completed_today_ids = [
        sid for sid in day_state.get("completed_source_ids", []) if str(sid).strip()
    ]

    if completed_today_ids:
        with st.expander("Textes deja valides aujourd'hui", expanded=False):
            shown_ids = list(reversed(completed_today_ids[-10:]))
            for sid in shown_ids:
                item = texts_by_id.get(str(sid), {})
                title = str(item.get("lesson_title") or item.get("theme_name") or sid)
                runs = get_shadowing_run_history(profile_id, day_key, sid)
                last_run = runs[-1] if runs else {}
                avg_score = float(last_run.get("avg_score", 0) or 0)
                scales = _shadowing_score_scales(avg_score)
                st.markdown(
                    f"- {title}: **{scales['on_100']}/100** "
                    f"({scales['on_20']}/20, {scales['on_10']}/10)"
                )

    source_id = str(daily_text.get("source_id", ""))
    full_text = str(daily_text.get("dialogue_text", "")).strip()
    chunks = daily_text.get("chunks") or _split_shadowing_chunks(full_text)
    if not chunks:
        st.warning("Le texte du jour ne contient pas de phrases exploitables.")
        return

    text_title = str(
        daily_text.get("lesson_title") or daily_text.get("theme_name") or "N/A"
    )
    st.markdown(f"### {text_title}")
    st.caption(
        f"Date: {day_key} | Theme: {daily_text.get('theme_name', 'N/A')} | "
        f"Niveau: {daily_text.get('cefr_level', 'B1')}"
    )
    st.text(full_text)

    voice_label = st.selectbox(
        "Voix pour les phrases",
        list(STORY_NARRATOR_VOICES.keys()),
        index=0,
        key=f"shadowing-voice-{profile_id}",
    )
    voice = STORY_NARRATOR_VOICES.get(voice_label, "alloy")

    records = get_shadowing_session_records(profile_id, day_key, source_id)
    next_idx = get_next_shadowing_chunk_index(records, len(chunks))
    scores = [int(r.get("score", 0)) for r in records]
    avg_score_100 = round(sum(scores) / len(scores), 1) if scores else 0
    avg_scales = _shadowing_score_scales(avg_score_100)
    source_slug = slugify(source_id)
    run_history = get_shadowing_run_history(profile_id, day_key, source_id)

    m1, m2, m3 = st.columns(3)
    m1.metric("Phrases total", len(chunks))
    m2.metric("Phrases notees", len(records))
    m3.metric("Moyenne (/100)", avg_scales["on_100"])
    st.caption(
        f"La note principale est sur /100. Les formats /20 et /10 sont la meme note convertie "
        f"({avg_scales['on_20']}/20 et {avg_scales['on_10']}/10)."
    )

    with st.expander("Comment la note est calculee", expanded=False):
        st.markdown(
            "- Une seule note de base est calculee par phrase: **qualite de repetition sur 100**.\n"
            "- Cette qualite repose sur la **fidelite au texte cible** et la **fluidite**.\n"
            "- Le mode actuel est **sans chrono**: tu peux envoyer quand tu veux.\n"
            "- Les formats **/20** et **/10** sont juste des conversions de la note /100.\n"
            "- Reperes rapides: 85-100 tres bon, 70-84 bon, 55-69 moyen, <55 a retravailler."
        )

    # ── Helper: render recommencer + run history ──
    def _render_recommencer_and_history():
        if st.button(
            "Recommencer ce texte (garder mon historique)",
            key=f"shadow-restart-{profile_id}-{day_key}-{source_slug}",
            width="stretch",
        ):
            reset_shadowing_session_keep_history(
                profile_id=profile_id,
                day_key=day_key,
                source_id=source_id,
                chunk_count=len(chunks),
            )
            state_prefix = f"shadow-{profile_id}-{day_key}-{source_slug}-"
            for state_key in list(st.session_state.keys()):
                if str(state_key).startswith(state_prefix):
                    st.session_state.pop(state_key, None)
            st.session_state.pop("shadow_last_autoplay_chunk", None)
            st.rerun()

        if run_history:
            with st.expander("Historique de mes tentatives", expanded=False):
                shown = list(reversed(run_history[-10:]))
                for i, run in enumerate(shown, start=1):
                    archived_at = str(run.get("archived_at", ""))
                    archived_label = (
                        archived_at.replace("T", " ")[:19] if archived_at else "N/A"
                    )
                    avg_s = run.get("avg_score", 0)
                    avg_sc = _shadowing_score_scales(avg_s)
                    avg_lb = _shadowing_score_label(avg_s)
                    pdone = int(run.get("phrases_done", 0))
                    cc = int(run.get("chunk_count", len(chunks)))
                    st.markdown(
                        f"- Tentative {i} ({archived_label}) - moyenne: **{avg_sc['on_100']}/100** "
                        f"({avg_sc['on_20']}/20, {avg_sc['on_10']}/10) "
                        f"- {avg_lb} ({pdone}/{cc} phrases)"
                    )

    # ── Session complete: full-width detail ──
    if next_idx >= len(chunks):
        if records:
            with st.expander("Detail par phrase", expanded=True):
                _render_shadowing_phrase_detail(records)

        _render_recommencer_and_history()

        completed_summary = _shadowing_records_summary(records, len(chunks))
        avg_done = float(completed_summary.get("avg_score", 0) or 0)
        if maybe_advance_shadowing_daily_text(
            profile_id=profile_id,
            day_key=day_key,
            source_id=source_id,
            texts=texts,
            avg_score=avg_done,
        ):
            st.success(
                "Bravo, moyenne >= 80/100. Nouveau texte charge pour aujourd'hui; "
                "le precedent a ete historise."
            )
            st.session_state.pop("shadow_last_autoplay_chunk", None)
            st.rerun()

        st.success(
            "Session du jour terminee. Demain, un autre texte sera propose automatiquement."
        )
        return

    # ── Session in progress: side-by-side layout ──
    current_chunk = str(chunks[next_idx]).strip()
    record_limit = _shadowing_record_seconds(current_chunk)

    col_active, col_detail = st.columns([3, 2])

    with col_active:
        st.markdown("### Shadowing actif")
        st.markdown(f"**Phrase {next_idx + 1} / {len(chunks)}**")
        st.write(current_chunk)
        st.caption(
            "Mode libre: pas de chrono. "
            "Repete la phrase puis envoie quand tu es pret."
        )

        chunk_audio_path, audio_err = ensure_shadowing_chunk_audio(
            profile_id=profile_id,
            source_id=source_id,
            chunk_idx=next_idx,
            chunk_text=current_chunk,
            voice=voice,
        )
        if audio_err:
            st.warning(f"Audio phrase indisponible: {audio_err}")
        elif chunk_audio_path and os.path.exists(chunk_audio_path):
            autoplay_chunk_marker = f"{profile_id}:{day_key}:{source_id}:{next_idx}"
            autoplay_state_key = "shadow_last_autoplay_chunk"
            if st.session_state.get(autoplay_state_key) != autoplay_chunk_marker:
                try:
                    with open(chunk_audio_path, "rb") as _af:
                        _ab64 = base64.b64encode(_af.read()).decode("utf-8")
                    st_components.html(
                        (
                            '<audio autoplay style="display:none">'
                            f'<source src="data:audio/wav;base64,{_ab64}">'
                            "</audio>"
                        ),
                        height=0,
                    )
                    st.session_state[autoplay_state_key] = autoplay_chunk_marker
                except Exception:
                    pass
            st.audio(chunk_audio_path, format="audio/wav")

        run_key = f"shadow-{profile_id}-{day_key}-{source_slug}-{next_idx}"
        blob_key = f"{run_key}-blob"
        widget_key = f"{run_key}-widget"

        # ── Audio input FIRST so bytes are captured before button click ──
        fmt_key = f"{run_key}-fmt"
        user_audio_widget = st.audio_input(
            "Enregistre ta repetition ici",
            key=widget_key,
        )
        if user_audio_widget is not None:
            raw_bytes = user_audio_widget.getvalue()
            if raw_bytes and len(raw_bytes) > 44:
                st.session_state[blob_key] = raw_bytes
                # Detect format from widget MIME type
                mime = getattr(user_audio_widget, "type", "") or ""
                if "webm" in mime:
                    st.session_state[fmt_key] = "webm"
                elif "ogg" in mime:
                    st.session_state[fmt_key] = "ogg"
                elif "mp3" in mime or "mpeg" in mime:
                    st.session_state[fmt_key] = "mp3"
                else:
                    st.session_state[fmt_key] = "wav"

        has_audio = bool(st.session_state.get(blob_key))
        if has_audio:
            st.success("Audio capture - pret a envoyer!", icon="✅")

        def _finalize_chunk():
            audio_bytes = st.session_state.get(blob_key)
            audio_fmt = st.session_state.get(fmt_key, "wav")
            if not audio_bytes:
                w = st.session_state.get(widget_key)
                if w is not None:
                    try:
                        raw = w.getvalue()
                        if raw and len(raw) > 44:
                            audio_bytes = raw
                            mime = getattr(w, "type", "") or ""
                            if "webm" in mime:
                                audio_fmt = "webm"
                            elif "ogg" in mime:
                                audio_fmt = "ogg"
                    except Exception:
                        audio_bytes = None
            duration_sec = 0.0
            user_text = ""
            score = 0
            feedback = ""

            if audio_bytes:
                duration = _audio_duration_seconds(audio_bytes)
                if duration is not None:
                    duration_sec = float(duration)

                with st.spinner("Transcription et notation..."):
                    user_text, stt_err = transcribe_audio_with_openrouter(
                        audio_bytes,
                        audio_format=audio_fmt,
                    )
                if stt_err:
                    score = 30
                    feedback = f"Transcription indisponible: {stt_err}"
                    user_text = ""
                else:
                    eval_data = evaluate_shadowing_chunk(
                        current_chunk,
                        user_text,
                        cefr_level=daily_text.get("cefr_level", "B1"),
                    )
                    score = int(eval_data.get("score", 0))
                    feedback = str(eval_data.get("feedback", "")).strip()
                    mismatch_msg = _shadowing_mismatch_feedback(
                        current_chunk, user_text
                    )
                    if mismatch_msg:
                        feedback = (
                            f"{feedback} {mismatch_msg}".strip()
                            if feedback
                            else mismatch_msg
                        )
            else:
                score = 0
                feedback = (
                    "Aucun audio detecte. Enregistre d'abord puis clique Envoyer."
                )

            save_shadowing_chunk_result(
                profile_id=profile_id,
                day_key=day_key,
                source_id=source_id,
                chunk_idx=next_idx,
                chunk_text=current_chunk,
                score=score,
                feedback=feedback,
                user_text=user_text,
                duration_sec=duration_sec,
                chunk_count=len(chunks),
            )

            st.session_state.pop(blob_key, None)
            st.session_state.pop(widget_key, None)
            st.session_state.pop(fmt_key, None)
            st.rerun()

        btn1, btn2 = st.columns(2)
        with btn1:
            send_disabled = not has_audio
            if st.button(
                "Envoyer maintenant",
                key=f"{run_key}-send-btn",
                width="stretch",
                disabled=send_disabled,
            ):
                _finalize_chunk()
        with btn2:
            if st.button("Passer", key=f"{run_key}-skip-btn", width="stretch"):
                save_shadowing_chunk_result(
                    profile_id=profile_id,
                    day_key=day_key,
                    source_id=source_id,
                    chunk_idx=next_idx,
                    chunk_text=current_chunk,
                    score=0,
                    feedback="Phrase passee manuellement.",
                    user_text="",
                    duration_sec=0.0,
                    chunk_count=len(chunks),
                )
                st.session_state.pop(blob_key, None)
                st.session_state.pop(widget_key, None)
                st.session_state.pop(fmt_key, None)
                st.rerun()

        if not has_audio:
            st.info("Enregistre ton audio ci-dessus, puis clique Envoyer.")

    with col_detail:
        st.markdown("### Resultats phrase par phrase")
        # Reload records from disk to reflect the latest save
        records_fresh = get_shadowing_session_records(profile_id, day_key, source_id)
        detail_container = st.container(height=500)
        with detail_container:
            if records_fresh:
                _render_shadowing_phrase_detail(records_fresh)
            else:
                st.info("Les resultats apparaitront ici au fur et a mesure.")

    # ── Recommencer + run history (full width, below columns) ──
    _render_recommencer_and_history()


# ── Story persistence ─────────────────────────────────────────────────────────


def story_path(story_id):
    return os.path.join(STORY_DIR, f"{story_id}.json")


def list_saved_stories():
    if not os.path.isdir(STORY_DIR):
        return []
    stories = []
    for fname in sorted(os.listdir(STORY_DIR), reverse=True):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(STORY_DIR, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                stories.append(data)
            except Exception:
                pass
    return stories


def load_story(story_id):
    path = story_path(story_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_story(story_data):
    with open(story_path(story_data["id"]), "w", encoding="utf-8") as f:
        json.dump(story_data, f, ensure_ascii=False, indent=2)


def story_chapter_audio_path(story_id, chapter_num):
    return os.path.join(STORY_AUDIO_DIR, f"{story_id}-ch{chapter_num}.wav")


def load_story_chapter_audio(story_id, chapter_num):
    path = story_chapter_audio_path(story_id, chapter_num)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def save_story_chapter_audio(story_id, chapter_num, audio_bytes):
    path = story_chapter_audio_path(story_id, chapter_num)
    with open(path, "wb") as f:
        f.write(audio_bytes)


# ── Story audio generation ────────────────────────────────────────────────────


def concatenate_wav_bytes(wav_bytes_list):
    """Merge multiple WAV byte arrays (same format) into one."""
    if not wav_bytes_list:
        return None
    if len(wav_bytes_list) == 1:
        return wav_bytes_list[0]
    all_pcm = []
    for wb in wav_bytes_list:
        buf = io.BytesIO(wb)
        try:
            with wave.open(buf, "rb") as wf:
                all_pcm.append(wf.readframes(wf.getnframes()))
        except Exception:
            pass
    if not all_pcm:
        return wav_bytes_list[0]
    return pcm16_to_wav_bytes(b"".join(all_pcm))


def generate_narrator_tts(text, voice=TTS_VOICE):
    """Single-narrator TTS for long text — chunks and concatenates WAV output."""
    chunks = split_text_for_tts(text, max_chars=900)
    wav_parts = []
    for chunk in chunks:
        audio_bytes, _mime, err = text_to_speech_openrouter(chunk, voice=voice)
        if err:
            return None, None, err
        if audio_bytes:
            wav_parts.append(audio_bytes)
    if not wav_parts:
        return None, None, "Aucun audio généré."
    combined = concatenate_wav_bytes(wav_parts)
    return combined, "audio/wav", None


# ── Story AI generation ───────────────────────────────────────────────────────


def generate_story_ai(topic, category, num_chapters=4, cefr_level="B2"):
    cefr = CEFR_DESCRIPTORS.get(cefr_level, CEFR_DESCRIPTORS["B2"])
    prompt = f"""You are a master storyteller writing in natural American English.

Write a complete story with exactly {num_chapters} chapters on this topic:
"{topic}"
Category: {category}

Target reading level: {cefr_level} — {cefr['label']}
Language calibration for {cefr_level}:
{cefr['english']}

Requirements:
- Each chapter is 350-500 words of compelling narrative prose (NOT dialogue-heavy).
- Strong narrative arc: establish the world/characters → rising conflict → climax → resolution.
- Vivid descriptions, sensory details, and American English idioms calibrated to {cefr_level}.
- 8-12 vocabulary highlights (words/phrases from the story representative of {cefr_level}).
- A concise 2-sentence summary suitable for a cover blurb.
- A short image generation prompt (10-15 words, vivid, cinematic) for a cover illustration.

Return ONLY a valid JSON object with this exact schema (no markdown, no comments):
{{
  "title": "A compelling title",
  "category": "{category}",
  "summary": "Two sentence cover blurb.",
  "cover_prompt": "cinematic anime oil painting, samurai at sunset, sakura, dramatic sky",
  "vocabulary": ["word or phrase", "..."],
  "chapters": [
    {{
      "number": 1,
      "title": "Chapter 1: The [chapter subtitle]",
      "content": "Full chapter text here..."
    }}
  ]
}}"""

    messages = [{"role": "user", "content": prompt}]
    text, err = openrouter_chat(messages, CHAT_MODEL, temperature=0.75, max_tokens=6000)
    if err:
        return None, err
    data = extract_json_from_text(text)
    if data is None or not isinstance(data, dict):
        return None, "La génération de l'histoire n'a pas retourné un JSON valide."
    if "chapters" not in data or not isinstance(data["chapters"], list):
        return None, "Structure JSON invalide — champ 'chapters' manquant."
    data["id"] = str(uuid.uuid4())[:8]
    data["created_at"] = now_iso()
    data["cefr_level"] = cefr_level
    return data, None


def _cover_image_url(cover_prompt):
    """Build a Pollinations.ai URL for the story cover image."""
    try:
        from urllib.parse import quote

        encoded = quote(cover_prompt)
        return f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=300&nologo=true"
    except Exception:
        return None


def _collect_tracks_for_slug(
    slug, theme_label, profile_id="default", level_filter="Tous"
):
    """Return WAV tracks for a theme slug with profile + optional CEFR filtering."""
    if not os.path.isdir(LESSON_AUDIO_DIR):
        return []
    profile_slug = _profile_storage_slug(profile_id)
    var_re = re.compile(
        rf"^var-{re.escape(profile_slug)}-{re.escape(slug)}-([a-z0-9]+)-(.+)\.wav$"
    )
    pack_re = re.compile(
        rf"^pack-{re.escape(profile_slug)}-{re.escape(slug)}-([a-z0-9]+)-(.+)\.wav$"
    )
    legacy_var_re = re.compile(rf"^var-{re.escape(slug)}-([a-z0-9]+)-(.+)\.wav$")
    legacy_pack_re = re.compile(rf"^pack-{re.escape(slug)}-([a-z0-9]+)-(.+)\.wav$")
    tracks = []
    for fname in sorted(os.listdir(LESSON_AUDIO_DIR)):
        path = os.path.join(LESSON_AUDIO_DIR, fname)
        m = var_re.match(fname)
        source = "Var"
        if not m:
            m = pack_re.match(fname)
            source = "Pack"
        if not m and profile_id == "default":
            m = legacy_var_re.match(fname)
            source = "Var"
        if not m and profile_id == "default":
            m = legacy_pack_re.match(fname)
            source = "Pack"
        if m:
            level = m.group(1).upper()
            if level_filter != "Tous" and level != level_filter:
                continue
            tracks.append(
                {
                    "label": f"{theme_label} · {source} {level}",
                    "file": path,
                }
            )
    return tracks


def _render_audio_player(tracks, title_line):
    """Embed a self-contained HTML5 playlist player with shuffle/loop/autoplay."""
    track_data = []
    for t in tracks:
        with open(t["file"], "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        track_data.append({"label": t["label"], "src": f"data:audio/wav;base64,{b64}"})

    tracks_json = json.dumps(track_data)
    height = min(160 + len(tracks) * 34, 600)

    player_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: sans-serif; margin: 0; padding: 8px; background: transparent; }}
  #pw {{ max-width: 660px; margin: auto; background: #1e1e2e; border-radius: 12px; padding: 16px; color: #cdd6f4; }}
  h3 {{ margin: 0 0 10px; font-size: .95em; color: #cba6f7; }}
  #tit {{ font-size: 1em; font-weight: bold; margin-bottom: 6px; min-height: 1.3em; color: #a6e3a1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  audio {{ width: 100%; margin-bottom: 10px; }}
  .ctrl {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; align-items: center; }}
  .ctrl span {{ font-size: .85em; color: #a6adc8; margin-left: auto; }}
  button {{ background: #313244; border: none; color: #cdd6f4; padding: 7px 12px; border-radius: 8px; cursor: pointer; font-size: .85em; transition: background .2s; }}
  button:hover {{ background: #45475a; }}
  button.on {{ background: #cba6f7; color: #1e1e2e; font-weight: bold; }}
  #tl {{ list-style: none; padding: 0; margin: 0; max-height: 260px; overflow-y: auto; }}
  #tl li {{ padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: .85em; transition: background .15s; display: flex; align-items: center; gap: 6px; }}
  #tl li:hover {{ background: #313244; }}
  #tl li.pl {{ background: #2a2a3e; color: #a6e3a1; font-weight: bold; }}
  .idx {{ color: #585b70; font-size: .78em; min-width: 20px; }}
</style>
</head>
<body>
<div id="pw">
  <h3>🎵 {title_line}</h3>
  <div id="tit">—</div>
  <audio id="au" controls></audio>
  <div class="ctrl">
    <button id="bprev">⏮</button>
    <button id="bnext">⏭</button>
    <button id="bshuf">🔀 Aléatoire</button>
    <button id="bloop">🔁 Boucle</button>
    <span id="ctr">— / {len(tracks)}</span>
  </div>
  <ul id="tl"></ul>
</div>
<script>
const T={tracks_json};
let ci=0,shuf=false,loop=false,ord=[];
function buildOrd(){{ord=[...Array(T.length).keys()];for(let i=ord.length-1;i>0;i--){{const j=Math.floor(Math.random()*(i+1));[ord[i],ord[j]]=[ord[j],ord[i]];}}}}
function renderList(){{
  const ul=document.getElementById('tl');ul.innerHTML='';
  T.forEach((t,i)=>{{
    const li=document.createElement('li');
    li.innerHTML=`<span class="idx">${{i+1}}</span>${{t.label}}`;
    if(i===ci)li.classList.add('pl');
    li.addEventListener('click',()=>{{ci=i;play(ci);}});
    ul.appendChild(li);
  }});
  const items=document.querySelectorAll('#tl li');
  if(items[ci])items[ci].scrollIntoView({{block:'nearest'}});
}}
function play(idx){{
  ci=idx;const au=document.getElementById('au');
  au.src=T[idx].src;
  document.getElementById('tit').textContent=T[idx].label;
  document.getElementById('ctr').textContent=(idx+1)+' / '+T.length;
  au.play();renderList();
}}
function next(){{
  if(shuf){{const p=ord.indexOf(ci);play(ord[(p+1)%ord.length]);}}
  else{{play((ci+1)%T.length);}}
}}
function prev(){{
  if(shuf){{const p=ord.indexOf(ci);play(ord[(p-1+ord.length)%ord.length]);}}
  else{{play((ci-1+T.length)%T.length);}}
}}
document.getElementById('bnext').addEventListener('click',next);
document.getElementById('bprev').addEventListener('click',prev);
document.getElementById('bshuf').addEventListener('click',function(){{
  shuf=!shuf;this.classList.toggle('on',shuf);if(shuf)buildOrd();
}});
document.getElementById('bloop').addEventListener('click',function(){{
  loop=!loop;this.classList.toggle('on',loop);
}});
document.getElementById('au').addEventListener('ended',function(){{
  if(loop){{this.play();}}
  else{{next();}}
}});
buildOrd();renderList();play(0);
</script>
</body>
</html>"""
    st_components.html(player_html, height=height, scrolling=False)


# ── Stories page ──────────────────────────────────────────────────────────────


def render_stories_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("📖 Histoires en anglais — écoute & immersion")
    st.write(
        "Génère des histoires complètes en anglais américain sur les thèmes qui te passionnent. "
        "Lis, écoute, et immerge-toi dans le récit."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    # ── Sidebar-style controls ────────────────────────────────────────────────
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Nouvelle histoire")

        category = st.selectbox(
            "Catégorie",
            list(STORY_CATEGORIES.keys()),
            key="story-cat",
        )

        suggestions = STORY_CATEGORIES[category]
        use_suggestion = st.toggle(
            "Utiliser un sujet suggéré", value=True, key="story-use-sug"
        )

        if use_suggestion:
            topic = st.selectbox("Sujet", suggestions, key="story-sug-pick")
        else:
            topic = st.text_input(
                "Ton propre sujet",
                placeholder="ex: The story of Genghis Khan...",
                key="story-custom-topic",
            )

        num_chapters = st.slider("Nombre de chapitres", 3, 6, 4, key="story-chapters")

        story_level_default = get_profile_module_level(profile, "stories")
        cefr_level = st.radio(
            "Niveau",
            CEFR_LEVELS,
            index=CEFR_LEVELS.index(story_level_default),
            horizontal=True,
            key=f"story-cefr-{profile_id}",
        )
        if cefr_level != story_level_default:
            set_profile_module_level(profile_id, "stories", cefr_level)
        badge = CEFR_DESCRIPTORS[cefr_level]["badge"]
        st.caption(f"{badge} — vocabulaire et style adaptés à ce niveau.")

        narrator_label = st.selectbox(
            "Voix narrateur",
            list(STORY_NARRATOR_VOICES.keys()),
            index=5,  # Fable
            key="story-voice",
        )
        narrator_voice = STORY_NARRATOR_VOICES[narrator_label]

        if st.button(
            "✨ Générer l'histoire",
            key="story-gen-btn",
            width="stretch",
            type="primary",
        ):
            if not topic or not topic.strip():
                st.warning("Entre un sujet pour générer l'histoire.")
            else:
                with st.spinner(
                    f"Génération de l'histoire ({num_chapters} chapitres, niveau {cefr_level})..."
                ):
                    story_data, err = generate_story_ai(
                        topic.strip(), category, num_chapters, cefr_level
                    )
                if err:
                    st.error(f"Erreur génération: {err}")
                else:
                    existing_titles = [
                        s["title"].strip().lower() for s in list_saved_stories()
                    ]
                    if story_data["title"].strip().lower() in existing_titles:
                        st.error(
                            f"Une histoire intitulée **{story_data['title']}** existe déjà. Supprime-la ou choisis un autre sujet."
                        )
                    else:
                        save_story(story_data)
                        st.session_state["story_active_id"] = story_data["id"]
                        st.success("Histoire générée !")
                        st.rerun()

        # ── Saved stories list ────────────────────────────────────────────────
        st.divider()
        st.subheader("Histoires sauvegardées")
        saved = list_saved_stories()
        if not saved:
            st.caption("Aucune histoire générée pour l'instant.")
        else:
            for s in saved:
                _cefr = s.get("cefr_level", "")
                label = f"{s.get('category','')[:2]} {s['title']}" + (
                    f" [{_cefr}]" if _cefr else ""
                )
                if st.button(label, key=f"story-load-{s['id']}", width="stretch"):
                    st.session_state["story_active_id"] = s["id"]
                    st.rerun()

    # ── Story display ─────────────────────────────────────────────────────────
    with col_right:
        active_id = st.session_state.get("story_active_id")
        if not active_id:
            st.info("Génère ou sélectionne une histoire pour l'afficher ici.")
            # Show category teaser images
            st.markdown("---")
            cols = st.columns(4)
            teasers = [
                ("🏯", "Manga & Anime", "Epic battles, destiny & honor"),
                ("👑", "Rois & Empires", "Rise and fall of great rulers"),
                ("🌍", "Pays & Nations", "How civilizations were born"),
                ("📜", "Documentaires", "History's greatest events"),
            ]
            for i, (em, name, desc) in enumerate(teasers):
                with cols[i]:
                    st.markdown(
                        f"<div style='text-align:center;padding:16px;background:#1e1e2e;"
                        f"border-radius:12px;'>"
                        f"<div style='font-size:2.5em'>{em}</div>"
                        f"<div style='font-weight:bold;color:#cba6f7;margin:4px 0'>{name}</div>"
                        f"<div style='font-size:.8em;color:#a6adc8'>{desc}</div></div>",
                        unsafe_allow_html=True,
                    )
            return

        story = load_story(active_id)
        if not story:
            st.error("Histoire introuvable.")
            return

        # ── Cover card ────────────────────────────────────────────────────────
        cover_url = _cover_image_url(story.get("cover_prompt", story["title"]))
        if cover_url:
            try:
                st.image(cover_url, width="stretch")
            except Exception:
                pass

        cat_icon = story.get("category", "")[:2]
        story_cefr = story.get("cefr_level", "")
        story_badge = CEFR_DESCRIPTORS.get(story_cefr, {}).get("badge", "")
        st.markdown(
            f"<h2 style='margin-top:8px'>{cat_icon} {story['title']}"
            f"{'&nbsp;&nbsp;<span style=\"font-size:.65em\">' + story_badge + '</span>' if story_badge else ''}</h2>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='color:#a6adc8;font-style:italic'>{story.get('summary','')}</p>",
            unsafe_allow_html=True,
        )

        # Vocabulary highlights
        vocab = story.get("vocabulary", [])
        if vocab:
            with st.expander("📚 Vocabulaire clé"):
                cols_v = st.columns(3)
                for i, word in enumerate(vocab):
                    with cols_v[i % 3]:
                        st.markdown(f"`{word}`")

        st.divider()

        # Delete story button
        if st.button("🗑️ Supprimer cette histoire", key=f"story-del-{active_id}"):
            path = story_path(active_id)
            if os.path.exists(path):
                os.remove(path)
            # Remove audio files
            for ch in story.get("chapters", []):
                ap = story_chapter_audio_path(active_id, ch["number"])
                if os.path.exists(ap):
                    os.remove(ap)
            st.session_state.pop("story_active_id", None)
            st.rerun()

        # ── Chapters ─────────────────────────────────────────────────────────
        for chapter in story.get("chapters", []):
            ch_num = chapter["number"]
            ch_title = chapter["title"]
            ch_content = chapter["content"]

            st.subheader(ch_title)
            st.write(ch_content)

            audio_key = f"story-audio-{active_id}-{ch_num}"

            # Load from disk if not in session_state
            if audio_key not in st.session_state:
                cached = load_story_chapter_audio(active_id, ch_num)
                if cached:
                    st.session_state[audio_key] = cached

            if audio_key in st.session_state:
                st.audio(st.session_state[audio_key], format="audio/wav")
                c1, c2 = st.columns([1, 1])
                with c1:
                    if st.button(
                        "🔄 Régénérer audio",
                        key=f"story-regen-{active_id}-{ch_num}",
                        width="stretch",
                    ):
                        with st.spinner(f"Régénération chapitre {ch_num}..."):
                            ab, _mime, err = generate_narrator_tts(
                                ch_content, voice=narrator_voice
                            )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        else:
                            save_story_chapter_audio(active_id, ch_num, ab)
                            st.session_state[audio_key] = ab
                            st.rerun()
                with c2:
                    if st.button(
                        "🗑️ Supprimer audio",
                        key=f"story-del-audio-{active_id}-{ch_num}",
                        width="stretch",
                    ):
                        ap = story_chapter_audio_path(active_id, ch_num)
                        if os.path.exists(ap):
                            os.remove(ap)
                        st.session_state.pop(audio_key, None)
                        st.rerun()
            else:
                if st.button(
                    f"🔊 Générer audio — {ch_title}",
                    key=f"story-gen-audio-{active_id}-{ch_num}",
                    width="stretch",
                ):
                    with st.spinner(
                        f"Synthèse vocale chapitre {ch_num} ({narrator_voice})..."
                    ):
                        ab, _mime, err = generate_narrator_tts(
                            ch_content, voice=narrator_voice
                        )
                    if err:
                        st.error(f"Erreur TTS: {err}")
                    else:
                        save_story_chapter_audio(active_id, ch_num, ab)
                        st.session_state[audio_key] = ab
                        st.rerun()

            st.divider()


def render_playlist_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Playlist audio — écoute en continu")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    playlist_level_default = get_profile_module_level(profile, "playlist")
    playlist_level = st.selectbox(
        "Filtrer par niveau",
        ["Tous"] + CEFR_LEVELS,
        index=0,
        key=f"playlist-level-{profile_id}",
    )
    if playlist_level in CEFR_LEVELS and playlist_level != playlist_level_default:
        set_profile_module_level(profile_id, "playlist", playlist_level)

    mode = st.radio(
        "Mode d'écoute",
        ["Un seul thème (tous niveaux)", "Mélange de thèmes"],
        horizontal=True,
        key="pl-mode",
    )

    tracks = []

    if mode == "Un seul thème (tous niveaux)":
        col_cat, col_theme = st.columns([1, 2])
        with col_cat:
            category = st.selectbox(
                "Catégorie", list(THEME_CATEGORIES.keys()), key="pl-cat"
            )
        with col_theme:
            filtered = [t for t in THEME_CATEGORIES[category] if t in ESSENTIAL_THEMES]
            theme_name = st.selectbox("Thème", filtered, key="pl-theme")

        tracks = _collect_tracks_for_slug(
            slugify(theme_name),
            theme_name,
            profile_id=profile_id,
            level_filter=playlist_level,
        )

        if not tracks:
            st.warning(
                f"Aucun audio généré pour **{theme_name}** (tous niveaux confondus). "
                "Rendez-vous dans **Leçons** pour générer les audios."
            )
            return

        st.success(f"{len(tracks)} audio(s) disponible(s) pour **{theme_name}**.")
        _render_audio_player(tracks, theme_name)

    else:  # Mélange de thèmes
        all_themes = list(ESSENTIAL_THEMES.keys())
        selected_themes = st.multiselect(
            "Thèmes à inclure dans la playlist",
            all_themes,
            key="pl-mix-themes",
            placeholder="Sélectionnez un ou plusieurs thèmes...",
        )

        if not selected_themes:
            st.info("Sélectionnez au moins un thème pour construire la playlist.")
            return

        for t in selected_themes:
            found = _collect_tracks_for_slug(
                slugify(t),
                t,
                profile_id=profile_id,
                level_filter=playlist_level,
            )
            tracks.extend(found)

        if not tracks:
            st.warning(
                "Aucun audio trouvé pour les thèmes sélectionnés. "
                "Générez d'abord les audios dans **Leçons**."
            )
            return

        # Summary per theme
        counts = {}
        for t in tracks:
            theme_label = t["label"].split(" · ")[0]
            counts[theme_label] = counts.get(theme_label, 0) + 1
        summary = " | ".join(f"{k}: {v}" for k, v in counts.items())
        st.success(f"{len(tracks)} audio(s) au total — {summary}")
        title_line = f"Mix — {len(selected_themes)} thème(s)"
        _render_audio_player(tracks, title_line)


def initialize_state():
    if "active_session" not in st.session_state:
        st.session_state.active_session = None


def render_practice_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("Pratique audio instantanee avec l'IA")
    st.write(
        "Enregistrez votre audio, envoyez-le, puis ecoutez la reponse vocale de l'IA."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    practice_level_default = get_profile_module_level(profile, "practice")
    practice_level = st.radio(
        "Niveau cible de la session",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(practice_level_default),
        horizontal=True,
        key=f"practice-level-{profile_id}",
    )
    if practice_level != practice_level_default:
        set_profile_module_level(profile_id, "practice", practice_level)

    practice_mode = st.radio(
        "Mode", ["Guide par theme", "Session libre"], horizontal=True
    )

    drill_label = st.selectbox(
        "Drill oral cible",
        list(PRACTICE_DRILL_MODES.keys()),
        index=0,
        help="Choisis un entrainement cible pour combler l'ecart comprehension vs production orale.",
    )
    drill_cfg = PRACTICE_DRILL_MODES[drill_label]
    training_mode = drill_cfg["key"]
    training_settings = {}

    if training_mode == "conversation_stress":
        training_settings["stress_reply_seconds"] = st.slider(
            "Delai reponse cible (secondes)",
            min_value=5,
            max_value=20,
            value=10,
            help="Objectif de rapidite entre la question de l'IA et ta reponse.",
        )
    elif training_mode == "tense_switch":
        training_settings["target_tense"] = st.selectbox(
            "Temps cible",
            ["present", "past", "future"],
            index=0,
            help="L'IA va te faire rester dans ce temps, puis te demander des reformulations.",
        )

    st.caption(f"Drill actif: {drill_label} — {drill_cfg['description']}")

    selected_theme = None
    selected_objective = ""
    if practice_mode == "Guide par theme":
        pick_mode = st.radio(
            "Choix du theme", ["Je choisis", "L'IA choisit"], horizontal=True
        )
        if pick_mode == "Je choisis":
            selected_theme = st.selectbox(
                "Theme de la session", list(ESSENTIAL_THEMES.keys())
            )
        else:
            if st.button("Choisir un theme automatiquement"):
                st.session_state.auto_theme = choose_theme_with_ai()
            selected_theme = st.session_state.get(
                "auto_theme", list(ESSENTIAL_THEMES.keys())[0]
            )
            st.info(f"Theme propose: {selected_theme}")
        selected_objective = st.text_input(
            "Objectif de la session (optionnel)",
            value="Practice natural chunks and stay fluent in this topic.",
        )

    if st.button("Demarrer une nouvelle session"):
        mode_value = "guided" if practice_mode == "Guide par theme" else "free"
        theme_value = selected_theme if mode_value == "guided" else "Free conversation"
        st.session_state.active_session = new_session(
            mode_value,
            theme_value,
            selected_objective,
            target_cefr=practice_level,
            training_mode=training_mode,
            training_settings=training_settings,
        )
        st.session_state.pop("practice_last_processed_audio", None)
        st.success(f"Session demarree: {st.session_state.active_session['id']}")

    session_data = st.session_state.active_session
    if session_data and session_data.get("profile_id", "default") != profile_id:
        st.session_state.active_session = None
        session_data = None

    if not session_data:
        st.info("Demarrez une session pour activer les echanges audio.")
        return

    active_drill_key = session_data.get("training_mode", "standard")
    active_drill_label = next(
        (
            lbl
            for lbl, cfg in PRACTICE_DRILL_MODES.items()
            if cfg.get("key") == active_drill_key
        ),
        active_drill_key,
    )
    st.caption(
        f"Session active: {session_data['id']} | Mode: {session_data['mode']} | Theme: {session_data['theme']} | Niveau: {session_data.get('target_cefr', 'B1')} | Drill: {active_drill_label}"
    )

    with st.expander("🗂 Historique IA recent (sauvegarde automatique)"):
        hist_sessions = _recent_practice_sessions(limit=20)
        if not hist_sessions:
            st.info("Aucune session IA sauvegardee pour le moment.")
        else:
            options = [
                f"{s.get('id')} | {s.get('theme', 'N/A')} | {len(s.get('turns', []))} tours"
                for s in hist_sessions
            ]
            selected_hist_idx = st.selectbox(
                "Sessions recentes",
                range(len(hist_sessions)),
                format_func=lambda i: options[i],
                key="practice-hist-select",
            )
            selected_hist = hist_sessions[selected_hist_idx]
            col_h1, col_h2 = st.columns([1, 1])
            with col_h1:
                if st.button(
                    "📂 Charger cette session",
                    key=f"practice-load-session-{selected_hist.get('id')}",
                    width="stretch",
                ):
                    st.session_state.active_session = selected_hist
                    st.session_state.pop("practice_last_processed_audio", None)
                    st.rerun()
            with col_h2:
                st.caption(f"Creee le {selected_hist.get('created_at', '')}")

            if selected_hist.get("evaluation"):
                st.markdown("**Derniere evaluation de cette session :**")
                st.markdown(selected_hist["evaluation"].get("text", ""))

            st.markdown("**Derniers echanges :**")
            for turn in selected_hist.get("turns", [])[-4:]:
                st.markdown(f"- Vous: {turn.get('user_text', '')}")
                st.markdown(f"- IA: {turn.get('ai_text', '')}")

    # ── Timer 4 minutes ──
    MAX_SESSION_SECONDS = 240  # 4 min
    WARN_SECONDS = 210  # avertir a 3:30
    elapsed = get_elapsed_seconds(session_data)
    remaining = max(0, MAX_SESSION_SECONDS - elapsed)
    progress = min(1.0, elapsed / MAX_SESSION_SECONDS)
    mins_e, secs_e = divmod(elapsed, 60)
    mins_r, secs_r = divmod(remaining, 60)

    if elapsed >= MAX_SESSION_SECONDS:
        st.error(
            f"⏰ Session de 4 minutes terminee ({mins_e}:{secs_e:02d})."
            " Obtenez votre evaluation ou demarrez une nouvelle session."
        )
    elif elapsed >= WARN_SECONDS:
        st.warning(
            f"⚠️ Moins de 30 secondes restantes ({mins_r}:{secs_r:02d}) !"
            " Terminez votre dernier echange rapidement."
        )
    st.progress(
        progress,
        text=f"⏱️ {mins_e}:{secs_e:02d} ecoulees  |  {mins_r}:{secs_r:02d} restantes  (limite : 4:00)",
    )

    if active_drill_key == "conversation_stress":
        stress_limit = int(
            session_data.get("training_settings", {}).get("stress_reply_seconds", 10)
        )
        if session_data.get("turns"):
            anchor_time = session_data["turns"][-1].get("created_at")
        else:
            anchor_time = session_data.get("started_at")
        since_prompt = _seconds_since_iso(anchor_time)
        if since_prompt > stress_limit:
            st.warning(
                f"Conversation stress: vise une reponse en <= {stress_limit}s (actuel: {since_prompt}s)."
            )

    # ── Conversation en cours (affichée AVANT l'input pour que l'input reste en bas) ──
    st.subheader("Conversation en cours")
    if not session_data["turns"]:
        st.write(
            "Aucun echange pour le moment — enregistrez votre premier message ci-dessous."
        )
    else:
        for turn in session_data["turns"]:
            with st.chat_message("user"):
                st.markdown(turn["user_text"])
                if os.path.exists(turn["user_audio_path"]):
                    st.audio(turn["user_audio_path"])
            with st.chat_message("assistant"):
                st.markdown(turn["ai_text"])
                ai_path = turn.get("ai_audio_path", "")
                if ai_path and os.path.exists(ai_path):
                    # Autoplay uniquement pour le dernier tour fraichement genere
                    if (
                        turn.get("turn") == st.session_state.get("autoplay_turn")
                        and os.path.getsize(ai_path) > 0
                    ):
                        mime = st.session_state.get("autoplay_audio_mime", "audio/wav")
                        with open(ai_path, "rb") as _af:
                            _ab64 = base64.b64encode(_af.read()).decode()
                        st_components.html(
                            f'<audio autoplay style="width:100%" controls>'
                            f'<source src="data:{mime};base64,{_ab64}">'
                            f"</audio>",
                            height=60,
                        )
                        st.session_state.pop("autoplay_turn", None)
                        st.session_state.pop("autoplay_audio_path", None)
                        st.session_state.pop("autoplay_audio_mime", None)
                    else:
                        st.audio(ai_path)

    # ── Evaluation ──
    if session_data.get("evaluation"):
        st.subheader("Evaluation")
        st.markdown(session_data["evaluation"]["text"])

    st.divider()

    # ── Audio input EN BAS (toujours visible, suit la conversation) ──
    # Clé dynamique basée sur le nombre de tours : force le reset du widget après chaque envoi
    n_turns = len(session_data["turns"])
    audio_key = f"practice_audio_input_{session_data['id']}_{n_turns}"

    if elapsed < MAX_SESSION_SECONDS:
        st.markdown("**🎙️ Votre message :**")
        st.caption(
            "Envoi automatique: dès que vous arretez l'enregistrement, le message est envoye a l'IA."
        )
        audio_file = st.audio_input(
            "Cliquez sur le micro, parlez, puis cliquez à nouveau pour arrêter",
            key=audio_key,
        )

        auto_send_ready = False
        user_audio_bytes = None
        if audio_file:
            candidate_bytes = audio_file.getvalue()
            fingerprint = hashlib.sha1(candidate_bytes).hexdigest()
            marker = f"{audio_key}:{fingerprint}"
            if st.session_state.get("practice_last_processed_audio") != marker:
                st.session_state["practice_last_processed_audio"] = marker
                auto_send_ready = True
                user_audio_bytes = candidate_bytes

        col_clear, col_eval = st.columns([1, 1])
        with col_clear:
            if st.button("🗑️ Effacer", width="stretch"):
                st.session_state.pop(audio_key, None)
                st.session_state.pop("practice_last_processed_audio", None)
                st.rerun()
        with col_eval:
            eval_clicked = st.button("📊 Evaluer", width="stretch")
    else:
        audio_file = None
        auto_send_ready = False
        user_audio_bytes = None
        col_eval_only = st.columns(1)[0]
        with col_eval_only:
            eval_clicked = st.button(
                "📊 Obtenir la note de fin de session",
                type="primary",
                width="stretch",
            )

    if auto_send_ready:
        if not user_audio_bytes:
            st.warning("Aucun audio detecte. Reessayez l'enregistrement.")
        else:
            user_submitted_at = now_iso()
            last_anchor = (
                session_data["turns"][-1].get("created_at")
                if session_data.get("turns")
                else session_data.get("started_at")
            )
            response_latency_seconds = _seconds_between_iso(
                last_anchor, user_submitted_at
            )
            if len(user_audio_bytes) < 100:
                st.warning("L'audio est trop court. Parlez plus longtemps.")
            else:
                turn_index = len(session_data["turns"]) + 1
                user_audio_name = f"{session_data['id']}-turn-{turn_index}-user.wav"
                user_audio_path = save_audio_bytes(user_audio_name, user_audio_bytes)

                with st.spinner("Transcription..."):
                    user_text, err = transcribe_audio_with_openrouter(
                        user_audio_bytes, audio_format="wav"
                    )
                if err:
                    st.error(f"Erreur transcription: {err}")
                else:
                    session_data["messages"].append(
                        {"role": "user", "content": user_text}
                    )
                    with st.spinner("L'IA prepare sa reponse..."):
                        ai_text, err = get_ai_reply(
                            session_data, user_text, elapsed_seconds=elapsed
                        )
                    if err:
                        st.error(f"Erreur reponse IA: {err}")
                    else:
                        session_data["messages"].append(
                            {"role": "assistant", "content": ai_text}
                        )
                        with st.spinner("Synthese vocale..."):
                            ai_audio_bytes, ai_audio_mime, err = (
                                text_to_speech_openrouter(ai_text)
                            )
                        if err:
                            ai_audio_mime = "audio/wav"
                            ai_audio_bytes = b""

                        ai_ext = ext_from_mime(ai_audio_mime)
                        ai_audio_name = (
                            f"{session_data['id']}-turn-{turn_index}-ai.{ai_ext}"
                        )
                        ai_audio_path = save_audio_bytes(ai_audio_name, ai_audio_bytes)

                        turn_record = {
                            "turn": turn_index,
                            "created_at": now_iso(),
                            "user_submitted_at": user_submitted_at,
                            "response_latency_seconds": response_latency_seconds,
                            "user_audio_path": user_audio_path,
                            "user_text": user_text,
                            "ai_text": ai_text,
                            "ai_audio_path": ai_audio_path,
                            "ai_audio_mime": ai_audio_mime,
                        }
                        session_data["turns"].append(turn_record)
                        save_session(session_data)  # sauvegarde automatique
                        st.session_state.active_session = session_data
                        st.session_state["autoplay_turn"] = turn_index
                        st.session_state["autoplay_audio_path"] = ai_audio_path
                        st.session_state["autoplay_audio_mime"] = ai_audio_mime
                        st.session_state.pop(audio_key, None)
                        st.rerun()

    if eval_clicked:
        if not session_data["turns"]:
            st.warning("Faites au moins un echange avant de demander l'evaluation.")
        else:
            with st.spinner("Evaluation en cours..."):
                result, err = evaluate_session(session_data)
            if err:
                st.error(f"Erreur evaluation: {err}")
            else:
                session_data["evaluation"] = {"created_at": now_iso(), "text": result}
                save_session(session_data)
                st.session_state.active_session = session_data
                st.rerun()


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


def render_vocabulary_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("📖 Vocabulaire, Traduction & Flashcards")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    vocab_level_default = get_profile_module_level(profile, "vocabulary")
    vocab_level = st.radio(
        "Niveau cible vocabulaire",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(vocab_level_default),
        horizontal=True,
        key=f"vocab-level-{profile_id}",
    )
    if vocab_level != vocab_level_default:
        set_profile_module_level(profile_id, "vocabulary", vocab_level)

    tab_translate, tab_flash, tab_hist = st.tabs(
        ["🔍 Traduction & Explication", "🃏 Flashcards (SRS)", "📚 Historique"]
    )

    # ── Tab 1 : Translation & Explanation ────────────────────────────────────
    with tab_translate:
        st.subheader("Analyser un mot ou une expression")
        term_input = st.text_input(
            "Mot, expression idiomatique, chunk…",
            placeholder="ex: to bite the bullet, run out of, nevertheless…",
            key="vocab-term-input",
        )
        tts_voice_labels = list(STORY_NARRATOR_VOICES.keys())
        col_voice, col_btn = st.columns([2, 1])
        with col_voice:
            v_label = st.selectbox(
                "Voix TTS", tts_voice_labels, index=0, key="vocab-voice"
            )
        with col_btn:
            st.write("")
            st.write("")
            analyze_btn = st.button(
                "✨ Analyser",
                key="vocab-analyze-btn",
                type="primary",
                width="stretch",
            )

        if analyze_btn:
            if not term_input.strip():
                st.warning("Entre un mot ou une expression.")
            else:
                # Clean previous result and its example audio
                st.session_state.pop("vocab_current", None)
                for _i in range(10):
                    st.session_state.pop(f"vocab_ex_audio_{_i}", None)
                with st.spinner("Analyse en cours…"):
                    result, err = translate_and_explain(
                        term_input.strip(),
                        target_cefr=vocab_level,
                    )
                if err:
                    st.error(f"Erreur IA : {err}")
                else:
                    st.session_state["vocab_current"] = result

        result = st.session_state.get("vocab_current")
        if result:
            st.markdown("---")
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(f"### {result.get('term', term_input)}")
                badge_level = result.get("level", "")
                pos = result.get("part_of_speech", "")
                if badge_level or pos:
                    st.caption(f"{pos}  ·  {badge_level}")
                st.markdown(f"**🇫🇷 Traduction :** {result.get('translation', '')}")
                st.markdown(f"**📝 Explication :** {result.get('explanation', '')}")
                synonyms = result.get("synonyms", [])
                if synonyms:
                    st.markdown(
                        f"**🔗 Synonymes / expressions proches :** {', '.join(synonyms)}"
                    )
            with col_b:
                if st.button(
                    "💾 Sauvegarder dans mon vocabulaire",
                    key="vocab-save-btn",
                    width="stretch",
                ):
                    entries = load_vocab(profile_id=profile_id)
                    existing_terms = [e.get("term", "").lower() for e in entries]
                    if result.get("term", "").lower() in existing_terms:
                        st.info("Ce mot est déjà dans ton vocabulaire.")
                    else:
                        entry_id = str(uuid.uuid4())[:8]
                        examples_with_audio = []
                        for _ei, _ex in enumerate(result.get("examples", [])):
                            _ab = st.session_state.get(f"vocab_ex_audio_{_ei}")
                            _ap = (
                                _save_example_audio(
                                    entry_id,
                                    _ei,
                                    _ab,
                                    profile_id=profile_id,
                                )
                                if _ab
                                else None
                            )
                            examples_with_audio.append({"text": _ex, "audio_path": _ap})
                        entry = {
                            "id": entry_id,
                            "profile_id": profile_id,
                            "term": result.get("term", term_input),
                            "created_at": now_iso(),
                            "translation": result.get("translation", ""),
                            "part_of_speech": result.get("part_of_speech", ""),
                            "explanation": result.get("explanation", ""),
                            "examples": examples_with_audio,
                            "synonyms": result.get("synonyms", []),
                            "level": result.get("level", ""),
                            "srs": {
                                "next_review": now_iso(),
                                "interval": 1,
                                "ease": 2.5,
                                "repetitions": 0,
                                "last_result": None,
                            },
                            "review_history": [],
                        }
                        entries.append(entry)
                        save_vocab(entries, profile_id=profile_id)
                        # Clean up current analysis from session state
                        st.session_state.pop("vocab_current", None)
                        for _i in range(10):
                            st.session_state.pop(f"vocab_ex_audio_{_i}", None)
                        st.success(f"«{entry['term']}» sauvegardé !")

            st.markdown("#### 💬 Phrases d'exemple")
            voice = STORY_NARRATOR_VOICES.get(v_label, "alloy")
            for i, ex in enumerate(result.get("examples", [])):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{i+1}.** {ex}")
                with c2:
                    if st.button(f"🔊 Audio", key=f"vocab-ex-audio-{i}"):
                        with st.spinner("Génération audio…"):
                            audio_bytes, _, tts_err = text_to_speech_openrouter(
                                ex, voice=voice
                            )
                        if tts_err:
                            st.error(tts_err)
                        else:
                            st.session_state[f"vocab_ex_audio_{i}"] = audio_bytes
                audio_key = f"vocab_ex_audio_{i}"
                if st.session_state.get(audio_key):
                    st.audio(st.session_state[audio_key], format="audio/wav")

    # ── Tab 2 : Flashcards SRS ────────────────────────────────────────────────
    with tab_flash:
        st.subheader("Flashcards — répétition espacée")

        flash_mode_label = st.radio(
            "Mode",
            ["🔤 Normal (terme → phrase)", "🔁 Inversé (définition → terme)"],
            horizontal=True,
            key="flash-mode-radio",
        )
        is_reverse = "Inversé" in flash_mode_label

        entries = load_vocab(profile_id=profile_id)
        due = get_due_cards(entries)

        total = len(entries)
        total_due = len(due)
        c1, c2, c3 = st.columns(3)
        c1.metric("Mots au total", total)
        c2.metric("À réviser aujourd'hui", total_due)
        c3.metric(
            "Maîtrisés (≥5 rép.)",
            sum(1 for e in entries if e.get("srs", {}).get("repetitions", 0) >= 5),
        )

        if not due:
            if total == 0:
                st.info(
                    "Ton vocabulaire est vide. Analyse des mots dans l'onglet **Traduction** et sauvegarde-les."
                )
            else:
                st.success(
                    "✅ Toutes les révisions du jour sont faites ! Reviens demain."
                )
            return

        mode_key = f"flash_mode_{profile_id}_{is_reverse}"
        if (
            "flash_idx" not in st.session_state
            or st.session_state.get("flash_mode_key") != mode_key
            or st.session_state.get("flash_profile_id") != profile_id
        ):
            st.session_state["flash_idx"] = 0
            st.session_state["flash_initial_due"] = total_due
            st.session_state["flash_mode_key"] = mode_key
            st.session_state["flash_profile_id"] = profile_id
            st.session_state["flash_revealed"] = False
            st.session_state["flash_eval_result"] = None
            st.session_state["flash_user_audio_bytes"] = None
            st.session_state["flash_user_audio_path"] = None

        initial_due = st.session_state.get("flash_initial_due", total_due)
        card_number = st.session_state.get("flash_idx", 0) + 1

        if not due:
            st.success("✅ Toutes les révisions du jour sont faites ! Reviens demain.")
            st.session_state.pop("flash_idx", None)
            st.session_state.pop("flash_initial_due", None)
            return

        idx = st.session_state["flash_idx"] % len(due)
        card = due[idx]

        st.markdown(f"**Carte {card_number} / {initial_due}**")
        st.markdown("---")

        # Card face
        if not is_reverse:
            st.markdown(f"## {card['term']}")
            pos = card.get("part_of_speech", "")
            level = card.get("level", "")
            if pos or level:
                st.caption(f"{pos}  ·  {level}")
            st.markdown(
                "*Utilise ce mot/cette expression dans une phrase à voix haute.*"
            )
        else:
            st.markdown("### Quel est le mot ou l'expression décrit ci-dessous ?")
            st.markdown(f"> {card.get('explanation', '')}")
            synonyms = card.get("synonyms", [])
            if synonyms:
                st.caption(
                    f"Indices — synonymes / expressions proches : {', '.join(synonyms)}"
                )
            st.markdown("*Prononce le terme / chunk correspondant en audio.*")

        # Audio recorder — use raw flash_idx (never modulo'd) so the key is
        # always unique and Streamlit never restores a previous card's audio.
        _mic_key = f"flash-mic-{profile_id}-{st.session_state.get('flash_idx', 0)}-{is_reverse}"
        user_audio_widget = st.audio_input(
            "🎤 Enregistre ta réponse",
            key=_mic_key,
        )
        if user_audio_widget:
            st.session_state["flash_user_audio_bytes"] = user_audio_widget.read()

        col_submit, col_reveal, col_skip = st.columns(3)

        with col_submit:
            if st.button(
                "✅ Soumettre",
                key="flash-submit",
                type="primary",
                width="stretch",
            ):
                user_bytes = st.session_state.get("flash_user_audio_bytes")
                if not user_bytes:
                    st.warning("Enregistre d'abord une réponse audio.")
                else:
                    with st.spinner("Transcription & évaluation…"):
                        user_text, stt_err = transcribe_audio_with_openrouter(
                            user_bytes
                        )
                    if stt_err:
                        st.error(f"Transcription : {stt_err}")
                    else:
                        if is_reverse:
                            eval_result, eval_err = evaluate_reverse_flashcard(
                                card["term"], user_text
                            )
                        else:
                            eval_result, eval_err = evaluate_vocab_usage(
                                card["term"],
                                card.get("explanation", card.get("translation", "")),
                                user_text,
                            )
                        if eval_err:
                            st.error(f"Évaluation : {eval_err}")
                        else:
                            eval_result["user_text"] = user_text
                            audio_path = _save_review_audio(
                                card["id"],
                                user_bytes,
                                profile_id=profile_id,
                            )
                            st.session_state["flash_user_audio_path"] = audio_path
                            st.session_state["flash_eval_result"] = eval_result
                            st.session_state["flash_revealed"] = True

        with col_reveal:
            if st.button("👁 Voir la réponse", key="flash-reveal", width="stretch"):
                st.session_state["flash_revealed"] = True

        with col_skip:
            if st.button("⏭ Passer", key="flash-skip", width="stretch"):
                st.session_state.pop(_mic_key, None)
                st.session_state["flash_idx"] = st.session_state.get("flash_idx", 0) + 1
                st.session_state["flash_revealed"] = False
                st.session_state["flash_eval_result"] = None
                st.session_state["flash_user_audio_bytes"] = None
                st.session_state["flash_user_audio_path"] = None
                st.rerun()

        # Reveal zone
        if st.session_state.get("flash_revealed"):
            st.markdown("---")
            if is_reverse:
                st.markdown(f"**✅ Réponse :** `{card['term']}`")
                st.markdown(f"**🇫🇷 Traduction :** {card.get('translation', '')}")
            else:
                st.markdown(f"**🇫🇷 Traduction :** {card.get('translation', '')}")
                st.markdown(f"**📝 Explication :** {card.get('explanation', '')}")

            examples = card.get("examples", [])
            if examples:
                st.markdown("**Exemples :**")
                for ex_item in examples:
                    txt = ex_item["text"] if isinstance(ex_item, dict) else ex_item
                    ex_audio = (
                        ex_item.get("audio_path") if isinstance(ex_item, dict) else None
                    )
                    st.markdown(f"- {txt}")
                    if ex_audio and os.path.exists(ex_audio):
                        st.audio(ex_audio, format="audio/wav")

            eval_result = st.session_state.get("flash_eval_result")
            if eval_result:
                user_text = eval_result.get("user_text", "")
                score = eval_result.get("score", 0)
                correct = eval_result.get("correct", False)
                feedback = eval_result.get("feedback", "")
                st.markdown(f"**Ta réponse :** *{user_text}*")
                saved_path = st.session_state.get("flash_user_audio_path")
                if saved_path and os.path.exists(saved_path):
                    st.audio(saved_path, format="audio/wav")
                if correct:
                    st.success(f"✅ Correct ! Score : {score}/100 — {feedback}")
                else:
                    st.error(f"❌ À retravailler. Score : {score}/100 — {feedback}")

            # 4-rating buttons
            st.markdown("##### Comment tu t'en es sorti ?")
            r0, r1, r2, r3 = st.columns(4)

            def _apply_rating(rating: int, label: str):
                _all = load_vocab(profile_id=profile_id)
                _eval = st.session_state.get("flash_eval_result")
                _ap = st.session_state.get("flash_user_audio_path")
                for e in _all:
                    if e["id"] == card["id"]:
                        e["srs"] = _srs_update_rated(e.get("srs", {}), rating=rating)
                        e["srs"]["last_result"] = label
                        rev = {
                            "date": now_iso(),
                            "mode": "reverse" if is_reverse else "normal",
                            "rating": rating,
                            "rating_label": label,
                            "user_text": _eval.get("user_text", "") if _eval else "",
                            "score": _eval.get("score") if _eval else None,
                            "audio_path": _ap,
                        }
                        if "review_history" not in e:
                            e["review_history"] = []
                        e["review_history"].append(rev)
                        break
                save_vocab(_all, profile_id=profile_id)
                st.session_state.pop(_mic_key, None)
                st.session_state["flash_idx"] = st.session_state.get("flash_idx", 0) + 1
                st.session_state["flash_revealed"] = False
                st.session_state["flash_eval_result"] = None
                st.session_state["flash_user_audio_bytes"] = None
                st.session_state["flash_user_audio_path"] = None
                st.rerun()

            with r0:
                if st.button("❌ À revoir", key="flash-r0", width="stretch"):
                    _apply_rating(0, "À revoir")
            with r1:
                if st.button("😬 Difficile", key="flash-r1", width="stretch"):
                    _apply_rating(1, "Difficile")
            with r2:
                if st.button(
                    "✅ Bien", key="flash-r2", width="stretch", type="primary"
                ):
                    _apply_rating(2, "Bien")
            with r3:
                if st.button("🌟 Facile", key="flash-r3", width="stretch"):
                    _apply_rating(3, "Facile")

    # ── Tab 3 : History ───────────────────────────────────────────────────────
    with tab_hist:
        st.subheader("Historique de mon vocabulaire")
        entries = load_vocab(profile_id=profile_id)
        if not entries:
            st.info("Aucun mot sauvegardé pour le moment.")
        else:
            search = st.text_input(
                "🔎 Rechercher",
                placeholder="Filtrer par mot…",
                key="vocab-hist-search",
            )
            hist_voice_label = st.selectbox(
                "Voix TTS pour les exemples",
                list(STORY_NARRATOR_VOICES.keys()),
                index=0,
                key="vocab-hist-voice",
            )
            hist_voice = STORY_NARRATOR_VOICES.get(hist_voice_label, "alloy")
            filtered = entries
            if search.strip():
                q = search.strip().lower()
                filtered = [
                    e
                    for e in entries
                    if q in e.get("term", "").lower()
                    or q in e.get("translation", "").lower()
                ]

            st.caption(f"{len(filtered)} mot(s) affiché(s)")

            for entry in reversed(filtered):
                srs = entry.get("srs", {})
                reps = srs.get("repetitions", 0)
                next_rev = srs.get("next_review", "")[:10]
                mastery = "🟢" if reps >= 5 else ("🟡" if reps >= 2 else "🔴")
                with st.expander(
                    f"{mastery} **{entry['term']}** — {entry.get('translation', '')}  ·  rév. {next_rev}"
                ):
                    st.markdown(
                        f"**Niveau :** {entry.get('level', '')}  ·  {entry.get('part_of_speech', '')}"
                    )
                    st.markdown(f"**Explication :** {entry.get('explanation', '')}")
                    synonyms = entry.get("synonyms", [])
                    if synonyms:
                        st.markdown(f"**Synonymes :** {', '.join(synonyms)}")

                    st.markdown("**Exemples :**")
                    for ex_idx, ex_item in enumerate(entry.get("examples", [])):
                        txt = ex_item["text"] if isinstance(ex_item, dict) else ex_item
                        audio_path = (
                            ex_item.get("audio_path")
                            if isinstance(ex_item, dict)
                            else None
                        )

                        st.markdown(f"**{ex_idx + 1}.** {txt}")
                        if audio_path and os.path.exists(audio_path):
                            st.audio(audio_path, format="audio/wav")
                            ca, cb = st.columns(2)
                            with ca:
                                if st.button(
                                    "🗑 Supprimer audio",
                                    key=f"vocab-ex-del-{entry['id']}-{ex_idx}",
                                    width="stretch",
                                ):
                                    os.remove(audio_path)
                                    _all = load_vocab(profile_id=profile_id)
                                    for _e in _all:
                                        if _e["id"] == entry["id"] and isinstance(
                                            _e["examples"][ex_idx], dict
                                        ):
                                            _e["examples"][ex_idx]["audio_path"] = None
                                            break
                                    save_vocab(_all, profile_id=profile_id)
                                    st.rerun()
                            with cb:
                                if st.button(
                                    "🔄 Régénérer audio",
                                    key=f"vocab-ex-regen-{entry['id']}-{ex_idx}",
                                    width="stretch",
                                ):
                                    with st.spinner("Génération audio…"):
                                        _ab, _, _err = text_to_speech_openrouter(
                                            txt, voice=hist_voice
                                        )
                                    if _err:
                                        st.error(_err)
                                    else:
                                        _new_path = _save_example_audio(
                                            entry["id"],
                                            ex_idx,
                                            _ab,
                                            profile_id=profile_id,
                                        )
                                        _all = load_vocab(profile_id=profile_id)
                                        for _e in _all:
                                            if _e["id"] == entry["id"] and isinstance(
                                                _e["examples"][ex_idx], dict
                                            ):
                                                _e["examples"][ex_idx][
                                                    "audio_path"
                                                ] = _new_path
                                                break
                                        save_vocab(_all, profile_id=profile_id)
                                        st.rerun()
                        else:
                            if st.button(
                                "🔊 Générer audio",
                                key=f"vocab-ex-gen-{entry['id']}-{ex_idx}",
                                width="stretch",
                            ):
                                with st.spinner("Génération audio…"):
                                    _ab, _, _err = text_to_speech_openrouter(
                                        txt, voice=hist_voice
                                    )
                                if _err:
                                    st.error(_err)
                                else:
                                    _new_path = _save_example_audio(
                                        entry["id"],
                                        ex_idx,
                                        _ab,
                                        profile_id=profile_id,
                                    )
                                    _all = load_vocab(profile_id=profile_id)
                                    for _e in _all:
                                        if _e["id"] == entry["id"]:
                                            if isinstance(_e["examples"][ex_idx], dict):
                                                _e["examples"][ex_idx][
                                                    "audio_path"
                                                ] = _new_path
                                            break
                                    save_vocab(_all, profile_id=profile_id)
                                    st.rerun()

                    # Review history with audio playback
                    reviews = entry.get("review_history", [])
                    if reviews:
                        st.markdown(f"**Historique des révisions ({len(reviews)}) :**")
                        for rev in reversed(reviews[-10:]):
                            date_str = rev.get("date", "")[:16].replace("T", " ")
                            mode_icon = "🔁" if rev.get("mode") == "reverse" else "🔤"
                            label = rev.get("rating_label", "—")
                            sc = rev.get("score")
                            score_str = f"  ·  Score {sc}/100" if sc is not None else ""
                            utxt = rev.get("user_text", "")
                            st.caption(
                                f"{mode_icon} {date_str}  ·  **{label}**{score_str}"
                                + (f"  —  *{utxt}*" if utxt else "")
                            )
                            ap = rev.get("audio_path")
                            if ap and os.path.exists(ap):
                                st.audio(ap, format="audio/wav")

                    col_srs, col_del = st.columns([3, 1])
                    with col_srs:
                        st.caption(
                            f"Répétitions : {reps}  ·  Intervalle : {srs.get('interval', 1)} j  ·  "
                            f"Facilité : {srs.get('ease', 2.5):.1f}  ·  Dernier résultat : {srs.get('last_result', '—')}"
                        )
                    with col_del:
                        if st.button("🗑 Supprimer", key=f"vocab-del-{entry['id']}"):
                            all_entries = load_vocab(profile_id=profile_id)
                            all_entries = [
                                e for e in all_entries if e["id"] != entry["id"]
                            ]
                            save_vocab(all_entries, profile_id=profile_id)
                            st.rerun()


def render_history_page():
    profile = get_active_profile()
    st.header("Historique complet des sessions audio")
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")
    sessions = load_all_sessions(profile_id=profile.get("id", "default"))
    if not sessions:
        st.info("Aucune session sauvegardee pour le moment.")
        return

    for session_data in sessions:
        with st.expander(
            f"{session_data.get('id')} | {session_data.get('mode')} | {session_data.get('theme')}"
        ):
            st.write(f"Creee le: {session_data.get('created_at', 'N/A')}")
            if session_data.get("evaluation"):
                st.markdown("**Derniere evaluation:**")
                st.markdown(session_data["evaluation"].get("text", ""))

            for turn in session_data.get("turns", []):
                st.markdown(f"**Vous:** {turn.get('user_text', '')}")
                user_audio_path = turn.get("user_audio_path")
                if user_audio_path and os.path.exists(user_audio_path):
                    st.audio(user_audio_path)

                st.markdown(f"**IA:** {turn.get('ai_text', '')}")
                ai_audio_path = turn.get("ai_audio_path")
                if ai_audio_path and os.path.exists(ai_audio_path):
                    st.audio(ai_audio_path)
                st.markdown("---")


def render_podcast_page():
    profile = get_active_profile()
    profile_id = profile.get("id", "default")

    st.header("🎙️ Podcasts du jour")
    st.write(
        "3 podcasts générés chaque jour sur vos sujets favoris : "
        "**News, IA, Football, Manga**. "
        "Écoutez-les en anglais américain au niveau de votre profil."
    )
    st.caption(f"Profil actif: {profile.get('name', 'Profil principal')}")

    podcast_level_default = get_profile_module_level(profile, "podcasts", "C1")
    podcast_level = st.radio(
        "Niveau cible podcasts",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(podcast_level_default),
        horizontal=True,
        key=f"podcast-level-{profile_id}",
    )
    if podcast_level != podcast_level_default:
        set_profile_module_level(profile_id, "podcasts", podcast_level)

    col_date, col_dur = st.columns([2, 1])
    with col_date:
        date_selected = st.date_input(
            "Date",
            value=utc_now().date(),
        ).strftime("%Y-%m-%d")
    with col_dur:
        duration = st.slider(
            "Durée cible (min)",
            min_value=5,
            max_value=10,
            value=7,
            help="Durée approximative de chaque podcast",
        )

    interest_filter = st.multiselect(
        "Filtrer par intérêt",
        USER_INTERESTS,
        default=USER_INTERESTS,
    )

    podcast_voice_pair = st.selectbox(
        "Paire de voix (Host A / Host B)",
        list(VOICE_PAIRS.keys()),
        key="podcast_voice_pair",
        index=0,
    )
    podcast_voice_a, podcast_voice_b = VOICE_PAIRS[podcast_voice_pair]

    podcasts = load_podcasts_for_date(date_selected)

    col_gen, col_regen = st.columns([3, 1])
    with col_gen:
        if st.button(
            "🎙️ Générer 3 podcasts du jour",
            type="primary",
            width="stretch",
            disabled=(podcasts is not None),
        ):
            with st.spinner("Génération des 3 podcasts en cours (30-60 secondes)..."):
                generated, err = generate_podcast_scripts(
                    date_selected,
                    USER_INTERESTS,
                    duration_minutes=duration,
                    target_cefr=podcast_level,
                )
            if err:
                st.error(f"Erreur génération podcasts: {err}")
            else:
                save_podcasts_for_date(date_selected, generated)
                st.success("3 podcasts générés et sauvegardés !")
                st.rerun()
    with col_regen:
        if podcasts and st.button("🔄 Régénérer", width="stretch"):
            path = podcast_file_path(date_selected)
            if os.path.exists(path):
                os.remove(path)
            # Clear audio cache keys for this date
            for key in list(st.session_state.keys()):
                if key.startswith(f"podcast-audio-{date_selected}"):
                    del st.session_state[key]
            st.rerun()

    if not podcasts:
        st.info(
            "Aucun podcast pour cette date. Cliquez sur 'Générer 3 podcasts du jour'."
        )
        st.markdown("**Vos centres d'intérêt configurés :**")
        for interest in USER_INTERESTS:
            st.markdown(f"- {interest}")
        return

    displayed = [
        p
        for p in podcasts
        if not interest_filter or p.get("interest") in interest_filter
    ]

    if not displayed:
        st.warning("Aucun podcast correspond à votre filtre.")
        return

    for podcast in displayed:
        pid = podcast.get("id", 1)
        interest = podcast.get("interest", "")
        audio_cache_key = f"podcast-audio-{date_selected}-{pid}"

        # Load from disk into session_state if not already there
        if audio_cache_key not in st.session_state:
            cached = load_podcast_audio_bytes(date_selected, pid)
            if cached:
                st.session_state[audio_cache_key] = {
                    "bytes": cached,
                    "mime": "audio/wav",
                }

        with st.container(border=True):
            col_title, col_badge = st.columns([5, 1])
            with col_title:
                st.subheader(f"🎧 {podcast.get('title', 'Podcast')}")
            with col_badge:
                interest_icons = {
                    "World News & Current Affairs": "🌍",
                    "Artificial Intelligence & Technology": "🤖",
                    "Football (Soccer)": "⚽",
                    "Manga & Anime": "🇯🇵",
                }
                icon = interest_icons.get(interest, "🎙️")
                st.markdown(f"**{icon} {interest}**")

            st.caption(podcast.get("summary", ""))
            st.caption(
                f"⏱️ ~{podcast.get('estimated_minutes', duration)} min  |  {CEFR_DESCRIPTORS.get(podcast_level, {}).get('badge', podcast_level)}  |  📅 {date_selected}"
            )

            if podcast.get("vocabulary_highlights"):
                st.markdown(
                    "**Vocabulaire clé :** "
                    + "  ".join(f"`{v}`" for v in podcast["vocabulary_highlights"])
                )

            with st.expander("📖 Lire le script complet"):
                st.text(podcast.get("script", ""))

            if audio_cache_key in st.session_state:
                st.audio(
                    st.session_state[audio_cache_key]["bytes"],
                    format=st.session_state[audio_cache_key]["mime"],
                )
                col_regen_pod, col_del_pod = st.columns([1, 1])
                with col_regen_pod:
                    if st.button(
                        "🔄 Régénérer audio",
                        key=f"regen-podcast-audio-{date_selected}-{pid}",
                        width="stretch",
                    ):
                        script = podcast.get("script", "")
                        script_norm = re.sub(r"\bHost A\s*:", "A:", script)
                        script_norm = re.sub(r"\bHost B\s*:", "B:", script_norm)
                        with st.spinner("Régénération audio podcast (2 voix)..."):
                            ab, mime, err = generate_dual_voice_tts(
                                script_norm, podcast_voice_a, podcast_voice_b
                            )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        elif ab:
                            save_podcast_audio_bytes(date_selected, pid, ab)
                            st.session_state[audio_cache_key] = {
                                "bytes": ab,
                                "mime": "audio/wav",
                            }
                            st.rerun()
                with col_del_pod:
                    if st.button(
                        "🗑️ Supprimer audio",
                        key=f"del-podcast-audio-{date_selected}-{pid}",
                        width="stretch",
                    ):
                        fname = podcast_audio_file_name(date_selected, pid)
                        path = os.path.join(PODCAST_AUDIO_DIR, fname)
                        if os.path.exists(path):
                            os.remove(path)
                        st.session_state.pop(audio_cache_key, None)
                        st.rerun()
            else:
                if st.button(
                    f"🔊 Générer audio ({podcast_voice_a} / {podcast_voice_b})",
                    key=f"btn-podcast-audio-{date_selected}-{pid}",
                    width="stretch",
                ):
                    script = podcast.get("script", "")
                    script_norm = re.sub(r"\bHost A\s*:", "A:", script)
                    script_norm = re.sub(r"\bHost B\s*:", "B:", script_norm)
                    with st.spinner("Synthèse vocale du podcast (2 voix)..."):
                        ab, mime, err = generate_dual_voice_tts(
                            script_norm, podcast_voice_a, podcast_voice_b
                        )
                    if err:
                        st.error(f"Erreur TTS: {err}")
                    elif ab:
                        save_podcast_audio_bytes(date_selected, pid, ab)
                        st.session_state[audio_cache_key] = {
                            "bytes": ab,
                            "mime": "audio/wav",
                        }
                        st.rerun()

            st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# ANGLAIS NATUREL — Phase 2 : combler le fosse avec l'anglais reel
# ═══════════════════════════════════════════════════════════════════════════════

CONNECTED_SPEECH_DIR = os.path.join(DATA_DIR, "connected_speech")
CONNECTED_SPEECH_AUDIO_DIR = os.path.join(DATA_DIR, "connected_speech_audio")
SLANG_DIR = os.path.join(DATA_DIR, "slang_idioms")
IMMERSION_GENERATED_DIR = os.path.join(DATA_DIR, "immersion_generated")

REAL_ENGLISH_DIR = os.path.join(DATA_DIR, "real_english")
REAL_ENGLISH_AUDIO_DIR = os.path.join(DATA_DIR, "real_english_audio")

CONNECTED_SPEECH_RULES = [
    {
        "full": "going to",
        "reduced": "gonna",
        "example": "I'm gonna grab some coffee.",
        "ipa": "/\u0261\u0254n\u0259/",
    },
    {
        "full": "want to",
        "reduced": "wanna",
        "example": "Do you wanna come with us?",
        "ipa": "/\u02c8w\u0251n\u0259/",
    },
    {
        "full": "got to / have got to",
        "reduced": "gotta",
        "example": "I gotta go right now.",
        "ipa": "/\u02c8\u0261\u0251\u0027\u0259/",
    },
    {
        "full": "have to",
        "reduced": "hafta",
        "example": "You hafta see this movie.",
        "ipa": "/\u02c8h\u00e6ft\u0259/",
    },
    {
        "full": "ought to",
        "reduced": "oughta",
        "example": "You oughta try the pizza here.",
        "ipa": "/\u02c8\u0254\u02d0t\u0259/",
    },
    {
        "full": "used to",
        "reduced": "useta",
        "example": "I useta live in New York.",
        "ipa": "/\u02c8ju\u02d0st\u0259/",
    },
    {
        "full": "supposed to",
        "reduced": "sposta",
        "example": "We're sposta meet at eight.",
        "ipa": "/\u02c8spo\u028ast\u0259/",
    },
    {
        "full": "kind of",
        "reduced": "kinda",
        "example": "It's kinda cold outside.",
        "ipa": "/\u02c8ka\u026and\u0259/",
    },
    {
        "full": "sort of",
        "reduced": "sorta",
        "example": "I'm sorta tired today.",
        "ipa": "/\u02c8s\u0254\u02d0rt\u0259/",
    },
    {
        "full": "a lot of",
        "reduced": "a lotta",
        "example": "There's a lotta people here.",
        "ipa": "/\u0259 \u02c8l\u0251\u0027\u0259/",
    },
    {
        "full": "out of",
        "reduced": "outta",
        "example": "Get outta here!",
        "ipa": "/\u02c8a\u028at\u0259/",
    },
    {
        "full": "don't know",
        "reduced": "dunno",
        "example": "I dunno what happened.",
        "ipa": "/d\u028c\u02c8no\u028a/",
    },
    {
        "full": "did you",
        "reduced": "didja",
        "example": "Didja see that?",
        "ipa": "/\u02c8d\u026ad\u0292\u0259/",
    },
    {
        "full": "would you",
        "reduced": "wouldja",
        "example": "Wouldja mind closing the door?",
        "ipa": "/\u02c8w\u028ad\u0292\u0259/",
    },
    {
        "full": "could you",
        "reduced": "couldja",
        "example": "Couldja pass me the salt?",
        "ipa": "/\u02c8k\u028ad\u0292\u0259/",
    },
    {
        "full": "what do you",
        "reduced": "whaddya",
        "example": "Whaddya think about this?",
        "ipa": "/\u02c8w\u0251d\u0259j\u0259/",
    },
    {
        "full": "what are you",
        "reduced": "whatcha",
        "example": "Whatcha doing tonight?",
        "ipa": "/\u02c8w\u0251t\u0283\u0259/",
    },
    {
        "full": "give me",
        "reduced": "gimme",
        "example": "Gimme a break!",
        "ipa": "/\u02c8\u0261\u026ami/",
    },
    {
        "full": "let me",
        "reduced": "lemme",
        "example": "Lemme think about it.",
        "ipa": "/\u02c8l\u025bmi/",
    },
    {
        "full": "tell him / tell her",
        "reduced": "tellim / teller",
        "example": "Just tellim I said hi.",
        "ipa": "",
    },
    {
        "full": "could have",
        "reduced": "coulda",
        "example": "I coulda been there on time.",
        "ipa": "/\u02c8k\u028ad\u0259/",
    },
    {
        "full": "should have",
        "reduced": "shoulda",
        "example": "You shoulda called me.",
        "ipa": "/\u02c8\u0283\u028ad\u0259/",
    },
    {
        "full": "would have",
        "reduced": "woulda",
        "example": "I woulda helped you.",
        "ipa": "/\u02c8w\u028ad\u0259/",
    },
    {
        "full": "must have",
        "reduced": "musta",
        "example": "He musta left early.",
        "ipa": "/\u02c8m\u028cst\u0259/",
    },
    {
        "full": "might have",
        "reduced": "mighta",
        "example": "She mighta forgotten.",
        "ipa": "/\u02c8ma\u026at\u0259/",
    },
    {
        "full": "them",
        "reduced": "'em",
        "example": "Tell 'em to come over.",
        "ipa": "/\u0259m/",
    },
    {
        "full": "because",
        "reduced": "'cause / cuz",
        "example": "I stayed home 'cause I was tired.",
        "ipa": "/k\u0259z/",
    },
    {
        "full": "probably",
        "reduced": "prolly",
        "example": "I'll prolly be late.",
        "ipa": "/\u02c8pr\u0251li/",
    },
    {
        "full": "isn't it / aren't you / etc.",
        "reduced": "innit / arencha",
        "example": "Nice day, innit?",
        "ipa": "",
    },
    {
        "full": "I am going to",
        "reduced": "I'mma",
        "example": "I'mma head out now.",
        "ipa": "/\u02c8a\u026am\u0259/",
    },
    # ── -ing dropping (g-dropping) ───────────────────────────────────────────
    {
        "full": "-ing (doing, going, etc.)",
        "reduced": "-in' (doin', goin', etc.)",
        "example": "Whatcha doin' tonight? I'm just hangin' out.",
        "ipa": "/\u026an/",
    },
    {
        "full": "something",
        "reduced": "somethin' / sumthin'",
        "example": "There's somethin' wrong with the car.",
        "ipa": "/\u02c8s\u028cmθ\u026an/",
    },
    {
        "full": "nothing",
        "reduced": "nothin' / nuthin'",
        "example": "There's nothin' on TV tonight.",
        "ipa": "/\u02c8n\u028cθ\u026an/",
    },
    {
        "full": "anything",
        "reduced": "anythin'",
        "example": "Is there anythin' I can do?",
        "ipa": "/\u02c8\u025bni\u02ccθ\u026an/",
    },
    {
        "full": "everything",
        "reduced": "everythin'",
        "example": "Everythin's gonna be fine.",
        "ipa": "/\u02c8\u025bvri\u02ccθ\u026an/",
    },
    # ── Trying / fixing / about to ──────────────────────────────────────────
    {
        "full": "trying to",
        "reduced": "tryna",
        "example": "I'm tryna figure this out.",
        "ipa": "/\u02c8tra\u026an\u0259/",
    },
    {
        "full": "about to",
        "reduced": "'boutta / bout to",
        "example": "I'm 'boutta leave, you comin'?",
        "ipa": "/\u02c8ba\u028at\u0259/",
    },
    {
        "full": "fixing to (about to)",
        "reduced": "finna",
        "example": "I'm finna get some food.",
        "ipa": "/\u02c8f\u026an\u0259/",
    },
    # ── Got / getting ────────────────────────────────────────────────────────
    {
        "full": "got you / I understand",
        "reduced": "gotcha",
        "example": "Oh, gotcha. That makes sense now.",
        "ipa": "/\u02c8\u0261\u0251t\u0283\u0259/",
    },
    {
        "full": "I bet you",
        "reduced": "betcha",
        "example": "I betcha ten bucks he's late.",
        "ipa": "/\u02c8b\u025bt\u0283\u0259/",
    },
    {
        "full": "don't you",
        "reduced": "dontcha",
        "example": "Dontcha think we should leave?",
        "ipa": "/\u02c8do\u028ant\u0283\u0259/",
    },
    # ── Weak forms (pronouns, prepositions) ──────────────────────────────────
    {
        "full": "you / your",
        "reduced": "ya / yer",
        "example": "How ya doin'? Is that yer car?",
        "ipa": "/j\u0259/ /j\u025cr/",
    },
    {
        "full": "come on",
        "reduced": "c'mon",
        "example": "C'mon, we're gonna be late!",
        "ipa": "/k\u0259\u02c8m\u0251n/",
    },
    {
        "full": "what is up",
        "reduced": "wassup / 'sup",
        "example": "'Sup dude, how's it goin'?",
        "ipa": "/w\u0259\u02c8s\u028cp/",
    },
    {
        "full": "and",
        "reduced": "'n / an'",
        "example": "Mac 'n cheese is my favorite.",
        "ipa": "/\u0259n/",
    },
    {
        "full": "of (cup of, kind of...)",
        "reduced": "a (cuppa, kinda...)",
        "example": "Grab me a cuppa coffee, will ya?",
        "ipa": "/\u0259/",
    },
    {
        "full": "to (weak form)",
        "reduced": "ta / t'",
        "example": "I need ta go. Nice t'meet ya.",
        "ipa": "/t\u0259/",
    },
    {
        "full": "for",
        "reduced": "fer",
        "example": "What'd ya do that fer?",
        "ipa": "/f\u025cr/",
    },
    {
        "full": "about",
        "reduced": "'bout",
        "example": "What's it all 'bout?",
        "ipa": "/ba\u028at/",
    },
    # ── Ain't & contractions ─────────────────────────────────────────────────
    {
        "full": "am not / is not / are not / has not / have not",
        "reduced": "ain't",
        "example": "I ain't got time for that. She ain't coming.",
        "ipa": "/e\u026ant/",
    },
    {
        "full": "you all",
        "reduced": "y'all",
        "example": "Y'all wanna grab dinner?",
        "ipa": "/j\u0254\u02d0l/",
    },
    {
        "full": "it is not / that is not",
        "reduced": "'tain't / 'snot",
        "example": "'Snot my fault. That 'tain't right.",
        "ipa": "",
    },
    # ── Linking & elision patterns ───────────────────────────────────────────
    {
        "full": "a lot",
        "reduced": "alot (spoken as one word)",
        "example": "I like her alot, she's really cool.",
        "ipa": "/\u0259\u02c8l\u0251t/",
    },
    {
        "full": "I don't care",
        "reduced": "I don't care / I could care less",
        "example": "Honestly? I could care less about that.",
        "ipa": "",
    },
    {
        "full": "do you want to",
        "reduced": "d'you wanna / d'ya wanna",
        "example": "D'ya wanna go see a movie?",
        "ipa": "/dj\u0259 \u02c8w\u0251n\u0259/",
    },
    {
        "full": "got to have / need to have",
        "reduced": "gotta have",
        "example": "You gotta have patience with this.",
        "ipa": "",
    },
    {
        "full": "what did you",
        "reduced": "whatdja / whatcha",
        "example": "Whatdja say? I didn't catch that.",
        "ipa": "/\u02c8w\u0251t\u0283\u0259/",
    },
    {
        "full": "where did you",
        "reduced": "wheredja",
        "example": "Wheredja put my keys?",
        "ipa": "",
    },
    {
        "full": "how did you",
        "reduced": "howdja",
        "example": "Howdja know about that?",
        "ipa": "",
    },
    {
        "full": "who is / who has",
        "reduced": "who's",
        "example": "Who's got my phone? Who's comin'?",
        "ipa": "/hu\u02d0z/",
    },
    {
        "full": "there is / there are",
        "reduced": "there's (for both singular & plural)",
        "example": "There's like ten people waiting outside.",
        "ipa": "/\u00f0\u025brz/",
    },
]

SLANG_CATEGORIES = {
    "Reactions & Emotions": [
        {
            "expression": "No way!",
            "meaning": "C'est pas possible ! / Pas question !",
            "example": "No way! You got the job? That's amazing!",
            "context": "Surprise, disbelief, or refusal",
        },
        {
            "expression": "For real?",
            "meaning": "Serieux ?",
            "example": "You're moving to Japan? For real?",
            "context": "Asking for confirmation, disbelief",
        },
        {
            "expression": "I'm down",
            "meaning": "Je suis partant(e)",
            "example": "Pizza tonight? Yeah, I'm down.",
            "context": "Agreeing to a plan casually",
        },
        {
            "expression": "That's sick!",
            "meaning": "C'est genial / trop bien !",
            "example": "You got front row seats? That's sick!",
            "context": "Enthusiasm (positive slang)",
        },
        {
            "expression": "I can't even",
            "meaning": "J'en peux plus / c'est trop",
            "example": "This show is so funny, I can't even.",
            "context": "Being overwhelmed (humor/emotion)",
        },
        {
            "expression": "I feel you",
            "meaning": "Je te comprends",
            "example": "Work has been crazy. — Yeah, I feel you.",
            "context": "Empathy, understanding",
        },
        {
            "expression": "My bad",
            "meaning": "C'est ma faute / desole",
            "example": "Oh, my bad, I didn't see you there.",
            "context": "Casual apology",
        },
        {
            "expression": "That hits different",
            "meaning": "Ca fait un effet particulier",
            "example": "Coffee on a rainy morning just hits different.",
            "context": "Something feels especially good",
        },
        {
            "expression": "I'm dead",
            "meaning": "Je suis mort(e) de rire",
            "example": "Did you see his face? I'm dead.",
            "context": "Something extremely funny",
        },
        {
            "expression": "Lowkey / Highkey",
            "meaning": "Un peu, discretement / carrement",
            "example": "I lowkey want to skip the party. / I highkey love this song.",
            "context": "Expressing intensity of feeling",
        },
    ],
    "Sarcasm & Humor (Chandler style)": [
        {
            "expression": "Could this BE any more...",
            "meaning": "Est-ce que ca pourrait etre plus... (ironie)",
            "example": "Could this meeting BE any longer?",
            "context": "Sarcastic emphasis (Chandler Bing)",
        },
        {
            "expression": "Oh great, just what I needed",
            "meaning": "Super, exactement ce qu'il me fallait (ironie)",
            "example": "Oh great, just what I needed — more homework.",
            "context": "Sarcastic reaction to bad news",
        },
        {
            "expression": "Yeah, right",
            "meaning": "Bien sur... (je n'y crois pas)",
            "example": "He said he'd be on time. Yeah, right.",
            "context": "Expressing disbelief sarcastically",
        },
        {
            "expression": "Tell me about it",
            "meaning": "A qui le dis-tu ! / M'en parle pas",
            "example": "This weather is awful. — Tell me about it.",
            "context": "Strong agreement about something negative",
        },
        {
            "expression": "Way to go",
            "meaning": "Bravo (souvent sarcastique)",
            "example": "You broke the vase? Way to go.",
            "context": "Ironic congratulation",
        },
        {
            "expression": "That's a stretch",
            "meaning": "C'est tire par les cheveux",
            "example": "You think he likes you because he said hi? That's a stretch.",
            "context": "Something is an exaggeration",
        },
        {
            "expression": "I was today years old when...",
            "meaning": "Je viens seulement d'apprendre que...",
            "example": "I was today years old when I found out ponies aren't baby horses.",
            "context": "Humorous realization",
        },
        {
            "expression": "Thanks, Captain Obvious",
            "meaning": "Merci pour cette info qu'on savait deja",
            "example": "It's raining. — Thanks, Captain Obvious.",
            "context": "When someone states the obvious",
        },
    ],
    "Conversation Fillers & Softeners": [
        {
            "expression": "You know what I mean?",
            "meaning": "Tu vois ce que je veux dire ?",
            "example": "It's like, everyone's pretending to be happy, you know what I mean?",
            "context": "Checking understanding, keeping flow",
        },
        {
            "expression": "I mean...",
            "meaning": "Enfin... / Ce que je veux dire c'est...",
            "example": "I mean, it's not terrible, but it's not great either.",
            "context": "Clarifying or softening a statement",
        },
        {
            "expression": "Like...",
            "meaning": "(mot de remplissage/hesitation)",
            "example": "It was like, super awkward, like, nobody talked.",
            "context": "Filler word in casual speech",
        },
        {
            "expression": "You know...",
            "meaning": "Tu sais...",
            "example": "You know, I've been thinking about changing jobs.",
            "context": "Introducing a thought naturally",
        },
        {
            "expression": "So basically...",
            "meaning": "En gros...",
            "example": "So basically, we have to redo the whole thing.",
            "context": "Summarizing, simplifying",
        },
        {
            "expression": "Honestly / To be honest",
            "meaning": "Franchement / Pour etre honnete",
            "example": "Honestly, I didn't love the movie.",
            "context": "Adding sincerity to an opinion",
        },
        {
            "expression": "Right?",
            "meaning": "Hein ? / N'est-ce pas ?",
            "example": "This pizza is incredible, right?",
            "context": "Seeking agreement (tag)",
        },
        {
            "expression": "Anyway...",
            "meaning": "Bref... / En tout cas...",
            "example": "Anyway, that's not the point. Let's move on.",
            "context": "Changing topic or refocusing",
        },
    ],
    "Everyday Phrasal Verbs (natural speech)": [
        {
            "expression": "hang out",
            "meaning": "trainer / passer du temps ensemble",
            "example": "Wanna hang out this weekend?",
            "context": "Spending time casually",
        },
        {
            "expression": "figure out",
            "meaning": "trouver / comprendre / resoudre",
            "example": "I can't figure out this math problem.",
            "context": "Solving or understanding something",
        },
        {
            "expression": "come up with",
            "meaning": "trouver (une idee)",
            "example": "We need to come up with a plan.",
            "context": "Creating/inventing",
        },
        {
            "expression": "end up",
            "meaning": "finir par",
            "example": "We ended up staying until midnight.",
            "context": "Unplanned result",
        },
        {
            "expression": "turn out",
            "meaning": "s'averer / se reveler",
            "example": "It turned out he was right all along.",
            "context": "Result that was unexpected",
        },
        {
            "expression": "look into",
            "meaning": "se renseigner sur / examiner",
            "example": "I'll look into it and get back to you.",
            "context": "Investigating",
        },
        {
            "expression": "work out",
            "meaning": "s'arranger / faire du sport / resoudre",
            "example": "Don't worry, it'll all work out.",
            "context": "Multiple meanings by context",
        },
        {
            "expression": "catch up",
            "meaning": "rattraper / prendre des nouvelles",
            "example": "Let's grab coffee and catch up.",
            "context": "Reconnecting with someone",
        },
        {
            "expression": "bring up",
            "meaning": "aborder (un sujet)",
            "example": "Don't bring up politics at dinner.",
            "context": "Mentioning a topic",
        },
        {
            "expression": "put up with",
            "meaning": "supporter / tolerer",
            "example": "I can't put up with this noise anymore.",
            "context": "Tolerating something unpleasant",
        },
    ],
    "TV Series & Pop Culture": [
        {
            "expression": "How you doin'?",
            "meaning": "Comment tu vas ? (drague/salut decontracte)",
            "example": "Hey, how you doin'?",
            "context": "Joey's catchphrase (Friends)",
        },
        {
            "expression": "We were on a break!",
            "meaning": "On faisait une pause !",
            "example": "It doesn't count! We were on a break!",
            "context": "Ross's famous defense (Friends)",
        },
        {
            "expression": "That's what she said",
            "meaning": "C'est ce qu'elle a dit (sous-entendu)",
            "example": "This thing is so hard to handle! — That's what she said.",
            "context": "The Office humor (double meaning)",
        },
        {
            "expression": "Winter is coming",
            "meaning": "Les temps durs arrivent (avertissement)",
            "example": "The deadline is next week. Winter is coming.",
            "context": "GoT reference as warning",
        },
        {
            "expression": "You're killing it!",
            "meaning": "Tu geres / Tu assures !",
            "example": "Great presentation — you're killing it!",
            "context": "Complimenting performance",
        },
        {
            "expression": "Binge-watch",
            "meaning": "Regarder des episodes en rafale",
            "example": "I binge-watched the whole season last night.",
            "context": "Watching many episodes at once",
        },
        {
            "expression": "Spoiler alert!",
            "meaning": "Attention, je vais reveler l'intrigue",
            "example": "Spoiler alert — the butler did it.",
            "context": "Warning before revealing plot",
        },
        {
            "expression": "Plot twist",
            "meaning": "Retournement de situation",
            "example": "Plot twist — they were twins the whole time.",
            "context": "Unexpected story turn",
        },
    ],
    "Greetings & Goodbyes (casual)": [
        {
            "expression": "What's up? / 'Sup?",
            "meaning": "Salut / Quoi de neuf ?",
            "example": "'Sup man? How's it goin'?",
            "context": "Very casual greeting among friends",
        },
        {
            "expression": "What's good?",
            "meaning": "Quoi de bon ? / Ca va ?",
            "example": "Hey bro, what's good?",
            "context": "Casual greeting (younger generation)",
        },
        {
            "expression": "Long time no see",
            "meaning": "Ca fait longtemps !",
            "example": "Oh wow, long time no see! How've you been?",
            "context": "When you haven't seen someone in a while",
        },
        {
            "expression": "Later / Catch ya later",
            "meaning": "A plus / A plus tard",
            "example": "Alright, catch ya later!",
            "context": "Casual goodbye",
        },
        {
            "expression": "Peace / Peace out",
            "meaning": "Salut / Ciao",
            "example": "I gotta bounce. Peace out!",
            "context": "Very informal goodbye",
        },
        {
            "expression": "Take it easy",
            "meaning": "Prends soin de toi / Relaxe",
            "example": "See ya tomorrow. Take it easy.",
            "context": "Friendly/warm goodbye",
        },
        {
            "expression": "I'm out / I'm outta here",
            "meaning": "Je me casse / Je m'en vais",
            "example": "Alright everyone, I'm outta here!",
            "context": "Announcing departure casually",
        },
        {
            "expression": "Bounce / Gotta bounce",
            "meaning": "Partir / Faut que j'y aille",
            "example": "Sorry, I gotta bounce. Got a meeting.",
            "context": "Leaving in a hurry",
        },
        {
            "expression": "Hit me up",
            "meaning": "Contacte-moi / Ecris-moi",
            "example": "If you wanna hang out, hit me up.",
            "context": "Asking someone to reach out",
        },
    ],
    "Agreement & Disagreement": [
        {
            "expression": "Totally / Absolutely",
            "meaning": "Completement / Carriment",
            "example": "Do you think it's a good idea? — Totally.",
            "context": "Strong casual agreement",
        },
        {
            "expression": "For sure",
            "meaning": "Bien sur / Carrement",
            "example": "Wanna come? — For sure!",
            "context": "Enthusiastic agreement",
        },
        {
            "expression": "Bet",
            "meaning": "OK / Ca marche / Pari tenu",
            "example": "Meet at 7? — Bet.",
            "context": "Quick agreement (Gen Z/Millennial)",
        },
        {
            "expression": "Nah",
            "meaning": "Non (decontracte)",
            "example": "You want some? — Nah, I'm good.",
            "context": "Casual refusal",
        },
        {
            "expression": "Hard pass",
            "meaning": "Non merci / Certainement pas",
            "example": "Wanna go to the dentist with me? — Hard pass.",
            "context": "Emphatic casual refusal",
        },
        {
            "expression": "I'm good",
            "meaning": "Non merci / Ca va (refus poli)",
            "example": "Want another slice? — I'm good, thanks.",
            "context": "Polite casual decline",
        },
        {
            "expression": "Fair enough",
            "meaning": "C'est juste / OK, je comprends",
            "example": "I just don't feel like going. — Fair enough.",
            "context": "Accepting someone's reasoning",
        },
        {
            "expression": "No cap / Cap",
            "meaning": "Sans mentir / Tu mens",
            "example": "That was the best burger ever, no cap.",
            "context": "Truthfulness (no cap = truly, cap = lie)",
        },
        {
            "expression": "I'm not gonna lie",
            "meaning": "Je vais pas mentir / Franchement",
            "example": "I'm not gonna lie, that test was brutal.",
            "context": "Introducing an honest/blunt opinion",
        },
        {
            "expression": "Same",
            "meaning": "Pareil / Moi aussi",
            "example": "I'm so tired. — Same.",
            "context": "Quick agreement/shared feeling",
        },
    ],
    "Describing People & Vibes": [
        {
            "expression": "Chill",
            "meaning": "Cool / Relaxe / Decontracte",
            "example": "He's super chill, you'll like him.",
            "context": "Someone laid-back and easy-going",
        },
        {
            "expression": "Sketchy",
            "meaning": "Louche / Suspect",
            "example": "That neighborhood is kinda sketchy at night.",
            "context": "Something/someone suspicious",
        },
        {
            "expression": "Basic",
            "meaning": "Basique / Sans originalite",
            "example": "She only drinks pumpkin spice lattes. So basic.",
            "context": "Following mainstream trends (slightly pejorative)",
        },
        {
            "expression": "Extra",
            "meaning": "Trop / Excessif / En faire des tonnes",
            "example": "She showed up in a ball gown. She's so extra.",
            "context": "Being over the top",
        },
        {
            "expression": "Salty",
            "meaning": "Vexe / Amer / Aigri",
            "example": "He's still salty about losing the game.",
            "context": "Bitter or annoyed about something",
        },
        {
            "expression": "Shady",
            "meaning": "Louche / Sournois / Malhonnete",
            "example": "That deal sounds kinda shady to me.",
            "context": "Dishonest or suspicious behavior",
        },
        {
            "expression": "Savage",
            "meaning": "Brutal / Sans pitie (positif ou negatif)",
            "example": "She just told him off in front of everyone. Savage.",
            "context": "Bold and unfiltered",
        },
        {
            "expression": "Goat (G.O.A.T.)",
            "meaning": "Le/La meilleur(e) de tous les temps",
            "example": "LeBron is the GOAT, don't even argue.",
            "context": "Greatest Of All Time",
        },
        {
            "expression": "Vibe / Vibes",
            "meaning": "Ambiance / Energie / Feeling",
            "example": "This place has great vibes.",
            "context": "Atmosphere or energy of a place/person",
        },
        {
            "expression": "Wholesome",
            "meaning": "Sain / Adorable / Touchant",
            "example": "That video of the dog is so wholesome.",
            "context": "Something heartwarming and pure",
        },
    ],
    "Intensifiers & Exclamations": [
        {
            "expression": "Literally",
            "meaning": "Litteralement (souvent exagere)",
            "example": "I'm literally dying of hunger.",
            "context": "Used for emphasis, often exaggerated",
        },
        {
            "expression": "Super / Crazy / Mad",
            "meaning": "Tres / Extremement",
            "example": "It's super cold. That's crazy expensive. I'm mad hungry.",
            "context": "Intensifiers replacing 'very'",
        },
        {
            "expression": "Hella",
            "meaning": "Tres / Vraiment (Californie)",
            "example": "That party was hella fun.",
            "context": "West Coast intensifier",
        },
        {
            "expression": "Low-key / High-key",
            "meaning": "Un peu (discretement) / Carrement",
            "example": "I'm low-key obsessed with that show.",
            "context": "Degree of intensity",
        },
        {
            "expression": "Straight up",
            "meaning": "Franchement / Carrement / Sans detour",
            "example": "She straight up told him to leave.",
            "context": "Directly, without sugarcoating",
        },
        {
            "expression": "Legit",
            "meaning": "Vraiment / Serieusement / Authentique",
            "example": "That sushi place is legit the best in town.",
            "context": "Genuine / truly",
        },
        {
            "expression": "Dude / Bro / Man",
            "meaning": "Mec / Gars / Mon pote (interjection)",
            "example": "Dude, you're not gonna believe this!",
            "context": "Attention-getting interjection (gender-neutral in casual use)",
        },
        {
            "expression": "Oh man / Oh boy",
            "meaning": "Oh la la / Ah mince",
            "example": "Oh man, I totally forgot about the meeting.",
            "context": "Expressing surprise or mild distress",
        },
        {
            "expression": "Nope / Yep / Yup",
            "meaning": "Non / Ouais",
            "example": "Did you finish? — Nope, not yet. Yep, all done.",
            "context": "Casual yes/no",
        },
        {
            "expression": "Big time / Major",
            "meaning": "Enormement / Grave",
            "example": "I messed up big time. That's a major problem.",
            "context": "Emphasizing magnitude",
        },
    ],
    "Work, School & Hustle": [
        {
            "expression": "Grind / On the grind",
            "meaning": "Bosser dur / Etre dans le rush",
            "example": "Can't hang out, I'm on the grind this week.",
            "context": "Working very hard",
        },
        {
            "expression": "Hustle",
            "meaning": "Se debrouiller / Bosser / Side-project",
            "example": "She's got a side hustle selling jewelry online.",
            "context": "Working hard or a secondary job",
        },
        {
            "expression": "Crunch time",
            "meaning": "La derniere ligne droite / Periode critique",
            "example": "It's crunch time — the deadline is tomorrow.",
            "context": "Period of intense work pressure",
        },
        {
            "expression": "Nail it / Nailed it",
            "meaning": "Reussir parfaitement",
            "example": "How was the interview? — I nailed it!",
            "context": "Doing something perfectly",
        },
        {
            "expression": "Blow it / Blew it",
            "meaning": "Tout rater / Foirer",
            "example": "I totally blew the presentation.",
            "context": "Failing at something",
        },
        {
            "expression": "Slack off / Slacker",
            "meaning": "Glander / Glandeur",
            "example": "Stop slacking off and finish the report.",
            "context": "Not working hard enough",
        },
        {
            "expression": "Pull an all-nighter",
            "meaning": "Passer une nuit blanche (a bosser)",
            "example": "I pulled an all-nighter to finish the essay.",
            "context": "Staying up all night to work/study",
        },
        {
            "expression": "Wing it",
            "meaning": "Improviser / Faire au feeling",
            "example": "I didn't prepare at all. I'll just wing it.",
            "context": "Improvising without preparation",
        },
        {
            "expression": "Burnout / Burned out",
            "meaning": "Epuisement / A bout",
            "example": "I'm completely burned out from this job.",
            "context": "Exhaustion from overwork",
        },
        {
            "expression": "Kill two birds with one stone",
            "meaning": "Faire d'une pierre deux coups",
            "example": "If we shop there, we can kill two birds with one stone.",
            "context": "Solving two problems at once",
        },
    ],
    "Food, Drinks & Going Out": [
        {
            "expression": "Grab a bite",
            "meaning": "Manger un morceau",
            "example": "Wanna grab a bite before the movie?",
            "context": "Eating something quickly/casually",
        },
        {
            "expression": "Hit up (a place)",
            "meaning": "Aller a (un endroit)",
            "example": "Let's hit up that new taco place.",
            "context": "Going to a place casually",
        },
        {
            "expression": "I could go for...",
            "meaning": "J'ai envie de... / Je mangerais bien...",
            "example": "I could go for some pizza right now.",
            "context": "Expressing a craving",
        },
        {
            "expression": "Munchies",
            "meaning": "Fringale / Petite faim",
            "example": "I've got the munchies. Got any snacks?",
            "context": "Being snacky/hungry",
        },
        {
            "expression": "Buzzed / Tipsy",
            "meaning": "Emeche / Un peu saoul",
            "example": "I'm not drunk, just a little buzzed.",
            "context": "Slightly drunk",
        },
        {
            "expression": "Pregame",
            "meaning": "Boire avant de sortir",
            "example": "Let's pregame at my place before the party.",
            "context": "Drinking before an event",
        },
        {
            "expression": "Leftovers",
            "meaning": "Les restes (nourriture)",
            "example": "I'm just gonna heat up some leftovers.",
            "context": "Food remaining from a previous meal",
        },
        {
            "expression": "Treat (yourself) / My treat",
            "meaning": "Se faire plaisir / C'est moi qui invite",
            "example": "Don't worry about the check. My treat.",
            "context": "Paying for someone / indulging",
        },
    ],
    "Money & Life": [
        {
            "expression": "Broke",
            "meaning": "Fauche / Sans argent",
            "example": "I can't go out. I'm broke until payday.",
            "context": "Having no money",
        },
        {
            "expression": "Loaded / Balling",
            "meaning": "Plein aux as / Riche",
            "example": "Her family is loaded. They have three houses.",
            "context": "Having a lot of money",
        },
        {
            "expression": "Flex / Flexing",
            "meaning": "Frimer / Se la raconter",
            "example": "He's always flexing his new sneakers on Instagram.",
            "context": "Showing off",
        },
        {
            "expression": "Rip-off",
            "meaning": "Arnaque / Trop cher",
            "example": "$20 for a salad? What a rip-off!",
            "context": "Something overpriced or a scam",
        },
        {
            "expression": "Splurge",
            "meaning": "Craquer / Se faire plaisir (depenser)",
            "example": "I splurged on a new laptop.",
            "context": "Spending a lot on something",
        },
        {
            "expression": "Cheap / Cheapskate",
            "meaning": "Radin / Pince",
            "example": "Don't be such a cheapskate, tip the waiter.",
            "context": "Someone unwilling to spend money",
        },
        {
            "expression": "Score / Scored",
            "meaning": "Trouver une bonne affaire / Decrocher",
            "example": "I scored these shoes for half price!",
            "context": "Getting a great deal",
        },
        {
            "expression": "Side gig / Side hustle",
            "meaning": "Petit boulot a cote",
            "example": "I do freelance design as a side gig.",
            "context": "Secondary job for extra income",
        },
    ],
}

DICTATION_TEMPLATES = [
    {
        "title": "Connected Speech Gap Fill",
        "instruction": "Listen and fill in the missing words. Focus on contractions and reductions.",
    },
    {
        "title": "Fast Dialogue Catch",
        "instruction": "Listen to the fast dialogue and write the exact words you hear in the gaps.",
    },
]


def _load_immersion_progress(profile_id):
    path = os.path.join(
        CONNECTED_SPEECH_DIR, f"progress-{_profile_storage_slug(profile_id)}.json"
    )
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "connected_speech_scores": {},
        "slang_reviewed": [],
        "dictation_history": [],
        "quiz_history": [],
    }


def _save_immersion_progress(profile_id, data):
    os.makedirs(CONNECTED_SPEECH_DIR, exist_ok=True)
    path = os.path.join(
        CONNECTED_SPEECH_DIR, f"progress-{_profile_storage_slug(profile_id)}.json"
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _generated_content_path(profile_id, category, content_id):
    slug = _profile_storage_slug(profile_id)
    return os.path.join(IMMERSION_GENERATED_DIR, f"{category}-{slug}-{content_id}.json")


def _save_generated_content(profile_id, category, content_id, data):
    os.makedirs(IMMERSION_GENERATED_DIR, exist_ok=True)
    path = _generated_content_path(profile_id, category, content_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"id": content_id, "category": category, "saved": now_iso(), **data},
            f,
            ensure_ascii=False,
            indent=2,
        )


def _load_generated_content(profile_id, category, content_id):
    path = _generated_content_path(profile_id, category, content_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _delete_generated_content(profile_id, category, content_id):
    path = _generated_content_path(profile_id, category, content_id)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def _list_generated_content(profile_id, category):
    slug = _profile_storage_slug(profile_id)
    prefix = f"{category}-{slug}-"
    items = []
    if not os.path.exists(IMMERSION_GENERATED_DIR):
        return items
    for fname in sorted(os.listdir(IMMERSION_GENERATED_DIR), reverse=True):
        if fname.startswith(prefix) and fname.endswith(".json"):
            fpath = os.path.join(IMMERSION_GENERATED_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    items.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return items


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
                        st.audio(af.read(), format="audio/wav")
                else:
                    if st.button(f"🔊 Ecouter la prononciation", key=f"cs-tts-{idx}"):
                        with st.spinner("Generation audio..."):
                            tts_text = f"{rule['example']}"
                            audio_bytes, mime, err = text_to_speech_openrouter(
                                tts_text, voice="echo"
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
                        st.audio(af.read(), format="audio/wav")
                else:
                    if st.button("🔊 Ecouter", key=f"slang-tts-{si}"):
                        with st.spinner("Generation audio..."):
                            audio_bytes, mime, err = text_to_speech_openrouter(
                                item["example"], voice="nova"
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
                            exercise["full_dialogue"], "echo", "nova"
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
                st.audio(
                    st.session_state[dict_audio_key]["bytes"],
                    format=st.session_state[dict_audio_key]["mime"],
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
                            quiz["dialogue"], "echo", "nova"
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
                st.audio(
                    st.session_state["quiz_audio"]["bytes"],
                    format=st.session_state["quiz_audio"]["mime"],
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
                            sitcom["text"], voice_a, voice_b
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
                st.audio(
                    st.session_state[audio_key]["bytes"],
                    format=st.session_state[audio_key]["mime"],
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
                        speed_text, voice=speed_voice
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
            st.audio(sa["bytes"], format=sa["mime"])
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

REAL_ENGLISH_SERIES = {
    "At the Coffee Shop": {
        "description": "Deux amis se retrouvent chaque jour au coffee shop. Small talk, commandes, potins.",
        "icon": "☕",
        "episodes": [
            "Ordering coffee and chatting about the weekend",
            "Running into an old friend at the register",
            "The barista messes up the order — polite complaint",
            "Catching up on gossip while waiting for lattes",
            "Debating whether to try the new seasonal drink",
            "Meeting someone new and making small talk",
        ],
    },
    "Roommates": {
        "description": "La vie en colocation a la americaine. Conflits, rires, vie quotidienne.",
        "icon": "🏠",
        "episodes": [
            "Deciding who does the dishes tonight",
            "The apartment is a mess before guests arrive",
            "Splitting the rent and bills fairly",
            "One roommate throws a party without asking",
            "Arguing about the thermostat temperature",
            "Helping each other get ready for a date",
        ],
    },
    "At Work": {
        "description": "Bureau americain : reunions, pauses cafe, drames entre collegues.",
        "icon": "💼",
        "episodes": [
            "Monday morning small talk at the coffee machine",
            "A coworker takes credit for your idea",
            "Awkward elevator conversation with the boss",
            "Planning a surprise farewell party for a colleague",
            "Complaining about a pointless meeting",
            "Asking for a raise — rehearsing with a friend",
        ],
    },
    "Family Dinner": {
        "description": "Repas de famille americain : traditions, tensions, retrouvailles.",
        "icon": "🍽️",
        "episodes": [
            "Thanksgiving dinner chaos — who's cooking what",
            "Grandma asks about your love life — again",
            "The family argues about politics at the table",
            "Surprising the family with big news",
            "Catching up with a cousin you haven't seen in years",
            "Convincing parents you don't need a 'real' job",
        ],
    },
    "Road Trip": {
        "description": "Road trip entre amis a travers les USA. Aventures sur la route.",
        "icon": "🚗",
        "episodes": [
            "Planning the route and arguing about stops",
            "Getting lost and asking locals for directions",
            "Car breaks down on a lonely highway",
            "Stopping at a sketchy diner in the middle of nowhere",
            "Singing along to the radio and telling stories",
            "Checking into a cheap motel for the night",
        ],
    },
    "Dating in America": {
        "description": "Rendez-vous, apps de dating, premiers dates maladroits.",
        "icon": "💕",
        "episodes": [
            "Swiping through dating apps with a friend",
            "Awkward first date at a fancy restaurant",
            "Texting back and forth — does she like me?",
            "Meeting the friends for the first time",
            "The 'what are we' conversation",
            "Getting dating advice from your mom",
        ],
    },
    "Neighborhood Life": {
        "description": "La vie de quartier : voisins curieux, barbecues, petits drames locaux.",
        "icon": "🏘️",
        "episodes": [
            "Meeting the neighbors when you move in",
            "The neighbor's dog won't stop barking",
            "Backyard barbecue invitation and small talk",
            "Package delivered to the wrong house",
            "Block party planning and drama",
            "Complaining about construction noise",
        ],
    },
    "Shopping & Errands": {
        "description": "Courses, retours en magasin, deals, galeres du quotidien.",
        "icon": "🛒",
        "episodes": [
            "Black Friday madness — fighting for deals",
            "Returning a broken item without a receipt",
            "Grocery shopping debate — organic or regular?",
            "Trying on clothes and asking for opinions",
            "The self-checkout machine is broken again",
            "Haggling at a yard sale",
        ],
    },
}

REAL_ENGLISH_LEVEL_INSTRUCTIONS = {
    "A1": (
        "Use basic everyday vocabulary BUT with REAL spoken forms — NOT textbook English. "
        "Short sentences (5-8 words). Present simple tense only. "
        "MANDATORY reductions: gonna (going to), wanna (want to), gotta (got to). "
        "Use fillers: um, uh, well, so. "
        "Use chunks: What's up?, No way!, That's cool, I dunno, Come on!, Oh my God. "
        "Greetings: Hey!, What's up?, How's it going? (NOT 'Hello, how are you?'). "
        "NEVER use 'shall', 'whom', or formal structures. Sound like a real person talking."
    ),
    "A2": (
        "Simple daily vocabulary with HEAVY spoken American forms. "
        "Short sentences with connectors (and, but, so, 'cause). "
        "MANDATORY reductions: gonna, wanna, gotta, kinda, lemme, gimme, c'mon. "
        "Chunks: a lot of, kind of, sort of, no big deal, hang on, hold on, check it out, "
        "that sucks, my bad, for real, you know what I mean?, right? "
        "Phrasal verbs: hang out, figure out, pick up, drop off, show up, work out. "
        "Fillers: like, you know, well, so, um, I mean. "
        "Reactions: No way!, Seriously?, Oh come on!, That's awesome!, Dude! "
        "NEVER write formal English. This is how Americans ACTUALLY talk."
    ),
    "B1": (
        "Natural conversational vocabulary FULL of spoken American patterns. "
        "MANDATORY reductions: gonna, wanna, gotta, kinda, dunno, lemme, gimme, hafta, "
        "shoulda, coulda, woulda, 'cause, y'all, ain't (informal). "
        "Chunks & collocations: the thing is, to be honest, at the end of the day, "
        "I was like, he was all like, no worries, it's all good, that makes sense, "
        "I'm good (= no thanks), my bad, for real though, I feel you. "
        "Phrasal verbs: figure out, hang out, come up with, look into, end up, "
        "pick up on, get along with, run into, blow off, freak out, chill out. "
        "Idioms: break the ice, hit it off, on the same page, a piece of cake, "
        "no brainer, the whole nine yards. "
        "Fillers & discourse: like, you know, I mean, basically, honestly, right?, "
        "so anyway, long story short. Natural pace."
    ),
    "B2": (
        "Rich informal American vocabulary with DENSE use of idioms, chunks and phrasal verbs. "
        "MANDATORY heavy connected speech: gonna, wanna, gotta, kinda, dunno, lemme, "
        "shoulda, coulda, woulda, hafta, oughta, musta, prolly, 'cause, c'mon, "
        "tryna (trying to), finna (fixing to), gotcha, betcha, whatcha, "
        "y'all, ain't, outta (out of), lotta (lot of). "
        "Idioms REQUIRED (use 5+ per dialogue): spill the tea, throw shade, "
        "low-key, high-key, no cap, slay, it hits different, vibe, salty, ghosted, "
        "on point, I'm dead (= that's hilarious), it's giving..., sus, rent-free, "
        "keep it 100, pull up, bet, say less, the tea is hot. "
        "Chunks: at this point, I'm not gonna lie, that being said, it is what it is, "
        "you do you, I can't even, I'm over it, same though, facts, period. "
        "Sarcasm, humor, and cultural references. Natural rapid American pace. "
        "Discourse markers: I mean, basically, honestly, the thing is, "
        "not gonna lie, real talk, for real for real."
    ),
    "C1": (
        "Fully natural American speech — sounds like an UNSCRIPTED conversation between friends. "
        "ALL reductions mandatory: gonna, wanna, gotta, kinda, dunno, lemme, gimme, hafta, "
        "shoulda, coulda, woulda, musta, oughta, prolly, tryna, finna, gotcha, betcha, "
        "whatcha, y'all, ain't, outta, lotta, sorta, buncha. "
        "Advanced idioms REQUIRED (8+ per dialogue): read the room, the elephant in the room, "
        "move the needle, circle back, deep dive, it's not rocket science, drop the ball, "
        "go down a rabbit hole, take it with a grain of salt, hit the ground running, "
        "the ball is in your court, cut to the chase, think outside the box, sleep on it, "
        "a dime a dozen, the whole shebang, when push comes to shove, by the skin of your teeth. "
        "Heavy phrasal verbs: blow something off, come through, pull through, live up to, "
        "brush off, crack down on, get carried away, put up with, call someone out, "
        "play it by ear, go all out, knock it out (of the park). "
        "Rapid-fire exchanges with interruptions, sarcasm, irony, cultural references to "
        "American TV (Friends, The Office, Seinfeld), sports, politics. Near-native speed."
    ),
    "C2": (
        "Completely authentic — indistinguishable from native Americans having a real conversation. "
        "ALL spoken forms, ALL reductions, ALL elisions — no holds barred. "
        "MANDATORY: gonna, wanna, gotta, kinda, dunno, lemme, gimme, hafta, shoulda, coulda, "
        "woulda, musta, oughta, prolly, tryna, finna, gotcha, betcha, whatcha, y'all, ain't, "
        "outta, lotta, sorta, buncha, 'bout, 'em, 'til, d'you, didja, doncha, wouldja, "
        "innit (borrowed), aight, bruh, fam, lowkey, highkey, no cap, deadass, hella, "
        "sus, slay, yeet, bussin', fire, mid, based, cap, periodt. "
        "Include: trailing off mid-sentence ('I was gonna... never mind'), self-corrections "
        "('Wait no, I mean—'), overlapping dialogue, mumbling, sarcastic tone markers. "
        "Regional expressions: y'all (South), hella (NorCal), wicked (Boston), "
        "jawn (Philly), deadass (NYC). "
        "Pop culture deep cuts, memes referenced in speech, spontaneous humor. "
        "Think: unscripted podcast between close friends after a few beers. "
        "NO simplification. NO textbook structures. Pure raw American English."
    ),
}


def _real_english_progress_path(profile_id):
    return os.path.join(REAL_ENGLISH_DIR, f"progress-{_profile_storage_slug(profile_id)}.json")


def _load_real_english_progress(profile_id):
    path = _real_english_progress_path(profile_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"completed_lessons": [], "lesson_history": []}


def _save_real_english_progress(profile_id, data):
    os.makedirs(REAL_ENGLISH_DIR, exist_ok=True)
    with open(_real_english_progress_path(profile_id), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _real_english_lesson_path(profile_id, lesson_id):
    slug = _profile_storage_slug(profile_id)
    return os.path.join(REAL_ENGLISH_DIR, f"lesson-{slug}-{lesson_id}.json")


def _save_real_english_lesson(profile_id, lesson_id, data):
    os.makedirs(REAL_ENGLISH_DIR, exist_ok=True)
    with open(_real_english_lesson_path(profile_id, lesson_id), "w", encoding="utf-8") as f:
        json.dump({"id": lesson_id, "saved": now_iso(), **data}, f, ensure_ascii=False, indent=2)


def _load_real_english_lesson(profile_id, lesson_id):
    path = _real_english_lesson_path(profile_id, lesson_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _list_real_english_lessons(profile_id):
    slug = _profile_storage_slug(profile_id)
    prefix = f"lesson-{slug}-"
    items = []
    if not os.path.exists(REAL_ENGLISH_DIR):
        return items
    for fname in sorted(os.listdir(REAL_ENGLISH_DIR), reverse=True):
        if fname.startswith(prefix) and fname.endswith(".json"):
            fpath = os.path.join(REAL_ENGLISH_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    items.append(json.load(f))
            except (json.JSONDecodeError, OSError):
                pass
    return items


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

    tab_episodes, tab_listen, tab_vocab, tab_shadow, tab_progress = st.tabs([
        "Episodes & Dialogues",
        "Ecouter la scene",
        "Vocabulaire, Chunks & Idioms",
        "Pratiquer (Shadowing)",
        "Ma progression",
    ])

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
        series_labels = [
            f"{REAL_ENGLISH_SERIES[s]['icon']} {s}" for s in series_names
        ]
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
            st.success("Cet episode est deja genere. Naviguez dans les onglets pour l'explorer.")
            if is_completed:
                st.markdown("✅ **Lecon terminee**")
            st.session_state["re_current_lesson"] = existing_lesson
            st.session_state["re_current_lesson_id"] = episode_id
        else:
            st.session_state.pop("re_current_lesson", None)
            st.session_state.pop("re_current_lesson_id", None)

        # ── Load saved lessons browser ───────────────────────────────
        if all_lessons:
            with st.expander(f"Mes episodes generes ({len(all_lessons)})", expanded=False):
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
                            # Remove audio
                            audio_path = os.path.join(REAL_ENGLISH_AUDIO_DIR, f"{lid}.wav")
                            if os.path.exists(audio_path):
                                os.remove(audio_path)
                            if lid in progress.get("completed_lessons", []):
                                progress["completed_lessons"].remove(lid)
                                _save_real_english_progress(profile_id, progress)
                            if st.session_state.get("re_current_lesson_id") == lid:
                                st.session_state.pop("re_current_lesson", None)
                                st.session_state.pop("re_current_lesson_id", None)
                            st.rerun()

        if st.button("Generer cet episode", key="re_generate"):
            with st.spinner("L'IA ecrit un dialogue authentique..."):
                level_instr = REAL_ENGLISH_LEVEL_INSTRUCTIONS.get(re_level, "")
                prompt = (
                    f"You are a scriptwriter for an American TV show. Write a REALISTIC, "
                    f"natural American English dialogue for this scene:\n\n"
                    f"Series: \"{selected_series}\"\n"
                    f"Episode scenario: \"{selected_episode}\"\n"
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
                    f"- 15-25 lines between 2-3 characters with American names\n"
                    f"- Include [stage directions] for tone/action\n"
                    f"- Mini-story with beginning, middle, and end\n"
                    f"- If someone would say 'going to' in real life, write 'gonna' instead.\n"
                    f"- If someone would say 'want to', write 'wanna'. Same for gotta, kinda, etc.\n"
                    f"- EVERY line should sound like something you'd hear in Friends, The Office, or a podcast.\n\n"
                    f"After the dialogue, provide:\n"
                    f"1. KEY_VOCABULARY: 8-12 important informal expressions, chunks, phrasal verbs, "
                    f"idioms, and reductions used in the dialogue. For each give: the expression, "
                    f"its standard/full form, the French translation, and the type "
                    f"(chunk/idiom/reduction/phrasal verb/slang).\n"
                    f"2. CULTURAL_NOTE: 2-3 sentences in French explaining any American cultural "
                    f"context in this dialogue.\n"
                    f"3. COMPREHENSION_QS: 3 quick comprehension questions about the dialogue "
                    f"(in English) with answers.\n\n"
                    f"Format as JSON:\n"
                    f'{{"dialogue": "full dialogue text with [stage directions]", '
                    f'"characters": ["Name1", "Name2"], '
                    f'"vocabulary": ['
                    f'{{"expression": "...", "full_form": "...", "french": "...", "type": "chunk"}}, ...'
                    f'], '
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

        # Voice selection (shared for generation)
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

        # ── Bibliotheque audio : tous les episodes avec audio deja genere ────
        audio_library = []
        for ls in all_lessons:
            lid = ls.get("id", "")
            afp = os.path.join(REAL_ENGLISH_AUDIO_DIR, f"{lid}.wav")
            has_audio = os.path.exists(afp)
            audio_library.append({
                "id": lid,
                "series": ls.get("series", ""),
                "episode": ls.get("episode", ""),
                "level": ls.get("level", ""),
                "icon": ls.get("series_icon", "📺"),
                "has_audio": has_audio,
                "audio_path": afp,
                "dialogue": ls.get("dialogue", ""),
            })

        episodes_with_audio = [a for a in audio_library if a["has_audio"]]
        episodes_without_audio = [a for a in audio_library if not a["has_audio"]]

        if episodes_with_audio:
            st.markdown(f"### 🎧 Mes audios generes ({len(episodes_with_audio)})")
            st.caption("Cliquez pour reecouter un episode a tout moment.")
            for ai, ep in enumerate(episodes_with_audio):
                is_current = (ep["id"] == st.session_state.get("re_current_lesson_id"))
                marker = " ◀️ *en cours*" if is_current else ""
                with st.expander(
                    f"{ep['icon']} {ep['series']} — {ep['episode']} ({ep['level']}){marker}"
                ):
                    with open(ep["audio_path"], "rb") as af:
                        st.audio(af.read(), format="audio/wav")

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
                                    ep["dialogue"], va, vb
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
                st.info("Generez ou selectionnez un episode dans l'onglet 'Episodes & Dialogues' d'abord.")
        else:
            audio_file = os.path.join(REAL_ENGLISH_AUDIO_DIR, f"{lesson_id}.wav")
            if not os.path.exists(audio_file):
                st.markdown(
                    f"### 🔊 Episode actuel sans audio : "
                    f"{lesson.get('series_icon', '📺')} {lesson.get('series', '')} — "
                    f"{lesson.get('episode', '')} ({lesson.get('level', '')})"
                )
                if st.button("🔊 Generer l'audio du dialogue", key="re_gen_audio"):
                    with st.spinner("Generation audio 2 voix..."):
                        audio_bytes, mime, err = generate_dual_voice_tts(
                            lesson["dialogue"], va, vb
                        )
                        if err:
                            st.error(f"Erreur TTS: {err}")
                        else:
                            os.makedirs(REAL_ENGLISH_AUDIO_DIR, exist_ok=True)
                            with open(audio_file, "wb") as af:
                                af.write(audio_bytes)
                            st.rerun()

        # ── Episodes sans audio (generation en attente) ──────────────────────
        if episodes_without_audio:
            with st.expander(
                f"📋 Episodes sans audio ({len(episodes_without_audio)})", expanded=False
            ):
                st.caption("Ces episodes ont ete generes mais n'ont pas encore d'audio.")
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
                                    ab, mime, err = generate_dual_voice_tts(
                                        loaded.get("dialogue", ""), va, vb
                                    )
                                    if not err:
                                        os.makedirs(REAL_ENGLISH_AUDIO_DIR, exist_ok=True)
                                        with open(ep["audio_path"], "wb") as af:
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
            st.info("Generez ou selectionnez un episode dans l'onglet 'Episodes & Dialogues' d'abord.")
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
                    e.get("term", "").lower() for e in vocab_entries if isinstance(e, dict)
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
                        expr_audio_file = os.path.join(
                            REAL_ENGLISH_AUDIO_DIR, f"vocab-{slugify(expr)}.wav"
                        )
                        if os.path.exists(expr_audio_file):
                            with open(expr_audio_file, "rb") as af:
                                st.audio(af.read(), format="audio/wav")
                        else:
                            if st.button("🔊", key=f"re_vocab_tts_{vi}"):
                                with st.spinner("Audio..."):
                                    ab, mime, err = text_to_speech_openrouter(expr, voice="echo")
                                    if not err:
                                        os.makedirs(REAL_ENGLISH_AUDIO_DIR, exist_ok=True)
                                        with open(expr_audio_file, "wb") as af:
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
                                        if full else f"Construisez une phrase avec '{expr}'."
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
                    v for v in vocab_items
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
            st.info("Generez ou selectionnez un episode dans l'onglet 'Episodes & Dialogues' d'abord.")
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
                v.get("expression", "") for v in lesson.get("vocabulary", [])
                if v.get("expression", "")
            ]

            if st.button("Envoyer vers le Shadowing interactif", key="re_to_shadowing"):
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
                    st.info("Ce dialogue est deja dans votre liste de shadowing (mis a jour).")

    # ── Tab 5: Ma progression ────────────────────────────────────────────────
    with tab_progress:
        st.subheader("Ma progression — Anglais reel")
        lesson = st.session_state.get("re_current_lesson")
        lesson_id = st.session_state.get("re_current_lesson_id")

        completed = progress.get("completed_lessons", [])
        total_episodes = sum(len(s["episodes"]) * len(CEFR_LEVELS) for s in REAL_ENGLISH_SERIES.values())
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
                    progress.setdefault("lesson_history", []).append({
                        "action": "uncompleted",
                        "lesson_id": lesson_id,
                        "date": now_iso(),
                    })
                    _save_real_english_progress(profile_id, progress)
                    st.rerun()
            else:
                st.warning("Cet episode n'est pas encore marque comme termine.")
                if st.button("✅ Marquer comme termine", key="re_complete"):
                    progress.setdefault("completed_lessons", []).append(lesson_id)
                    progress.setdefault("lesson_history", []).append({
                        "action": "completed",
                        "lesson_id": lesson_id,
                        "series": lesson.get("series", ""),
                        "episode": lesson.get("episode", ""),
                        "level": lesson.get("level", ""),
                        "date": now_iso(),
                    })
                    _save_real_english_progress(profile_id, progress)

                    # Auto-add vocabulary to flashcards
                    vocab_items = lesson.get("vocabulary", [])
                    if vocab_items:
                        vocab_entries = load_vocab(profile_id=profile_id)
                        existing_terms = {
                            e.get("term", "").lower()
                            for e in vocab_entries if isinstance(e, dict)
                        }
                        added = 0
                        for v in vocab_items[:LESSON_FLASHCARD_LIMIT]:
                            et = v.get("expression", "").strip()
                            if not et or et.lower() in existing_terms:
                                continue
                            new_card = {
                                "id": str(uuid.uuid4())[:8],
                                "term": et,
                                "translation": v.get("french", ""),
                                "part_of_speech": v.get("type", "chunk"),
                                "explanation": (
                                    f"Forme complete: {v.get('full_form', '')}. "
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
                                "source_lesson_id": f"real-{lesson_id}",
                                "profile_id": profile_id,
                            }
                            vocab_entries.append(new_card)
                            existing_terms.add(et.lower())
                            added += 1
                        if added > 0:
                            save_vocab(vocab_entries, profile_id=profile_id)
                            st.info(f"{added} flashcards ajoutees automatiquement depuis cette lecon.")

                    st.success("Episode marque comme termine !")
                    st.rerun()
        else:
            st.info("Selectionnez un episode dans l'onglet 'Episodes & Dialogues' pour le marquer comme termine.")

        # Recent history
        history = progress.get("lesson_history", [])
        if history:
            with st.expander(f"Historique recent ({len(history)} actions)"):
                for h in reversed(history[-20:]):
                    action = "✅ Termine" if h.get("action") == "completed" else "↩️ Annule"
                    date = h.get("date", "")[:10]
                    series = h.get("series", "")
                    ep = h.get("episode", "")
                    lvl = h.get("level", "")
                    st.markdown(f"- {action} — {date} — {series} — {ep} ({lvl})")


def main():
    ensure_directories()
    initialize_state()

    st.set_page_config(page_title="English Audio Coach", layout="wide")
    st.title("English Audio Coach (A1 -> C2)")

    if not OPENROUTER_API_KEY:
        st.error(
            "Ajoutez OPENROUTER_API_KEY dans le fichier .env pour activer les fonctions IA/audio."
        )

    st.sidebar.header("Profil")
    profiles = load_profiles()
    profile_ids = [p["id"] for p in profiles]
    if "profile_gate_passed" not in st.session_state:
        st.session_state["profile_gate_passed"] = False

    current_profile_id = st.session_state.get("active_profile_id", "")
    if current_profile_id not in profile_ids:
        current_profile_id = ""

    selectable_profiles = ["__choose__"] + profile_ids
    if current_profile_id:
        default_choice = current_profile_id
    else:
        default_choice = "__choose__"

    selected_profile_id = st.sidebar.selectbox(
        "Profil actif",
        selectable_profiles,
        index=selectable_profiles.index(default_choice),
        format_func=lambda pid: next(
            (
                f"{p.get('name', pid)} ({p.get('target_cefr', 'B1')})"
                for p in profiles
                if p.get("id") == pid
            ),
            "Choisir un profil...",
        ),
        key="active-profile-required-select",
    )

    if selected_profile_id in profile_ids:
        st.session_state["active_profile_id"] = selected_profile_id
        st.session_state["profile_gate_passed"] = True

    active_profile = None
    if st.session_state.get("profile_gate_passed"):
        active_profile = get_active_profile()
        st.sidebar.caption(
            f"Niveau lecons par defaut: {active_profile.get('target_cefr', 'B1')}"
        )

    with st.sidebar.expander("Ajouter / mettre a jour un profil"):
        st.caption(
            "Profils existants: " + ", ".join(p.get("name", "") for p in profiles)
        )
        with st.form("profile-create-form", clear_on_submit=True):
            new_profile_name = st.text_input("Nom du profil", key="profile-new-name")
            new_profile_level = st.selectbox(
                "Niveau de depart",
                CEFR_LEVELS,
                index=CEFR_LEVELS.index("B1"),
                key="profile-new-level",
            )
            save_profile = st.form_submit_button(
                "Enregistrer le profil",
                width="stretch",
            )

        if save_profile:
            already_exists = any(
                p.get("name", "").lower() == new_profile_name.strip().lower()
                for p in profiles
            )
            created_profile, profile_err = create_or_update_profile(
                new_profile_name,
                target_cefr=new_profile_level,
            )
            if profile_err:
                st.warning(profile_err)
            else:
                st.session_state["active_profile_id"] = created_profile["id"]
                st.session_state["profile_gate_passed"] = True
                if already_exists:
                    st.success(f"Profil mis a jour: {created_profile['name']}")
                else:
                    st.success(f"Profil cree: {created_profile['name']}")
                st.rerun()

    if not st.session_state.get("profile_gate_passed"):
        st.warning("Choisissez un profil pour démarrer l'application.")
        st.stop()

    previous_profile_id = st.session_state.get("last_active_profile_id")
    current_active_profile_id = st.session_state.get("active_profile_id")
    if previous_profile_id and previous_profile_id != current_active_profile_id:
        st.session_state.active_session = None
        for k in list(st.session_state.keys()):
            if k.startswith("flash_") or k.startswith("flash-"):
                del st.session_state[k]
            if k.startswith("vocab_") or k.startswith("vocab-"):
                del st.session_state[k]
            if k.startswith("shadow_") or k.startswith("shadow-"):
                del st.session_state[k]
    st.session_state["last_active_profile_id"] = current_active_profile_id

    st.sidebar.header("Navigation")
    page = st.sidebar.radio(
        "Aller a",
        [
            "Accueil",
            "Lecons (Ecoute)",
            "Lecons basees sur echanges IA",
            "Anglais naturel",
            "Anglais reel (Mini-series)",
            "Histoires",
            "Playlist",
            "Podcasts",
            "Pratique avec l'IA",
            "Shadowing interactif",
            "Vocabulaire & Flashcards",
            "Historique",
        ],
    )

    with st.sidebar.expander("Modeles OpenRouter"):
        st.caption(f"STT: {STT_MODEL}")
        st.caption(f"Chat: {CHAT_MODEL}")
        st.caption(f"Evaluation: {EVAL_MODEL}")
        st.caption(f"TTS: {TTS_MODEL} ({TTS_VOICE})")

    if page == "Accueil":
        render_home()
    elif page == "Lecons (Ecoute)":
        render_lessons_page()
    elif page == "Lecons basees sur echanges IA":
        render_ai_lessons_page()
    elif page == "Anglais naturel":
        render_natural_english_page()
    elif page == "Anglais reel (Mini-series)":
        render_real_english_page()
    elif page == "Histoires":
        render_stories_page()
    elif page == "Playlist":
        render_playlist_page()
    elif page == "Podcasts":
        render_podcast_page()
    elif page == "Pratique avec l'IA":
        render_practice_page()
    elif page == "Shadowing interactif":
        render_shadowing_daily_page()
    elif page == "Vocabulaire & Flashcards":
        render_vocabulary_page()
    elif page == "Historique":
        render_history_page()


if __name__ == "__main__":
    main()
