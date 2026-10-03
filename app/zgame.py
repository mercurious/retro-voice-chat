"""zgame: an Infocom story file (Zork I-III) running in dfrotz, driven one command at a time.

dfrotz is Frotz's text-only interface. Started with -m (no MORE prompts) and a 255-column screen it
prints, per command, an optional status line (" West of House ...  Score: 0  Moves: 3"), the game's
response and then the ">" prompt, which is how a response is known to be complete.
Stdlib only, like retrovoice.
"""
import os, re, select, subprocess, time

GAMES = {"1": ("zork1", "Zork I"), "2": ("zork2", "Zork II"), "3": ("zork3", "Zork III")}

WIDTH = 255   # dfrotz's maximum; longer paragraphs are wrapped and joined again in _clean()
STATUS = re.compile(r"^ (\S.*?) {10,}(\S.*?)\s*$")   # padded to the screen width; only it starts with one space
FILE_PROMPT = re.compile(r"Please enter a filename \[[^\]]*\]: ")
OVERWRITE = "Overwrite existing file? "
# The Infocom parser's complaints (gparser.zil): the command was not understood, and no time passed.
PARSER_FAIL = re.compile(
    r"^(I don't know the word|I beg your pardon|Beg pardon|That sentence isn't one I recognize|"
    r"There was no verb in that sentence|There seems to be a noun missing|There were too many nouns|"
    r"You used the word .* in a way that I don't understand|I couldn't understand that sentence|"
    r"What do you want to |I don't understand! What are you referring to|You can't use multiple |"
    r"I don't see what you're referring to|That question can't be answered|It's difficult to repeat)")
# printed once at the start; shown on screen, not read aloud
BANNER_QUIET = re.compile(r"^(Copyright \(c\)|ZORK is a registered trademark|Release \d+ / Serial number)")


class GameOver(Exception):
    pass


class ZGame:
    def __init__(self, story, dfrotz, save_dir):
        story, dfrotz, save_dir = (os.path.abspath(x) for x in (story, dfrotz, save_dir))
        os.makedirs(save_dir, exist_ok=True)
        self.name = os.path.splitext(os.path.basename(story))[0]
        self.room, self.score = "", ""
        self.eof = False
        self.proc = subprocess.Popen([dfrotz, "-m", "-p", "-q", "-x", "-w", str(WIDTH), "-h", "255", "-Z", "0",
                                      "-R", ".", story], cwd=save_dir, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.intro = self._clean(self._read())

    def alive(self):
        return not self.eof and self.proc.poll() is None

    def send(self, command):
        """Run one command line; returns the game's response. Save/restore file questions are answered with
        the default file name (saves go to save_dir), and saving over the previous save is allowed."""
        if not self.alive():
            raise GameOver()
        self._write(command)
        raw = self._read()
        while True:
            if raw.endswith(OVERWRITE):
                self._write("y")
            elif raw.endswith("]: ") and FILE_PROMPT.search(raw[-80:]):
                self._write("")
            else:
                break
            raw += self._read()
        raw = FILE_PROMPT.sub("", raw).replace(OVERWRITE, "")
        return self._clean(raw)

    def close(self):
        if self.alive():
            self.proc.kill()
        self.proc.wait()

    # -- internals
    def _write(self, line):
        try:
            self.proc.stdin.write((line.replace("\n", " ") + "\n").encode("ascii", "replace"))
        except (BrokenPipeError, OSError):
            raise GameOver() from None

    def _read(self, timeout=15.0):
        """Output up to the next prompt: ">" or a file question, followed by a short silence."""
        buf, fd, t_end = b"", self.proc.stdout.fileno(), time.time() + timeout
        while time.time() < t_end:
            text = buf.decode("latin-1")
            waiting = text.endswith(">") or text.endswith(OVERWRITE) or text.endswith("]: ")
            r, _, _ = select.select([fd], [], [], 0.03 if waiting else 0.2)
            if not r:
                if waiting:
                    break
                if not self.alive():
                    break
                continue
            chunk = os.read(fd, 65536)
            if not chunk:
                self.eof = True
                break
            buf += chunk
        text = buf.decode("latin-1")
        if not buf and not self.alive():
            raise GameOver()
        return text

    def _clean(self, raw):
        """Status line into .room/.score, drop the prompt, join lines dfrotz wrapped at the screen width."""
        out = []
        for line in raw.replace("\r", "").split("\n"):
            m = STATUS.match(line) if len(line) >= 100 else None
            if m:
                self.room, self.score = m.group(1), re.sub(r"\s+", " ", m.group(2))
                continue
            if line.startswith(">"):
                line = line[1:]
            if out and len(out[-1]) >= WIDTH - 20 and line.strip():
                out[-1] += " " + line.strip()    # a paragraph wider than the screen
            else:
                out.append(line.rstrip())
        text = "\n".join(out).strip("\n")
        return re.sub(r">\s*$", "", text).rstrip()

    @staticmethod
    def parser_failed(text):
        return bool(PARSER_FAIL.match(text.strip()))

    @staticmethod
    def speech(text):
        """The response as sentences to read aloud: every line ends like a sentence (a room name is its own
        line), and the copyright lines of the opening banner are left out."""
        parts = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or BANNER_QUIET.match(line):
                continue
            parts.append(line if line[-1] in ".!?:;,\"')" else line + ".")
        return " ".join(parts)
