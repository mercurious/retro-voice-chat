"""Word puzzles for ENIGMA (retrovoice.py, RV_PERSONA=enigma).

A small language model cannot be trusted to invent a letter puzzle: it reads words in chunks, not letters,
so its anagrams drop letters and its "change one letter" answers change two. Here the code makes and checks
every puzzle, and the model only hosts. Two sources:
  - generators: letter operations (anagram, change / drop / add a letter, reversal, starts-and-ends,
    two-step chains) between a common word and a member of a hand-checked category list. Each answer is
    verified, and unique within its category, before the puzzle is offered.
  - the bank (puzzle/bank/*.json): original puzzles written ahead of time in the style of radio puzzle
    segments, each with a mechanical check that test/test_puzzles.py runs (puzzle/bank_check.py).
A puzzle is a dict: clue (spoken exactly), answer, accept (other right answers), hints (one at a time),
reveal (spoken when the player gives up), level 1-3. A round is a themed set of quick ones read back to back.
Stdlib only.
"""
import json, os, random, re

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "puzzle")
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def words(name):
    try:
        return [w.strip() for w in open(os.path.join(DIR, name)) if w.strip() and not w.startswith("#")]
    except OSError:
        return []


def spell(word):
    """How a word is spelled out loud: "B-E-A-R". Pocket TTS says each capital letter by name."""
    return "-".join(c.upper() for c in word if c.isalpha())


def say_word(word):
    """A word as the host gives it: the word, then its spelling, since puzzles turn on letters and a spoken
    word can be heard as its homophone (bear / bare)."""
    return f"{word.capitalize()}, {spell(word)}"


def letter_name(c):
    """A single letter as the host says it (the app's TTS step turns "the letter M" into "the letter em")."""
    return f"the letter {c.upper()}"


def article(word):
    return "an" if word[0] in "aeiou" else "a"


class Lexicon:
    def __init__(self):
        self.common = set(words("common.txt"))
        self.valid = self.common | set(words("extra.txt"))
        self.block = set(words("block.txt"))
        try:
            raw = json.load(open(os.path.join(DIR, "categories.json")))
        except (OSError, ValueError):
            raw = {}
        self.cats = {}
        obscure, weak = set(raw.get("_obscure", [])), raw.get("_weak", {})
        for name, c in raw.items():
            if name.startswith("_"):
                continue
            members = sorted({m for m in c["members"]})
            # answers: single words a solver can be expected to know, and fairly in the category
            fair = [m for m in members if m.isalpha() and m not in obscure and m not in weak.get(name, ())]
            self.cats[name] = {"name": name, "singular": c["singular"], "plural": c["plural"], "members": members,
                               "single": fair, "all": set(members)}
        self.by_letters = {}
        for w in self.common:
            if w not in self.block:
                self.by_letters.setdefault("".join(sorted(w)), []).append(w)
        self._drop_keys = None

    def drop_keys(self):
        """Sorted letters of each common word minus one letter -> those words (for drop-and-rearrange)."""
        if self._drop_keys is None:
            dk = {}
            for w in self.common:
                if 4 <= len(w) <= 9 and w not in self.block:
                    for d in drops(w):
                        dk.setdefault("".join(sorted(d)), set()).add(w)
            self._drop_keys = dk
        return self._drop_keys

    def ok_source(self, w, answer):
        """A word the host may give out: common, clean, and not just the answer with an ending."""
        if w not in self.common or w in self.block or w == answer:
            return False
        if w.startswith(answer) or answer.startswith(w):    # pears -> pear, plum -> plums: no puzzle in that
            return False
        n = 0
        while n < min(len(w), len(answer)) and w[n] == answer[n]:
            n += 1
        if len(answer) >= 6 and n >= len(answer) - 1:      # recorded -> recorder: only the ending differs
            return False
        return True


# ---------------------------------------------------------------------------------------- operations

def one_change(a, b):
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) == 1


def one_drop(a, b):
    """b is a with one letter taken out."""
    return len(a) == len(b) + 1 and any(a[:i] + a[i + 1:] == b for i in range(len(a)))


def is_anagram(a, b):
    return a != b and sorted(a) == sorted(b)


def changes(w, pool):
    out = []
    for i in range(len(w)):
        for c in LETTERS:
            if c != w[i]:
                v = w[:i] + c + w[i + 1:]
                if v in pool:
                    out.append(v)
    return out


def drops(w):
    return {w[:i] + w[i + 1:] for i in range(len(w))}


def adds(w):
    return {w[:i] + c + w[i:] for i in range(len(w) + 1) for c in LETTERS}


