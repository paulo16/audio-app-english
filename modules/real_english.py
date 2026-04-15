import json
import os
import streamlit as st
from datetime import datetime, timezone
from modules.config import *
from modules.utils import now_iso
from modules.ai_client import openrouter_chat, tts_smart
from modules.vocabulary import load_vocab, save_vocab
from modules.profiles import _profile_storage_slug

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
    return os.path.join(
        REAL_ENGLISH_DIR, f"progress-{_profile_storage_slug(profile_id)}.json"
    )


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
    with open(
        _real_english_lesson_path(profile_id, lesson_id), "w", encoding="utf-8"
    ) as f:
        json.dump(
            {"id": lesson_id, "saved": now_iso(), **data},
            f,
            ensure_ascii=False,
            indent=2,
        )


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


def _mark_real_english_lesson_completed(profile_id, progress, lesson_id, lesson):
    completed = progress.setdefault("completed_lessons", [])
    if lesson_id in completed:
        return {"already_completed": True, "added_flashcards": 0}

    completed.append(lesson_id)
    progress.setdefault("lesson_history", []).append(
        {
            "action": "completed",
            "lesson_id": lesson_id,
            "series": lesson.get("series", ""),
            "episode": lesson.get("episode", ""),
            "level": lesson.get("level", ""),
            "date": now_iso(),
        }
    )
    _save_real_english_progress(profile_id, progress)

    vocab_items = lesson.get("vocabulary", [])
    added = 0
    if vocab_items:
        vocab_entries = load_vocab(profile_id=profile_id)
        existing_terms = {
            e.get("term", "").lower() for e in vocab_entries if isinstance(e, dict)
        }
        for vocab in vocab_items[:LESSON_FLASHCARD_LIMIT]:
            expr = str(vocab.get("expression", "")).strip()
            if not expr or expr.lower() in existing_terms:
                continue
            vocab_entries.append(
                {
                    "id": str(uuid.uuid4())[:8],
                    "term": expr,
                    "translation": vocab.get("french", ""),
                    "part_of_speech": vocab.get("type", "chunk"),
                    "explanation": (
                        f"Forme complete: {vocab.get('full_form', '')}. "
                        f"Construisez une phrase avec '{expr}'."
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
            )
            existing_terms.add(expr.lower())
            added += 1

        if added > 0:
            save_vocab(vocab_entries, profile_id=profile_id)

    return {"already_completed": False, "added_flashcards": added}

