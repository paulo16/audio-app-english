import json
import os

from modules.config import *
from modules.utils import now_iso
from modules.profiles import _profile_storage_slug

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