# Each operation: how to find source words for a category member, and how the host words it.
# single: the one-off puzzle; intro: a round's theme line ({sing} / {plural}); item: one clue in a round.
OPS = {
    "anagram": {"single": "Rearrange the letters of {W}, to name {sing}.",
                "intro": "Every answer is {sing}. I'll give you a word. Rearrange its letters to get the answer.",
                "reveal": "{A}. Rearrange the letters of {w} and you get {a}."},
    "change": {"single": "Change one letter in {W}, to get {sing}.",
               "intro": "Every answer is {sing}. I'll give you a word. Change one letter to get the answer.",
               "reveal": "{A}. Change one letter in {w} and you get {a}."},
    "drop": {"single": "Take one letter out of {W}, to get {sing}.",
             "intro": "Every answer is {sing}. I'll give you a word. Take out one letter to get the answer.",
             "reveal": "{A}. Take one letter out of {w} and you get {a}."},
    "add": {"single": "Add one letter to {W}, to get {sing}.",
            "intro": "Every answer is {sing}. I'll give you a word. Add one letter, anywhere, to get the answer.",
            "reveal": "{A}. Add one letter to {w} and you get {a}."},
    "reverse": {"single": "Spell {W}, backward to get {sing}.",
                "intro": "Every answer is {sing}. I'll give you a word. Spell it backward to get the answer.",
                "reveal": "{A}. {w} spelled backward is {a}."},
    "anadrop": {"single": "Take one letter out of {W}, then rearrange what's left, to get {sing}.",
                "intro": "Every answer is {sing}. I'll give you a word. Drop one letter and rearrange the rest "
                         "to get the answer.",
                "reveal": "{A}. Drop a letter from {w}, rearrange the rest, and you get {a}."},
}
OP_LEVEL = {"change": 1, "reverse": 1, "drop": 2, "add": 2, "anagram": 2, "anadrop": 3}


def sources(lex, op, member, cat):
    """Common words that turn into this category member by the operation, and into no other member (counting
    the obscure and weak ones too, so a player's "other" answer is never right but unaccepted)."""
    members = {m for m in cat["all"] if m.isalpha()}
    if op == "anagram":
        cands = [w for w in lex.by_letters.get("".join(sorted(member)), []) if w != member]
        ok = lambda w: not any(is_anagram(w, m) for m in members if m != member)
    elif op == "change":
        cands = changes(member, lex.common)
        ok = lambda w: not any(one_change(w, m) for m in members if m != member)
    elif op == "drop":     # source has one more letter than the answer
        cands = [w for w in adds(member) if w in lex.common]
        ok = lambda w: not any(one_drop(w, m) for m in members if m != member)
    elif op == "add":
        cands = [w for w in drops(member) if w in lex.common and len(w) >= 3]
        ok = lambda w: not any(one_drop(m, w) for m in members if m != member)
    elif op == "reverse":
        r = member[::-1]
        cands = [r] if r in lex.common and r != member else []
        ok = lambda w: True
    elif op == "anadrop":    # a plain drop is the easier puzzle: leave those to "drop"
        cands = [w for w in lex.drop_keys().get("".join(sorted(member)), ()) if not one_drop(w, member)]
        keys = {"".join(sorted(m)) for m in members if m != member}
        ok = lambda w: not any("".join(sorted(d)) in keys for d in drops(w))
    else:
        return []
    return sorted({w for w in cands if lex.ok_source(w, member) and ok(w)})


def fits(op, src, word):
    """word comes from src by the operation (a guess that "works" even if it is not the answer)."""
    if op == "anagram":
        return is_anagram(src, word)
    if op == "change":
        return one_change(src, word)
    if op == "drop":
        return one_drop(src, word)
    if op == "add":
        return one_drop(word, src)
    if op == "reverse":
        return word == src[::-1]
    if op == "anadrop":
        return any(sorted(d) == sorted(word) for d in drops(src))
    return False


