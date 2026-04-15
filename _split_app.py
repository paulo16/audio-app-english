#!/usr/bin/env python3
"""
Split app.py into organized modules and pages.

Produces:
  modules/__init__.py         - empty
  modules/config.py           - constants, API keys, env config
  modules/utils.py            - utility helpers (dates, slugify, audio player, json)
  modules/profiles.py         - user profile CRUD
  modules/ai_client.py        - OpenRouter API, TTS, STT, audio utils
  modules/lessons.py          - lesson packs, variations, flashcards, catalog
  modules/shadowing.py        - shadowing/pronunciation practice
  modules/sessions.py         - conversation sessions, translation drills, AI reply
  modules/podcasts.py         - podcast data & generation
  modules/stories.py          - story data & generation
  modules/ai_lessons.py       - AI lesson data & generation
  modules/vocabulary.py       - vocabulary/SRS/flashcards
  modules/immersion.py        - natural English constants & data helpers
  modules/real_english.py     - real English series constants & data helpers

  pages/__init__.py
  pages/ai_lessons_page.py
  pages/home_page.py
  pages/lessons_page.py
  pages/shadowing_page.py
  pages/stories_page.py
  pages/playlist_page.py
  pages/practice_page.py
  pages/vocabulary_page.py
  pages/history_page.py
  pages/podcast_page.py
  pages/natural_english_page.py
  pages/real_english_page.py

  app.py is rewritten as a thin entry point (original backed up as app_original.py)
"""
import os
import shutil
from collections import defaultdict

SRC = "app.py"
BACKUP = "app_original.py"

with open(SRC, "r", encoding="utf-8") as f:
    lines = f.readlines()

total = len(lines)
print(f"Source: {SRC}  ({total} lines)")

# ─────────────────────────────────────────────────────────────────────────────
# SECTION BOUNDARIES
# Each tuple: (first_line_1based, target_module)
# Content from boundary[i] up to (but not including) boundary[i+1] goes to
# target_module[i].  Use '_skip' to drop lines (e.g. duplicate definitions).
# ─────────────────────────────────────────────────────────────────────────────
BOUNDARIES = [
    # ── Config & constants ─────────────────────────────────────────────────
    (1, "modules/config"),
    # ── Core utilities (ensure_directories, time helpers, slugify) ─────────
    (511, "modules/utils"),
    # ── Profile management ─────────────────────────────────────────────────
    (563, "modules/profiles"),
    # ── AI client: OpenRouter, TTS (openrouter + ElevenLabs), STT, audio ───
    (748, "modules/ai_client"),
    # ── More utils: _audio_player_with_repeat, extract_json_from_text ───────
    (1362, "modules/utils"),
    # ── Lesson packs, variations, flashcards ──────────────────────────────
    (1465, "modules/lessons"),
    # ── Shadowing / pronunciation practice ────────────────────────────────
    (1929, "modules/shadowing"),
    # ── Lesson catalog helpers (theme labels, practice catalog) ───────────
    (2663, "modules/lessons"),
    # ── Conversation sessions: translation drills, AI reply, evaluation ───
    (2889, "modules/sessions"),
    # ── Podcast data & generation ─────────────────────────────────────────
    (3728, "modules/podcasts"),
    # ── More utils: save_audio_bytes, ext_from_mime, ISO date helpers ─────
    (3825, "modules/utils"),
    # ── Sessions continued: get_elapsed, get_ai_reply, evaluate_session ───
    (3869, "modules/sessions"),
    # ── AI lessons data & generation ──────────────────────────────────────
    (4419, "modules/ai_lessons"),
    # ── Pages ─────────────────────────────────────────────────────────────
    (4625, "pages/ai_lessons_page"),
    (4984, "pages/home_page"),
    (5034, "pages/lessons_page"),
    (5509, "pages/shadowing_page"),
    # ── Story data (persistence) ──────────────────────────────────────────
    (5905, "modules/stories"),
    # Skip the duplicate concatenate_wav_bytes definition (identical to ai_client)
    (5961, "_skip"),
    # ── Story generation & audio player ───────────────────────────────────
    (5980, "modules/stories"),
    # ── Story / playlist pages ────────────────────────────────────────────
    (6203, "pages/stories_page"),
    (6459, "pages/playlist_page"),
    (6552, "pages/practice_page"),
    # ── Vocabulary / SRS ──────────────────────────────────────────────────
    (7263, "modules/vocabulary"),
    # ── Pages: vocabulary, history, podcast ───────────────────────────────
    (7540, "pages/vocabulary_page"),
    (8120, "pages/history_page"),
    (8151, "pages/podcast_page"),
    # ── Natural-English constants (CONNECTED_SPEECH_RULES etc.) + helpers ─
    (8369, "modules/immersion"),
    # ── Natural English page ──────────────────────────────────────────────
    (9519, "pages/natural_english_page"),
    # ── Real-English series constants + helpers ───────────────────────────
    (11049, "modules/real_english"),
    # ── Real English page ─────────────────────────────────────────────────
    (11358, "pages/real_english_page"),
    # ── main() lives in new app.py — skip here ────────────────────────────
    (12145, "_skip"),
]

