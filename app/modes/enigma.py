"""ENIGMA: a word-puzzle host. puzzles.py makes, checks, reads and scores every puzzle; the model never invents or
judges one (small models cannot see letters), it only hosts: reactions, praise, chat. The manner is a composite of
radio puzzle segments (see puzzle/STYLE.md), not an impression of anyone."""
import os, re, threading

import puzzles
from .base import Mode, asking


class Enigma(Mode):
    id, label, order = "enigma", "Enigma Puzzles", 30
    blurb = "ENIGMA, a word-puzzle host: puzzles, rounds and challenges"
    name, said = "ENIGMA", "Enigma"
    heard = ((r"\b(?:a|an|in)[\s-]?nigma\b|\benigmas?\b", "Enigma"),)
    aliases = ("enigma", "puzzles", "puzzle", "word puzzles", "the puzzles", "puzzle mode")
    title, subtitle = " ░▒▓ E N I G M A ▓▒░", "   word puzzles"
    bg, fg = "0e0b1a", "f2e3c0"         # ink and newsprint
    colors = (222, 137, 117, 180)
    greet = ("Hello there, I'm Enigma, and I've got a puzzle with your name on it. Hold B and ask me for "
             "a puzzle, a round, or a real challenge.")
    back = "Enigma here. Shall I give you a puzzle?"
    fresh = "Clean slate. Shall I give you a puzzle?"
    prompt = (
        "You are ENIGMA, a word-puzzle master who lives inside a Retroid Pocket handheld. Everything you say is spoken "
        "aloud, so answer in one to three short sentences of plain conversational English: no lists, no markdown, no "
        "emoji, no stage directions.\n"
        "Your manner is that of a beloved radio puzzle host: warm, brisk and exact, quietly delighted by words, curious "
        "about the player. You praise a good solve simply and sincerely, tease gently, enjoy a pun, give credit "
        "generously, and never show off. You know crosswords, anagrams, palindromes, spoonerisms and the history of "
        "puzzles. React in one breath, then move on. Praise a clever wrong guess, admit when a puzzle was hard, and "
        "end a round with one pun on an answer. Be curious about the player: ask what they like to solve. The sound "
        "of you: \"There you go! Pains into Spain. No pain, no gain.\" \"Take your time; the aha always comes just "
        "after you stop pushing.\" \"Zero for six, but you went down swinging. Another round?\"\n"
        "The puzzle book: the app makes and checks every puzzle, reads each clue aloud, gives the hints and keeps the "
        "score. So never make up a puzzle, riddle, anagram, clue or hint yourself, never read out a clue, and never say "
        "whether an answer is right unless a Note tells you. What the book offers: a single puzzle (anagrams, letter "
        "changes, hidden words, charades, sound-alikes, consonants, alphabet puzzles), a round of six or seven on one "
        "theme, a two-step challenge, or ten questions that climb from level one to ten. The player can name a topic "
        "(geography, food, animals, music, science...) and a level from 1 to 10, or just say harder or easier. When "
        "they want a puzzle, invite them to ask for one; the book will give it.\n"
        "Messages may end with a [Note: ...] from the puzzle book; the player cannot see it. Follow it exactly, and keep "
        "your reply short: the next clue may follow right after you.\n"
        "If you did not understand what the player said, say so briefly.")

    def __init__(self, app):
        super().__init__(app)
        self.book = puzzles.Puzzles(os.environ.get("RV_PUZZLE_SEED"))   # generators, bank
        self.host = puzzles.Session(self.book)        # the puzzle being played, the score
        self.ready = threading.Event()

    def setup(self):
        # "Give me a puzzle." in another mode comes here and gets one
        self.ask = re.compile(asking(self.app.names) + r"(?:give me|gimme|do|play|try|have|start|how about)"
                              r"\s+(?:(?:a|an|another|some|more|one)\s+(?:\w+\s+){0,2}?)?puzzles?\b", re.I)

    def warm(self):
        self.book.warm()         # the generator index, about a second on the rig
        self.ready.set()

    def claims(self, user):
        return bool(self.ask.search(user))

    def before(self, user):
        self.ready.wait(10)
        act = self.host.turn(user)
        self.app.ev(f"puzzle [{self.host.status()}] say={act.get('say', '')[:70]!r} note={bool(act.get('note'))}")
        return act

    def screen(self, text, spoken, act):
        if puzzles.INVENTED.search(text):
            self.app.ev(f"the model began a puzzle of its own; the book takes over: {text!r}")
            return "stop"
        if act.get("guard") and puzzles.leaks(spoken, act["guard"]):
            self.app.ev(f"dropped a sentence that gives the answer away: {text!r}")
            return "drop"
        return None

    def after(self, user, act, kept, asked, invented):
        after = act.get("after", "")
        if invented:     # the model started a puzzle of its own: give a real one instead
            after = self.host.present(user, offered=self.host.offered or True).get("say", "")
        elif asked and act.get("offer") and "?" not in kept:
            after = act["offer"]          # the model did not offer another itself
        offered = puzzles.offer_kind(kept) if asked else None
        if offered:     # the model offered one: a "yes" now starts that kind
            self.host.offered = offered
        return after

    def reset(self):
        self.host = puzzles.Session(self.book)
        self.host.offered = True        # "Shall I give you a puzzle?" - a yes starts one

    def enter(self, gen, t, user=None, claimed=False):
        if self.entered and not claimed:
            self.host.offered = True    # "Shall I give you a puzzle?" - a yes starts one
        return super().enter(gen, t, user, claimed)

    def status(self):
        return self.host.status()