def letter_hints(answer, cat=None):
    """Hints that close in: the first letter, then the length and last letter, then the pattern."""
    h = [f"It starts with {letter_name(answer[0])}."]
    h.append(f"It has {len(answer)} letters and ends in {letter_name(answer[-1])}.")
    h.append("The pattern is " + ", ".join(c.upper() if i in (0, len(answer) // 2, len(answer) - 1) else "blank"
                                           for i, c in enumerate(answer)) + ".")
    return h


def make_item(op, member, src, cat, single):
    level = OP_LEVEL[op] + (1 if len(member) >= 7 else 0) - (1 if len(member) <= 4 and op != "anadrop" else 0)
    t = OPS[op]
    fmt = {"W": say_word(src), "w": src.capitalize(), "a": member.capitalize(), "A": member.capitalize(),
           "sing": cat["singular"], "plural": cat["plural"]}
    clue = t["single"].format(**fmt) if single else f"{say_word(src)}."
    return {"kind": op, "cat": cat["name"], "source": src, "clue": clue, "answer": member, "accept": [],
            "hints": letter_hints(member, cat), "reveal": t["reveal"].format(**fmt), "level": max(1, min(3, level))}


def load_bank(path=None):
    """Every puzzle in puzzle/bank/*.json (or one file)."""
    path = path or os.path.join(DIR, "bank")
    files = [path] if path.endswith(".json") else \
        sorted(os.path.join(path, f) for f in os.listdir(path) if f.endswith(".json")) if os.path.isdir(path) else []
    bank = []
    for f in files:
        try:
            bank += json.load(open(f))
        except (OSError, ValueError):
            pass
    return bank


class Puzzles:
    def __init__(self, seed=None, bank_path=None):
        self.lex = Lexicon()
        self.rng = random.Random(seed)
        self.used = set()            # sources and answers already played this session
        self._index = {}             # (op, cat) -> [(member, [sources])], built on first use
        bank = load_bank(bank_path)
        self.bank_single = [b for b in bank if b.get("type", "single") == "single" and not b.get("challenge")]
        self.bank_rounds = [b for b in bank if b.get("type") == "round"]
        self.bank_challenge = [b for b in bank if b.get("challenge")]
        for lst in (self.bank_single, self.bank_rounds, self.bank_challenge):
            self.rng.shuffle(lst)

    # -- generator index
    def index(self, op, cat_name):
        key = (op, cat_name)
        if key not in self._index:
            cat = self.lex.cats[cat_name]
            pairs = []
            for m in cat["single"]:
                if len(m) < 3 or m in self.lex.block:
                    continue
                s = sources(self.lex, op, m, cat)
                if s:
                    pairs.append((m, s))
            self._index[key] = pairs
        return self._index[key]

    def warm(self):
        """Build every (operation, category) index ahead of the first request."""
        for op in OPS:
            for c in self.lex.cats:
                self.index(op, c)

    def fresh(self, pairs):
        return [(m, [s for s in srcs if s not in self.used]) for m, srcs in pairs
                if m not in self.used and any(s not in self.used for s in srcs)]

    def mark(self, *ws):
        self.used.update(w for w in ws if w)

    # -- picking
    def category_for(self, text):
        """The category a request names ("a puzzle about animals"), if any."""
        t = text.lower()
        for name, c in self.lex.cats.items():
            words_ = {name.replace("_", " "), c["plural"].lower(), c["singular"].lower().split(" ", 1)[-1]}
            if any(re.search(r"\b" + re.escape(w) + r"s?\b", t) for w in words_ if w):
                return name
        return None

    def single(self, level=2, cat=None, kinds=None):
        """One puzzle: a generated one or one from the bank (about a third), near the asked level."""
        if not cat and not kinds and self.bank_single and self.rng.random() < 0.5:
            for b in self.bank_single:
                if b["id"] not in self.used and b["answer"] not in self.used and abs(b.get("level", 2) - level) <= 1:
                    self.mark(b["id"], b["answer"])
                    return dict(b)
        ops = kinds or [o for o in OPS if abs(OP_LEVEL[o] - level) <= 1] or list(OPS)
        for _ in range(40):
            op = self.rng.choice(ops)
            c = cat or self.rng.choice(list(self.lex.cats))
            pairs = self.fresh(self.index(op, c))
            if not pairs:
                continue
            cand = []
            for m, srcs in pairs:
                for s in srcs:
                    it = make_item(op, m, s, self.lex.cats[c], True)
                    cand.append((abs(it["level"] - level), self.rng.random(), it))
            cand.sort(key=lambda x: (x[0], x[1]))
            it = cand[0][2]
            self.mark(it["answer"], it["source"])
            return it
        return None

    def round(self, level=2, cat=None, n=6):
        """A themed round: one operation, one category, n quick clues, easier ones first."""
        if not cat and self.bank_rounds and self.rng.random() < 0.5:     # the written rounds are the cleverer ones
            for b in self.bank_rounds:     # skipping items whose answer this session has already had
                items = [dict(i) for i in b["items"] if i["answer"] not in self.used]
                if b["id"] not in self.used and len(items) >= 5:
                    self.mark(b["id"], *(i["answer"] for i in items))
                    return {**b, "items": items}
        combos = [(op, c) for op in OPS for c in ([cat] if cat else self.lex.cats)]
        self.rng.shuffle(combos)
        best = None
        for op, c in combos:
            if op == "anadrop" and level < 3:
                continue
            pairs = self.fresh(self.index(op, c))
            if len(pairs) < n + 1:
                continue
            items, seen = [], set()
            self.rng.shuffle(pairs)
            for m, srcs in pairs:     # no clue may be another clue's answer (melon -> lemon, lemon -> melon)
                srcs = [x for x in srcs if x not in seen]
                if m in seen or not srcs:
                    continue
                it = make_item(op, m, self.rng.choice(srcs), self.lex.cats[c], False)
                seen.update((m, it["source"]))
                items.append(it)
            if len(items) < n:
                continue
            near = [i for i in items if abs(i["level"] - level) <= 1]
            if len(near) >= n:
                items = near
            self.rng.shuffle(items)
            items = sorted(items[:n], key=lambda i: (i["level"], len(i["answer"])))
            best = (op, c, items)
            break
        if not best:
            return None
        op, c, items = best
        for it in items:
            self.mark(it["answer"], it["source"])
        cat_ = self.lex.cats[c]
        return {"type": "round", "id": f"gen-{op}-{c}", "title": f"{cat_['plural'].capitalize()}",
                "intro": OPS[op]["intro"].format(sing=cat_["singular"], plural=cat_["plural"]), "items": items}

    def challenge(self):
        """A harder, open-ended one: a bank challenge, or a two-step chain between two categories."""
        for b in self.bank_challenge:
            if b["id"] not in self.used and b["answer"] not in self.used:
                self.mark(b["id"], b["answer"], *b.get("parts", []))
                return dict(b)
        return self.chain()

    def chain(self):
        """Take a member of one category, change or drop one letter, rearrange, and get a member of another;
        offered only when exactly one pair in the two lists works."""
        names = list(self.lex.cats)
        for _ in range(300):
            a, b = self.rng.sample(names, 2)
            op = self.rng.choice(["change", "drop", "anagram"])
            pairs = []
            for x in self.lex.cats[a]["single"]:
                for y in self.lex.cats[b]["single"]:
                    if x == y or min(len(x), len(y)) < 4:
                        continue
                    if op == "change" and one_change(x, y) or op == "drop" and one_drop(x, y) \
                            or op == "anagram" and is_anagram(x, y):
                        pairs.append((x, y))
            if len(pairs) != 1:
                continue
            x, y = pairs[0]
            if x in self.used or y in self.used:
                continue
            A, B = self.lex.cats[a], self.lex.cats[b]
            how, how_x = {"change": ("change one letter", "change one letter in {x}"),
                          "drop": ("take out one letter", "take one letter out of {x}"),
                          "anagram": ("rearrange the letters", "rearrange the letters of {x}")}[op]
            self.mark(x, y)
            return {"kind": "chain", "type": "single", "id": f"chain-{x}-{y}", "challenge": True, "level": 3,
                    "clue": f"Here's a challenge. Think of {A['singular']}. {how.capitalize()}, and you'll get "
                            f"{B['singular']}. What are they? There's only one answer I know of.",
                    "answer": f"{x} {y}", "accept": [], "parts": [x, y],
                    "hints": [f"{A['singular'].capitalize()} that starts with {letter_name(x[0])}.",
                              f"{B['singular'].capitalize()} that starts with {letter_name(y[0])}.",
                              f"The first one is {len(x)} letters, the second {len(y)}."],
                    "reveal": f"{x.capitalize()} and {y.capitalize()}: {how_x.format(x=x)} and you get {y}."}
        return None


# ---------------------------------------------------------------------------------------------- grading

NUMS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
        "eight": "8", "nine": "9", "ten": "10"}


