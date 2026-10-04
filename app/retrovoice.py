#!/usr/bin/env python3
"""retrovoice: push-to-talk voice chat on the Retroid Pocket Flip 2.

gamepad -> mic (parec) -> Qwen3-ASR (llama-server) -> LLM (llama-server, streamed)
        -> sentence splitter -> Pocket TTS (tts-server, streamed PCM) -> speaker (pacat)
The reply's text is shown word by word as its audio plays, never ahead of the voice.

Stdlib only. Servers are started by launch.sh. Test hooks: write commands to the control FIFO
(default /tmp/retrovoice.ctl): ptt_down, ptt_up, inject <wav>, say <text>, stop, voice, repeat,
new, quit.
"""
import array, fcntl, io, json, math, os, queue, random, re, select, shutil, struct, subprocess, sys
import textwrap, threading, time, unicodedata, urllib.error, urllib.request, uuid, wave
from zgame import GAMES, GameOver, ZGame
import puzzles

VERSION = "0.0.1"
ASR_URL = os.environ.get("RV_ASR_URL", "http://127.0.0.1:8091")
LLM_URL = os.environ.get("RV_LLM_URL", "http://127.0.0.1:8092")
TTS_URL = os.environ.get("RV_TTS_URL", "http://127.0.0.1:8093")
CTL_PATH = os.environ.get("RV_CTL", "/tmp/retrovoice.ctl")
LOG_DIR = os.environ.get("RV_LOG_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs"))
MODEL_LABEL = os.environ.get("RV_MODEL_LABEL", "gemma-4-E2B")
# What the player chose last, kept between sessions: {"voice": <name> | "random"}
PREFS_PATH = os.environ.get("RV_PREFS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "prefs.json"))
HEADLESS = "--headless" in sys.argv
MIC_RATE, TTS_RATE = 16000, 24000
MAX_REC_S, MIN_REC_S = 30.0, 0.35
# Whenever playback starts from silence, hold the audio back until this much is buffered. The first
# sentence is synthesized while the LLM is still generating, which slows TTS (1.2x real time at equal
# priority, 1.9x with launch.sh's nice -10, vs 2.2x alone), and pacat buffers only 120 ms.
PREROLL_S = float(os.environ.get("RV_PREROLL", "0.6"))
# Output level. Pocket TTS speech averages about -18 dBFS with peaks within 1 dB of full scale: quiet next to
# a game, and at the volume it then takes (100%), the Flip 2's headphone amp crackles on the peaks (the sink
# volume is the codec's HPH gain; 100% is its +6 dB top step). So the voice is made louder under a capped
# peak: makeup gain, then a peak limiter down to RV_CEIL_DB. The defaults put it 6 dB up (about -12 dBFS):
# in listening tests at 60% volume that was "good"/"loud" and clean; soft clipping for more was "distorted".
# RV_GAIN_DB=0 RV_CEIL_DB=0 leaves the samples alone; a lower ceiling (-6) is safer at 100% volume.
GAIN_DB = float(os.environ.get("RV_GAIN_DB", "12"))
CEIL_DB = float(os.environ.get("RV_CEIL_DB", "-1"))
# Context budget. The whole window is used: when the next request (prompt + reply) would pass CTX_TRIM of
# it, the oldest exchanges are dropped in one cut, down to CTX_KEEP. Not a slide: any cut changes the start
# of the prompt, and the server then reads the whole kept conversation again (~30 tokens/s on the rig with
# E4B: 1,300 tokens took 43 s). RV_CONTEXT=endurance never trims, to see what happens when it fills up.
CTX_MODE = os.environ.get("RV_CONTEXT", "trim")
CTX_TRIM = float(os.environ.get("RV_CTX_TRIM", "0.9"))
CTX_KEEP = float(os.environ.get("RV_CTX_KEEP", "0.2"))
PREFILL_TPS = 30.0
CHAT_MAX_TOKENS, GAME_MAX_TOKENS = 200, 60
CTX_FULL = re.compile(r"request \((\d+) tokens\) exceeds the available context size")

# Zork (zgame.py): the game holds the world and writes every word of the story; the LLM only turns what
# the player says into the game's commands, when the words are not a command already.
GAME_DIR = os.environ.get("RV_GAME_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "games"))
DFROTZ = os.environ.get("RV_DFROTZ", os.path.join(GAME_DIR, "dfrotz"))
# spoken commands must start the sentence: "Let's play Zork two." starts it, "I used to play Zork" does not
ASKING = r"^\W*(?:(?:ok|okay|alright|so|now|hey|trixy|trixie|enigma|please|let's|lets|let us|can we|could we|i want to|" \
         r"i'd like to|i would like to|we should|time to)\W+)*"
GAME_START = re.compile(ASKING + r"(play|start|launch|load|begin|resume|continue)\b.{0,20}?\bzork\b"
                        r"(?:\s*(1|2|3|one|two|three|iii|ii|i)\b)?", re.I)
GAME_EXIT = re.compile(ASKING + r"((stop|quit|exit|leave|end|close)\b.{0,16}?\b(game|zork)\b|stop playing\b)", re.I)
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
FILLER = re.compile(r"^(?:okay|ok|alright|all right|now|and|then|so|um|uh|trixy|trixie)\b[,.]?\s*", re.I)


def direct_command(text):
    """The spoken line as a game command if it already is one, else None (the LLM translates it)."""
    s = re.sub(r"\bplease\b", "", text.strip().lower())
    while FILLER.match(s):
        s = FILLER.sub("", s, count=1)
    s = re.sub(r"[,.]?\s+then\s+", ". ", s)   # ASR writes "lamp. Then take" as often as "lamp, then take"
    s = re.sub(r"\bsuper[\s-]+brief\b", "superbrief", s)   # ASR splits Zork's made-up word
    words = [HEARD.get(w, w) for w in re.findall(r"[a-z0-9']+|\.", s)]
    real = [w for w in words if w != "."]
    if not real or real[0] not in DIRECT_VERBS or len(real) > 8 or NOT_DIRECT & set(real) \
            or real[0] == "i" and len(real) > 1:
        return None
    return " ".join(words).replace(" .", ".").strip(". ")


def msgs_chars(msgs):
    return sum(len(m.get("content", "")) + 12 for m in msgs)   # ~12 characters of chat template per message

TRIXY_PROMPT = (
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
    "If you did not understand what the player said, say so briefly.\n"
    f"Today's date is {time.strftime('%B %d, %Y')}.")
# ENIGMA (RV_PERSONA=enigma): a word-puzzle host. puzzles.py makes, checks, reads and scores every puzzle; the
# model never invents or judges one (small models cannot see letters), it only hosts: reactions, praise, chat.
# The manner is a composite of radio puzzle segments (see puzzle/STYLE.md), not an impression of anyone.
ENIGMA_PROMPT = (
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
    "If you did not understand what the player said, say so briefly.\n"
    f"Today's date is {time.strftime('%B %d, %Y')}.")
# Who is talking. name: on screen; said: how TTS should say it (and how the ASR spells it back).
PERSONAS = {
    "trixy": {"name": "TRIXY", "said": "Trixie", "title": " ▓▒░ T R I X Y ░▒▓", "subtitle": "   retro voice chat",
              "system": TRIXY_PROMPT, "games": True, "trivia": True, "puzzles": False,
              "greet": "I'm ready. Hold the B button or R1 and talk to me.",
              "fresh": "Fresh start. What's on your mind?",
              "colors": ("\033[38;5;46m", "\033[38;5;28m", "\033[38;5;214m", "\033[38;5;44m")},
    "enigma": {"name": "ENIGMA", "said": "Enigma", "title": " ░▒▓ E N I G M A ▓▒░", "subtitle": "   word puzzles",
               "system": ENIGMA_PROMPT, "games": False, "trivia": False, "puzzles": True,
               "greet": "Hello there, I'm Enigma, and I've got a puzzle with your name on it. Hold B and ask me for "
                        "a puzzle, a round, or a real challenge.",
               "fresh": "Clean slate. Shall I give you a puzzle?",
               "colors": ("\033[38;5;222m", "\033[38;5;137m", "\033[38;5;117m", "\033[38;5;180m")},
}
PERSONA = PERSONAS.get(os.environ.get("RV_PERSONA", "trixy").lower(), PERSONAS["trixy"])
SYSTEM_PROMPT = os.environ.get("RV_SYSTEM", PERSONA["system"])
TEMPERATURE = float(os.environ.get("RV_TEMP", "0.4"))

# Verified trivia bank: the app, not the model, picks questions and holds the answers, so a quiz never
# rests on a fact the model made up. A request attaches a hidden card to the player's message; the
# player's next turn gets a hidden grading note with the true answer.
TRIVIA_PATH = os.environ.get("RV_TRIVIA", os.path.join(os.path.dirname(os.path.abspath(__file__)), "trivia.json"))
TRIVIA_ASK = re.compile(r"\b(trivia|quiz|another (one|question)|next (one|question)|ask me (a|another|one)|"
                        r"(hard|harder|tough|tougher|difficult) (one|question))\b", re.I)


STOP = set("the a an of in on to for and or is was what which who whom how did does do year game games video "
           "all time your you me my it its that this with from by first original called name named".split())


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


QUESTION = re.compile(r"\s*(who|what|when|where|why|how|which|whose|can you|could you|do you|did you|have you|"
                      r"tell me|name)\b", re.I)


def load_trivia():
    import random
    try:
        bank = json.load(open(TRIVIA_PATH))
    except (OSError, ValueError):
        return []
    random.shuffle(bank)
    return bank

# ---------------------------------------------------------------------------------------------- input

EV_KEY, EV_ABS, EV_SW = 1, 3, 5
BTN = {0x130: "south", 0x131: "east", 0x133: "north", 0x134: "west", 0x136: "l1", 0x137: "r1",
       0x13a: "select", 0x13b: "start", 0x13c: "home", 0x220: "up", 0x221: "down"}
ABS_HAT0Y = 17
EVENT = struct.Struct("qqHHi")  # struct input_event on 64-bit: timeval, type, code, value
PAD_NAMES = ("Retroid Pocket Gamepad", "Sony Interactive Entertainment DualSense Wireless Controller",
             "Microsoft X-Box", "Xbox Wireless Controller")


def eviocgsw(nbytes):
    return (2 << 30) | (nbytes << 16) | (ord("E") << 8) | 0x1B


def input_devices():
    found = []
    for ev in sorted(os.listdir("/sys/class/input")):
        if not ev.startswith("event"):
            continue
        try:
            name = open(f"/sys/class/input/{ev}/device/name").read().strip()
        except OSError:
            continue
        if name in PAD_NAMES:
            found.append((f"/dev/input/{ev}", name))
    return found


def headset_mic_inserted():
    """SW_MICROPHONE_INSERT on the codec's jack device (None if it can't be read)."""
    for ev in os.listdir("/sys/class/input"):
        try:
            if "Headset Jack" not in open(f"/sys/class/input/{ev}/device/name").read() or \
               "DualSense" in open(f"/sys/class/input/{ev}/device/name").read():
                continue
            with open(f"/dev/input/{ev}", "rb") as f:
                buf = bytearray(8)
                fcntl.ioctl(f, eviocgsw(len(buf)), buf)
                return bool(buf[0] & (1 << 4))  # SW_MICROPHONE_INSERT = 4
        except OSError:
            continue
    return None


class InputThread(threading.Thread):
    """Gamepads (non-exclusive read) plus the control FIFO, as events on a queue."""

    def __init__(self, out):
        super().__init__(daemon=True)
        self.out, self.fds, self.last_scan = out, {}, 0.0
        try:
            os.mkfifo(CTL_PATH)
        except FileExistsError:
            pass
        self.ctl = os.open(CTL_PATH, os.O_RDWR | os.O_NONBLOCK)
        self.ctl_buf = b""

    def rescan(self):
        present = dict(input_devices())
        for path in list(self.fds):
            if path not in present:
                os.close(self.fds.pop(path)[0])
        for path, name in present.items():
            if path not in self.fds:
                try:
                    self.fds[path] = (os.open(path, os.O_RDONLY | os.O_NONBLOCK), name)
                    label = "built-in pad (via InputPlumber)" if "DualSense" in name else name
                    self.out.put(("sys", f"controller: {label}"))
                except OSError:
                    pass
        self.last_scan = time.time()

    def run(self):
        hat = 0
        while True:
            if time.time() - self.last_scan > 5:
                self.rescan()
            fdmap = {fd: path for path, (fd, _) in self.fds.items()}
            r, _, _ = select.select(list(fdmap) + [self.ctl], [], [], 1.0)
            for fd in r:
                if fd == self.ctl:
                    self.ctl_buf += os.read(self.ctl, 4096)
                    while b"\n" in self.ctl_buf:
                        line, self.ctl_buf = self.ctl_buf.split(b"\n", 1)
                        cmd, _, arg = line.decode(errors="replace").strip().partition(" ")
                        if cmd:
                            self.out.put(("ctl", cmd, arg.strip()))
                    continue
                try:
                    data = os.read(fd, EVENT.size * 64)
                except OSError:
                    self.last_scan = 0
                    continue
                for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
                    _, _, typ, code, val = EVENT.unpack_from(data, i)
                    if typ == EV_KEY and code in BTN and val in (0, 1):
                        self.out.put(("btn", BTN[code], val))
                    elif typ == EV_ABS and code == ABS_HAT0Y:
                        if val != hat:
                            if val:
                                self.out.put(("btn", "up" if val < 0 else "down", 1))
                            hat = val

# ---------------------------------------------------------------------------------------------- audio


def pick_source():
    """(source name or None, human description)."""
    forced = os.environ.get("RV_SOURCE")
    if forced:
        return forced, forced
    try:
        out = subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True,
                             timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None, "pactl unavailable"
    names = [l.split("\t")[1] for l in out.splitlines() if "\t" in l]
    real = [n for n in names if not n.endswith(".monitor")]
    for n in real:  # plugged-in USB / Bluetooth mics first
        if "usb" in n.lower() or "bluez" in n.lower():
            return n, "USB/BT mic"
    for n in real:  # the Flip 2's own card: 3.5 mm headset mic, else the built-in mic (only there with a device tree that powers it)
        if "sound_card0" not in n:
            continue
        ports, ins = source_ports(n), headset_mic_inserted()
        if "[In] Mic" in ports and ins is not True:
            set_source_port(n, "[In] Mic")
            return n, "built-in mic"
        if ins is False:
            return None, "no mic: plug a headset (TRRS) or USB-C mic"
        if "[In] Headset" in ports:
            set_source_port(n, "[In] Headset")
        return n, "headset mic"
    return (real[0], real[0]) if real else (None, "no microphone found")


def source_ports(name):
    """Port names of one PipeWire source ("[In] Headset", "[In] Mic", ...)."""
    try:
        out = subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    for block in out.split("Source #")[1:]:
        if f"Name: {name}\n" in block:
            return re.findall(r"^\t\t(\[In\] [^:]+):", block, re.M)
    return []


def set_source_port(name, port):
    """Select the capture port explicitly: the card runs api.acp.auto-port = false."""
    subprocess.run(["pactl", "set-source-port", name, port], capture_output=True, timeout=5)


class MicStream:
    """Always-open capture (parec) into a ring buffer. Opening a PipeWire capture on the Flip 2 takes ~1.5 s
    (source resume + UCM enable + ADC power-up), so a per-press recording loses the start of every
    utterance. Push-to-talk just marks a span in this stream, with a little pre-roll."""
    CHUNK = 1600  # 50 ms of s16 mono at 16 kHz
    PRE_S, POST_S = 0.25, 0.15

    def __init__(self, on_level):
        self.on_level, self.proc, self.source = on_level, None, None
        self.lock = threading.Lock()
        self.ring = bytearray()      # recent audio
        self.base = 0                # absolute byte offset of ring[0]
        self.total = 0               # absolute bytes received
        self.mark = None
        self.last_rx = 0.0

    def ensure(self, source):
        if source == self.source and self.proc and self.proc.poll() is None:
            return
        self.close()
        self.source = source
        if not source:
            return
        self.proc = subprocess.Popen(["parec", "--raw", "--format=s16le", f"--rate={MIC_RATE}", "--channels=1",
                                      f"--device={source}", "--latency-msec=50", "--client-name=retrovoice-mic"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        threading.Thread(target=self._pump, args=(self.proc,), daemon=True).start()

    def _pump(self, proc):
        while proc.poll() is None:
            chunk = proc.stdout.read(self.CHUNK)
            if not chunk:
                break
            with self.lock:
                self.ring += chunk
                self.total += len(chunk)
                self.last_rx = time.time()
                cap = int((MAX_REC_S + 5) * MIC_RATE * 2)
                if len(self.ring) > cap:
                    drop = len(self.ring) - cap
                    del self.ring[:drop]
                    self.base += drop
            if self.mark is not None:
                a = array.array("h", chunk[: len(chunk) // 2 * 2])
                rms = math.sqrt(sum(x * x for x in a) / max(1, len(a))) / 32768.0
                self.on_level(min(1.0, rms * 4.0))

    def start(self):
        with self.lock:
            self.mark = max(self.base, self.total - int(self.PRE_S * MIC_RATE) * 2)

    def stop(self):
        time.sleep(self.POST_S)
        with self.lock:
            if self.mark is None:
                return b""
            seg = bytes(self.ring[self.mark - self.base:])
            self.mark = None
        return seg[: int(MAX_REC_S * MIC_RATE) * 2]

    def alive(self):
        return self.proc is not None and self.proc.poll() is None and time.time() - self.last_rx < 2.0

    def close(self):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc, self.mark = None, None


def pcm_to_wav(pcm, rate):
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate), w.writeframes(pcm)
    return bio.getvalue()


class Limiter:
    """Makeup gain, then a peak limiter. The gain is set per 2 ms block from that block's peak and the next
    one's, so it is already down when a peak arrives; it ramps inside the block, holds for a moment after a
    peak (a gain that recovers faster ripples at the voice's pitch), then recovers slowly. The wave keeps
    its shape."""
    BLOCK = 48          # samples: 2 ms at 24 kHz

    def __init__(self, gain_db, ceil_db, release_ms=150.0, hold_ms=10.0, rate=TTS_RATE):
        self.makeup = 10 ** (gain_db / 20)
        self.ceil = 32767 * 10 ** (min(0.0, ceil_db) / 20)
        self.rel = 1 - math.exp(-(self.BLOCK / rate * 1000) / release_ms)
        self.hold_n = int(hold_ms / (self.BLOCK / rate * 1000))    # blocks the gain stays down after a peak
        self.g, self.hold = 1.0, 0    # limiter gain at the end of the last block (1 = no reduction)

    def reset(self):
        self.g, self.hold = 1.0, 0

    def process(self, pcm):
        """pcm: whole s16 samples. Returns as many samples."""
        a = array.array("h")
        a.frombytes(pcm)
        n, B, mk, ceil = len(a), self.BLOCK, self.makeup, self.ceil
        if not n:
            return pcm
        want = []       # per block: the most gain its peak allows
        for i in range(0, n, B):
            blk = a[i:i + B]
            pk = max(max(blk), -min(blk)) * mk
            want.append(1.0 if pk <= ceil else ceil / pk)
        out, g = array.array("h"), min(self.g, want[0])
        for k, i in enumerate(range(0, n, B)):
            target = min(want[k], want[k + 1]) if k + 1 < len(want) else want[k]
            if target < g:
                g1, self.hold = target, self.hold_n
            elif self.hold:
                g1, self.hold = g, self.hold - 1
            else:
                g1 = g + (target - g) * self.rel
            blk = a[i:i + B]
            g0, step = g * mk, (g1 - g) * mk / len(blk)
            out.extend([int(x * (g0 + step * j)) for j, x in enumerate(blk)])
            g = g1
        self.g = g
        return out.tobytes()


class Player:
    """Persistent pacat fed raw s16le by its own thread; flush() drops whatever is queued or buffered.
    pacat reads at playback speed and its pipe holds ~1.4 s, so writing from the caller would pace the
    caller's TTS reads to playback (and hide how fast TTS really is)."""

    def __init__(self):
        self.lock, self.proc, self.until, self.epoch = threading.Lock(), None, 0.0, 0
        self.q = queue.Queue()
        self.limiter = Limiter(GAIN_DB, CEIL_DB) if (GAIN_DB or CEIL_DB < 0) else None
        self._spawn()
        threading.Thread(target=self._feed, daemon=True).start()

    def _spawn(self):
        self.proc = subprocess.Popen(["pacat", "--raw", "--format=s16le", f"--rate={TTS_RATE}", "--channels=1",
                                      "--latency-msec=120", "--client-name=retrovoice"],
                                     stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _feed(self):
        while True:
            epoch, pcm = self.q.get()
            proc = self.proc
            if epoch != self.epoch:
                continue            # queued before a flush
            try:
                proc.stdin.write(pcm)
                proc.stdin.flush()
            except (OSError, ValueError):
                with self.lock:
                    if epoch == self.epoch and proc is self.proc:   # pacat died on its own
                        self._spawn()

    def write(self, pcm):
        """Queue pcm (whole s16 samples); returns the (estimated) time it starts playing."""
        if self.limiter:
            pcm = self.limiter.process(pcm)
        with self.lock:
            start = max(self.until, time.time() + 0.12)
            self.until = start + len(pcm) / (2 * TTS_RATE)
            self.q.put((self.epoch, pcm))
            return start

    def flush(self):
        with self.lock:
            self.epoch += 1
            try:
                self.proc.kill()
            except OSError:
                pass
            self._spawn()
            self.until = 0.0
            if self.limiter:
                self.limiter.reset()

    def speaking(self):
        return time.time() < self.until

    def close(self):
        self.epoch += 1            # so the feeder does not respawn pacat
        try:
            self.proc.kill()
        except OSError:
            pass

# ---------------------------------------------------------------------------------------------- servers


def http_json(url, body=None, timeout=120, headers=None, data=None):
    if body is not None:
        data, headers = json.dumps(body).encode(), {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def sysfs(d, name):
    try:
        with open(os.path.join(d, name)) as f:
            return f.read().strip()
    except OSError:
        return ""


def find_battery():
    """The handheld's own battery; a connected gamepad's battery has scope Device."""
    base = "/sys/class/power_supply"
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        d = os.path.join(base, name)
        if sysfs(d, "type") == "Battery" and sysfs(d, "scope") != "Device" and sysfs(d, "capacity"):
            return d
    return None


def load_prefs():
    try:
        with open(PREFS_PATH) as f:
            p = json.load(f)
        return p if isinstance(p, dict) else {}
    except (OSError, ValueError):
        return {}


def save_prefs(prefs):
    try:
        with open(PREFS_PATH + ".tmp", "w") as f:
            json.dump(prefs, f)
        os.replace(PREFS_PATH + ".tmp", PREFS_PATH)
    except OSError:
        pass


def system_load():
    """One status line: CPU busy over half a second, what the GPU is doing, memory in use."""
    def cpu():
        v = [int(x) for x in open("/proc/stat").readline().split()[1:9]]
        return sum(v), v[3] + v[4]      # total, idle + iowait
    try:
        t0, i0 = cpu()
        time.sleep(0.5)
        t1, i1 = cpu()
        mem = dict(l.split(":")[0:2] for l in open("/proc/meminfo"))
        total, avail = int(mem["MemTotal"].split()[0]), int(mem["MemAvailable"].split()[0])
        gpu = "running the model" if os.environ.get("RV_LLM_GPU") else "off"
        return (f"load: CPU {100 * (1 - (i1 - i0) / max(1, t1 - t0)):.0f}% · GPU {gpu} · "
                f"RAM {100 * (1 - avail / total):.0f}% of {total / 1048576:.1f} GB")
    except (OSError, ValueError, KeyError, IndexError):
        return ""


def healthy(url):
    try:
        with urllib.request.urlopen(url + "/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def transcribe(wav_bytes, language=None):
    """The utterance as text. Qwen3-ASR names the language it heard ("language Portuguese<asr_text>..."): a
    short English word could come back as Portuguese ("sim"), and noise as the model's own prompt translated
    ("Transcreva audio para texto"). So anything not English is heard again with an English hint (an "en" hint
    leaves silence silent; "English" made the model read its prompt back)."""
    boundary = uuid.uuid4().hex
    parts = []
    fields = [("model", "asr"), ("response_format", "json")] + ([("language", language)] if language else [])
    for name, val in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{val}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="utt.wav"\r\n'
                  f"Content-Type: audio/wav\r\n\r\n").encode() + wav_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    r = http_json(ASR_URL + "/v1/audio/transcriptions", data=b"".join(parts),
                  headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    text = r.get("text", "")
    if "<asr_text>" in text:
        head, text = text.split("<asr_text>", 1)
        lang = head.replace("language", "").strip()
        if lang not in ("English", "None", "") and not language:
            return transcribe(wav_bytes, "en")
    for pat, rep in ASR_FIXES:
        text = re.sub(pat, rep, text, flags=re.I)
    return text.strip()


# The assistant's name is written TRIXY and said "Trixie", which is how the ASR spells it back; ENIGMA is said
# "Enigma" (written in capitals, TTS would spell it out).
ASR_FIXES = [(r"\btri(?:xie|xi|xey|cksy|cksie|ksy|ksie)\b", "Trixy"),
             (r"\bzor(?:c|g|ch|ck|ke)\b", "Zork"),
             (r"\b(?:a|an|in)[\s-]?nigma\b|\benigmas?\b", "Enigma")]
SAY_NAME = re.compile(r"\b" + PERSONA["name"] + r"\b", re.I)


HIDDEN = re.compile(r"\[[^\]]*(\]|$)")   # [answer: ...] notes, including an unterminated one mid-stream


def clean_for_speech(text):
    text = HIDDEN.sub("", text)
    out = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in "*#_`~|<>[]{}":
            continue
        if cat[0] in "LNPZ" or ch in "'\"$%&+-=/":
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


# Pocket TTS garbles spelled words ("P-A-I-N-S" came out as "PA ions", a lone "M." as "Monsieur"). What it
# does say clearly, checked by synthesizing on the rig and transcribing back: capitals with commas
# ("P, A, I, N, S"), W as "double-you", and a single letter by its name ("the letter em"). Only the audio is
# rewritten; the screen keeps B-E-A-R.
LETTER_NAMES = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "ay bee see dee ee eff gee aitch eye jay kay ell em en oh pee cue ar "
                                                       "ess tee you vee double-you ex why zee".split()))
SPELLED = re.compile(r"\b[A-Z](?:-[A-Z])+\b")
ONE_LETTER = re.compile(r"\b(the letters?|letter) ([A-Z])\b")
PATTERN = re.compile(r"(pattern is )([^.]*)")


def tts_text(text):
    text = SAY_NAME.sub(PERSONA["said"], text)
    text = SPELLED.sub(lambda m: ", ".join("double-you" if c == "W" else c for c in m.group(0).split("-")), text)
    text = ONE_LETTER.sub(lambda m: f"{m.group(1)} {LETTER_NAMES[m.group(2)]}", text)
    return PATTERN.sub(lambda m: m.group(1) + re.sub(r"\b[A-Z]\b", lambda c: LETTER_NAMES[c.group(0)], m.group(2)),
                       text)


SENT_END = re.compile(r"([.!?…]+[\"')\]]*)(\s+|$)")


MIN_CHUNK = 28   # a sentence shorter than this rides along with the next one


def split_sentences(buf, first):
    """Return (complete chunks, remainder). The first chunk may break at a comma to start speaking early;
    very short sentences are held and spoken together with the next, so a quick "Sure!" does not finish
    playing before the next sentence has been generated."""
    done = []
    pos = 0
    while True:
        m = SENT_END.search(buf, pos)
        if m and m.end() < len(buf) or (m and buf.endswith(("\n",))):
            if len(buf[: m.end(1)].strip()) < MIN_CHUNK:
                pos = m.end()          # too short: keep it and look for the next sentence end
                continue
            done.append(buf[: m.end(1)].strip())
            buf, pos = buf[m.end():], 0
            first = False
            continue
        if first and not done and len(buf) > 30:
            c = buf.rfind(", ", 20)
            if c > 0:
                done.append(buf[: c + 1].strip())
                buf = buf[c + 2:]
                first = False
                continue
        return [s for s in done if s], buf

# ---------------------------------------------------------------------------------------------- app


class App:
    def __init__(self):
        self.q = queue.Queue()
        self.state, self.note = "BOOT", "warming up"
        self.lines = []            # (who, text)
        self.live = None           # index of the reply being streamed
        self.level = 0.0
        self.rec_start = 0.0
        self.scroll = 0
        self.prefs = load_prefs()
        self.voices, self.voice = ["alba"], "alba"
        self.voice_pref = os.environ.get("RV_VOICE") or self.prefs.get("voice") or "random"   # a name, or "random"
        self.history = []
        self.trivia, self.trivia_active = (load_trivia() if PERSONA["trivia"] else []), None
        self.book = puzzles.Puzzles(os.environ.get("RV_PUZZLE_SEED")) if PERSONA["puzzles"] else None   # generators, bank
        self.host = puzzles.Session(self.book) if self.book else None   # the puzzle being played, the score
        self.metrics = ""
        self.n_ctx = 0             # the LLM's context window (tokens), from /props
        self.ctx_used = 0          # tokens the conversation fills: prompt + reply of the last turn
        self.ctx_base = 0          # system prompt alone, for a new chat
        self.bat_dir = find_battery()
        self.bat_pct, self.bat_status, self.bat_w = None, "", None   # watts: smoothed over ~15 s
        self.bat_t = 0.0
        self.tpc = 0.3             # LLM tokens per character of conversation, learned from each request
        self.kv_mode = "chat"      # whose prompt the LLM server holds: "chat" or "game"
        self.ctx_saved = 0         # the other mode's context use
        self.game = None           # ZGame while playing
        self.game_lock = threading.Lock()
        self.game_title, self.game_system, self.game_history, self.game_last = "", "", [], ""
        self.gen = 0               # bumps on every interrupt; stale work checks it
        self.held = set()
        self.source, self.source_desc = None, "?"
        self.mic = MicStream(self._set_level)
        self.player = None
        self.jack_ins, self.jack_due = None, 0.0   # headset-mic switch as last seen; when to re-pick the mic
        self.tts_q = queue.Queue()
        self.tts_busy = False
        self.captions = []         # spoken pieces of transcript lines, revealed as their audio plays
        self.cap_lock = threading.Lock()
        self.sec_per_char = 0.075  # speaking rate, learned from finished pieces
        self.work_q = queue.Queue()
        self.last_reply = ""
        self.dirty = True
        self.running = True
        os.makedirs(LOG_DIR, exist_ok=True)
        self.log = open(os.path.join(LOG_DIR, "turns.jsonl"), "a")
        self.evlog = open(os.path.join(LOG_DIR, "events.log"), "a")

    def ev(self, msg):
        self.evlog.write(f"{time.strftime('%H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} [{self.state} g{self.gen}] {msg}\n")
        self.evlog.flush()

    # -- helpers
    def _set_level(self, v):
        self.level = v
        self.dirty = True

    def add(self, who, text):
        self.lines.append([who, text])
        self.scroll = 0
        self.dirty = True
        if HEADLESS:
            print(f"[{who}] {text}", flush=True)
        return len(self.lines) - 1

    def set_state(self, st, note=""):
        if st != self.state:
            self.ev(f"state -> {st} {note}")
        self.state, self.note, self.dirty = st, note, True
        if HEADLESS:
            print(f"== {st} {note}", flush=True)

    # -- boot
    def boot(self):
        """Status lines while the servers load, the model warmed up, and only then READY and the greeting:
        nothing asks for a button before it works. Lines go through the queue so they keep their order."""
        say = lambda line: line and self.q.put(("sys", line))
        time.sleep(0.5)     # the controller line lands first
        info = {k: os.environ.get("RV_INFO_" + k.upper(), "") for k in ("driver", "llama", "tuning")}
        say(f"driver: {info['driver'] or 'none in use: the model runs on the CPU'}")
        say(info["llama"] and f"llama.cpp: {info['llama']}")
        say(info["tuning"] and f"tuning: {info['tuning']}")
        for name, url in (("ASR", ASR_URL), ("LLM", LLM_URL), ("TTS", TTS_URL)):
            t0 = time.time()
            while not healthy(url):
                self.set_state("BOOT", f"loading {name} ({time.time() - t0:.0f}s)")
                time.sleep(0.5)
                if time.time() - t0 > 300:
                    self.set_state("ERROR", f"{name} server did not start")
                    return False
        if not info["llama"]:
            try:
                say(f"llama.cpp: {http_json(LLM_URL + '/props', timeout=10).get('build_info', '?')}")
            except Exception:
                pass
        try:
            v = http_json(TTS_URL + "/v1/audio/voices", timeout=10)
            names = [x.get("name") or x.get("id") for x in (v.get("data") or v.get("voices") or [])
                     if isinstance(x, dict)] or [x for x in (v.get("voices") or []) if isinstance(x, str)]
            if names:
                self.voices = names
        except Exception:
            pass
        self.voice = self.voice_pref if self.voice_pref in self.voices else random.choice(self.voices)
        self.player = Player()
        self.set_state("BOOT", "warming up the model")
        if self.book:      # the generator index (~2 s on the rig) is built while the model warms up
            threading.Thread(target=self.book.warm, daemon=True).start()
        self.warm_llm()
        say(system_load())
        say(f"voice: {self.voice_label()}")
        self.source, self.source_desc = pick_source()
        self.mic.ensure(self.source)
        self.jack_ins = headset_mic_inserted()
        while not self.q.empty():
            time.sleep(0.05)
        time.sleep(0.2)
        greet = PERSONA["greet"] if self.source else \
            "I'm ready, but I can't find a microphone. Plug in a headset with a mic and I'll hear you."
        self.speak_now(greet, self.add("host", ""))
        self.set_state("READY", self.source_desc)
        if os.environ.get("RV_START_GAME"):
            self.work_q.put((self.gen, "game", os.environ["RV_START_GAME"]))
        return True

    def warm_llm(self):
        """Process the system prompt once so the first real turn only reads the new words."""
        t0 = time.time()
        try:
            self.n_ctx = http_json(LLM_URL + "/props", timeout=10)["default_generation_settings"]["n_ctx"]
            r = http_json(LLM_URL + "/v1/chat/completions",
                          {"messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "hi"}],
                           "max_tokens": 1, "chat_template_kwargs": {"enable_thinking": False}}, timeout=300)
            tm = r.get("timings") or {}
            self.ctx_base = tm.get("cache_n", 0) + tm.get("prompt_n", 0)
            self.ctx_used = self.ctx_used or self.ctx_base
            self.dirty = True
            self.ev(f"llm warm-up {time.time() - t0:.1f}s, context {self.ctx_base}/{self.n_ctx}")
        except Exception as e:
            self.ev(f"llm warm-up failed: {e!r}")

    def speak_now(self, text, line=None):
        self.speak(self.gen, text, None, line)

    def speak(self, gen, text, turn, line):
        """Queue text for speech; False if nothing is speakable. With a transcript line, the line shows the
        text only as it is heard."""
        text = clean_for_speech(text)
        if not text:
            return False
        cap = {"gen": gen, "line": line, "text": text, "start": None, "end": 0.0, "done": False, "shown": 0}
        if line is not None:
            with self.cap_lock:
                self.captions.append(cap)
        self.tts_q.put((gen, turn, cap))
        return True

    def heard(self, cap, now):
        """The part of a caption whose audio has started: each word appears as it begins."""
        text = cap["text"]
        if cap.get("failed"):
            n = len(text)
        elif cap["start"] is None or now < cap["start"]:
            n = 0
        else:
            span = cap["end"] - cap["start"]
            if not cap["done"]:   # still arriving: its full length is estimated from the text
                span = max(span, len(text) * self.sec_per_char)
            n = int(len(text) * min(1.0, (now - cap["start"]) / span)) if span > 0 else len(text)
            j = text.find(" ", n)
            n = len(text) if j < 0 else j
        cap["shown"] = max(cap["shown"], n)
        return text[: cap["shown"]]

    def captions_tick(self):
        now = time.time()
        with self.cap_lock:
            caps = [c for c in self.captions if c["gen"] == self.gen]
        parts = {}
        for c in caps:
            parts.setdefault(c["line"], []).append(self.heard(c, now))
        for i, ps in parts.items():
            text = " ".join(p for p in ps if p)
            if i < len(self.lines) and self.lines[i][1] != text:
                self.lines[i][1] = text
                self.dirty = True

    # -- interrupt everything in flight
    def interrupt(self):
        self.captions_tick()       # freeze each line at what was actually heard
        with self.cap_lock:
            cut = {c["line"] for c in self.captions if c["gen"] == self.gen and c["shown"] < len(c["text"])}
            self.captions = []
        if self.live is not None:
            cut.add(self.live)
            self.live = None
        self.gen += 1
        for qq in (self.tts_q, self.work_q):
            try:
                while True:
                    qq.get_nowait()
            except queue.Empty:
                pass
        if self.player:
            self.player.flush()
        for i in cut:
            if i < len(self.lines):
                self.lines[i][1] = (self.lines[i][1] + " …").strip()
                self.dirty = True

    # -- workers
    def trivia_notes(self, user):
        """Hidden notes appended to the player's words: grade an open question, deal a new card."""
        notes = []
        asking = bool(TRIVIA_ASK.search(user)) and bool(self.trivia)
        # "Who made Choplifter?" mid-quiz is a new question, not an answer ("Is it Sega?" still is one)
        side_question = bool(QUESTION.match(user)) and not asking
        grading = self.trivia_active is not None and not side_question
        if grading:
            q = self.trivia_active
            alts = (" (also accept: " + ", ".join(q["alt"]) + ")") if q["alt"] else ""
            notes.append(f"[Note: the answer to your last trivia question is {q['a']}{alts}. Tell the player "
                         f"honestly whether they got it; if not, tell them the correct answer.]")
            self.trivia_active = None
        if not asking and not grading:
            fact = lookup_fact(self.trivia, user)
            if fact:
                notes.append(f"[Note: verified fact to use in your answer. {fact['q']} {fact['a']}.]")
                self.ev(f"fact note: {fact['a']}")
        if asking:
            card = self.trivia.pop(0)
            self.trivia.append(card)
            self.trivia_active = card
            notes.append(f"[Note: ask this trivia question in your own words, then add [answer: {card['a']}]. "
                         f"Question: {card['q']}]")
            self.ev(f"trivia card: {card['q']}")
        return user + ("\n\n" + " ".join(notes) if notes else "")

    def speaker_loop(self):
        preroll = int(PREROLL_S * TTS_RATE) * 2
        while self.running:
            gen, turn, cap = self.tts_q.get()
            if gen != self.gen:
                continue
            self.tts_busy = True
            cap["t_req"], cap["i"], audio = time.time(), len(turn.get("tts", [])) if turn else 0, 0
            try:
                req = urllib.request.Request(TTS_URL + "/v1/audio/speech",
                                             json.dumps({"input": tts_text(cap["text"]),
                                                         "voice": self.voice,
                                                         "response_format": "pcm"}).encode(),
                                             {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    buf = b""
                    while True:
                        chunk = r.read(4800)
                        if gen != self.gen:
                            break
                        buf += chunk
                        # starting from silence: hold the audio until PREROLL_S is buffered (or the piece
                        # is complete), so a slow synthesis is one short wait instead of a stutter
                        if chunk and len(buf) < preroll and not self.player.speaking():
                            continue
                        cut = len(buf) // 2 * 2
                        if cut:
                            self.play(buf[:cut], cap, turn)
                            audio += cut
                        buf = buf[cut:]
                        if not chunk:
                            break
            except Exception as e:
                cap["failed"] = True
                self.q.put(("sys", f"TTS error: {e}"))
            finally:
                cap["done"] = True
                if cap["start"] is not None and gen == self.gen and not cap.get("failed"):
                    self.sec_per_char += 0.3 * ((cap["end"] - cap["start"]) / len(cap["text"]) - self.sec_per_char)
                if turn is not None:   # [chars, seconds of audio, seconds to synthesize, wait before playing]
                    turn.setdefault("tts", []).append([len(cap["text"]), round(audio / (2 * TTS_RATE), 2),
                                                       round(time.time() - cap["t_req"], 2),
                                                       round(cap.get("wait", -1), 2)])
                self.tts_busy = False

    def play(self, pcm, cap, turn):
        now, ran_out = time.time(), self.player.until
        dry = not self.player.speaking()
        start = self.player.write(pcm)
        if cap["start"] is None:
            cap["start"], cap["wait"] = start, now - cap["t_req"]
        cap["end"] = self.player.until
        if turn is None:
            return
        if "first_audio" not in turn:
            turn["first_audio"], turn["t_play"] = now, start
            if cap["gen"] == self.gen and self.state == "THINKING":
                self.set_state("SPEAKING", "")
        elif dry:   # the audio ran dry mid-reply: [seconds into the reply, seconds of silence, piece]
            gap = max(0.0, now - ran_out)
            turn["gaps"] = turn.get("gaps", 0) + 1
            turn["gap_s"] = turn.get("gap_s", 0.0) + gap
            turn.setdefault("gap_at", []).append([round(ran_out - turn["t_play"], 2), round(gap, 2), cap["i"]])

    def work_loop(self):
        while self.running:
            gen, kind, payload = self.work_q.get()
            if gen != self.gen:
                continue
            try:
                self.turn(gen, kind, payload)
            except Exception as e:
                self.ev(f"turn error: {e!r}")
                self.q.put(("sys", f"error: {e}"))
                self.set_state("READY", self.source_desc)
            finally:
                if gen != self.gen and self.state in ("HEARING", "THINKING"):
                    self.ev("turn cancelled, releasing status")
                    self.set_state("READY", "cancelled")

    def turn(self, gen, kind, payload):
        t = {"t0": time.time()}
        if kind == "wav":
            self.set_state("HEARING", "transcribing")
            user = transcribe(payload)
            t["asr"] = time.time()
            self.ev(f"asr {t['asr'] - t['t0']:.2f}s -> {user!r}")
            if gen != self.gen:
                return
            if len(re.findall(r"[A-Za-z0-9]", user)) < 2:   # silence often transcribes as a filler like "嗯。"
                self.add("sys", "(didn't catch that, try again)")
                self.set_state("READY", self.source_desc)
                return
        elif kind == "game":
            return self.start_game(gen, payload, t)
        else:
            user = payload
            t["asr"] = t["t0"]
        self.add("you", user)
        self.set_state("THINKING", "")
        if self.game or PERSONA["games"] and GAME_START.search(user):
            return self.game_turn(gen, user, t)
        # ENIGMA: the puzzle book answers first. Its words (clues, hints, verdicts) are spoken as written; the
        # model is asked only when there is a note for it, or nothing from the book (plain conversation).
        pre = after = ""
        guard, max_tokens, ask_llm, act = None, CHAT_MAX_TOKENS, True, {}
        if self.host:
            act = self.host.turn(user)
            pre, after, guard = act.get("say", ""), act.get("after", ""), act.get("guard")
            max_tokens = act.get("tokens", CHAT_MAX_TOKENS)
            ask_llm = bool(act.get("note")) or not pre
            user_msg = user + ("\n\n" + act["note"] if act.get("note") else "")
            self.ev(f"puzzle [{self.host.status()}] say={pre[:70]!r} note={bool(act.get('note'))}")
        else:
            user_msg = self.trivia_notes(user)
        row = self.live = self.add("host", "")   # filled in by captions_tick as the words are heard
        t["pieces"] = 0
        if pre:
            t["pieces"] += self.speak(gen, pre, t, row)
            t.setdefault("ttft", time.time())
        reply, kept, timings, msgs, invented = "", "", {}, [], False
        if ask_llm:
            reply, kept, timings, msgs, invented = self.stream_reply(
                gen, user_msg, row, t, max_tokens, guard, act.get("sentences", 0) if self.host else 0,
                book=bool(self.host))
        if gen != self.gen:
            if pre:      # cut off by the player: the book's words were said, so they stay in the conversation
                self.history += [{"role": "user", "content": user_msg}, {"role": "assistant", "content": pre}]
            return
        if self.host and invented:     # the model started a puzzle of its own: give a real one instead
            after = self.host.present(user, offered=self.host.offered or True).get("say", "")
        elif self.host and ask_llm and act.get("offer") and "?" not in kept:
            after = act["offer"]          # the model did not offer another itself
        if after:
            t["pieces"] += self.speak(gen, after, t, row)
        self.live = None
        if msgs:
            self.take_timings(timings, msgs, reply, "chat")
        # the raw reply keeps any hidden [answer: ...] so the next turn can grade against it
        raw_reply = " ".join(x.strip() for x in (pre, kept, after) if x.strip())
        reply = clean_for_speech(raw_reply)
        self.last_reply = reply
        self.history += [{"role": "user", "content": user_msg}, {"role": "assistant", "content": raw_reply}]
        if self.host:
            offered = puzzles.offer_kind(kept) if ask_llm else None
            if offered:     # the model offered one: a "yes" now starts that kind
                self.host.offered = offered
            if not ask_llm:     # the model has not read this exchange: let it, while the book's words play
                self.prime([{"role": "system", "content": SYSTEM_PROMPT}] + self.history, "chat")
        # wait for the audio to start so the metrics include it
        for _ in range(200):
            if "first_audio" in t or gen != self.gen:
                break
            time.sleep(0.05)
        if gen == self.gen and "first_audio" not in t:   # nothing voiced (TTS failed, or nothing speakable)
            self.lines[row][1] = reply
            self.set_state("READY", self.source_desc)
        asr_s = t["asr"] - t["t0"]
        ttft_s = t.get("ttft", time.time()) - t["asr"]
        fa = t.get("first_audio")
        self.metrics = (f"hear {asr_s:.1f}s · think {ttft_s:.1f}s · first word "
                        f"{(fa - t['t0']) if fa else 0:.1f}s · " +
                        (f"{timings.get('predicted_per_second', 0):.1f} tok/s" if ask_llm else "puzzle book"))
        self.dirty = True
        # log once the whole reply has been voiced (or cut off), so every stall is in it
        while gen == self.gen and len(t.get("tts", [])) < t["pieces"]:
            time.sleep(0.1)
        self.log.write(json.dumps({"time": time.strftime("%F %T"), "user": user, "reply": reply,
                                   "raw": raw_reply.strip(), "gaps": t.get("gaps", 0),
                                   "gap_s": round(t.get("gap_s", 0.0), 2), "gap_at": t.get("gap_at", []),
                                   "tts": t.get("tts", []), "preroll_s": PREROLL_S,
                                   "asr_s": round(asr_s, 2), "ttft_s": round(ttft_s, 2),
                                   "first_audio_s": round(fa - t["t0"], 2) if fa else None,
                                   "tok_s": timings.get("predicted_per_second"), "ctx": [self.ctx_used, self.n_ctx],
                                   "bat": [self.bat_pct, round(self.bat_w, 2) if self.bat_w is not None else None],
                                   "voice": self.voice, "llm": ask_llm,
                                   "puzzle": self.host.status() if self.host else None,
                                   "model": MODEL_LABEL}) + "\n")
        self.log.flush()

    def stream_reply(self, gen, user_msg, row, t, max_tokens, guard=None, sentences=0, book=False):
        """Ask the model, speaking each sentence as it is written. guard: the open puzzle; a sentence that
        names its answer is dropped, unspoken and out of the history. sentences: stop after this many (the
        rest is not generated). A sentence cut off by max_tokens is never spoken. book: ENIGMA; a sentence in
        which the model starts making up a puzzle of its own ends the reply (the puzzle book takes over).
        Returns (reply, kept, timings, msgs, invented)."""
        self.reread_note("chat", SYSTEM_PROMPT, self.history)
        self.history = self.fit(self.history, SYSTEM_PROMPT, user_msg, max_tokens)
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history + [{"role": "user", "content": user_msg}]
        body = {"messages": msgs, "stream": True, "temperature": TEMPERATURE, "top_p": 0.9,
                "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(LLM_URL + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        reply, kept, pending, first, timings, finish = "", "", "", True, {}, None
        state = {"done": False, "invented": False, "n": 0}

        def say(s):
            nonlocal kept
            if state["done"]:
                return
            if book and puzzles.INVENTED.search(s):
                self.ev(f"the model began a puzzle of its own; the book takes over: {s!r}")
                state["done"] = state["invented"] = True
                return
            if guard and puzzles.leaks(clean_for_speech(s), guard):
                self.ev(f"dropped a sentence that gives the answer away: {s!r}")
                return
            kept += s + " "
            t["pieces"] += self.speak(gen, s, t, row)
            state["n"] += len(re.findall(r"[.!?…]+(?=\s|$)", s))
            if sentences and state["n"] >= sentences:
                state["done"] = True

        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:   # e.g. the conversation no longer fits the context window
            raise RuntimeError(self.llm_error(e.read())) from None
        with resp as r:
            for raw in r:
                if gen != self.gen or state["done"]:
                    break  # closing the response makes llama-server stop generating
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data: ") or line == "data: [DONE]":
                    continue
                ev = json.loads(line[6:])
                if "error" in ev:
                    raise RuntimeError(self.llm_error(line[6:]))
                timings = ev.get("timings") or timings
                for ch in ev.get("choices", []):
                    finish = ch.get("finish_reason") or finish
                    piece = ch.get("delta", {}).get("content") or ""
                    if not piece:
                        continue
                    if "ttft" not in t:
                        t["ttft"] = time.time()   # still THINKING: SPEAKING starts with the audio
                    reply += piece
                    pending += piece
                    sents, pending = split_sentences(pending, first)
                    for s in sents:
                        say(s)
                        first = False
        # the last piece: spoken if the model finished it, dropped if the token limit cut it off mid-sentence
        if gen == self.gen and pending.strip() and not state["done"]:
            if finish == "length" and not re.search(r"[.!?…][\"')\]]*\s*$", pending):
                self.ev(f"dropped an unfinished sentence: {pending.strip()!r}")
            else:
                say(pending)
        return reply, kept.strip(), timings, msgs, state["invented"]

    def llm_error(self, body):
        """The LLM server's error message; a context overflow also pins the meter at the size it asked for."""
        try:
            msg = json.loads(body)["error"]["message"]
        except Exception:
            msg = body.decode(errors="replace") if isinstance(body, bytes) else str(body)
        m = CTX_FULL.search(msg)
        if m:
            self.ctx_used, self.dirty = int(m.group(1)), True
            msg = f"the context window is full ({int(m.group(1)):,} of {self.n_ctx:,} tokens): START for a new chat"
        return msg

    # -- context budget
    def take_timings(self, tm, msgs, reply, mode):
        """After a request: the tokens now in the window, and the tokens-per-character rate for estimates."""
        used = tm.get("cache_n", 0) + tm.get("prompt_n", 0) + tm.get("predicted_n", 0)
        self.kv_mode = mode
        if used:
            self.ctx_used, self.dirty = used, True
            self.tpc = min(0.6, max(0.15, used / (msgs_chars(msgs) + len(reply))))

    def fit(self, history, system, new_msg, max_tokens, background=False):
        """The history to send so that prompt + reply stay within CTX_TRIM of the window. background: the cut
        is read by a prime while the game talks, so the status line does not announce a wait."""
        if CTX_MODE == "endurance" or not self.n_ctx:
            return history
        est = lambda h: int(msgs_chars([{"content": system}] + h) * self.tpc)
        need = est(history + [{"content": new_msg}]) + max_tokens
        if need <= CTX_TRIM * self.n_ctx:
            return history
        kept = history
        while kept and est(kept) > CTX_KEEP * self.n_ctx:
            kept = kept[2:]
        tokens, dropped = est(kept), (len(history) - len(kept)) // 2
        if not dropped:          # nothing left to forget: the request goes as is
            return history
        self.ev(f"context budget: {need} > {CTX_TRIM:.0%} of {self.n_ctx}: dropped {dropped} exchanges, "
                f"kept {len(kept) // 2} (~{tokens} tokens)")
        self.add("sys", f"memory full: forgot the oldest {dropped} exchanges, re-reading the last "
                        f"{len(kept) // 2} (~{tokens:,} tokens, ~{tokens / PREFILL_TPS:.0f} s)")
        if not background:
            self.set_state("THINKING", f"re-reading memory (~{tokens / PREFILL_TPS:.0f} s)")
        return kept

    def reread_note(self, mode, system, history):
        """Switching between chat and game: the server holds the other mode's prompt and reads this one again."""
        if self.kv_mode != mode and history:
            s = msgs_chars([{"content": system}] + history) * self.tpc / PREFILL_TPS
            if s > 3:
                self.set_state("THINKING", f"re-reading {'our conversation' if mode == 'chat' else 'the game'} "
                                           f"(~{s:.0f} s)")

    def prime(self, msgs, mode):
        """Read a prompt ahead, while the answer is being spoken, so the next request only reads the player's
        new words (single slot: this replaces whatever the server held)."""
        def run():
            try:
                r = http_json(LLM_URL + "/v1/chat/completions", {"messages": msgs, "max_tokens": 1,
                              "chat_template_kwargs": {"enable_thinking": False}}, timeout=300)
                tm = r.get("timings") or {}
                if (mode == "game") == (self.game is not None):
                    self.take_timings(tm, msgs, "", mode)
                self.ev(f"primed {mode}: {tm.get('prompt_n', 0)} new tokens in {tm.get('prompt_ms', 0) / 1000:.1f}s")
            except Exception as e:
                self.ev(f"prime {mode} failed: {e!r}")
        threading.Thread(target=run, daemon=True).start()

    # -- Zork
    def start_game(self, gen, num, t):
        name, title = GAMES.get(num, GAMES["1"])
        story = os.path.join(GAME_DIR, name + ".z3")
        if not os.path.exists(story) or not os.access(DFROTZ, os.X_OK):
            self.add("sys", f"{title} is not installed ({story}, {DFROTZ})")
            self.set_state("READY", self.source_desc)
            return
        if self.game:
            self.leave_game(None)
        with self.game_lock:
            self.game = ZGame(story, DFROTZ, os.path.join(GAME_DIR, "saves"))
        self.game_title, self.game_last, self.game_history = title, self.game.intro, []
        self.game_system = GAME_SYSTEM.format(title=title)
        self.ctx_saved, self.ctx_used, self.metrics = self.ctx_used, 0, ""
        self.ev(f"game: started {title}")
        self.speak_game(gen, self.game.intro, t)
        if os.path.exists(os.path.join(GAME_DIR, "saves", name + ".qzl")):
            t["pieces"] += self.speak(gen, "You have a saved game. Say restore to pick it up.", t,
                                      self.add("host", ""))
        self.prime_game()

    def leave_game(self, msg, save=True):
        """Back to chat; the game is saved first (Zork's own save file, "restore" brings it back)."""
        with self.game_lock:
            g, self.game = self.game, None
            if g and save and g.alive():
                try:
                    g.send("save")
                except GameOver:
                    pass
            if g:
                g.close()
        self.ev(f"game: left {self.game_title}")
        self.ctx_used, self.ctx_saved = self.ctx_saved, 0
        self.game_history, self.game_last = [], ""
        self.dirty = True
        if msg:
            self.speak_now(msg, self.add("host", ""))
        if self.history:
            self.prime([{"role": "system", "content": SYSTEM_PROMPT}] + self.history +
                       [{"role": "user", "content": ""}], "chat")

    def game_send(self, cmd):
        with self.game_lock:
            if not self.game:
                raise GameOver()
            return self.game.send(cmd)

    def prime_game(self):
        self.game_history = self.fit(self.game_history, self.game_system, f"Game:\n{self.game_last}\n\nPlayer:",
                                     GAME_MAX_TOKENS, background=True)
        self.prime([{"role": "system", "content": self.game_system}] + self.game_history +
                   [{"role": "user", "content": f"Game:\n{self.game_last}\n\nPlayer:"}], "game")

    def translate(self, gen, user):
        """The player's words as game commands, by the LLM ({"commands": [...]}, see CMD_GRAMMAR)."""
        msg = f"Game:\n{self.game_last}\n\nPlayer: {user}"
        self.reread_note("game", self.game_system, self.game_history)
        self.game_history = self.fit(self.game_history, self.game_system, msg, GAME_MAX_TOKENS)
        msgs = [{"role": "system", "content": self.game_system}] + self.game_history + \
               [{"role": "user", "content": msg}]
        body = {"messages": msgs, "temperature": 0.2, "max_tokens": GAME_MAX_TOKENS, "grammar": CMD_GRAMMAR,
                "chat_template_kwargs": {"enable_thinking": False}}
        try:
            r = http_json(LLM_URL + "/v1/chat/completions", body, timeout=300)
        except urllib.error.HTTPError as e:
            raise RuntimeError(self.llm_error(e.read())) from None
        content = r["choices"][0]["message"].get("content") or ""
        self.take_timings(r.get("timings") or {}, msgs, content, "game")
        try:
            cmds = json.loads(content)["commands"]
        except (ValueError, KeyError, TypeError):
            cmds = []
        cmds = [re.sub(r"\s+", " ", c).strip() for c in cmds if isinstance(c, str) and re.search(r"[a-z]", c, re.I)][:4]
        self.ev(f"game: LLM {user!r} -> {cmds}")
        return cmds

    def speak_game(self, gen, text, t):
        """Read the game's words aloud; the transcript line fills in as they are heard."""
        speech = ZGame.speech(text)
        row = self.live = self.add("game", "")
        chunks, rest = split_sentences(speech + "\n", True)
        if rest.strip():
            chunks.append(rest.strip())
        t["pieces"] = t.get("pieces", 0) + sum(self.speak(gen, c, t, row) for c in chunks)
        self.live = None
        self.last_reply = clean_for_speech(speech)
        if not t["pieces"]:
            self.lines[row][1] = speech

    def game_turn(self, gen, user, t):
        if not self.game:
            m = GAME_START.search(user)
            return self.start_game(gen, GAME_NUM.get((m.group(2) or "1").lower(), "1"), t)
        if GAME_EXIT.search(user):
            self.leave_game(f"{self.game_title} saved. Say play Zork to pick up where you left off.")
            return
        cmd, cmds, out, t_llm, ended = direct_command(user), [], "", None, False
        try:
            if cmd:
                out = self.game_send(cmd)
                if ZGame.parser_failed(out):
                    self.ev(f"game: {cmd!r} -> {out!r}, asking the LLM")
                else:
                    cmds = [cmd]
            if not cmds:
                t1 = time.time()
                cmds = self.translate(gen, user)
                t_llm = time.time() - t1
                if gen != self.gen:
                    return
                out = "\n\n".join(self.game_send(c) for c in cmds)
        except GameOver:
            ended = True
        t["pieces"] = 0
        if cmds:
            self.add("sys", "> " + ". ".join(cmds))
            self.game_history += [{"role": "user", "content": f"Game:\n{self.game_last}\n\nPlayer: {user}"},
                                  {"role": "assistant", "content": json.dumps({"commands": cmds})}]
            self.game_last = out
            if out:
                self.speak_game(gen, out, t)
        elif not ended:
            t["pieces"] = self.speak(gen, "I didn't hear a move there. Try things like look around, go north, or "
                                          "take the lamp.", t, self.add("host", ""))
        if ended or not (self.game and self.game.alive()):
            self.leave_game(f"The game is over. Say play Zork to start again.", save=False)
        elif cmds:
            self.prime_game()
        for _ in range(200):   # the metrics include the first word heard
            if "first_audio" in t or gen != self.gen or not t["pieces"]:
                break
            time.sleep(0.05)
        if gen == self.gen and t["pieces"] and "first_audio" not in t:
            self.set_state("READY", self.source_desc)
        elif not t["pieces"]:
            self.set_state("READY", self.source_desc)
        fa = t.get("first_audio")
        asr_s = t["asr"] - t["t0"]
        self.metrics = (f"hear {asr_s:.1f}s · " + (f"understand {t_llm:.1f}s" if t_llm is not None else "direct") +
                        (f" · first word {fa - t['t0']:.1f}s" if fa else ""))
        self.dirty = True
        self.log.write(json.dumps({"time": time.strftime("%F %T"), "mode": "game", "game": self.game_title,
                                   "user": user, "direct": t_llm is None, "cmds": cmds, "out": out,
                                   "room": self.game.room if self.game else "",
                                   "score": self.game.score if self.game else "",
                                   "asr_s": round(asr_s, 2), "llm_s": round(t_llm, 2) if t_llm is not None else None,
                                   "first_audio_s": round(fa - t["t0"], 2) if fa else None,
                                   "ctx": [self.ctx_used, self.n_ctx],
                                   "bat": [self.bat_pct, round(self.bat_w, 2) if self.bat_w is not None else None],
                                   "voice": self.voice, "model": MODEL_LABEL}) + "\n")
        self.log.flush()

    def poll_battery(self):
        d = self.bat_dir
        try:
            pct = int(sysfs(d, "capacity"))
            w = int(sysfs(d, "voltage_now")) * abs(int(sysfs(d, "current_now"))) / 1e12
        except (TypeError, ValueError):
            return
        self.bat_w = w if self.bat_w is None else self.bat_w + 0.15 * (w - self.bat_w)
        self.bat_pct, self.bat_status, self.dirty = pct, sysfs(d, "status"), True

    def poll_jack(self, now):
        """A headset plugged in or pulled while idle: pick the mic again, so the status line is right before
        the next press (it kept saying "no mic" until B was pressed). Waits a second for PipeWire's ports."""
        ins = headset_mic_inserted()
        if ins != self.jack_ins:
            self.jack_ins, self.jack_due = ins, now + 1.0
        if self.jack_due and now >= self.jack_due and self.state == "READY" and not os.environ.get("RV_SOURCE"):
            self.jack_due = 0.0
            self.source, self.source_desc = pick_source()
            self.mic.ensure(self.source) if self.source else self.mic.close()
            self.ev(f"jack changed: {self.source_desc}")
            self.set_state("READY", self.source_desc)

    # -- controls
    def ptt_down(self):
        self.interrupt()
        if self.mic.alive():
            self.mic.start()          # mark first: the source check below takes a moment
        self.source, self.source_desc = pick_source()
        if not self.source:
            self.mic.close()
            self.add("sys", self.source_desc)
            self.set_state("READY", self.source_desc)
            return
        was = self.mic.source
        self.mic.ensure(self.source)
        self.rec_start = time.time()
        if self.mic.mark is None or was != self.source:
            self.mic.start()
        self.set_state("LISTENING", "" if self.mic.alive() else "mic warming up…")

    def ptt_up(self):
        if self.state != "LISTENING":
            return
        pcm = self.mic.stop()
        self.level = 0.0
        if len(pcm) < MIN_REC_S * MIC_RATE * 2:
            msg = "too short: hold the button while you talk" if self.mic.alive() else \
                "the mic delivered no audio (is the headset plugged in?)"
            self.set_state("READY", msg)
            return
        a = array.array("h", pcm[: len(pcm) // 2 * 2])
        peak = max((abs(x) for x in a), default=0)
        self.save_utterance(pcm)
        if peak < 64:
            self.add("sys", "(the mic sent silence)")
            self.set_state("READY", self.source_desc)
            return
        self.work_q.put((self.gen, "wav", pcm_to_wav(pcm, MIC_RATE)))

    def save_utterance(self, pcm):
        try:
            d = os.path.join(LOG_DIR, "utt")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, time.strftime("utt_%H%M%S.wav")), "wb") as f:
                f.write(pcm_to_wav(pcm, MIC_RATE))
            for old in sorted(os.listdir(d))[:-30]:
                os.remove(os.path.join(d, old))
        except OSError:
            pass

    def handle(self, ev):
        kind = ev[0]
        self.ev(f"event {ev}")
        if kind == "sys":
            self.add("sys", ev[1])
            return
        if kind == "btn":
            name, val = ev[1], ev[2]
            (self.held.add if val else self.held.discard)(name)
            if name in ("south", "r1"):
                if val:
                    if self.state not in ("LISTENING", "HEARING", "THINKING") and len({"south", "r1"} & self.held) == 1:
                        self.ptt_down()
                elif not ({"south", "r1"} & self.held):
                    self.ptt_up()
            elif val and name == "east":
                self.interrupt()
                self.set_state("READY", "stopped")
            elif val and name == "north":
                self.cycle_voice()
            elif val and name == "west" and self.last_reply:
                self.interrupt()
                self.speak_now(self.last_reply)
            elif val and name == "start":
                if "select" in self.held:
                    self.running = False
                else:
                    self.new_chat()
            elif val and name == "home":
                self.running = False
            elif val and name in ("up", "down"):
                self.scroll = max(0, self.scroll + (3 if name == "up" else -3))
                self.dirty = True
            return
        cmd, arg = ev[1], ev[2]
        if cmd == "ptt_down":
            self.ptt_down()
        elif cmd == "ptt_up":
            self.ptt_up()
        elif cmd == "inject":
            self.interrupt()
            try:
                with open(arg, "rb") as f:
                    self.work_q.put((self.gen, "wav", f.read()))
            except OSError as e:
                self.add("sys", f"inject: {e}")
        elif cmd == "say":
            self.interrupt()
            self.work_q.put((self.gen, "text", arg))
        elif cmd == "stop":
            self.interrupt()
            self.set_state("READY", "stopped")
        elif cmd == "voice":
            self.cycle_voice(arg or None)
        elif cmd == "repeat" and self.last_reply:
            self.interrupt()
            self.speak_now(self.last_reply)
        elif cmd == "new":
            self.new_chat()
        elif cmd == "quit":
            self.running = False

    def voice_label(self):
        if self.voice_pref != "random":
            return self.voice if self.player else self.voice_pref
        return f"{self.voice} (random)" if self.player else "random"     # not picked before the voices are known

    def cycle_voice(self, name=None):
        """Next voice; after the last one comes "random": a different voice every session. The choice is
        kept in prefs.json and used at the next start."""
        order = self.voices + ["random"]
        if name and name in order:
            pick = name
        else:
            cur = "random" if self.voice_pref == "random" else self.voice
            pick = order[(order.index(cur) + 1) % len(order)] if cur in order else order[0]
        self.voice_pref = pick
        if pick == "random":
            self.voice = random.choice([v for v in self.voices if v != self.voice] or self.voices)
            line = f"Random voice. This time, {self.voice}."
        else:
            self.voice, line = pick, f"Voice {pick}."
        self.prefs["voice"] = pick
        save_prefs(self.prefs)
        self.interrupt()
        self.speak_now(line)
        self.add("sys", f"voice: {self.voice_label()}")

    def new_chat(self):
        self.interrupt()
        if self.game:
            self.leave_game(None)
        self.history, self.lines, self.last_reply = [], [], ""
        self.ctx_used = self.ctx_base
        self.trivia_active = None
        if self.host:
            self.host = puzzles.Session(self.book)
            self.host.offered = True        # "Shall I give you a puzzle?" - a yes starts one
        self.speak_now(PERSONA["fresh"], self.add("host", ""))
        self.set_state("READY", self.source_desc)

    # -- UI
    (G, DIM, AMB, CYN), RED, RST = PERSONA["colors"], "\033[38;5;203m", "\033[0m"

    def render(self):
        cols, rows = shutil.get_terminal_size((100, 30))
        out = ["\033[H\033[2J\033[?25l"]
        title = PERSONA["title"] + PERSONA["subtitle"]
        right = f"voice: {self.voice_label()}  ·  {MODEL_LABEL} "
        if self.bat_pct is not None and cols - len(title) - len(right) - 3 < 28:   # narrow: the meter wins
            title = PERSONA["title"]
        bat, bat_len = self.battery_meter(cols - len(title) - len(right) - 3)
        out.append(self.G + "\033[1m" + title + self.RST + self.DIM +
                   right.rjust(max(0, cols - len(title) - bat_len)) + self.RST + bat + "\n")
        out.append(self.DIM + "─" * cols + self.RST + "\n")
        body_h = rows - 9
        wrapped = []
        for n, (who, text) in enumerate(self.lines):
            color, tag = {"you": (self.AMB, "YOU" + "›".rjust(len(PERSONA["name"]) - 2)),
                          "host": (self.G, PERSONA["name"] + "›"), "game": (self.G, "ZORK" + "›".rjust(len(PERSONA["name"]) - 3)),
                          "sys": (self.CYN, "  ·" + " " * (len(PERSONA["name"]) - 3))}[who]
            tag += " "
            for i, w in enumerate(textwrap.wrap(text or "…", max(20, cols - 8)) or [""]):
                wrapped.append(color + (tag if i == 0 else " " * len(tag)) + w + self.RST)
            if not (who == "sys" and n + 1 < len(self.lines) and self.lines[n + 1][0] == "sys"):
                wrapped.append("")      # status lines sit together
        end = max(0, len(wrapped) - self.scroll)
        view = wrapped[max(0, end - body_h): end]
        out.append("\n".join(view) + "\n" * (body_h - len(view) + 1))
        out.append(self.DIM + "─" * cols + self.RST + "\n")
        spin = "◐◓◑◒"[int(time.time() * 6) % 4]
        if self.state == "LISTENING":
            n = int(self.level * 30)
            st = f"{self.RED}● LISTENING {self.G}{'▮' * n}{self.DIM}{'▯' * (30 - n)}{self.RST}  " \
                 f"{time.time() - self.rec_start:4.1f}s   release to send"
        elif self.state in ("HEARING", "THINKING"):
            st = f"{self.G}{spin} {self.state}…{self.RST} {self.note}"
        elif self.state == "SPEAKING" or (self.player and self.player.speaking()):
            st = f"{self.G}♪ SPEAKING{self.RST}   [A] to stop"
        elif self.state == "BOOT":
            st = f"{self.G}{spin} BOOTING{self.RST} {self.note}"
        elif self.state == "ERROR":
            st = f"{self.RED}✖ {self.note}{self.RST}"
        elif self.game:
            st = f"{self.G}▶ {self.game_title}{self.RST}  {self.game.room}   {self.DIM}{self.game.score}{self.RST}" \
                 f"   hold [B] to talk"
        else:
            mic = self.note if self.note else self.source_desc
            ask = "hold [B] or [R1] to talk   " if self.source else ""      # no mic: nothing to hold a button for
            st = f"{self.G}▶ READY{self.RST}   {ask}{self.DIM}{mic}{self.RST}"
            if self.host and self.host.status():
                st = f"{self.G}▶ {self.host.status()}{self.RST}   {ask}{self.DIM}{mic}{self.RST}"
        hints = "[B]/[R1] hold: talk   [A] stop   [X] voice   [Y] repeat   [START] new chat   [SELECT+START] quit"
        if self.state in ("BOOT", "ERROR"):
            hints = "[SELECT+START] quit"       # nothing else works before the model is loaded
        out.append(st + "\n\n")
        out.append(self.DIM + hints + self.RST + "\n\n")
        out.append(self.bottom_line(cols))
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        self.dirty = False

    def battery_meter(self, room):
        """Battery meter for the top right corner, as (text, visible length); fits in `room` columns."""
        if self.bat_pct is None:
            return "", 0
        pct = self.bat_pct
        if self.bat_status in ("Charging", "Full"):
            tail = f" {pct}% {self.bat_status.lower()} "
        else:
            tail = f" {pct}% · {self.bat_w:.1f} W "
        head = " ·  battery "
        cells = min(10, room - len(head) - len(tail))
        if cells < 4:                        # narrow screen: just the number
            head, cells = " · ", 0
        n = min(cells, round(pct * cells / 100))
        color = self.G if pct > 50 or self.bat_status in ("Charging", "Full") else self.AMB if pct > 20 else self.RED
        text = f"{self.DIM}{head}{color}{'▮' * n}{self.DIM}{'▯' * (cells - n)}{color}{tail}{self.RST}"
        return text, len(head) + cells + len(tail)

    def bottom_line(self, cols):
        """Turn metrics on the left, context window meter in the lower right corner."""
        if not self.n_ctx:
            return self.DIM + self.metrics + self.RST
        frac = self.ctx_used / self.n_ctx
        count = f" {self.ctx_used:,} / {self.n_ctx:,}"
        left = self.metrics
        cells = min(20, max(6, cols - 1 - len(left) - 2 - len("context ") - len(count)))
        if len(left) + 2 + len("context ") + cells + len(count) > cols - 1:   # narrow screen: meter wins
            left = ""
        n = min(cells, round(frac * cells))
        color = self.G if frac < 0.6 else self.AMB if frac < 0.85 else self.RED
        meter = f"{self.DIM}context {color}{'▮' * n}{self.DIM}{'▯' * (cells - n)}{color}{count}{self.RST}"
        pad = cols - 1 - len(left) - len("context ") - cells - len(count)
        return self.DIM + left + self.RST + " " * pad + meter

    def main(self):
        self.add("sys", f"v{VERSION} brought to you by mercurious assisted by claude")
        InputThread(self.q).start()
        threading.Thread(target=self.speaker_loop, daemon=True).start()
        threading.Thread(target=self.work_loop, daemon=True).start()
        booter = threading.Thread(target=self.boot, daemon=True)
        booter.start()
        last, self.jack_t = 0.0, 0.0
        try:
            while self.running:
                try:
                    ev = self.q.get(timeout=0.08)
                    if self.state != "BOOT" or ev[0] == "ctl" and ev[1] == "quit":
                        self.handle(ev)
                    elif ev[0] == "sys":
                        self.add("sys", ev[1])
                    elif ev[0] == "btn":      # before the model is loaded only quitting works
                        (self.held.add if ev[2] else self.held.discard)(ev[1])
                        if ev[2] and (ev[1] == "home" or ev[1] == "start" and "select" in self.held):
                            self.running = False
                except queue.Empty:
                    pass
                self.captions_tick()
                if self.state == "SPEAKING" and self.live is None and self.player and not self.player.speaking() \
                        and self.tts_q.empty() and not self.tts_busy:
                    self.set_state("READY", self.source_desc)
                now = time.time()
                if now - self.jack_t >= 1 and self.state != "BOOT":
                    self.jack_t = now
                    self.poll_jack(now)
                if self.bat_dir and now - self.bat_t >= 2:
                    self.bat_t = now
                    self.poll_battery()
                animated = self.state in ("LISTENING", "HEARING", "THINKING", "BOOT")
                if not HEADLESS and (self.dirty or animated) and now - last > 0.1:
                    self.render()
                    last = now
        finally:
            self.running = False
            if self.game:
                self.leave_game(None)
            if self.player:
                self.player.close()
            self.mic.close()
            if not HEADLESS:
                sys.stdout.write("\033[0m\033[?25h\033[H\033[2J")
                sys.stdout.flush()


if __name__ == "__main__":
    App().main()
