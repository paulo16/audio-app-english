import io
import json
import os
import re
import uuid
import requests
import streamlit as st
import streamlit.components.v1 as st_components
from datetime import date, datetime, timedelta, timezone
from streamlit_autorefresh import st_autorefresh
from modules.config import *
from modules.utils import *
from modules.profiles import *
from modules.ai_client import *
from modules.lessons import *
from modules.shadowing import *
from modules.sessions import *
from modules.podcasts import *
from modules.stories import *
from modules.ai_lessons import *
from modules.vocabulary import *
from modules.immersion import *
from modules.real_english import *

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

