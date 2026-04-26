import base64
import io
import json
import os
import re
import tempfile
import time
import wave
from datetime import datetime

import requests
import streamlit as st

from modules.config import *

STT_PROVIDER_AUTO = "auto"
STT_PROVIDER_OPENROUTER = "openrouter"
STT_PROVIDER_GOOGLE = "google_free"
STT_PROVIDER_WHISPER = "whisper_local"


def get_stt_provider_options():
    return [
        (STT_PROVIDER_AUTO, "Auto (OpenRouter -> Google -> Whisper)"),
        (STT_PROVIDER_OPENROUTER, "OpenRouter"),
        (STT_PROVIDER_GOOGLE, "Google gratuit"),
        (STT_PROVIDER_WHISPER, "Whisper local"),
    ]


def get_stt_mode():
    return st.session_state.get("stt_mode", STT_PROVIDER_AUTO)


def set_stt_mode(mode):
    valid = {k for k, _ in get_stt_provider_options()}
    st.session_state["stt_mode"] = mode if mode in valid else STT_PROVIDER_AUTO


def get_last_stt_provider_used():
    return st.session_state.get("stt_last_provider_used", "")


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


def _openrouter_stt_in_cooldown():
    until_ts = st.session_state.get("openrouter_stt_unavailable_until", 0)
    return time.time() < float(until_ts)


def _mark_openrouter_stt_unavailable(seconds=900):
    st.session_state["openrouter_stt_unavailable_until"] = time.time() + int(seconds)


def _is_openrouter_quota_error(err_text):
    raw = str(err_text or "")
    txt = raw.lower()
    patterns = [
        "insufficient credits",
        "insufficient credit",
        "insufficient balance",
        "payment required",
        "quota",
        "exceeded your current quota",
        "billing",
        '"402"',
    ]
    return any(p in txt for p in patterns)


def _transcribe_audio_openrouter_once(audio_bytes, audio_format="wav"):
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


def _transcribe_audio_google_free(audio_bytes):
    try:
        import speech_recognition as sr
    except Exception:
        return (
            None,
            "Fallback STT gratuit indisponible. Installe SpeechRecognition: pip install SpeechRecognition",
        )

    try:
        recognizer = sr.Recognizer()
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio_data = recognizer.record(source)

        # Try English first because the app is mainly for English speaking practice.
        try:
            text = recognizer.recognize_google(audio_data, language="en-US")
        except sr.UnknownValueError:
            text = recognizer.recognize_google(audio_data, language="fr-FR")
        if not text or not text.strip():
            return None, "Transcription vide (fallback gratuit)."
        return text.strip(), None
    except Exception as exc:
        return None, f"Google STT gratuit: {exc}"


def _transcribe_audio_whisper_last_resort(audio_bytes):
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return (
            None,
            "Whisper local indisponible. Installe faster-whisper: pip install faster-whisper",
        )

    @st.cache_resource(show_spinner=False)
    def _get_whisper_model_cached():
        # Lightweight default model for acceptable speed on CPU.
        return WhisperModel("small", device="cpu", compute_type="int8")

    try:
        model = _get_whisper_model_cached()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            segments, _ = model.transcribe(tmp_path, beam_size=1, vad_filter=True)
            text = " ".join(seg.text.strip() for seg in segments if seg.text).strip()
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        if not text:
            return None, "Whisper local: transcription vide."
        return text, None
    except Exception as exc:
        return None, f"Whisper local: {exc}"