def norm(text):
    """Lowercase words, with spelled-out letters joined: "M-E-L-O-N" or "m e l o n" -> "melon"."""
    t = text.lower().replace("’", "'")
    t = re.sub(r"\b([a-z])(?:[\s.,-]+([a-z])\b)+", lambda m: re.sub(r"[\s.,-]+", "", m.group(0)), t)
    return re.findall(r"[a-z0-9']+", t)


def forms(ans):
    a = ans.lower()
    out = {a}
    out |= {a + "s", a + "es"} if not a.endswith("s") else {a[:-1]}
    return out


_SOUNDS = None


def sounds_of(w):
    """A word's pronunciations (CMU Pronouncing Dictionary, puzzle/sounds.txt), a final S or Z sound dropped so
    plurals (and one dictionary slip, "tern" as T ER N Z) still match. Empty if the word is not listed."""
    global _SOUNDS
    if _SOUNDS is None:
        _SOUNDS = {}
        for line in words("sounds.txt"):
            w_, _, ph = line.partition(" ")
            _SOUNDS[w_] = {re.sub(r" [SZ]$", "", p) for p in ph.split("|")}
    return _SOUNDS.get(w.lower(), set())


def homophones(a, b):
    """Two words that are said the same (pear / pair), by the dictionary, not by spelling."""
    return bool(sounds_of(a) & sounds_of(b))


def grade(puzzle, text):
    """'right', 'half' (one of two parts), or 'wrong' for the player's words against the puzzle."""
    toks = norm(text)
    joined = " ".join(toks)
    squashed = "".join(toks)

    def said(ans):
        a = " ".join(norm(ans))
        if not a:
            return False
        if " " in a:
            return f" {a} " in f" {joined} " or a.replace(" ", "") in squashed
        return any(f in toks for f in forms(a))

    def sounds(ans):     # the recognizer may write a homophone of a one-word answer: pair for pear
        a = ans.lower()
        if " " in a:
            return False
        given = set(norm(puzzle.get("clue", ""))) | {puzzle.get("source", "")}   # never the clue's own word
        return any(t not in given and homophones(t, a) for t in toks)

    if puzzle.get("parts"):
        hits = sum(1 for p in puzzle["parts"] if said(p) or sounds(p))
        return "right" if hits == len(puzzle["parts"]) else "half" if hits else "wrong"
    for a in [puzzle["answer"]] + list(puzzle.get("accept", [])):
        if said(a):
            return "right"
    for a in [puzzle["answer"]] + list(puzzle.get("accept", [])):
        if sounds(a):
            return "right"
    return "wrong"


def leaks(text, puzzle):
    """True when a sentence the model wrote gives the answer away."""
    toks = set(norm(text))
    parts = puzzle.get("parts") or [puzzle["answer"]]
    for p in parts:
        a = norm(p)
        if len(a) == 1 and forms(a[0]) & toks:
            return True
        if len(a) > 1 and " ".join(a) in " ".join(norm(text)):
            return True
    return False


# ---------------------------------------------------------------------------------------------- the host

ASK = re.compile(r"\b(puzzles?|another( one)?|next( one)?|new one|one more|give me (one|a|something)|riddle|teaser|anagrams?|"
                 r"word games?|let'?s (play|go|do (it|this|one|that))|hit me|bring it( on)?|i'?m ready|quiz me)\b", re.I)
