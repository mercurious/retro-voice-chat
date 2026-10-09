"""Voice Zork: Infocom's Zork I-III, run by Frotz (zgame.py). The game holds the world and writes every word of
the story; the model only turns what the player says into the game's commands, when the words are not a
command already."""
import json, os, re, threading, time

from zgame import GAMES, GameOver, ZGame
from .base import Mode, asking

GAME_DIR = os.environ.get("RV_GAME_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                      "games"))
DFROTZ = os.environ.get("RV_DFROTZ", os.path.join(GAME_DIR, "dfrotz"))
GAME_MAX_TOKENS = 60
GAME_NUM = {"1": "1", "one": "1", "i": "1", "2": "2", "two": "2", "ii": "2", "3": "3", "three": "3", "iii": "3"}
GAME_SYSTEM = (
    "You are the voice interface to {title}, an Infocom text adventure. The player speaks; you turn what they "
    "say into commands for the game's parser. It understands short imperative commands: a verb and a noun, "
    "sometimes a preposition and a second noun. Examples: north, up, enter house, open mailbox, take leaflet, "
    "read leaflet, drop sword, put coffin in case, attack troll with sword, turn on lamp, examine rug, "
    "move rug, open trap door, inventory, look, wait, again, score, save, restore.\n"
    "Rules: use the nouns the game's own text used. A sentence with several actions becomes several commands, "
    "in order. Directions are single words: north, south, east, west, northeast, northwest, southeast, "
    "southwest, up, down, in, out. \"Look around\" is look; \"what am I carrying\" is inventory; \"check "
    "the X\" is examine X; \"grab X\" or \"pick up X\" is take X. When the game asked a question, pass the "
    "player's answer through (yes, no, a name). When the player is not asking for a game action at all, "
    "return no commands.\n"
    "Reply only with JSON: {{\"commands\": [\"...\"]}}")
# Compact JSON forced from the first token. A response_format JSON schema lets Gemma 4 open a thinking block
# first (llama.cpp's gemma4 grammar allows one): on the rig that took 3 of 5 requests in one context, two of
# them used all 60 tokens and returned nothing. This grammar: 5 of 5, 5-16 tokens, 1.7-3.4 s.
CMD_GRAMMAR = r'''root ::= "{\"commands\":[" ( cmd ( "," cmd ){0,3} )? "]}"
cmd ::= "\"" [a-zA-Z0-9 ,.'-]{1,48} "\""'''
# first words of a spoken line that is already a command ("Go north.", "Open the mailbox.")
DIRECT_VERBS = set(
    "north south east west northeast northwest southeast southwest up down in out enter exit n s e w ne nw se "
    "sw u d look l examine x read take get drop put open close unlock lock turn move push pull climb go walk "
    "attack kill hit throw give eat drink inventory i wait z again g score diagnose save restore restart quit pick "
    "verbose brief superbrief light extinguish tie untie dig fill pour wave rub touch listen smell search board "
    "launch pray inflate deflate ring wind knock kick break burn cut lower raise jump swim wake yes no y "
    "odysseus ulysses echo xyzzy plugh hello".split())
NOT_DIRECT = set("i'm we let's lets should could can maybe think want what where why how who you".split())
# what the speech recognizer writes for the game's words: verb forms (British voices) and a few nouns
HEARD = {"takes": "take", "took": "take", "opened": "open", "opens": "open", "drops": "drop", "dropped": "drop",
         "puts": "put", "turns": "turn", "turned": "turn", "boy": "buoy", "pod": "pot"}


class Zork(Mode):
    id, label, order = "zork", "Voice Zork", 40
    blurb = "play Infocom's Zork one, two and three by voice"
    name, said = "ZORK", "Zork"
    heard = ((r"\bzor(?:c|g|ch|ck|ke)\b", "Zork"),)
    aliases = ("zork", "voice zork", "the game", "adventure", "text adventure")
    title, subtitle = " ▒▒ Z O R K ▒▒", "   voice adventure"
    bg, fg = "0c0800", "ffb000"         # amber terminal
    colors = (214, 94, 230, 172)
    fresh = "Game saved. Say play Zork, or Zork two or three."

    def __init__(self, app):
        super().__init__(app)
        self.game = None           # ZGame while playing
        self.lock = threading.Lock()
        self.title, self.game_system, self.game_last = "", "", ""
        self.num = app.prefs.get("zork", "1")

    def setup(self):
        ask = asking(self.app.names)
        # spoken commands must start the sentence: "Let's play Zork two." starts it, "I used to play Zork" does not
        self.start_re = re.compile(ask + r"(play|start|launch|load|begin|resume|continue)\b.{0,20}?\bzork\b"
                                         r"(?:\s*(1|2|3|one|two|three|iii|ii|i)\b)?", re.I)
        self.exit_re = re.compile(ask + r"((stop|quit|exit|leave|end|close)\b.{0,16}?\b(game|zork)\b|stop playing\b)",
                                  re.I)
        self.filler = re.compile(r"^(?:okay|ok|alright|all right|now|and|then|so|um|uh|" + "|".join(self.app.names) +
                                 r")\b[,.]?\s*", re.I)

    def available(self):
        return os.access(DFROTZ, os.X_OK)

    def claims(self, user):
        return bool(self.start_re.search(user))

    def which(self, user):
        m = user and self.start_re.search(user)
        return GAME_NUM.get((m.group(2) or "1").lower(), "1") if m else None

    def status(self):
        g = self.game        # the worker can close it while the screen is drawn
        return g.room if g else ""

    def ready_line(self, mic):
        app, g = self.app, self.game
        if not g:
            return f"{app.G}▶ VOICE ZORK{app.RST}   {app.DIM}say play Zork, Zork two or three{app.RST}"
        return f"{app.G}▶ {self.title}{app.RST}  {g.room}   {app.DIM}{g.score}{app.RST}"

    # -- switching
    def enter(self, gen, t, user=None, claimed=False):
        self.entered = True
        num = self.which(user) or self.num
        if not self.game or num != self.num:
            self.start_game(gen, num, t)
        else:
            self.prime_game()

    def leave(self):
        if self.game:
            self.leave_game(None)

    def reset(self):
        self.leave_game(None)

    def close(self):
        if self.game:
            self.leave_game(None)

    # -- the game
    def direct_command(self, text):
        """The spoken line as a game command if it already is one, else None (the LLM translates it)."""
        s = re.sub(r"\bplease\b", "", text.strip().lower())
        while self.filler.match(s):
            s = self.filler.sub("", s, count=1)
        s = re.sub(r"[,.]?\s+then\s+", ". ", s)   # ASR writes "lamp. Then take" as often as "lamp, then take"
        s = re.sub(r"\bsuper[\s-]+brief\b", "superbrief", s)   # ASR splits Zork's made-up word
        words = [HEARD.get(w, w) for w in re.findall(r"[a-z0-9']+|\.", s)]
        real = [w for w in words if w != "."]
        if not real or real[0] not in DIRECT_VERBS or len(real) > 8 or NOT_DIRECT & set(real) \
                or real[0] == "i" and len(real) > 1:
            return None
        return " ".join(words).replace(" .", ".").strip(". ")

    def start_game(self, gen, num, t):
        app = self.app
        name, title = GAMES.get(num, GAMES["1"])
        story = os.path.join(GAME_DIR, name + ".z3")
        if not os.path.exists(story) or not self.available():
            app.add("sys", f"{title} is not installed ({story}, {DFROTZ})")
            return
        if self.game:
            self.leave_game(None)
        with self.lock:
            self.game = ZGame(story, DFROTZ, os.path.join(GAME_DIR, "saves"))
        self.title, self.game_last, self.history, self.num = title, self.game.intro, [], num
        app.prefs["zork"] = num
        self.game_system = GAME_SYSTEM.format(title=title)
        app.ctx_used, app.metrics = 0, ""
        app.ev(f"game: started {title}")
        app.speak_text(gen, ZGame.speech(self.game.intro), t, "game")
        if os.path.exists(os.path.join(GAME_DIR, "saves", name + ".qzl")):
            t["pieces"] += app.speak(gen, "You have a saved game. Say restore to pick it up.", t, app.add("host", ""))
        self.prime_game()

    def leave_game(self, msg, save=True):
        """The game is saved first (Zork's own save file, "restore" brings it back)."""
        with self.lock:
            g, self.game = self.game, None
            if g and save and g.alive():
                try:
                    g.send("save")
                except GameOver:
                    pass
            if g:
                g.close()
                self.app.ev(f"game: left {self.title}")
        self.history, self.game_last = [], ""
        self.app.dirty = True
        if msg:
            self.app.speak_now(msg, self.app.add("host", ""))

    def system(self):
        return self.game_system

    def send(self, cmd):
        with self.lock:
            if not self.game:
                raise GameOver()
            return self.game.send(cmd)

    def prime_game(self):
        app, ask = self.app, f"Game:\n{self.game_last}\n\nPlayer:"
        self.history = app.fit(self.history, self.game_system, ask, GAME_MAX_TOKENS, background=True)
        app.prime([{"role": "system", "content": self.game_system}] + self.history +
                  [{"role": "user", "content": ask}], self.kv)

    def translate(self, gen, user):
        """The player's words as game commands, by the LLM ({"commands": [...]}, see CMD_GRAMMAR)."""
        app, msg = self.app, f"Game:\n{self.game_last}\n\nPlayer: {user}"
        app.reread_note(self.kv, self.game_system, self.history)
        self.history = app.fit(self.history, self.game_system, msg, GAME_MAX_TOKENS)
        msgs = [{"role": "system", "content": self.game_system}] + self.history + [{"role": "user", "content": msg}]
        r = app.complete({"messages": msgs, "temperature": 0.2, "max_tokens": GAME_MAX_TOKENS, "grammar": CMD_GRAMMAR,
                          "chat_template_kwargs": {"enable_thinking": False}}, self.kv)
        content = r["choices"][0]["message"].get("content") or ""
        app.take_timings(r.get("timings") or {}, msgs, content, self.kv)
        try:
            cmds = json.loads(content)["commands"]
        except (ValueError, KeyError, TypeError):
            cmds = []
        cmds = [re.sub(r"\s+", " ", c).strip() for c in cmds if isinstance(c, str) and re.search(r"[a-z]", c, re.I)][:4]
        app.ev(f"game: LLM {user!r} -> {cmds}")
        return cmds

    def turn(self, gen, user, t):
        app = self.app
        t["pieces"] = 0
        if not self.game:
            if self.start_re.search(user):
                self.start_game(gen, self.which(user), t)
            else:
                t["pieces"] = app.speak(gen, "Say play Zork, or Zork two or three. Or press select for another mode.",
                                        t, app.add("host", ""))
            app.wait_first_word(gen, t)
            return True
        if self.exit_re.search(user):
            self.leave_game(f"{self.title} saved. Say play Zork to pick up where you left off.")
            if app.prev and app.prev is not self:     # back to the mode the game was started from
                app.enter_mode(gen, app.prev.id, None, t, quiet=True)
            app.set_state("READY", app.source_desc)
            return True
        cmd, cmds, out, t_llm, ended = self.direct_command(user), [], "", None, False
        try:
            if cmd:
                out = self.send(cmd)
                if ZGame.parser_failed(out):
                    app.ev(f"game: {cmd!r} -> {out!r}, asking the LLM")
                else:
                    cmds = [cmd]
            if not cmds:
                t1 = time.time()
                cmds = self.translate(gen, user)
                t_llm = time.time() - t1
                if gen != app.gen:
                    return True
                out = "\n\n".join(self.send(c) for c in cmds)
        except GameOver:
            ended = True
        if cmds:
            app.add("sys", "> " + ". ".join(cmds))
            self.history += [{"role": "user", "content": f"Game:\n{self.game_last}\n\nPlayer: {user}"},
                             {"role": "assistant", "content": json.dumps({"commands": cmds})}]
            self.game_last = out
            if out:
                app.speak_text(gen, ZGame.speech(out), t, "game")
        elif not ended:
            t["pieces"] = app.speak(gen, "I didn't hear a move there. Try things like look around, go north, or "
                                         "take the lamp.", t, app.add("host", ""))
        if ended or not (self.game and self.game.alive()):
            self.leave_game("The game is over. Say play Zork to start again.", save=False)
        elif cmds:
            self.prime_game()
        app.wait_first_word(gen, t)
        fa = t.get("first_audio")
        asr_s = t["asr"] - t["t0"]
        app.metrics = (f"hear {asr_s:.1f}s · " + (f"understand {t_llm:.1f}s" if t_llm is not None else "direct") +
                       (f" · first word {fa - t['t0']:.1f}s" if fa else ""))
        app.dirty = True
        g = self.game
        app.log_turn({"game": self.title, "user": user, "direct": t_llm is None, "cmds": cmds, "out": out,
                      "room": g.room if g else "", "score": g.score if g else "",
                      "asr_s": round(asr_s, 2), "llm_s": round(t_llm, 2) if t_llm is not None else None,
                      "first_audio_s": round(fa - t["t0"], 2) if fa else None})
        return True