def transcribe_audio_with_openrouter(
    audio_bytes, audio_format="wav", preferred_provider=None
):
    selected = preferred_provider or get_stt_mode()

    def _mark_used(provider_key):
        st.session_state["stt_last_provider_used"] = provider_key

    # Forced provider mode: use only the selected engine.
    if selected == STT_PROVIDER_OPENROUTER:
        if _openrouter_stt_in_cooldown():
            return (
                None,
                "OpenRouter STT est en pause temporaire (quota). Passe en mode Auto ou Google/Whisper.",
            )
        text, err = _transcribe_audio_openrouter_once(audio_bytes, audio_format)
        if err:
            if _is_openrouter_quota_error(err):
                _mark_openrouter_stt_unavailable(seconds=900)
            return None, f"OpenRouter: {err}"
        st.session_state.pop("openrouter_stt_unavailable_until", None)
        _mark_used(STT_PROVIDER_OPENROUTER)
        return text, None

    if selected == STT_PROVIDER_GOOGLE:
        text, err = _transcribe_audio_google_free(audio_bytes)
        if err:
            return None, f"Google gratuit: {err}"
        _mark_used(STT_PROVIDER_GOOGLE)
        return text, None

    if selected == STT_PROVIDER_WHISPER:
        text, err = _transcribe_audio_whisper_last_resort(audio_bytes)
        if err:
            return None, f"Whisper local: {err}"
        _mark_used(STT_PROVIDER_WHISPER)
        return text, None

    # Preferred path: OpenRouter when available and not in temporary quota cooldown.
    if OPENROUTER_API_KEY and not _openrouter_stt_in_cooldown():
        text, err = _transcribe_audio_openrouter_once(audio_bytes, audio_format)
        if not err:
            # OpenRouter works again; clear any previous cooldown marker.
            st.session_state.pop("openrouter_stt_unavailable_until", None)
            _mark_used(STT_PROVIDER_OPENROUTER)
            return text, None

        # If credits/quota are exhausted, avoid hammering OpenRouter for a while.
        if _is_openrouter_quota_error(err):
            _mark_openrouter_stt_unavailable(seconds=900)

        # Fallback order requested by user: Google free first, Whisper last.
        google_text, google_err = _transcribe_audio_google_free(audio_bytes)
        if not google_err:
            _mark_used(STT_PROVIDER_GOOGLE)
            return google_text, None

        whisper_text, whisper_err = _transcribe_audio_whisper_last_resort(audio_bytes)
        if not whisper_err:
            _mark_used(STT_PROVIDER_WHISPER)
            return whisper_text, None

        return (
            None,
            f"OpenRouter: {err} | Google gratuit: {google_err} | Whisper local: {whisper_err}",
        )

    # No key or temporary cooldown: Google free first, Whisper local last.
    google_text, google_err = _transcribe_audio_google_free(audio_bytes)
    if not google_err:
        _mark_used(STT_PROVIDER_GOOGLE)
        return google_text, None

    whisper_text, whisper_err = _transcribe_audio_whisper_last_resort(audio_bytes)
    if not whisper_err:
        _mark_used(STT_PROVIDER_WHISPER)
        return whisper_text, None

    if not OPENROUTER_API_KEY:
        return (
            None,
            f"OPENROUTER indisponible + Google gratuit: {google_err} + Whisper local: {whisper_err}",
        )
    return (
        None,
        f"OpenRouter temporairement indisponible + Google gratuit: {google_err} + Whisper local: {whisper_err}",
    )


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


def _stream_tts_once(
    text, model, voice, requested_format, tone_hint=None, language_hint=None
):
    max_retries = 3
    last_conn_err = None
    # Build system prompt — add tone/emotion guidance when available
    base_system = (
        "You are a multilingual text-to-speech narrator. "
        "If the text is primarily in French, use a natural native French pronunciation. "
        "If the text is primarily in English, use a natural American accent. "
        "Your only job is to read the text provided by the user EXACTLY as written, "
        "word for word. Do NOT respond to the content, do NOT add commentary, "
        "do NOT answer questions in the text. "
        "NEVER read speaker names, labels like 'A:' or 'B:', or character names followed by colons. "
        "NEVER read stage directions such as (laughs), [sighs], *whispers* or similar annotations. "
        "Read only the actual spoken words."
    )
    if language_hint == "fr":
        base_system += (
            " For this request, the text is written in FRENCH."
            " You MUST read it aloud in French with native French pronunciation."
            " Do NOT translate any part of it into English."
            " Do NOT answer or respond to questions contained in the text."
            " Just read every word in French exactly as written."
        )
    elif language_hint == "en":
        base_system += (
            " For this request, the text is written in ENGLISH."
            " You MUST read it aloud in English with a natural American accent."
            " Do NOT translate any part of it into French."
            " Do NOT answer or respond to questions contained in the text."
            " Just read every word in English exactly as written."
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
                            "content": (
                                (
                                    f"Read this {'French' if language_hint == 'fr' else 'English'}"
                                    f" text aloud VERBATIM. This is a script to narrate, NOT a question to answer."
                                    f" Do NOT translate or respond to it:\n\n{text}"
                                )
                                if language_hint
                                else f"Read this text aloud exactly as written:\n\n{text}"
                            ),
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


def text_to_speech_openrouter(
    text,
    voice=TTS_VOICE,
    audio_format=TTS_AUDIO_FORMAT,
    tone_hint=None,
    language_hint=None,
):
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
                language_hint=language_hint,
            )
            if not err:
                return audio_bytes, mime_type, None
            attempts.append(err)

    if attempts:
        # Keep message concise while still showing the latest provider feedback.
        return None, None, " | ".join(attempts[-3:])
    return None, None, "Aucune tentative TTS n'a pu etre executee."


# ── ElevenLabs TTS engine ────────────────────────────────────────────────────


def _elevenlabs_quota_ok():
    """Check remaining ElevenLabs character quota. Returns (ok, message)."""
    if not ELEVENLABS_API_KEY:
        return False, "Cle API ElevenLabs manquante."
    try:
        resp = requests.get(
            f"{ELEVENLABS_BASE_URL}/user/subscription",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            timeout=10,
        )
        if resp.status_code != 200:
            return (
                False,
                f"Erreur ElevenLabs API ({resp.status_code}): {resp.text[:200]}",
            )
        data = resp.json()
        remaining = data.get("character_limit", 0) - data.get("character_count", 0)
        if remaining <= 0:
            return False, (
                "Tokens ElevenLabs epuises ! "
                f"Limite: {data.get('character_limit', '?')} caracteres, "
                f"utilises: {data.get('character_count', '?')}. "
                "Repassez en TTS par defaut ou attendez le renouvellement."
            )
        return True, f"ElevenLabs: {remaining:,} caracteres restants."
    except Exception as exc:
        return False, f"Impossible de verifier le quota ElevenLabs: {exc}"