ROUND = re.compile(r"\b(rounds?|on[- ]?air|a series|a set|a bunch|a few|several|a quiz)\b", re.I)
CHALLENGE = re.compile(r"\b(challenge|weekly|stumper|brain ?buster|hard one|toughie|real(ly)? (tough|hard) one)\b", re.I)
HARDER = re.compile(r"\b(harder|tougher|more difficult|too easy|trickier|challenge me)\b", re.I)
EASIER = re.compile(r"\b(easier|simpler|too hard|too difficult|too tough|gentler)\b", re.I)
HINT = re.compile(r"\b(hints?|clue me in|help( me)?|nudge|give me a letter|first letter|another clue|a clue)\b", re.I)
REPEAT = re.compile(r"\b(repeat|say (it|that|the \w+) again|again,? please|one more time|"
                    r"what was (it|that|the (word|clue|puzzle|question))|read (it|that|the \w+) again|come again|"
                    r"pardon|(didn'?t|did not) (hear|catch))\b", re.I)
GIVEUP = re.compile(r"\b(give up|i give|tell me( the answer| what it is)?|what('?s| is| was) the answer|reveal|"
                    r"no idea|(i )?(don'?t|do not) know|pass|skip( it| this( one)?)?|stumped|beats me|i'?m stuck)\b", re.I)
NEW = re.compile(r"\b((new|different|another|next) (one|puzzle)|skip (it|this one)|move on)\b", re.I)
STOP = re.compile(r"\b((stop|end|quit|finish|enough)( with)?( the| this| these)? (puzzles?|round|game|challenge)|"
                  r"no more puzzles|let'?s (just )?(talk|chat)|that'?s enough)\b", re.I)
YES = re.compile(r"^\W*(yes|yeah|yep|yup|sure|ok(ay)?|absolutely|go ahead|go for it|let'?s do it|bring it on|hit me|"
                 r"why not|of course|please|definitely|you bet|i'?d love|alright|all right)\b", re.I)
NO = re.compile(r"^\W*(no|nope|nah|not (now|right now)|i'?m good|maybe later|pass|no thanks)\b", re.I)
GUESS_LEAD = re.compile(r"^\W*(?:(?:is it|it'?s|it is|i think|i'?d say|maybe|perhaps|how about|what about|could it be|"
                        r"would it be|my guess is|i guess|i'?ll (say|guess|go with)|the answer is|that'?s|that would be|"
                        r"um+|uh+|hmm+|oh|ok(ay)?|well|so|is the answer)\W+)*", re.I)
QUESTIONY = re.compile(r"^\W*(why|how|who|when|where|what('?s| is| was| does| do| are| kind)|which|can you|could you|"
                       r"do you|did you|have you|are you|tell me about|explain|i don'?t (get|understand))\b", re.I)
def is_question(t):
    """Some sentence of it asks something ("That was fun. Who makes your puzzles?")."""
    return any(QUESTIONY.match(x) for x in re.split(r"(?<=[.!?])\s+", t))


# "Can you give me a puzzle?" asks for one; "What's the hardest puzzle you've seen?" only talks about them
REQUEST = re.compile(r"\b(give|gimme|have|get|try|do|play|want|got|another|next|one more|new one|throw|hit me|"
                     r"how about|what about)\b", re.I)
# the model offered a puzzle ("Would you like another?"): the player's "yes" should start one
OFFER = re.compile(r"\b(want|like|try|shall i|ready for|up for|how about)\b[^.?!]{0,40}\b(puzzles?|rounds?|challenge|"
                   r"another|anagrams?|one)\b[^.!]*\?", re.I)

# The host's own words around the mechanics. The shape follows the radio segments (puzzle/STYLE.md): the clock
# and precision of one (rule, worked example, quick items, last one flagged, a score), the delight and
# generosity of the other (praise a good miss, accept any valid answer out loud, say why a guess fails). The
# wording is ENIGMA's own; lines that are either host's signature are deliberately left out.
LEAD_SINGLE = ["Here's one to chew on.", "Try this on.", "Ears open. Here it comes.", "A quick one for you.",
               "Here's a little word trick.", "See what you make of this.", "Fresh one, just for you.",
               "Okay, here's your puzzle."]
LEAD_ROUND = ["Let's play a round.", "Round time. Here's the rule.", "I've got a little set for you.",
              "A round, same trick each time.", "Okay, a round. Listen for the rule."]
RIGHT_QUICK = ["{A}. Right.", "{A}, exactly.", "Yes, {a}.", "That's the one: {a}.", "{A}. Good.",
               "{A}. Nicely done.", "You've got it, {a}.", "{A}. Quick work.", "Right, {a}."]
SOLVED = ["{A}! Exactly right.", "Yes! {A}. Lovely.", "{A}. Beautifully done.", "There you go, {A}!",
          "{A}! You saw right through it."]
SOLVED_HINTED = ["{A}! The nudge did it.", "Yes, {A}. You got there.", "{A}! Worth the wait."]
VALID_ALT = ["{G} works too. I'll take it.", "I didn't expect {g}, but it counts."]
WRONG = ["Not {g}, no.", "Hmm, no. Try another.", "Not that one.", "Good guess, but no.", "No. Have another go.",
         "Not {g}. Keep going."]