# Sort (should already be sorted, but make sure)
BOUNDARIES.sort(key=lambda x: x[0])

# ─────────────────────────────────────────────────────────────────────────────
# Build content map
# ─────────────────────────────────────────────────────────────────────────────
module_content = defaultdict(list)
for i, (start, module) in enumerate(BOUNDARIES):
    end = BOUNDARIES[i + 1][0] - 1 if i + 1 < len(BOUNDARIES) else total
    if module == "_skip":
        continue
    chunk = lines[start - 1 : end]  # 0-indexed
    module_content[module].extend(chunk)

# ─────────────────────────────────────────────────────────────────────────────
# Per-module import headers
# config.py keeps the original imports (lines 1-510 of app.py).
# All other modules get a header prepended.
# ─────────────────────────────────────────────────────────────────────────────

_STDLIB_FULL = """\
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
"""

_STREAMLIT = """\
import requests
import streamlit as st
import streamlit.components.v1 as st_components
from streamlit_autorefresh import st_autorefresh
"""

_CONFIG_STAR = "from modules.config import *\n"

# fmt: off
HEADERS = {
    "modules/config": None,  # keep original content as-is

    "modules/utils": (
        _STDLIB_FULL
        + _STREAMLIT
        + _CONFIG_STAR
    ),

    "modules/profiles": (
        "import json\n"
        "import os\n"
        "import uuid\n"
        "from datetime import timezone\n"
        "import streamlit as st\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso, slugify\n"
    ),

    "modules/ai_client": (
        "import base64\n"
        "import io\n"
        "import json\n"
        "import os\n"
        "import re\n"
        "import wave\n"
        "from datetime import datetime\n"
        "import requests\n"
        "import streamlit as st\n"
        + _CONFIG_STAR
    ),

    "modules/lessons": (
        "import json\n"
        "import os\n"
        "import re\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso, slugify, extract_json_from_text\n"
        + "from modules.ai_client import (\n"
        "    openrouter_chat,\n"
        "    tts_smart,\n"
        "    dual_voice_tts_smart,\n"
        "    generate_dual_voice_tts,\n"
        "    concatenate_wav_bytes,\n"
        ")\n"
        + "# Imported lazily to avoid circular: from modules.vocabulary import load_vocab, save_vocab\n"
    ),

    "modules/shadowing": (
        "import io\n"
        "import json\n"
        "import os\n"
        "import wave\n"
        "import streamlit as st\n"
        "from datetime import date, datetime, timedelta, timezone\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso, slugify\n"
        + "from modules.ai_client import openrouter_chat, tts_smart, concatenate_wav_bytes\n"
    ),

    "modules/sessions": (
        "import json\n"
        "import os\n"
        "import re\n"
        "import uuid\n"
        "import requests\n"
        "import streamlit as st\n"
        "from datetime import datetime, timedelta, timezone\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso, slugify, _parse_iso, _seconds_since_iso, _seconds_between_iso, ext_from_mime, save_audio_bytes\n"
        + "from modules.profiles import load_profiles\n"
        + "from modules.ai_client import openrouter_chat, openrouter_headers\n"
        + "from modules.lessons import load_lesson_pack, load_quick_variations\n"
    ),

    "modules/podcasts": (
        "import json\n"
        "import os\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso\n"
        + "from modules.ai_client import openrouter_chat, dual_voice_tts_smart, generate_dual_voice_tts\n"
    ),

    "modules/stories": (
        "import io\n"
        "import json\n"
        "import os\n"
        "import uuid\n"
        "import requests\n"
        "import streamlit as st\n"
        "import streamlit.components.v1 as st_components\n"
        + _CONFIG_STAR
        + "from modules.ai_client import openrouter_chat, tts_smart, concatenate_wav_bytes\n"
    ),

    "modules/ai_lessons": (
        "import json\n"
        "import os\n"
        "import streamlit as st\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso\n"
        + "from modules.ai_client import openrouter_chat, tts_smart\n"
        + "from modules.sessions import load_all_sessions\n"
    ),

    "modules/vocabulary": (
        "import json\n"
        "import os\n"
        "import streamlit as st\n"
        "from datetime import date, datetime, timedelta, timezone\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso\n"
        + "from modules.ai_client import openrouter_chat, tts_smart\n"
    ),

    "modules/immersion": (
        "import json\n"
        "import os\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso\n"
    ),

    "modules/real_english": (
        "import json\n"
        "import os\n"
        "import streamlit as st\n"
        "from datetime import datetime, timezone\n"
        + _CONFIG_STAR
        + "from modules.utils import now_iso\n"
        + "from modules.ai_client import openrouter_chat, tts_smart\n"
        + "from modules.vocabulary import load_vocab, save_vocab\n"
    ),
}

