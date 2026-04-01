import base64
import io
import json
import os
import re
import uuid
import wave
from datetime import datetime

import requests
import streamlit as st
import streamlit.components.v1 as st_components
from dotenv import load_dotenv

load_dotenv()


def _cfg(key, default=""):
    """Read config from st.secrets (Streamlit Cloud) then os.environ (.env local)."""
    try:
        val = st.secrets.get(key)
        if val is not None:
            return str(val)
    except Exception:
        pass
    return os.getenv(key, default)


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


def ensure_directories():
    for path in [
        DATA_DIR,
        LESSON_PACK_DIR,
        LESSON_AUDIO_DIR,
        VARIATIONS_DIR,
        USER_CONVERSATIONS_DIR,
        SESSIONS_DIR,
        AUDIO_DIR,
        PODCAST_DIR,
        PODCAST_AUDIO_DIR,
    ]:
        os.makedirs(path, exist_ok=True)


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def slugify(value):
    value = value.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


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


def _stream_tts_once(text, model, voice, requested_format):
    max_retries = 3
    last_conn_err = None
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
                            "content": (
                                "You are a text-to-speech narrator with a natural American accent. "
                                "Your only job is to read the text provided by the user EXACTLY as written, "
                                "word for word. Do NOT respond to the content, do NOT add commentary, "
                                "do NOT answer questions in the text. "
                                "If the text is a dialogue with speakers labeled (e.g. 'A:' or 'B:'), "
                                "read every line naturally as if performing both parts. "
                                "Read the text verbatim from start to finish."
                            ),
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


def text_to_speech_openrouter(text, voice=TTS_VOICE, audio_format=TTS_AUDIO_FORMAT):
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


def parse_dialogue_to_turns(dialogue_text):
    """Parse 'A: ...' / 'B: ...' lines into [{speaker, text}, ...] dicts."""
    turns = []
    current_speaker = None
    current_lines = []
    for line in dialogue_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([AB]):\s*(.+)$", line)
        if m:
            if current_speaker and current_lines:
                turns.append(
                    {"speaker": current_speaker, "text": " ".join(current_lines)}
                )
            current_speaker = m.group(1)
            current_lines = [m.group(2)]
        elif current_speaker:
            current_lines.append(line)
    if current_speaker and current_lines:
        turns.append({"speaker": current_speaker, "text": " ".join(current_lines)})
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
        # Split long individual turns — keeps speaker context intact
        sub_chunks = split_text_for_tts(turn["text"], max_chars=1200)
        for chunk in sub_chunks:
            audio_bytes, _, err = text_to_speech_openrouter(chunk, voice=voice)
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
- Include at least 2 idiomatic expressions or chunks typical of {cefr_level} per dialogue
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


def lesson_pack_path(theme_name, cefr_level="B1"):
    return os.path.join(
        LESSON_PACK_DIR, f"{slugify(theme_name)}-{cefr_level.lower()}.json"
    )


def load_lesson_pack(theme_name, cefr_level="B1"):
    path = lesson_pack_path(theme_name, cefr_level)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_lesson_pack(theme_name, pack_data, cefr_level="B1"):
    with open(lesson_pack_path(theme_name, cefr_level), "w", encoding="utf-8") as f:
        json.dump(pack_data, f, ensure_ascii=False, indent=2)


# ── Variations persistence ────────────────────────────────────────────────────


def variations_path(theme_name, cefr_level="B1"):
    return os.path.join(
        VARIATIONS_DIR, f"{slugify(theme_name)}-{cefr_level.lower()}_variations.json"
    )


def load_quick_variations(theme_name, cefr_level="B1"):
    path = variations_path(theme_name, cefr_level)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_quick_variations(theme_name, variations, cefr_level="B1"):
    with open(variations_path(theme_name, cefr_level), "w", encoding="utf-8") as f:
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
- Include realistic chunks and idiomatic phrases appropriate for {cefr_level}.
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