NEAR = ["Close! One letter's off.", "So close. Check the spelling.", "You're circling it."]
FITS_NOT_CAT = "{G} works with the letters, but it isn't {sing}."
RULE_LENGTH = "{G} has {n} letters; I need {m}."
RULE_CHANGE = "{G} changes more than one letter. Just one."
RULE_LETTERS = "{G} uses a letter that {W} doesn't have."
NO_MORE_HINTS = "That's every hint I've got. Keep trying, or say you give up and I'll tell you."
HINT_LEAD = ["Here's a nudge.", "Let me help a little.", "Think about this.", "Try it this way.", "A small hint, then."]
HINT_MORE = ["A bigger hint.", "Let me narrow it down.", "One more push.", "Here's another."]
REVEAL_LEAD = ["I'll tell you. It's", "Here's the answer:", "It was", "Let me end the suspense:"]
NEXT_LABEL = ["Number {n}", "Here's number {n}", "Next one", "Try this one", "How about this"]
LAST_LABEL = ["And the final one", "Last one, coming up", "And the last"]
ROUND_END = {"all": "A clean sweep! Every one.", "most": "That's the set: {s} of {n}. Nicely played.",
             "some": "That's the set: {s} of {n}.", "few": "{s} of {n}. Those were tough ones."}
NUMBERS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


