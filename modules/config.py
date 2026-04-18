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

# ── ElevenLabs TTS ──────────────────────────────────────────────────────────
ELEVENLABS_API_KEY = _cfg("ELEVENLABS_API_KEY")
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
# Natural American voices (voice IDs from ElevenLabs)
ELEVENLABS_VOICES = {
    "Rachel (femme US)": "21m00Tcm4TlvDq8ikWAM",
    "Drew (homme US)": "29vD33N1CtxCmqQRPOHJ",
    "Clyde (homme US grave)": "2EiwWnXFnvU5JabPnv8n",
    "Dave (homme US)": "CYw3kZ02Hs0563khs1Fj",
    "Fin (homme US jeune)": "D38z5RcWu1voky8WS1ja",
    "Sarah (femme US)": "EXAVITQu4vr4xnSDxMaL",
    "Laura (femme US)": "FGY2WhTYpPnrIDTdsKH5",
    "Charlie (homme US)": "IKne3meq5aSn9XLyUdCD",
    "Charlotte (femme US)": "XB0fDUnXU5powFXDhCwa",
    "Emily (femme US)": "LcfcDJNUP1GQjkzn1xUU",
    "Josh (homme US)": "TxGEqnHWrfWFTfGW9XjX",
    "Adam (homme US)": "pNInz6obpgDQGcFmaJgB",
    "Sam (homme US)": "yoZ06aMxZJJ28mfd3POQ",
    "Dorothy (femme US agee)": "ThT5KcBeYPX3keUQqHPh",
}
# Voice pairs for ElevenLabs dialogues
ELEVENLABS_VOICE_PAIRS = {
    "Homme + Femme (Josh + Rachel)": ("TxGEqnHWrfWFTfGW9XjX", "21m00Tcm4TlvDq8ikWAM"),
    "Femme + Homme (Sarah + Adam)": ("EXAVITQu4vr4xnSDxMaL", "pNInz6obpgDQGcFmaJgB"),
    "Homme + Homme (Josh + Adam)": ("TxGEqnHWrfWFTfGW9XjX", "pNInz6obpgDQGcFmaJgB"),
    "Femme + Femme (Rachel + Laura)": ("21m00Tcm4TlvDq8ikWAM", "FGY2WhTYpPnrIDTdsKH5"),
    "Homme + Femme (Drew + Charlotte)": (
        "29vD33N1CtxCmqQRPOHJ",
        "XB0fDUnXU5powFXDhCwa",
    ),
}

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

CONNECTED_SPEECH_DIR = os.path.join(DATA_DIR, "connected_speech")
CONNECTED_SPEECH_AUDIO_DIR = os.path.join(DATA_DIR, "connected_speech_audio")
SLANG_DIR = os.path.join(DATA_DIR, "slang_idioms")
IMMERSION_GENERATED_DIR = os.path.join(DATA_DIR, "immersion_generated")
REAL_ENGLISH_DIR = os.path.join(DATA_DIR, "real_english")
REAL_ENGLISH_AUDIO_DIR = os.path.join(DATA_DIR, "real_english_audio")

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
    "Tech job interviews (Dev & IT Teacher)": "Practice real software developer and CS teacher interview scenarios: whiteboard questions, system design, teaching demos, behavioral STAR answers, and salary negotiation in tech.",
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
        "Tech job interviews (Dev & IT Teacher)",
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
    "Translation challenge (FR <-> EN)": {
        "key": "fr_to_en",
        "description": "Guided translation drill with selectable direction (FR -> EN or EN -> FR).",
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
