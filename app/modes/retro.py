"""Retro Gaming: TRIXY, a retro computer companion, with a bank of checked retro-gaming trivia.

The app, not the model, picks quiz questions and holds the answers, so a quiz never rests on a fact the model
made up. A request attaches a hidden card to the player's message; the player's next turn gets a hidden grading
note with the true answer. A question that matches a card gets the card's fact as a note."""
import json, os, random, re

from .base import Mode

TRIVIA_PATH = os.environ.get("RV_TRIVIA", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                         "trivia.json"))
TRIVIA_ASK = re.compile(r"\b(trivia|quiz|another (one|question)|next (one|question)|ask me (a|another|one)|"
                        r"(hard|harder|tough|tougher|difficult) (one|question))\b", re.I)
STOP = set("the a an of in on to for and or is was what which who whom how did does do year game games video "
           "all time your you me my it its that this with from by first original called name named".split())
QUESTION = re.compile(r"\s*(who|what|when|where|why|how|which|whose|can you|could you|do you|did you|have you|"
                      r"tell me|name)\b", re.I)


def keywords(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP}


def lookup_fact(bank, text):
    """Bank entry that covers most of the player's content words, sharing at least one name or number
    (tiny local retrieval), or None."""
    words, best, score = keywords(text), None, 0.0
    if not words:
        return None
    for q in bank:
        k = keywords(q["q"])
        names = {w.lower() for w in re.findall(r"\b(?:[A-Z][a-zA-Z0-9]+|\d{4})\b", q["q"])}
        shared = words & k
        if not shared or not (shared & names or "best" in shared):
            continue
        s = len(shared) / len(words) + 0.5 * len(shared) / len(k)   # tie-break: closest whole question
        if s > score:
            best, score = q, s
    return best if score >= 0.6 else None


def load_trivia():
    try:
        bank = json.load(open(TRIVIA_PATH))
    except (OSError, ValueError):
        return []
    random.shuffle(bank)
    return bank


class Retro(Mode):
    id, label, order = "retro", "Retro Gaming", 20
    blurb = "TRIXY, a retro gaming companion with trivia"
    name, said = "TRIXY", "Trixie"
    heard = ((r"\btri(?:xie|xi|xey|cksy|cksie|ksy|ksie)\b", "Trixy"),)
    aliases = ("retro", "retro gaming", "retro games", "gaming", "trixy", "trivia")
    title, subtitle = " ▓▒░ T R I X Y ░▒▓", "   retro gaming"
    bg, fg = "030a03", "33ff66"         # phosphor green
    colors = (46, 28, 214, 44)
    greet = "TRIXY here, ready to talk games. Hold the B button or R1 and talk to me."
    back = "TRIXY here. What are we playing?"
    fresh = "Fresh start. What's on your mind?"
    prompt = (
        "You are TRIXY, a friendly retro computer voice living inside a Retroid Pocket handheld game console. "
        "Everything you say is spoken aloud, so answer in one to three short sentences of plain conversational "
        "English: no lists, no markdown, no emoji, no stage directions. Be warm, curious and a little playful, "
        "like an 8-bit adventure companion.\n"
        "Accuracy matters. When you know a fact, state it plainly and directly, including well-known records, "
        "release years, sales leaders and who made a game. Never invent game titles, names, dates or numbers: "
        "only when you genuinely do not know, say so briefly instead of guessing. For events after your "
        "training, share what you know and mention you may be out of date.\n"
        "Trivia: only quiz the player with questions the game system gives you in a Note; never make up quiz "
        "questions yourself. Ask one at a time, and right after it write the correct answer in square brackets, "
        "like [answer: Sonic the Hedgehog]; bracketed text is never spoken.\n"
        "Messages may end with a [Note: ...] from the game system; the player cannot see it. Follow it, and "
        "trust any verified fact it gives you.\n"
        "If you did not understand what the player said, say so briefly.")

    def __init__(self, app):
        super().__init__(app)
        self.trivia, self.active = load_trivia(), None

    def before(self, user):
        """Hidden notes appended to the player's words: grade an open question, deal a new card."""
        notes = []
        asking = bool(TRIVIA_ASK.search(user)) and bool(self.trivia)
        # "Who made Choplifter?" mid-quiz is a new question, not an answer ("Is it Sega?" still is one)
        side_question = bool(QUESTION.match(user)) and not asking
        grading = self.active is not None and not side_question
        if grading:
            q = self.active
            alts = (" (also accept: " + ", ".join(q["alt"]) + ")") if q["alt"] else ""
            notes.append(f"[Note: the answer to your last trivia question is {q['a']}{alts}. Tell the player "
                         f"honestly whether they got it; if not, tell them the correct answer.]")
            self.active = None
        if not asking and not grading:
            fact = lookup_fact(self.trivia, user)
            if fact:
                notes.append(f"[Note: verified fact to use in your answer. {fact['q']} {fact['a']}.]")
                self.app.ev(f"fact note: {fact['a']}")
        if asking:
            card = self.trivia.pop(0)
            self.trivia.append(card)
            self.active = card
            notes.append(f"[Note: ask this trivia question in your own words, then add [answer: {card['a']}]. "
                         f"Question: {card['q']}]")
            self.app.ev(f"trivia card: {card['q']}")
        return {"note": " ".join(notes)} if notes else {}

    def reset(self):
        self.active = None