class Session:
    """What ENIGMA does with each thing the player says. The code keeps the puzzle, the answer and the score;
    turn(text) returns a dict for the app:
      say    the app speaks this as is, with no model call (clues, hints, verdicts mid-round: fast and exact)
      note   a hidden note for the model, which then speaks its own short reply
      after  spoken verbatim after the model's reply (a clue is never left to the model to read)
      guard  the open puzzle: a sentence the model writes that contains its answer is not spoken
      tokens the model's reply budget for this turn
    An empty dict means plain conversation."""

    def __init__(self, puzzles=None, seed=None):
        self.p = puzzles or Puzzles(seed)
        self.rng = self.p.rng
        self.level = 2
        self.cur = None             # the open puzzle (in a round: the current item)
        self.round = None           # the round being played: its items, position, score
        self.ri = self.score = 0
        self.hint_i = 0
        self.offered = False        # the last thing said invited another puzzle
        self.streak = self.giveups = 0

    # -- state the UI shows
    def status(self):
        if self.round:
            return f"round: {self.ri + 1} of {len(self.round['items'])} · {self.score} right"
        if self.cur:
            kind = "challenge" if self.cur.get("challenge") else "puzzle"
            return f"{kind} open" + (f" · {self.hint_i} hint{'s' if self.hint_i > 1 else ''}" if self.hint_i else "")
        return ""

    def open_clue(self):
        """The current clue, for the model's note when the player talks about something else."""
        if not self.cur:
            return ""
        if self.round:
            return f"{self.round['intro']} The current word: {self.cur['clue']}"
        return self.cur["clue"]

    # -- presenting
    def present_single(self, text=""):
        cat = self.p.category_for(text)
        pz = self.p.single(self.level, cat=cat)
        if not pz:
            return {"say": "Hmm, I'm out of fresh ones like that. Ask me for a round instead?"}
        self.cur, self.round, self.hint_i, self.offered = pz, None, 0, False
        return {"say": f"{self.rng.choice(LEAD_SINGLE)} {pz['clue']}"}

    def present_challenge(self):
        pz = self.p.challenge()
        if not pz:
            return self.present_single()
        self.cur, self.round, self.hint_i, self.offered = pz, None, 0, False
        return {"say": pz["clue"] + " Take your time. Ask for a hint whenever you like."}

    def present_round(self, text=""):
        cat = self.p.category_for(text)
        r = self.p.round(self.level, cat=cat, n=7)
        if not r:
            return self.present_single(text)
        intro = r["intro"]
        if r["id"].startswith("gen-") and len(r["items"]) > 1:
            ex = r["items"].pop(0)        # the easiest one is the worked example, as on the radio
            why = {"anagram": "same letters", "change": "one letter changed", "drop": "one letter out",
                   "add": "one letter added", "reverse": "spelled backward",
                   "anadrop": "one letter out, the rest rearranged"}.get(ex.get("kind"), "")
            intro += f" For example, {ex['clue'].rstrip('.')}, would be {ex['answer'].capitalize()}" + \
                     (f": {why}." if why else ".")
        self.round, self.ri, self.score, self.offered = r, 0, 0, False
        self.cur, self.hint_i = r["items"][0], 0
        return {"say": f"{self.rng.choice(LEAD_ROUND)} {intro} Number one: {self.cur['clue']}"}

    def next_item(self, lead):
        """After an item in a round is answered or revealed: the next clue, or the end of the round."""
        self.ri += 1
        self.hint_i = 0
        items = self.round["items"]
        if self.ri < len(items):
            self.cur = items[self.ri]
            label = self.rng.choice(LAST_LABEL) if self.ri == len(items) - 1 else \
                self.rng.choice(NEXT_LABEL).format(n=NUMBERS[self.ri])
            return {"say": f"{lead} {label}: {self.cur['clue']}"}
        score, n = self.score, len(items)
        self.round = self.cur = None
        self.offered = True
        self.adapt(score / n >= 0.8, score / n < 0.4)
        tier = "all" if score == n else "most" if score / n >= 0.6 else "some" if score / n >= 0.3 else "few"
        answers = ", ".join(i["answer"] for i in items)
        return {"say": f"{lead} {ROUND_END[tier].format(s=score, n=n)}",
                "note": f"[Note: the round is over ({score} of {n}; you already said the score). The answers were: "
                        f"{answers}. Add one short line, a pun on one of those answers if easy, and offer another "
                        f"round or a single puzzle.]", "tokens": 30}

    def adapt(self, up, down):
        if up and self.level < 3:
            self.level += 1
        elif down and self.level > 1:
            self.level -= 1

    # -- answers
    def right(self, word=None):
        """word: a valid answer other than the planned one, which the host accepts out loud."""
        pz = self.cur
        alt = self.rng.choice(VALID_ALT).format(G=word.capitalize(), g=word) + " " if word else ""
        self.streak += 1
        self.giveups = 0
        if self.round:
            self.score += 1
            a = pz["answer"]
            return self.next_item(alt + self.rng.choice(RIGHT_QUICK).format(a=a, A=a.capitalize()))
        self.cur = None
        self.offered = True
        if self.streak >= 3:
            self.adapt(True, False)
            self.streak = 0
        ans = " and ".join(pz.get("parts") or [pz["answer"]]).capitalize()
        verdict = alt + self.rng.choice(SOLVED_HINTED if self.hint_i else SOLVED).format(A=ans)
        # the verdict is spoken at once; the model's line follows while it plays (a short note reads fast)
        return {"say": verdict, "note": f"[Note: solved: {pz['reveal']} You already said it's right, so don't say so "
                                        f"again. Add one short warm line, a pun on the word if easy, and offer "
                                        f"another.]", "tokens": 30}

    def reveal(self):
        pz = self.cur
        self.streak = 0
        self.giveups += 1
        if self.giveups >= 2:
            self.adapt(False, True)
            self.giveups = 0
        if self.round:      # quick, as on the radio: just the word
            return self.next_item(f"{self.rng.choice(REVEAL_LEAD)} {pz['answer'].capitalize()}.")
        text = f"{self.rng.choice(REVEAL_LEAD)} {pz['reveal']}"
        self.cur = None
        self.offered = True
        return {"say": text + " Want another?"}

    def hint(self):
        hints = self.cur.get("hints") or []
        if self.hint_i >= len(hints):
            return {"say": NO_MORE_HINTS}
        h = hints[self.hint_i]
        self.hint_i += 1
        lead = self.rng.choice(HINT_LEAD if self.hint_i == 1 else HINT_MORE)
        return {"say": f"{lead} {h}"}

    def wrong(self, words, raw):
        pz = self.cur
        g = " ".join(words) if words else raw
        ans = pz["answer"].lower()
        # a guess that obeys the letters and is in the category is right, even if it was not the planned one
        if pz.get("source") and pz.get("kind") in OPS:
            cat = self.p.lex.cats.get(pz.get("cat"), {})
            for w in words:
                if fits(pz["kind"], pz["source"], w) and w != pz["source"]:
                    if w in cat.get("all", ()):
                        return self.right(w)
                    if w in self.p.lex.valid and len(words) <= 3:
                        return {"say": FITS_NOT_CAT.format(G=w.capitalize(), sing=cat.get("singular", "the category"))}
        if len(words) == 1 and " " not in ans:
            w = words[0]
            if w != pz.get("source") and (one_change(w, ans) or one_drop(w, ans) or one_drop(ans, w)):
                return {"say": self.rng.choice(NEAR)}
            # say which rule the guess breaks, as the radio puzzlemaster does
            src, op = pz.get("source"), pz.get("kind")
            if src and op in OPS and w in self.p.lex.valid and w != src:
                if len(w) != len(ans):
                    return {"say": RULE_LENGTH.format(G=w.capitalize(), n=len(w), m=len(ans))}
                if op == "change" and len(w) == len(src):
                    return {"say": RULE_CHANGE.format(G=w.capitalize())}
                if op in ("anagram", "anadrop") and not set(w) <= set(src):
                    return {"say": RULE_LETTERS.format(G=w.capitalize(), W=src.capitalize())}
        lines = WRONG if len(words) <= 2 else [w for w in WRONG if "{g}" not in w]   # never "no, not do a round"
        return {"say": self.rng.choice(lines).format(g=g)}

    # -- one turn
    def turn(self, text):
        t = text.strip()
        if self.cur:
            core = GUESS_LEAD.sub("", t)
            words = norm(core)
            g = grade(self.cur, t)
            if g == "right":
                return self.right()
            if g == "half":
                return {"say": "That's half of it! Now the other one."}
            if STOP.search(t):
                pz, self.cur, self.round = self.cur, None, None
                return {"say": f"No problem. {self.rng.choice(REVEAL_LEAD)} {pz['reveal']}"}
            if REPEAT.search(t):
                again = (self.round["intro"] + " " if self.round and self.ri == 0 else "") + self.cur["clue"]
                return {"say": "Sure. " + again}
            if GIVEUP.search(t):
                return self.reveal()
            if HINT.search(t):
                return self.hint()
            if NEW.search(t) or ROUND.search(t) or CHALLENGE.search(t) or ASK.search(t) and not words[3:]:
                if self.round and not (ROUND.search(t) or CHALLENGE.search(t)):
                    return self.reveal()        # "next one" mid-round: skip to the next clue
                pz, self.cur, self.round = self.cur, None, None
                first = f"{self.rng.choice(REVEAL_LEAD)} {pz['reveal']} "
                nxt = self.present_challenge() if CHALLENGE.search(t) else \
                    self.present_round(t) if ROUND.search(t) else self.present_single(t)
                return {**nxt, "say": first + nxt.get("say", "")}
            if HARDER.search(t) or EASIER.search(t):
                self.adapt(bool(HARDER.search(t)), bool(EASIER.search(t)))
                return {"say": "Noted, the next one will be " + ("tougher." if HARDER.search(t) else "gentler.") +
                               " But this one's still open. " + self.cur["clue"]}
            if words and len(words) <= 4 and not is_question(t):
                return self.wrong(words, t)
            return {"note": f"[Note: a puzzle is open and unsolved: {self.open_clue()} The player said something "
                            f"that isn't a guess. Answer briefly without giving the answer away, then remind them "
                            f"they can guess, ask for a hint, or give up.]", "guard": self.cur, "tokens": 70}
        offered, self.offered = self.offered, False
        if STOP.search(t):
            return {}
        harder, easier = bool(HARDER.search(t)), bool(EASIER.search(t))
        if harder or easier:
            self.adapt(harder, easier)
        if is_question(t) and not REQUEST.search(t):
            return {}
        if CHALLENGE.search(t):
            return self.present_challenge()
        if ROUND.search(t):
            return self.present_round(t)
        if ASK.search(t) or harder or easier or offered and YES.match(t):
            return self.present_single(t)
        if offered and NO.match(t):
            return {"note": "[Note: the player doesn't want another puzzle right now. Say that's fine in one short "
                            "sentence; you're happy to just chat.]", "tokens": 40}
        return {}


