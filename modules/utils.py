import base64
import hashlib
import io
import json
import os
import re
import uuid
import wave
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from modules.config import *


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


def _audio_player_with_repeat(audio_bytes, mime_type="audio/wav", key="audio_rpt"):
    """Render an HTML5 audio player with repeat (loop / 20x) controls."""
    b64 = base64.b64encode(audio_bytes).decode()
    uid = key.replace("-", "_")
    html = f"""
    <div id="ap_{uid}">
      <audio id="aud_{uid}" controls style="width:100%">
        <source src="data:{mime_type};base64,{b64}" type="{mime_type}">
      </audio>
      <div style="margin-top:6px;display:flex;gap:8px;align-items:center;">
        <button id="btn_loop_{uid}" onclick="toggleLoop_{uid}()"
          style="padding:4px 12px;border:1px solid #555;border-radius:6px;
                 background:#222;color:#eee;cursor:pointer;font-size:13px;">
          🔁 Boucle infinie: OFF
        </button>
        <button id="btn_20_{uid}" onclick="play20_{uid}()"
          style="padding:4px 12px;border:1px solid #555;border-radius:6px;
                 background:#222;color:#eee;cursor:pointer;font-size:13px;">
          🔂 Repeter 20x
        </button>
        <span id="cnt_{uid}" style="color:#aaa;font-size:12px;"></span>
      </div>
    </div>
    <script>
    (function() {{
      var a = document.getElementById("aud_{uid}");
      var looping = false;
      var countMode = false;
      var maxCount = 0;
      var played = 0;

      window.toggleLoop_{uid} = function() {{
        looping = !looping;
        countMode = false;
        a.loop = looping;
        document.getElementById("btn_loop_{uid}").innerText =
          looping ? "🔁 Boucle infinie: ON" : "🔁 Boucle infinie: OFF";
        document.getElementById("btn_loop_{uid}").style.background =
          looping ? "#1a6b1a" : "#222";
        document.getElementById("cnt_{uid}").innerText = "";
        if (looping) a.play();
      }};

      window.play20_{uid} = function() {{
        looping = false;
        a.loop = false;
        document.getElementById("btn_loop_{uid}").innerText = "🔁 Boucle infinie: OFF";
        document.getElementById("btn_loop_{uid}").style.background = "#222";
        countMode = true;
        maxCount = 20;
        played = 0;
        document.getElementById("cnt_{uid}").innerText = "0 / 20";
        a.currentTime = 0;
        a.play();
      }};

      a.addEventListener("ended", function() {{
        if (countMode) {{
          played++;
          document.getElementById("cnt_{uid}").innerText = played + " / " + maxCount;
          if (played < maxCount) {{
            a.currentTime = 0;
            a.play();
          }} else {{
            countMode = false;
            document.getElementById("cnt_{uid}").innerText = "20/20 ✅";
          }}
        }}
      }});
    }})();
    </script>
    """
    import streamlit.components.v1 as components

    components.html(html, height=110)


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
