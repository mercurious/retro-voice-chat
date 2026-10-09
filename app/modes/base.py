"""The Mode class: what one mode of the app is (its host, prompt, theme) and the hooks the app calls.

The app (retrovoice.py) owns the voice stack: microphone, speech recognition, the model, speech, the screen.
A mode decides what the player's words mean while it is on. Each mode keeps its own conversation, transcript
and context use, so switching away and back picks up where it left off.

Hooks, all optional:
  setup()                     after every mode exists (compile regexes that name every host, ...)
  warm()                      in the background at boot, after the model is ready (load data)
  claims(user)                True: these words, said in another mode, switch to this one
  enter(gen, t, user, claimed)    switched to (or started in); speaks a greeting, or answers `user`
  leave()                     switched away (Zork saves the game)
  turn(gen, user, t)          True if the mode handled the whole turn itself (Zork)
  before(user)                for a chat turn: a dict of book words and hidden notes (see Session in
                              puzzles.py for the keys); {} is plain conversation
  screen(text, spoken, act)   each sentence the model writes: None to speak it, "drop" to skip it,
                              "stop" to end the reply
  after(user, act, kept, asked, invented)   words to speak after the model's reply
  reset()                     START: a new conversation
  status()                    a short state for the status line and the log
  ready_line(mic)             the whole status line while idle
  close()                     the app is quitting
"""
import time

# 256-colour codes: (host and title, dim rules and hints, the player's lines, status lines)
ANSI = "\033[38;5;{}m"


class Mode:
    id = ""                 # prefs, RV_START, the "mode" control command
    label = ""              # the menu
    blurb = ""              # one line under the menu, and in the general chat prompt
    order = 100             # menu position
    name = "HOST"           # on screen, and the speaker tag
    said = None             # how speech should say the name (and how the ASR spells it back)
    heard = ()              # (pattern, replacement) fixes for how the ASR writes this mode's words
    aliases = ()            # "switch to <alias>"
    title = ""
    subtitle = ""
    bg, fg = "000000", "e0e0e0"     # the terminal's background and text
    colors = (252, 244, 214, 44)
    prompt = ""
    greet = ""              # the first time this mode is entered
    back = ""               # coming back to it later
    fresh = ""              # START
    kv = None               # which prompt the model server holds while this mode talks (default: id)

    def __init__(self, app):
        self.app = app
        self.kv = self.kv or self.id
        self.history, self.lines = [], []
        self.ctx_used = self.ctx_base = 0
        self.entered = False
        self.sys = None

    @property
    def ansi(self):
        return tuple(ANSI.format(c) for c in self.colors)

    def system(self):
        """The system prompt, fixed for the session (a change would make the model read it all again)."""
        if self.sys is None:
            self.sys = self.build() + f"\nToday's date is {time.strftime('%B %d, %Y')}."
        return self.sys

    def build(self):
        return self.prompt

    def available(self):
        return True

    def setup(self):
        pass

    def warm(self):
        pass

    def claims(self, user):
        return False

    def enter(self, gen, t, user=None, claimed=False):
        app = self.app
        first, self.entered = not self.entered, True
        if claimed and user:        # "give me a puzzle" said elsewhere: answer it here
            return app.chat_turn(gen, user, t)
        line = self.greet if first or not self.back else self.back
        app.speak(gen, line, None, app.add("host", ""))
        app.prime_mode()

    def leave(self):
        pass

    def turn(self, gen, user, t):
        return False

    def before(self, user):
        return {}

    def screen(self, text, spoken, act):
        return None

    def after(self, user, act, kept, asked, invented):
        return act.get("after", "")

    def reset(self):
        pass

    def status(self):
        return ""

    def ready_line(self, mic):
        app, s = self.app, self.status()
        return f"{app.G}▶ {s or 'READY'}{app.RST}   {app.DIM}{mic}{app.RST}"

    def close(self):
        pass


def asking(names):
    """A request has to start the sentence ("Let's play Zork two." starts it, "I used to play Zork" does not);
    this is what may come before it, including any host's name."""
    return (r"^\W*(?:(?:ok|okay|alright|so|now|hey|please|let's|lets|let us|can we|could we|i want to|i'd like to|"
            r"i would like to|we should|time to|" + "|".join(names) + r")\W+)*")