# ---------------------------------------------------------------------------------------------- bank checks

def _letters(s):
    return re.sub(r"[^a-z]", "", s.lower())


def check_claim(c, lex):
    """One mechanical claim from a bank puzzle's "check" list: (ok, why)."""
    op = c.get("op")
    a, b = _letters(c.get("a", "")), _letters(c.get("b", ""))
    if op == "words":
        bad = [w for w in c["words"] if not all(x in lex.valid for x in w.lower().split())]
        return not bad, f"not in the word list: {bad}"
    if op == "anagram":
        return is_anagram(a, b), f"{a} / {b} are not anagrams"
    if op == "change":
        return one_change(a, b), f"{a} -> {b} is not a one-letter change"
    if op == "drop":
        return one_drop(a, b), f"{b} is not {a} minus one letter"
    if op == "reverse":
        return a[::-1] == b, f"{a} reversed is not {b}"
    if op == "concat":
        return "".join(_letters(p) for p in c["parts"]) == b, f"{c['parts']} do not make {b}"
    if op == "hidden":
        return b in _letters(c["phrase"]), f"{b} is not hidden in {c['phrase']!r}"
    if op == "initials":
        return "".join(w[0] for w in re.findall(r"[a-z]+", c["phrase"].lower())) == b, f"initials of {c['phrase']!r} != {b}"
    if op == "insert":
        ins = _letters(c["ins"])
        return any(a[:i] + ins + a[i:] == b for i in range(len(a) + 1)), f"{ins} into {a} does not make {b}"
    if op == "remove":
        d = _letters(c["del"])
        return any(b[:i] + d + b[i:] == a for i in range(len(b) + 1)), f"removing {d} from {a} does not leave {b}"
    if op == "replace":
        f, t = _letters(c["from"]), _letters(c["to"])
        return f in a and (a.replace(f, t, 1) == b or a.replace(f, t) == b), f"{a} with {f}->{t} is not {b}"
    if op == "contains":
        return b in a, f"{b} not in {a}"
    if op == "palindrome":
        w = _letters(c["w"])
        return w == w[::-1], f"{w} is not a palindrome"
    if op == "length":
        return len(_letters(c["w"])) == c["n"], f"{c['w']} is not {c['n']} letters"
    if op == "letters":      # b uses only letters found in a
        return set(b) <= set(a), f"{b} uses letters not in {a}"
    if op == "sound":     # a claim about sound (rhyme, homophone, spoonerism): no letters to check, reviewed by hand
        return bool(c.get("why")), "sound claim needs a why"
    if op == "free":
        return bool(c.get("why")), "free claim needs a why"
    return False, f"unknown op {op}"


def check_puzzle(p, lex):
    """Problems with one bank entry (empty when it is sound)."""
    errs = []
    items = p["items"] if p.get("type") == "round" else [p]
    if p.get("type") == "round" and (len(items) < 4 or not p.get("intro")):
        errs.append("a round needs an intro and at least 4 items")
    for it in items:
        ans = it.get("answer", "")
        if not ans or not it.get("clue"):
            errs.append(f"missing clue or answer: {it}")
            continue
        for part in (it.get("parts") or [ans]):
            if re.search(r"\b" + re.escape(part.lower()) + r"\b", it["clue"].lower()):
                errs.append(f"the clue gives away {part!r}: {it['clue']}")
        if p.get("type") != "round" and not it.get("hints"):
            errs.append(f"no hints: {it['clue']}")
        checks = it.get("check") or []
        if not checks:
            errs.append(f"no checks: {it['clue']}")
        named = " ".join(json.dumps(c).lower() for c in checks)
        if not any(c.get("op") == "free" for c in checks) and \
                not all(_letters(x) in _letters(named) for x in (it.get("parts") or [ans])):
            errs.append(f"the checks never mention the answer {ans!r}")
        for c in checks:
            ok, why = check_claim(c, lex)
            if not ok:
                errs.append(f"{p.get('id')}: {why}")
    return errs