# Page header: import everything from all modules so render functions just work
_PAGE_HEADER = (
    "import io\n"
    "import json\n"
    "import os\n"
    "import re\n"
    "import uuid\n"
    "import requests\n"
    "import streamlit as st\n"
    "import streamlit.components.v1 as st_components\n"
    "from datetime import date, datetime, timedelta, timezone\n"
    "from streamlit_autorefresh import st_autorefresh\n"
    + _CONFIG_STAR
    + "from modules.utils import *\n"
    + "from modules.profiles import *\n"
    + "from modules.ai_client import *\n"
    + "from modules.lessons import *\n"
    + "from modules.shadowing import *\n"
    + "from modules.sessions import *\n"
    + "from modules.podcasts import *\n"
    + "from modules.stories import *\n"
    + "from modules.ai_lessons import *\n"
    + "from modules.vocabulary import *\n"
    + "from modules.immersion import *\n"
    + "from modules.real_english import *\n"
)

for key in [
    "pages/ai_lessons_page",
    "pages/home_page",
    "pages/lessons_page",
    "pages/shadowing_page",
    "pages/stories_page",
    "pages/playlist_page",
    "pages/practice_page",
    "pages/vocabulary_page",
    "pages/history_page",
    "pages/podcast_page",
    "pages/natural_english_page",
    "pages/real_english_page",
]:
    HEADERS[key] = _PAGE_HEADER
# fmt: on

# ─────────────────────────────────────────────────────────────────────────────
# Write files
# ─────────────────────────────────────────────────────────────────────────────
os.makedirs("modules", exist_ok=True)
os.makedirs("pages", exist_ok=True)

# Empty __init__ files
for init in ["modules/__init__.py", "pages/__init__.py"]:
    if not os.path.exists(init):
        open(init, "w").close()
        print(f"  Created {init}")

