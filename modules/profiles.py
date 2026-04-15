import json
import os
import uuid
from datetime import timezone
import streamlit as st
from modules.config import *
from modules.utils import now_iso, slugify

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