def text_to_speech_elevenlabs(text, voice_id=None, language_hint=None):
    """Generate speech using ElevenLabs API. Returns (audio_bytes, mime_type, error)."""
    if not ELEVENLABS_API_KEY:
        return None, None, "Cle API ElevenLabs manquante."

    ok, msg = _elevenlabs_quota_ok()
    if not ok:
        st.warning(msg)
        return None, None, msg

    if voice_id is None:
        voice_id = list(ELEVENLABS_VOICES.values())[0]  # Rachel par defaut

    payload = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }
    if language_hint:
        payload["language_code"] = language_hint

    try:
        resp = requests.post(
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json=payload,
            timeout=120,
        )
        if resp.status_code == 401:
            return None, None, "Cle API ElevenLabs invalide."
        if resp.status_code == 429:
            msg = "Tokens ElevenLabs epuises ! Repassez en TTS par defaut."
            st.warning(msg)
            return None, None, msg
        if resp.status_code != 200:
            return (
                None,
                None,
                f"Erreur ElevenLabs ({resp.status_code}): {resp.text[:200]}",
            )
        return resp.content, "audio/mpeg", None
    except Exception as exc:
        return None, None, f"Erreur ElevenLabs: {exc}"


def generate_dual_voice_elevenlabs(
    dialogue_text, voice_a_id, voice_b_id, language_hint=None
):
    """Generate dialogue audio using ElevenLabs with two voices."""
    turns = parse_dialogue_to_turns(dialogue_text)
    if not turns:
        sub_chunks = split_text_for_tts(dialogue_text, max_chars=2000)
        audio_parts = []
        for chunk in sub_chunks:
            ab, mime, err = text_to_speech_elevenlabs(
                chunk, voice_id=voice_a_id, language_hint=language_hint
            )
            if err:
                return None, None, err
            audio_parts.append(ab)
        if not audio_parts:
            return None, None, "Aucun audio genere."
        return b"".join(audio_parts), "audio/mpeg", None

    audio_parts = []
    for turn in turns:
        vid = voice_a_id if turn["speaker"] == "A" else voice_b_id
        sub_chunks = split_text_for_tts(turn["text"], max_chars=2000)
        for chunk in sub_chunks:
            ab, mime, err = text_to_speech_elevenlabs(
                chunk, voice_id=vid, language_hint=language_hint
            )
            if err:
                return None, None, f"Erreur voix {turn['speaker']}: {err}"
            audio_parts.append(ab)

    if not audio_parts:
        return None, None, "Aucun audio genere."
    return b"".join(audio_parts), "audio/mpeg", None


def get_tts_engine():
    """Return current TTS engine choice from session state."""
    return st.session_state.get("tts_engine", "default")


def tts_smart(
    text, voice=TTS_VOICE, voice_elevenlabs_id=None, tone_hint=None, language_hint=None
):
    """Unified TTS: routes to ElevenLabs or default based on session choice."""
    engine = get_tts_engine()
    if engine == "elevenlabs":
        return text_to_speech_elevenlabs(
            text, voice_id=voice_elevenlabs_id, language_hint=language_hint
        )
    return text_to_speech_openrouter(
        text, voice=voice, tone_hint=tone_hint, language_hint=language_hint
    )


def dual_voice_tts_smart(
    dialogue_text,
    voice_a,
    voice_b,
    el_voice_a=None,
    el_voice_b=None,
    language_hint=None,
):
    """Unified dual-voice TTS: routes to ElevenLabs or default."""
    engine = get_tts_engine()
    if engine == "elevenlabs":
        return generate_dual_voice_elevenlabs(
            dialogue_text, el_voice_a, el_voice_b, language_hint=language_hint
        )
    return generate_dual_voice_tts(dialogue_text, voice_a, voice_b)


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


def generate_dual_voice_tts(dialogue_text, voice_a, voice_b, language_hint=None):
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
        try:
            return concatenate_wav_bytes(wav_parts), "audio/wav", None
        except Exception as exc:
            return None, None, f"Erreur concatenation audio (mono): {exc}"

    wav_parts = []
    for turn in turns:
        voice = voice_a if turn["speaker"] == "A" else voice_b
        tone = turn.get("tone")
        # Split long individual turns — keeps speaker context intact
        sub_chunks = split_text_for_tts(turn["text"], max_chars=1200)
        for chunk in sub_chunks:
            audio_bytes, _, err = text_to_speech_openrouter(
                chunk, voice=voice, tone_hint=tone
            )
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