for module, content in module_content.items():
    out_path = module + ".py"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    # Strip trailing blank lines then add final newline
    while content and not content[-1].strip():
        content.pop()
    content.append("\n")

    header = HEADERS.get(module)

    with open(out_path, "w", encoding="utf-8") as f:
        if header:
            f.write(header)
            f.write("\n")
        f.writelines(content)

    raw_lines = len(content)
    print(f"  {out_path}  ({raw_lines} body lines)")

# ─────────────────────────────────────────────────────────────────────────────
# Fix: auto_add_lesson_flashcards circular import
# It calls load_vocab / save_vocab — use a local lazy import inside the function
# ─────────────────────────────────────────────────────────────────────────────
lessons_path = "modules/lessons.py"
with open(lessons_path, "r", encoding="utf-8") as f:
    txt = f.read()

# Replace direct calls to load_vocab/save_vocab with lazy imports inside the function
if "def auto_add_lesson_flashcards(" in txt:
    # Add lazy imports at the top of the function body
    txt = txt.replace(
        "def auto_add_lesson_flashcards(",
        "def auto_add_lesson_flashcards(",
    )
    # Insert lazy imports right after the first line of auto_add_lesson_flashcards
    # We do this by patching the known call sites inside the function
    txt = txt.replace(
        "    entries = load_vocab(profile_id)",
        "    from modules.vocabulary import load_vocab, save_vocab  # lazy – avoids circular import\n    entries = load_vocab(profile_id)",
        1,  # only first occurrence
    )
    with open(lessons_path, "w", encoding="utf-8") as f:
        f.write(txt)
    print("  Patched lazy import in modules/lessons.py (auto_add_lesson_flashcards)")

# ─────────────────────────────────────────────────────────────────────────────
# Remove duplicate concatenate_wav_bytes comment from modules/stories.py
# (we already skipped lines 5961-5979; just remove the orphaned comment if any)
# ─────────────────────────────────────────────────────────────────────────────
stories_path = "modules/stories.py"
with open(stories_path, "r", encoding="utf-8") as f:
    txt = f.read()
if "# \u2500\u2500 Story audio generation" in txt:
    txt = txt.replace("# \u2500\u2500 Story audio generation \u2500" * 1, "")
with open(stories_path, "w", encoding="utf-8") as f:
    f.write(txt)

# ─────────────────────────────────────────────────────────────────────────────
# Back up original app.py and write new thin entry point
# ─────────────────────────────────────────────────────────────────────────────
if not os.path.exists(BACKUP):
    shutil.copy2(SRC, BACKUP)
    print(f"\n  Backed up original → {BACKUP}")

# Extract main() body from original (lines 12145-end)
main_start = 12145  # def main():
main_lines = lines[main_start - 1 :]  # 0-indexed

new_app = (
    '"""English Audio Coach — entry point.\n\n'
    "All logic lives in modules/ and pages/.\n"
    '"""\n'
    "import streamlit as st\n"
    "from modules.config import *\n"
    "from modules.utils import ensure_directories\n"
    "from modules.profiles import load_profiles, get_active_profile, create_or_update_profile\n"
    "from modules.ai_client import get_tts_engine, _elevenlabs_quota_ok\n"
    "from pages.home_page import render_home\n"
    "from pages.lessons_page import render_lessons_page\n"
    "from pages.ai_lessons_page import render_ai_lessons_page\n"
    "from pages.natural_english_page import render_natural_english_page\n"
    "from pages.real_english_page import render_real_english_page\n"
    "from pages.stories_page import render_stories_page\n"
    "from pages.playlist_page import render_playlist_page\n"
    "from pages.podcast_page import render_podcast_page\n"
    "from pages.practice_page import render_practice_page, initialize_state\n"
    "from pages.shadowing_page import render_shadowing_daily_page\n"
    "from pages.vocabulary_page import render_vocabulary_page\n"
    "from pages.history_page import render_history_page\n"
    "\n\n"
)

new_app += "".join(main_lines)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(new_app)

print(f"\n  Rewrote {SRC} (thin entry point, {len(main_lines)} lines from main())")
print("\nDone! Run the app and fix any remaining import errors.")
