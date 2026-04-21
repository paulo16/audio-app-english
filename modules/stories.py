import io
import json
import os
import uuid

import requests
import streamlit as st

from modules.ai_client import (
    concatenate_wav_bytes,
    openrouter_chat,
    split_text_for_tts,
    text_to_speech_openrouter,
    tts_smart,
)
from modules.config import *
from modules.profiles import _profile_storage_slug
from modules.utils import extract_json_from_text, now_iso


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
function updateMS(label){{
  if('mediaSession' in navigator){{
    const au=document.getElementById('au');
    navigator.mediaSession.metadata=new MediaMetadata({{title:label,artist:'English Audio',album:'{title_line}'}});
    navigator.mediaSession.setActionHandler('play',()=>au.play());
    navigator.mediaSession.setActionHandler('pause',()=>au.pause());
    navigator.mediaSession.setActionHandler('nexttrack',next);
    navigator.mediaSession.setActionHandler('previoustrack',prev);
  }}
}}
function play(idx){{
  ci=idx;const au=document.getElementById('au');
  au.src=T[idx].src;
  document.getElementById('tit').textContent=T[idx].label;
  document.getElementById('ctr').textContent=(idx+1)+' / '+T.length;
  au.play();renderList();updateMS(T[idx].label);
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
    import warnings

    import streamlit.components.v1 as _cv1

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        _cv1.html(player_html, height=height)


# ── Stories page ──────────────────────────────────────────────────────────────