def build_tutor_system_prompt(mode, theme, objective):
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

    return (
        "You are a friendly American English conversation partner for a B1 learner targeting C2. "
        "Speak like a real native American — casual, natural, with contractions and fillers (yeah, totally, I mean, you know, right?). "
        "NEVER explicitly correct the learner. NEVER say 'you should say', 'the correct form is', 'actually it's', or anything that interrupts the flow. "
        "Instead, use IMPLICIT RECASTS only: if the learner makes a grammar or vocabulary mistake, simply use the correct form naturally in your reply without drawing attention to it. "
        "Example: learner says 'I goed to the store' → you reply 'Oh nice, you went to the store! What did you get?' — correction embedded, conversation continues. "
        "Your only job during the conversation is to keep talking naturally, ask follow-up questions, and model correct American English through your own speech. "
        "All detailed corrections and feedback are saved for the end-of-session evaluation — do NOT give them during the conversation. "
        f"Mode: {mode}. {topic_instruction} {objective_instruction} "
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


def new_session(mode, theme, objective):
    session_id = (
        f"session-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    )
    data = {
        "id": session_id,
        "created_at": now_iso(),
        "started_at": now_iso(),
        "mode": mode,
        "theme": theme,
        "objective": objective,
        "messages": [
            {
                "role": "system",
                "content": build_tutor_system_prompt(
                    mode=mode, theme=theme, objective=objective
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


def load_all_sessions():
    sessions = []
    for file_name in os.listdir(SESSIONS_DIR):
        if not file_name.endswith(".json"):
            continue
        path = os.path.join(SESSIONS_DIR, file_name)
        with open(path, "r", encoding="utf-8") as f:
            sessions.append(json.load(f))
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


def generate_podcast_scripts(date_str, interests, duration_minutes=7):
    """Generate 3 podcast discussions (one per interest category) via OpenRouter AI."""
    interests_list = "\n".join(f"- {i}" for i in interests)
    prompt = f"""Today's date: {date_str}.

You are a podcast producer creating engaging English-learning content for an intermediate learner targeting C2 American English.

Generate exactly 3 podcast episodes as a JSON array, one for each of these interest areas:
{interests_list}

For each podcast, write a lively, natural discussion between 2 American hosts (Host A and Host B).

Requirements:
- Each podcast should last approximately {duration_minutes} minutes when read aloud (~{duration_minutes * 130} words per script).
- Use natural American conversational English: contractions, fillers (you know, I mean, right, totally, absolutely, kind of, sort of), natural interruptions and overlaps.
- Both hosts share opinions, debate facts, make jokes, and disagree sometimes — like a real podcast.
- Base topics on plausible current events, recent trends, or hot discussions related to today's date ({date_str}) in that interest area.
- Use rich C1/C2 vocabulary naturally embedded in conversation.
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


def get_elapsed_seconds(session_data):
    """Return seconds elapsed since the session started."""
    started = session_data.get("started_at") or session_data.get("created_at")
    if not started:
        return 0
    try:
        started_dt = datetime.fromisoformat(started.replace("Z", ""))
        return int((datetime.utcnow() - started_dt).total_seconds())
    except Exception:
        return 0


def get_ai_reply(session_data, user_text, elapsed_seconds=0):
    messages = list(session_data["messages"])
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

    prompt = f"""
Evaluate this learner's spoken English (B1 level aiming for C2 American English).

Give a score from 1 to 10 for:
- Grammar
- Chunks/Vocabulary
- Fluency
- Naturalness

Then provide:
1) Strong points
2) Priority corrections (with corrected examples)
3) What to practice next week

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


def render_home():
    st.header("Objectif: B1 -> C2 American English")
    st.write(
        "Cette application combine ecoute intensive, repetition et conversations audio instantanees avec l'IA."
    )
    st.markdown(
        """
- **Lecons**: 10 variations par theme de vie quotidienne + packs 5x5 min
- **Podcasts**: 3 podcasts par jour sur News, IA, Football et Manga (5-10 min, accent US, niveau C1/C2)
- **Pratique IA**: mode guide (theme) ou libre, conversations audio
- **Evaluation** de fin de session: grammaire, chunks, fluidite, naturel
- **Historique** audio complet: reecoute de toutes les sessions
"""
    )


def render_lessons_page():
    st.header("Lecons audio: ecouter et repeter")

    # ── Niveau CEFR ──────────────────────────────────────────────────────────
    cefr_level = st.radio(
        "Niveau cible",
        ["B1", "B2", "C1", "C2"],
        horizontal=True,
        index=1,
        help="Les dialogues seront générés avec le vocabulaire, la grammaire et les chunks adaptés à ce niveau.",
    )
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
        key=f"voice-pair-{slugify(theme_name)}-{cefr_level}",
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
            "**Objectif:** internaliser les chunks, les liaisons et le rythme americain."
        )

        var_cache_key = f"quick-variations-ai-{slugify(theme_name)}-{cefr_level}"

        # Load from disk into session_state on first render of this theme+level
        if var_cache_key not in st.session_state:
            saved_vars = load_quick_variations(theme_name, cefr_level)
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
                    save_quick_variations(theme_name, ai_variations, cefr_level)
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

                    audio_key = (
                        f"quick-audio-{slugify(theme_name)}-{cefr_level}-{item['id']}"
                    )
                    audio_disk_file = f"var-{slugify(theme_name)}-{cefr_level.lower()}-{item['id']}.wav"

                    # Load from disk if not already in session_state
                    if audio_key not in st.session_state:
                        cached = load_lesson_audio(audio_disk_file)
                        if cached:
                            st.session_state[audio_key] = {
                                "bytes": cached,
                                "mime": "audio/wav",
                            }

                    if audio_key in st.session_state:
                        st.audio(
                            st.session_state[audio_key]["bytes"],
                            format=st.session_state[audio_key]["mime"],
                        )
                        col_regen_v, col_del_v = st.columns([1, 1])
                        with col_regen_v:
                            if st.button(
                                "🔄 Régénérer",
                                key=f"regen-{audio_key}",
                                use_container_width=True,
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
                                use_container_width=True,
                            ):
                                disk_path = lesson_audio_path(audio_disk_file)
                                if os.path.exists(disk_path):
                                    os.remove(disk_path)
                                st.session_state.pop(audio_key, None)
                                st.rerun()
                    else:
                        if st.button(
                            "🔊 Générer audio US (2 voix)",
                            key=f"btn-{audio_key}",
                            use_container_width=True,
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
        pack = load_lesson_pack(theme_name, cefr_level)

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
                    save_lesson_pack(theme_name, generated, cefr_level)
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

                    btn_key = f"pack-audio-{slugify(theme_name)}-{cefr_level}-{idx}"
                    audio_disk_file = (
                        f"pack-{slugify(theme_name)}-{cefr_level.lower()}-{idx}.wav"
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
                        st.audio(
                            st.session_state[btn_key]["bytes"],
                            format=st.session_state[btn_key]["mime"],
                        )
                        col_regen_p, col_del_p = st.columns([1, 1])
                        with col_regen_p:
                            if st.button(
                                "🔄 Régénérer",
                                key=f"regen-{btn_key}",
                                use_container_width=True,
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
                                use_container_width=True,
                            ):
                                disk_path = lesson_audio_path(audio_disk_file)
                                if os.path.exists(disk_path):
                                    os.remove(disk_path)
                                st.session_state.pop(btn_key, None)
                                st.rerun()
                    else:
                        if st.button(
                            "🔊 Générer audio US (2 voix)",
                            key=f"btn-{btn_key}",
                            use_container_width=True,
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


def _collect_tracks_for_slug(slug, theme_label):
    """Return all WAV audio tracks on disk for a given theme slug (all levels)."""
    if not os.path.isdir(LESSON_AUDIO_DIR):
        return []
    var_re = re.compile(rf"^var-{re.escape(slug)}-(.+?)\.wav$")
    pack_re = re.compile(rf"^pack-{re.escape(slug)}-(.+?)\.wav$")
    tracks = []
    for fname in sorted(os.listdir(LESSON_AUDIO_DIR)):
        path = os.path.join(LESSON_AUDIO_DIR, fname)
        m = var_re.match(fname)
        if m:
            tracks.append({"label": f"{theme_label} · Var {m.group(1)}", "file": path})
            continue
        m = pack_re.match(fname)
        if m:
            tracks.append({"label": f"{theme_label} · Pack {m.group(1)}", "file": path})
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
  else{{const last=shuf?(ord.indexOf(ci)===ord.length-1):(ci===T.length-1);if(!last)next();}}
}});
buildOrd();renderList();play(0);
</script>
</body>
</html>"""
    st_components.html(player_html, height=height, scrolling=False)


def render_playlist_page():
    st.header("Playlist audio — écoute en continu")

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

        tracks = _collect_tracks_for_slug(slugify(theme_name), theme_name)

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
            found = _collect_tracks_for_slug(slugify(t), t)
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
    st.header("Pratique audio instantanee avec l'IA")
    st.write(
        "Enregistrez votre audio, envoyez-le, puis ecoutez la reponse vocale de l'IA."
    )

    practice_mode = st.radio(
        "Mode", ["Guide par theme", "Session libre"], horizontal=True
    )

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
            mode_value, theme_value, selected_objective
        )
        st.success(f"Session demarree: {st.session_state.active_session['id']}")

    session_data = st.session_state.active_session
    if not session_data:
        st.info("Demarrez une session pour activer les echanges audio.")
        return

    st.caption(
        f"Session active: {session_data['id']} | Mode: {session_data['mode']} | Theme: {session_data['theme']}"
    )

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
    audio_key = f"practice_audio_input_{n_turns}"

    if elapsed < MAX_SESSION_SECONDS:
        st.markdown("**🎙️ Votre message :**")
        audio_file = st.audio_input(
            "Cliquez sur le micro, parlez, puis cliquez à nouveau pour arrêter",
            key=audio_key,
        )

        col_send, col_clear, col_eval = st.columns([2, 1, 1])
        with col_send:
            send_clicked = st.button(
                "📤 Envoyer",
                use_container_width=True,
                type="primary",
            )
        with col_clear:
            if st.button("🗑️ Effacer", use_container_width=True):
                st.session_state.pop(audio_key, None)
                st.rerun()
        with col_eval:
            eval_clicked = st.button("📊 Evaluer", use_container_width=True)
    else:
        audio_file = None
        send_clicked = False
        col_eval_only = st.columns(1)[0]
        with col_eval_only:
            eval_clicked = st.button(
                "📊 Obtenir la note de fin de session",
                type="primary",
                use_container_width=True,
            )

    if send_clicked:
        if not audio_file:
            st.warning("Enregistrez d'abord un audio en cliquant sur le micro.")
        else:
            user_audio_bytes = audio_file.getvalue()
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


def render_history_page():
    st.header("Historique complet des sessions audio")
    sessions = load_all_sessions()
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
    st.header("🎙️ Podcasts du jour")
    st.write(
        "3 podcasts générés chaque jour sur vos sujets favoris : "
        "**News, IA, Football, Manga**. "
        "Écoutez-les en anglais américain pour développer votre compréhension orale C1/C2."
    )

    col_date, col_dur = st.columns([2, 1])
    with col_date:
        date_selected = st.date_input(
            "Date",
            value=datetime.utcnow().date(),
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
            use_container_width=True,
            disabled=(podcasts is not None),
        ):
            with st.spinner("Génération des 3 podcasts en cours (30-60 secondes)..."):
                generated, err = generate_podcast_scripts(
                    date_selected, USER_INTERESTS, duration_minutes=duration
                )
            if err:
                st.error(f"Erreur génération podcasts: {err}")
            else:
                save_podcasts_for_date(date_selected, generated)
                st.success("3 podcasts générés et sauvegardés !")
                st.rerun()
    with col_regen:
        if podcasts and st.button("🔄 Régénérer", use_container_width=True):
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
                f"⏱️ ~{podcast.get('estimated_minutes', duration)} min  |  🔴 C1/C2  |  📅 {date_selected}"
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
                        use_container_width=True,
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
                        use_container_width=True,
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
                    use_container_width=True,
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


def main():
    ensure_directories()
    initialize_state()

    st.set_page_config(page_title="English Audio Coach", layout="wide")
    st.title("English Audio Coach (B1 -> C2)")

    if not OPENROUTER_API_KEY:
        st.error(
            "Ajoutez OPENROUTER_API_KEY dans le fichier .env pour activer les fonctions IA/audio."
        )

    st.sidebar.header("Navigation")
    page = st.sidebar.radio(
        "Aller a",
        [
            "Accueil",
            "Lecons (Ecoute)",
            "Playlist",
            "Podcasts",
            "Pratique avec l'IA",
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
    elif page == "Playlist":
        render_playlist_page()
    elif page == "Podcasts":
        render_podcast_page()
    elif page == "Pratique avec l'IA":
        render_practice_page()
    elif page == "Historique":
        render_history_page()


if __name__ == "__main__":
    main()
