"""Word puzzles for ENIGMA (modes/enigma.py, the Enigma Puzzles mode of retrovoice.py).

A small language model cannot be trusted to invent a letter puzzle: it reads words in chunks, not letters,
so its anagrams drop letters and its "change one letter" answers change two. Here the code makes and checks
every puzzle, and the model only hosts. Two sources:
  - generators: letter operations (anagram, change / drop / add a letter, reversal, drop-and-rearrange,
    swapped first letters, consonyms, two-step chains) between a common word and a member of a hand-checked
    category list, plus category puzzles (length and end letters, only two consonants, alphabetically
    between, acrostics) and two-letter prefixes. Each answer is verified, and unique within its category,
    before the puzzle is offered.
  - the bank (puzzle/bank/*.json): original puzzles written ahead of time in the style of radio puzzle
    segments, each with a mechanical check that test/test_puzzles.py runs (puzzle/bank_check.py).
A puzzle is a dict: clue (spoken exactly), answer, accept (other right answers), hints (one at a time),
reveal (spoken when the player gives up), rating 1-10. A round is a themed set of quick ones read back to back;
the ladder is ten puzzles rated one to ten.
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


def up1(s):
    """First letter up, the rest as written ("a U.S. state" -> "A U.S. state"; capitalize() would say "u.s.")."""
    return s[:1].upper() + s[1:]


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
        self._skel = None

    def by_skeleton(self):
        """Consonant skeleton -> the common words with it (for consonyms)."""
        if self._skel is None:
            sk = {}
            for w in self.common:
                if w not in self.block:
                    sk.setdefault(skeleton(w), []).append(w)
            self._skel = sk
        return self._skel

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
                "reveal": "{A}. Rearrange the letters of {w} and you get {a}.", "why": "same letters"},
    "change": {"single": "Change one letter in {W}, to get {sing}.",
               "intro": "Every answer is {sing}. I'll give you a word. Change one letter to get the answer.",
               "reveal": "{A}. Change one letter in {w} and you get {a}.", "why": "one letter changed"},
    "drop": {"single": "Take one letter out of {W}, to get {sing}.",
             "intro": "Every answer is {sing}. I'll give you a word. Take out one letter to get the answer.",
             "reveal": "{A}. Take one letter out of {w} and you get {a}.", "why": "one letter out"},
    "add": {"single": "Add one letter to {W}, to get {sing}.",
            "intro": "Every answer is {sing}. I'll give you a word. Add one letter, anywhere, to get the answer.",
            "reveal": "{A}. Add one letter to {w} and you get {a}.", "why": "one letter added"},
    "reverse": {"single": "Spell {W}, backward to get {sing}.",
                "intro": "Every answer is {sing}. I'll give you a word. Spell it backward to get the answer.",
                "reveal": "{A}. {w} spelled backward is {a}.", "why": "spelled backward"},
    "anadrop": {"single": "Take one letter out of {W}, then rearrange what's left, to get {sing}.",
                "intro": "Every answer is {sing}. I'll give you a word. Drop one letter and rearrange the rest "
                         "to get the answer.",
                "reveal": "{A}. Drop a letter from {w}, rearrange the rest, and you get {a}.",
                "why": "one letter out, the rest rearranged"},
    "swap2": {"single": "Swap the first two letters of {W}, to get {sing}.",
              "intro": "Every answer is {sing}. I'll give you a word. Swap its first two letters to get the answer.",
              "reveal": "{A}. Swap the first two letters of {w} and you get {a}.", "why": "first two letters swapped"},
    "consonym": {"single": "Name {sing} with the same consonants, in the same order, as {W}. Only the vowels "
                           "change.",
                 "intro": "Every answer is {sing} with the same consonants, in the same order, as the word I give "
                          "you. Only the vowels change.",
                 "reveal": "{A}. It has the same consonants as {w}.", "why": "same consonants"},
}
# How hard each kind is to begin with, on ENIGMA's 1-10 scale (rate() adjusts for length, category, rarity).
BASE = {"startend": 1, "between": 2, "change": 2, "reverse": 2, "swap2": 3, "add": 3, "drop": 3, "anagram": 4,
        "consonants": 4, "dropboth": 4, "consonym": 5, "prefix2": 5, "anadrop": 6, "chain": 8}
# categories whose lists are complete, so "alphabetically between" has one true answer
CLOSED = {"state", "country", "month", "planet", "zodiac", "greek_letter", "president"}
# pieces a "same two letters in front" puzzle may use: consonant clusters that start English words
ONSETS = set("bl br ch cl cr dr fl fr gl gr pl pr sc sh sk sl sm sn sp st sw th tr tw wh wr".split())
VOWELS = set("aeiouy")
# a topic the player names, as the categories it covers
TOPICS = {"geograph": ["country", "state", "capital", "city", "river"], "travel": ["country", "capital", "city"],
          "music": ["instrument", "composer", "dance"], "food": ["fruit", "vegetable", "food", "cheese", "spice", "nut"],
          "cook": ["food", "kitchen", "spice", "vegetable"], "nature": ["animal", "bird", "fish", "insect", "tree",
          "flower", "weather"], "animal": ["animal", "bird", "fish", "insect"], "plant": ["flower", "tree"],
          "garden": ["flower", "tree", "vegetable", "tool"], "science": ["metal", "planet", "gem", "shape", "weather"],
          "space": ["planet", "zodiac"], "history": ["president", "greek_god", "weapon"],
          "myth": ["greek_god"], "sport": ["sport", "game"], "game": ["game", "sport"], "home": ["furniture",
          "kitchen", "tool"], "fashion": ["clothing", "fabric", "color"], "cloth": ["clothing", "fabric"],
          "people": ["job", "family"], "work": ["job", "tool"], "drink": ["drink"], "transport": ["vehicle", "car"],
          "car": ["car", "vehicle"], "art": ["color", "composer", "shape"], "feeling": ["emotion"],
          "body": ["body"], "language": ["language"], "word": []}


def skeleton(w):
    return "".join(c for c in w if c not in VOWELS)


def rate(kind, answer, cat=None, lex=None, src=""):
    """A generated puzzle's difficulty, 1-10: its kind, then longer answers, bigger categories and rarer
    words make it harder; an anagram that keeps its first letter is easier."""
    r = BASE.get(kind, 4)
    n = len(answer.replace(" ", ""))
    r += -1 if n <= 4 else 0 if n <= 6 else 1 if n <= 8 else 2
    if kind in ("anagram", "anadrop") and n >= 7:
        r += 1
    if cat:
        size = len(cat["all"])
        r += -1 if size <= 15 else 1 if size >= 80 else 0
    if lex and answer not in lex.common:
        r += 1
    if kind == "anagram" and src and src[0] == answer[0]:
        r -= 1
    if kind == "change" and src and src[0] != answer[0] and src[1:] == answer[1:]:
        r -= 1              # a new first letter (bear, pear) is the easy kind of change
    return max(1, min(10, r))


def bank_rating(b):
    """A written puzzle's place on the 1-10 scale, from its level (challenges 8-9); the id spreads ties."""
    h = sum(map(ord, b.get("id", ""))) % 2
    if b.get("challenge"):
        return 8 + h
    return {1: 2, 2: 4, 3: 6}.get(b.get("level", 2), 4) + h


def bank_kind(b):
    ops = [c.get("op") for c in (b.get("check") or (b.get("items") or [{}])[0].get("check", [])) if c.get("op") != "words"]
    return "bank-" + (ops[0] if ops else "free")


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
    elif op == "swap2":
        w = member[1] + member[0] + member[2:] if len(member) >= 4 else ""
        cands = [w] if w in lex.common and w != member else []
        ok = lambda w: True    # one swap gives one word
    elif op == "consonym":   # same consonants in order, at least three of them, different vowels
        k = skeleton(member)
        cands = [w for w in lex.by_skeleton().get(k, ()) if w != member] if len(k) >= 3 else []
        ok = lambda w: not any(skeleton(m) == k for m in members if m != member)
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
    if op == "swap2":
        return len(src) >= 2 and word == src[1] + src[0] + src[2:]
    if op == "consonym":
        return word != src and skeleton(word) == skeleton(src)
    return False


def letter_hints(answer, cat=None):
    """Hints that close in: the first letter, then the length and last letter, then the pattern."""
    h = [f"It starts with {letter_name(answer[0])}."]
    h.append(f"It has {len(answer)} letters and ends in {letter_name(answer[-1])}.")
    h.append("The pattern is " + ", ".join(c.upper() if i in (0, len(answer) // 2, len(answer) - 1) else "blank"
                                           for i, c in enumerate(answer)) + ".")
    return h


def make_item(op, member, src, cat, single, lex=None):
    t = OPS[op]
    fmt = {"W": say_word(src), "w": src.capitalize(), "a": member.capitalize(), "A": member.capitalize(),
           "sing": cat["singular"], "plural": cat["plural"]}
    clue = t["single"].format(**fmt) if single else f"{say_word(src)}."
    return {"kind": op, "cat": cat["name"], "source": src, "clue": clue, "answer": member, "accept": [],
            "hints": letter_hints(member, cat), "reveal": t["reveal"].format(**fmt),
            "rating": rate(op, member, cat, lex, src)}


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


def _cap(s):
    return " ".join(w.capitalize() for w in s.split())


class Puzzles:
    def __init__(self, seed=None, bank_path=None):
        self.lex = Lexicon()
        self.rng = random.Random(seed)
        self.used = set()            # sources and answers already played this session
        self._index = {}             # (op, cat) -> [(member, [sources])], built on first use
        self._pool = None            # every generated one-off puzzle as (rating, kind, cat, answer, extra)
        bank = load_bank(bank_path)
        for b in bank:
            b.setdefault("rating", bank_rating(b))
            b.setdefault("kind", bank_kind(b))
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

    def pool(self):
        """Every generated one-off puzzle, rated: (rating, kind, cat, answer, extra). Built once (about 1-2 s on
        the rig, at boot while the model warms up)."""
        if self._pool is not None:
            return self._pool
        lex, out = self.lex, []
        for op in OPS:
            for c in lex.cats:
                for m, srcs in self.index(op, c):
                    for s in srcs:
                        out.append((rate(op, m, lex.cats[c], lex, s), op, c, m, s))
        for c, cat in lex.cats.items():
            allw = sorted(m for m in cat["all"])
            fair = set(cat["single"])
            # same length, same first and last letter: the only member that fits
            sig = {}
            for m in allw:
                if m.isalpha():
                    sig.setdefault((len(m), m[0], m[-1]), []).append(m)
            for ms in sig.values():
                if len(ms) == 1 and ms[0] in fair and len(ms[0]) >= 4:
                    out.append((rate("startend", ms[0], cat, lex), "startend", c, ms[0], ""))
            # only these two consonants
            cons = {}
            for m in allw:
                if m.isalpha():
                    k = "".join(sorted(set(skeleton(m))))
                    cons.setdefault(k, []).append(m)
            for k, ms in cons.items():
                if len(k) == 2 and len(ms) == 1 and ms[0] in fair and len(skeleton(ms[0])) >= 2:
                    out.append((rate("consonants", ms[0], cat, lex), "consonants", c, ms[0], k))
            # alphabetically between its neighbors, in a complete list
            if c in CLOSED:
                for i in range(1, len(allw) - 1):
                    if allw[i] in fair:
                        out.append((rate("between", allw[i], cat, lex), "between", c, allw[i],
                                    (allw[i - 1], allw[i + 1])))
        out += self.prefix_pairs()
        self._pool = out
        return out

    def prefix_pairs(self):
        """Two words that take the same two letters in front to make two new words, and only one such pair of
        letters (rest -> prefixes, from the common words that start with a consonant cluster)."""
        lex = self.lex
        takes = {}
        for w in lex.common:
            p, rest = w[:2], w[2:]
            if p in ONSETS and len(rest) >= 3 and rest in lex.common and w not in lex.block and rest not in lex.block:
                takes.setdefault(rest, set()).add(p)
        by_p = {}
        for rest, ps in takes.items():
            for p in ps:
                by_p.setdefault(p, []).append(rest)
        rng, out = random.Random(7), []
        for p, rests in sorted(by_p.items()):
            rests.sort()
            for _ in range(min(12, len(rests))):
                a, b = rng.sample(rests, 2) if len(rests) >= 2 else (None, None)
                if not a or takes[a] & takes[b] != {p} or a[:2] == b[:2]:
                    continue
                out.append((rate("prefix2", p + a, None, lex), "prefix2", None, p, (a, b)))
        return out

    def warm(self):
        """Build every index ahead of the first request."""
        self.pool()

    def fresh(self, pairs):
        return [(m, [s for s in srcs if s not in self.used]) for m, srcs in pairs
                if m not in self.used and any(s not in self.used for s in srcs)]

    def mark(self, *ws):
        self.used.update(w for w in ws if w)

    # -- making a puzzle from a pool entry
    def build(self, entry):
        rating, kind, c, ans, x = entry
        cat = self.lex.cats.get(c) if c else None
        if kind in OPS:
            it = make_item(kind, ans, x, cat, True, self.lex)
            it["rating"] = rating
            return it
        sing = cat["singular"] if cat else ""
        base = {"kind": kind, "cat": c, "source": "", "accept": [], "rating": rating, "answer": ans}
        if kind == "startend":
            return {**base, "clue": f"Name {sing} with {len(ans)} letters that starts with {letter_name(ans[0])} "
                                    f"and ends with {letter_name(ans[-1])}.",
                    "hints": [f"The second letter is {ans[1].upper()}.", letter_hints(ans)[2]],
                    "reveal": f"{_cap(ans)}: {len(ans)} letters, from {ans[0].upper()} to {ans[-1].upper()}."}
        if kind == "consonants":
            k = [ch for ch in dict.fromkeys(skeleton(ans))]
            return {**base, "clue": f"Name {sing} whose only consonants are {k[0].upper()} and {k[1].upper()}. "
                                    f"Each may appear more than once.",
                    "hints": letter_hints(ans)[1:] + [f"It starts with {letter_name(ans[0])}."],
                    "reveal": f"{_cap(ans)}. Its only consonants are {k[0].upper()} and {k[1].upper()}."}
        if kind == "between":
            lo, hi = x
            return {**base, "clue": f"Name {sing} that comes alphabetically between {_cap(lo)} and {_cap(hi)}.",
                    "accept": [], "hints": letter_hints(ans),
                    "reveal": f"{_cap(ans)}. In the alphabet it falls right between {_cap(lo)} and {_cap(hi)}."}
        if kind == "prefix2":
            a, b = x
            return {**base, "kind": "prefix2", "answer": ans, "accept": [f"{ans + a}+{ans + b}"], "source": "",
                    "clue": f"What two letters can you put in front of both {say_word(a)}, and {say_word(b)}, "
                            f"to make two new words?",
                    "hints": [f"The first letter is {ans[0].upper()}.", f"One of the new words is {ans + a}."],
                    "reveal": f"{spell(ans)}: {ans + a} and {ans + b}.", "parts_say": [ans + a, ans + b]}
        return None

    # -- picking
    def category_for(self, text):
        """The categories a request names ("a puzzle about animals", "a geography puzzle"), or None."""
        t = text.lower()
        for name, c in self.lex.cats.items():
            words_ = {name.replace("_", " "), c["plural"].lower(), c["singular"].lower().split(" ", 1)[-1]}
            if any(re.search(r"\b" + re.escape(w) + r"s?\b", t) for w in words_ if w):
                return [name]
        for stem, cats in TOPICS.items():
            if cats and re.search(r"\b" + stem, t):
                return cats
        return None

    def single(self, level=4, cat=None, kinds=None, avoid=None, exact=False):
        """One puzzle near a 1-10 level: from the written bank (half the time, when it has one that close and
        no topic was named) or the generated pool. cat: a list of categories; avoid: a kind not to repeat;
        exact: only this level and the one above (when the player asked for harder)."""
        lo, hi = (level, level + 1) if exact else (level - 1, level + 1)
        ok = lambda r: lo <= r <= hi
        bank = [b for b in self.bank_single if b["id"] not in self.used and b["answer"] not in self.used
                and ok(b["rating"]) and b["kind"] != avoid]
        if level >= 8 and not cat and not kinds:
            bank += [b for b in self.bank_challenge if b["id"] not in self.used and b["answer"] not in self.used
                     and ok(b["rating"])]
        if not cat and not kinds and avoid != "dropboth" and 3 <= level <= 6 and self.rng.random() < 0.08:
            d = self.dropboth(level)
            if d and ok(d["rating"]):
                return d
        if bank and not cat and not kinds and self.rng.random() < 0.5:
            b = self.rng.choice(bank)
            self.mark(b["id"], b["answer"], *b.get("parts", []))
            return dict(b)
        pool = [e for e in self.pool() if ok(e[0]) and (not cat or e[2] in cat) and (not kinds or e[1] in kinds)
                and e[1] != avoid and e[3] not in self.used and not (isinstance(e[4], str) and e[4] in self.used)]
        if not pool and (cat or avoid or exact):      # widen rather than come back empty
            return self.single(level, cat, kinds) if (avoid or exact) else self.single(level, None, kinds)
        if not pool:
            pool = [e for e in self.pool() if e[3] not in self.used]
            pool.sort(key=lambda e: abs(e[0] - level))
            pool = pool[:200]
        if not pool:
            return None
        e = self.rng.choice(pool)
        it = self.build(e)
        self.mark(it["answer"], it.get("source"), *(e[4] if isinstance(e[4], tuple) else ()))
        return it

    def round(self, level=4, cat=None, n=6):
        """A themed round: one operation, one category, n quick clues, easier ones first; or a written round;
        or, now and then, an acrostic."""
        if not cat and self.rng.random() < 0.15:
            r = self.acrostic(level)
            if r:
                return r
        if not cat and self.bank_rounds and self.rng.random() < 0.5:     # the written rounds are the cleverer ones
            cands = []
            for b in self.bank_rounds:     # skipping items whose answer this session has already had
                items = [dict(i) for i in b["items"] if i["answer"] not in self.used]
                if b["id"] not in self.used and len(items) >= 5:
                    cands.append((abs(b["rating"] - level), self.rng.random(), b, items))
            if cands:
                _, _, b, items = min(cands, key=lambda x: x[:2])
                self.mark(b["id"], *(i["answer"] for i in items))
                return {**b, "items": items}
        combos = [(op, c) for op in OPS for c in (cat or self.lex.cats)]
        self.rng.shuffle(combos)
        best = None
        for op, c in combos:
            if BASE[op] > level + 1:
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
                it = make_item(op, m, self.rng.choice(srcs), self.lex.cats[c], False, self.lex)
                seen.update((m, it["source"]))
                items.append(it)
            if len(items) < n:
                continue
            items.sort(key=lambda i: abs(i["rating"] - level))
            items = sorted(items[:n], key=lambda i: (i["rating"], len(i["answer"])))
            if best is None or abs(sum(i["rating"] for i in items) / n - level) < best[0]:
                best = (abs(sum(i["rating"] for i in items) / n - level), op, c, items)
            if best[0] <= 1:
                break
        if not best:
            return None
        _, op, c, items = best
        for it in items:
            self.mark(it["answer"], it["source"])
        cat_ = self.lex.cats[c]
        return {"type": "round", "id": f"gen-{op}-{c}", "title": f"{cat_['plural'].capitalize()}",
                "intro": OPS[op]["intro"].format(sing=cat_["singular"], plural=cat_["plural"]), "items": items,
                "why": OPS[op]["why"]}

    def acrostic(self, level=4):
        """Spell a word with one category member per letter; any member with that letter counts."""
        cats = list(self.lex.cats)
        self.rng.shuffle(cats)
        for c in cats:
            cat = self.lex.cats[c]
            initials = {}
            for m in cat["all"]:
                if m.isalpha():
                    initials.setdefault(m[0], []).append(m)
            fair_init = {m[0] for m in cat["single"]}
            words_ = [w for w in self.lex.common if 4 <= len(w) <= 6 and len(set(w)) == len(w)
                      and all(ch in fair_init for ch in w) and w not in self.lex.block]
            if not words_:
                continue
            w = self.rng.choice(sorted(words_))
            items = []
            for ch in w:
                fair = [m for m in cat["single"] if m[0] == ch]
                ans = self.rng.choice(fair)
                items.append({"kind": "acrostic", "cat": c, "clue": f"{up1(cat['singular'])} that starts "
                              f"with {letter_name(ch)}.", "answer": ans,
                              "accept": [m for m in initials[ch] if m != ans], "rating": 2, "source": ""})
            return {"type": "round", "id": f"acrostic-{c}-{w}", "title": f"{w.upper()} in {cat['plural']}",
                    "intro": f"Let's spell {say_word(w)}, with {cat['plural']}: for each letter, name "
                             f"{cat['singular']} that starts with it. Any one will do.", "items": items}
        return None

    def challenge(self):
        """A harder, open-ended one: a bank challenge, or a two-step chain between two categories."""
        for b in self.bank_challenge:
            if b["id"] not in self.used and b["answer"] not in self.used:
                self.mark(b["id"], b["answer"], *b.get("parts", []))
                return dict(b)
        return self.chain()

    def dropboth(self, level=4):
        """Take one letter out of each of two words to get two members of one category."""
        cats = list(self.lex.cats)
        self.rng.shuffle(cats)
        for c in cats:
            pairs = self.fresh(self.index("drop", c))
            if len(pairs) < 2:
                continue
            (m1, s1), (m2, s2) = self.rng.sample(pairs, 2)
            s1, s2 = self.rng.choice(s1), self.rng.choice(s2)
            cat = self.lex.cats[c]
            self.mark(m1, m2, s1, s2)
            return {"kind": "dropboth", "type": "single", "id": f"dropboth-{m1}-{m2}", "cat": c, "source": "",
                    "clue": f"Take one letter out of each of these words to get two {cat['plural']}: "
                            f"{say_word(s1)}, and {say_word(s2)}.",
                    "answer": f"{m1} {m2}", "parts": [m1, m2], "accept": [],
                    "rating": max(rate("drop", m1, cat, self.lex), rate("drop", m2, cat, self.lex)) + 1,
                    "hints": [f"The first one starts with {letter_name(m1[0])}.",
                              f"The second one starts with {letter_name(m2[0])}."],
                    "reveal": f"{m1.capitalize()} and {m2}: {s1} without a letter is {m1}, and {s2} is {m2}."}
        return None

    def bonus(self, answer, cat_name):
        """After a solve: one more letter change from the answer gives a member of another category."""
        for c, cat in self.lex.cats.items():
            if c == cat_name:
                continue
            hits = [m for m in cat["all"] if m.isalpha() and one_change(answer, m)]
            if len(hits) == 1 and hits[0] in cat["single"] and hits[0] not in self.used:
                m = hits[0]
                self.mark(m)
                return {"kind": "change", "cat": c, "source": answer, "answer": m, "accept": [], "rating": 3,
                        "clue": f"Bonus! Change one letter in {say_word(answer)}, to get {cat['singular']}.",
                        "hints": letter_hints(m), "reveal": f"{m.capitalize()}. Change one letter in {answer} "
                                                            f"and you get {m}.", "bonus": True}
        return None

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
            return {"kind": "chain", "type": "single", "id": f"chain-{x}-{y}", "challenge": True, "rating": 8,
                    "clue": f"Here's a challenge. Think of {A['singular']}. {how.capitalize()}, and you'll get "
                            f"{B['singular']}. What are they? There's only one answer I know of.",
                    "answer": f"{x} {y}", "accept": [], "parts": [x, y],
                    "hints": [f"{up1(A['singular'])} that starts with {letter_name(x[0])}.",
                              f"{up1(B['singular'])} that starts with {letter_name(y[0])}.",
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


def _squash(w):
    """Spelling noise the recognizer adds to a name: Sophia / Sofia, Phillip / Filip."""
    w = w.replace("ph", "f").replace("ck", "k").replace("ae", "e")
    return re.sub(r"(.)+", r"", w)


def edits(a, b):
    """Levenshtein distance."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def grade(puzzle, text, lex=None):
    """'right', 'half' (one of two parts), or 'wrong' for the player's words against the puzzle. An accepted
    answer written "grape+grate" needs both words. With the lexicon, a misheard spelling of a long answer counts
    when the misheard word is not itself a real word (Venin for Benin, Sophia for Sofia)."""
    toks = norm(text)
    joined = " ".join(toks)
    squashed = "".join(toks)

    def said(ans):
        if "+" in ans:
            return all(said(x) for x in ans.split("+"))
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
    if lex is not None:
        given = set(norm(puzzle.get("clue", ""))) | {puzzle.get("source", "")}
        for a in [puzzle["answer"]] + list(puzzle.get("accept", [])):
            a = a.lower()
            if " " in a or "+" in a or len(a) < 5:
                continue
            for t in toks:
                if t in given or t == a or (t in lex.valid and _squash(t) != _squash(a)):
                    continue
                if edits(_squash(t), _squash(a)) <= (1 if len(a) < 8 else 2):
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
                 r"word games?|let'?s (play|go|do (it|this|one|that))|hit me|bring it( on)?|i'?m ready|quiz me|"
                 r"same level|that level|like that)\b", re.I)
ROUND = re.compile(r"\b(rounds?|on[- ]?air|a series|a set|a bunch|a few|several|a quiz)\b", re.I)
CHALLENGE = re.compile(r"\b(challenges?|weekly|stumper|brain ?buster|hard one|toughie|real(ly)? (tough|hard) one)\b", re.I)
LADDER = re.compile(r"\b((ten|10) (questions|puzzles|in a row)|ladder|progressive(ly)?|gauntlet|level(s)? up|step by step|"
                    r"get(s|ting)? (harder|tougher)|increasing(ly)? (hard|difficult)|marathon)\b", re.I)
HARDER = re.compile(r"\b(harder|tougher|more difficult|too easy|trickier|challenge me|step it up|turn it up)\b", re.I)
EASIER = re.compile(r"\b(easier|simpler|too hard|too difficult|too tough|gentler|dial it down)\b", re.I)
A_BIT = re.compile(r"\b(a (little|bit|tad|touch)|slightly|somewhat)\b", re.I)
NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
LEVEL_NUM = re.compile(r"\blevel (\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", re.I)
LEVEL_WORDS = [(re.compile(r"\b(expert|genius|fiendish|brutal|hardest|very hard|really hard|insanely)\b", re.I), 9),
               (re.compile(r"\b(intermediate|medium|moderate|middle|normal|average)\b", re.I), 5),
               (re.compile(r"\b(easy|beginner|simple|gentle|starter)\b", re.I), 2),
               (re.compile(r"\b(hard|difficult|tough|advanced)\b", re.I), 7)]
KIND_CHANGE = re.compile(r"\b((another|different|other|new) (kind|type|sort|style|format)|something different|"
                         r"mix it up|change it up|switch it up)\b", re.I)
HINT = re.compile(r"\b(hints?|clue me in|help( me)?|nudge|give me a letter|first letter|another clue|a clue)\b", re.I)
REPEAT = re.compile(r"\b(repeat|say (it|that|the \w+) again|again,? please|one more time|"
                    r"what was (it|that|the (word|clue|puzzle|question))|read (it|that|the \w+) again|come again|"
                    r"pardon|(didn'?t|did not) (hear|catch))\b", re.I)
GIVEUP = re.compile(r"\b(give up|i give|tell me( the answer| what it is)?|what('?s| is| was) the answer|reveal|"
                    r"no idea|(i )?(don'?t|do not) know|pass|skip( it| this( one)?)?|stumped|beats me|i'?m stuck)\b", re.I)
NEW = re.compile(r"\b((new|different|another|next) (one|puzzle)|skip (it|this one)|move on)\b", re.I)
STOP = re.compile(r"\b((stop|end|quit|finish|enough)( with)?( the| this| these)? (puzzles?|round|game|challenge|ladder)|"
                  r"no more puzzles|let'?s (just )?(talk|chat)|that'?s enough)\b", re.I)
YES = re.compile(r"^\W*(yes|yeah|yep|yup|sure|ok(ay)?|absolutely|go ahead|go for it|let'?s do it|bring it on|hit me|"
                 r"why not|of course|please|definitely|you bet|i'?d love|alright|all right|sounds good|let'?s go|"
                 r"i'?m ready|ready|go on|do it|sim|si|oui|ja)\b", re.I)
NO = re.compile(r"^\W*(no|nope|nah|not (now|right now|really)|i'?m good|maybe later|pass|no thanks|i'?m done|later)\b",
                re.I)
GUESS_LEAD = re.compile(r"^\W*(?:(?:is it|it'?s|it is|i think|i'?d say|maybe|perhaps|how about|what about|could it be|"
                        r"would it be|my guess is|i guess|i'?ll (say|guess|go with)|the answer is|that'?s|that would be|"
                        r"um+|uh+|hmm+|oh|ok(ay)?|well|so|is the answer)\W+)*", re.I)
QUESTIONY = re.compile(r"^\W*(why|how|who|when|where|what|which|can you|could you|do you|did you|have you|are you|"
                       r"tell me about|explain|i don'?t (get|understand))\b", re.I)


def is_question(t):
    """Some sentence of it asks something ("That was fun. Who makes your puzzles?")."""
    return any(QUESTIONY.match(x) for x in re.split(r"(?<=[.!?])\s+", t))


# "Can you give me a puzzle?" asks for one; "What puzzles do you play?" only talks about them
REQUEST = re.compile(r"\b(give me|gimme|can (i|we) (have|get|try|do|play)|could (i|we) (have|get|try|do)|may i|"
                     r"(can|could|would) you (give|do|make|throw|run|start)|i('?d| would) like|i want|i'?ll take|"
                     r"let'?s (do|have|try|play|go)|another|next|one more|new one|hit me|how about|what about|"
                     r"throw me|try me|bring (it|on)|ready for)\b", re.I)
# the model offered a puzzle ("Would you like another?"): the player's "yes" should start one
OFFER = re.compile(r"\b(want|like|try|shall i|ready for|up for|how about)\b[^.?!]{0,40}\b(puzzles?|rounds?|challenges?|"
                   r"another|anagrams?|one|ladder)\b[^.!]*\?", re.I)
# a model sentence that is making up a puzzle of its own (small models do, despite the prompt)
INVENTED = re.compile(r"(?i:\banagram\s*(:|of\b|for you)|\bunscramble\b|"
                      r"\brearrange (them|these|the following|this|the letters)\b|\btake the letters\b|"
                      r"\b(form|make|spell|find) (a|another|one) (new )?word\b|"
                      r"\briddle\b[^.?!]*:|what am i\?|i'?m thinking of a (word|number)|here'?s (a|one|another|your) "
                      r"(new |little |quick )?(puzzle|riddle|anagram|challenge|question)\b|(what|which) (word|letters?)\b"
                      r"[^.?!]*\?)|\b(?:[A-Z][ ,.-]+){3,}[A-Z]\b")    # the last: spelled-out letters, T R A P


# an offer that is not a question: "I'm here whenever you're ready for another challenge."
OFFER_STATED = re.compile(r"\b(ready for|up for|in the mood for) (another|a|the next|one more|a new) (\w+ )?"
                          r"(puzzles?|rounds?|challenges?|one|ladder)\b", re.I)


def offer_kind(text):
    """What a sentence offered: "challenge", "round", "ladder", or True for a puzzle; None if nothing."""
    m = OFFER.search(text or "") or OFFER_STATED.search(text or "")
    if not m:
        return None
    s = m.group(0).lower()
    return "challenge" if "challenge" in s else "round" if "round" in s else "ladder" if "ladder" in s else True


def level_asked(t, level):
    """The level the player asks for, or None: "level six", "something intermediate", "harder", "a bit easier"."""
    if LADDER.search(t):          # "ten questions that get harder" is the ladder, not a level
        return None
    m = LEVEL_NUM.search(t)
    if m:
        v = m.group(1).lower()
        return max(1, min(10, int(v) if v.isdigit() else NUMWORD[v]))
    if HARDER.search(t):
        return min(10, level + (1 if A_BIT.search(t) else 2))
    if EASIER.search(t):
        return max(1, level - (1 if A_BIT.search(t) else 2))
    # "an intermediate one, please" asks for a level; "what's the hardest puzzle you've seen?" does not
    asking = REQUEST.search(t) or not is_question(t) and (ASK.search(t) or CHALLENGE.search(t) or
                                                           re.search(r"\blevel\b", t))
    for rx, v in LEVEL_WORDS:
        if rx.search(t) and asking:
            return v
    return None


# The host's own words around the mechanics. The shape follows the radio segments (puzzle/STYLE.md): the clock
# and precision of one (rule, worked example, quick items, last one flagged, a score), the delight and
# generosity of the other (praise a good miss, accept any valid answer out loud, say why a guess fails). The
# wording is ENIGMA's own; lines that are either host's signature are deliberately left out.
LEAD_SINGLE = ["Here's one to chew on.", "Try this on.", "Ears open. Here it comes.", "A quick one for you.",
               "Here's a little word trick.", "See what you make of this.", "Fresh one, just for you.",
               "Okay, here's your puzzle."]
LEAD_ROUND = ["Let's play a round.", "Round time. Here's the rule.", "I've got a little set for you.",
              "A round, same trick each time.", "Okay, a round. Listen for the rule."]
LEAD_LADDER = "Ten questions, each one harder than the last. Level one up to level ten. Ask for a hint any time."
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
LEVEL_UP = ["All right, turning it up: level {n}.", "Level {n} it is. Let's see you sweat.",
            "Fair enough. Level {n}, coming up."]
LEVEL_DOWN = ["Easing off: level {n}.", "Level {n}. A gentler one.", "No shame in that. Level {n}."]
OFFER_LINE = ["Want another?", "Another one?", "Ready for the next?"]
NUMBERS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


class Session:
    """What ENIGMA does with each thing the player says. The code keeps the puzzle, the answer, the level and
    the score; turn(text) returns a dict for the app:
      say        the app speaks this as is, with no model call (clues, hints, verdicts: fast and exact)
      note       a hidden note for the model, which then speaks its own short reply
      after      spoken verbatim after the model's reply (a clue is never left to the model to read)
      guard      the open puzzle: a sentence the model writes that contains its answer is not spoken
      tokens     the model's reply budget for this turn; sentences: at most this many of its sentences
      offer      spoken after the model's line if the model did not ask a question itself
    An empty dict means plain conversation."""

    def __init__(self, puzzles=None, seed=None):
        self.p = puzzles or Puzzles(seed)
        self.rng = self.p.rng
        self.level = 4              # 1-10
        self.cur = None             # the open puzzle (in a round or the ladder: the current item)
        self.round = None           # the round or ladder being played: its items, position, score
        self.ri = self.score = 0
        self.hint_i = 0
        self.offered = None         # the last thing said invited another: True, "round", "challenge", "ladder"
        self.streak = self.giveups = 0
        self.last_kind = None

    # -- state the UI shows
    def status(self):
        lv = f"level {self.level}"
        if self.round:
            if self.round.get("ladder"):     # each question carries its own level
                return f"ladder: question {self.ri + 1} of 10, level {self.ri + 1} · {self.score} right"
            return f"round: {self.ri + 1} of {len(self.round['items'])} · {self.score} right · {lv}"
        if self.cur:
            kind = "challenge" if self.cur.get("challenge") else "puzzle"
            hints = f" · {self.hint_i} hint{'s' if self.hint_i > 1 else ''}" if self.hint_i else ""
            return f"{kind} open{hints} · {lv}"
        return ""

    def open_clue(self):
        """The current clue, for the model's note when the player talks about something else."""
        if not self.cur:
            return ""
        if self.round and not self.round.get("ladder"):
            return f"{self.round['intro']} The current word: {self.cur['clue']}"
        return self.cur["clue"]

    # -- presenting
    def open(self, pz):
        self.cur, self.hint_i, self.offered = pz, 0, None
        self.last_kind = pz.get("kind")

    def present_single(self, text="", exact=False, avoid=None):
        cats = self.p.category_for(text)
        pz = self.p.single(self.level, cat=cats, avoid=avoid, exact=exact)
        if not pz:
            return {"say": "Hmm, I'm out of fresh ones like that. Ask me for a round instead?"}
        self.round = None
        self.open(pz)
        tail = " Take your time." if pz.get("challenge") else ""
        return {"say": f"{self.rng.choice(LEAD_SINGLE)} {pz['clue']}{tail}"}

    def present_challenge(self):
        pz = self.p.challenge()
        if not pz:
            return self.present_single()
        self.round = None
        self.open(pz)
        return {"say": pz["clue"] + " Take your time. Ask for a hint whenever you like."}

    def present_round(self, text=""):
        cats = self.p.category_for(text)
        r = self.p.round(self.level, cat=cats, n=7)
        if not r:
            return self.present_single(text)
        intro = r["intro"]
        if r["id"].startswith("gen-") and len(r["items"]) > 1:
            ex = r["items"].pop(0)        # the easiest one is the worked example, as on the radio
            intro += f" For example, {ex['clue'].rstrip('.')}, would be {ex['answer'].capitalize()}: {r['why']}."
        self.round, self.ri, self.score = r, 0, 0
        self.open(r["items"][0])
        return {"say": f"{self.rng.choice(LEAD_ROUND)} {intro} Number one: {self.cur['clue']}"}

    def present_ladder(self):
        """Ten questions at levels one to ten, a different kind each time where possible."""
        self.round = {"ladder": True, "items": [None] * 10, "intro": LEAD_LADDER, "id": "ladder"}
        self.ri, self.score = 0, 0
        return {"say": f"{LEAD_LADDER} {self.ladder_question()}"}

    def ladder_question(self):
        n = self.ri + 1
        pz = self.p.single(n, avoid=self.last_kind, exact=True) or self.p.single(n)
        self.round["items"][self.ri] = pz
        self.open(pz)
        return f"Question {NUMBERS[self.ri]}, level {n}. {pz['clue']}"

    def next_item(self, lead):
        """After an item in a round or the ladder is answered or revealed: the next one, or the end."""
        self.ri += 1
        self.hint_i = 0
        items = self.round["items"]
        if self.ri < len(items):
            if self.round.get("ladder"):
                return {"say": f"{lead} {self.ladder_question()}"}
            self.open(items[self.ri])
            label = self.rng.choice(LAST_LABEL) if self.ri == len(items) - 1 else \
                self.rng.choice(NEXT_LABEL).format(n=NUMBERS[self.ri])
            return {"say": f"{lead} {label}: {self.cur['clue']}"}
        score, n, ladder = self.score, len(items), self.round.get("ladder")
        self.round = self.cur = None
        self.offered = True
        if ladder:
            self.level = max(1, min(10, score))       # where the player topped out is their level now
        else:
            self.adapt(score / n >= 0.8, score / n < 0.4)
        tier = "all" if score == n else "most" if score / n >= 0.6 else "some" if score / n >= 0.3 else "few"
        answers = ", ".join(i["answer"] for i in items if i)
        what = "ladder" if ladder else "round"
        return {"say": f"{lead} {ROUND_END[tier].format(s=score, n=n)}",
                "note": f"[Note: the {what} is over ({score} of {n}; you already said the score). The answers "
                        f"were: {answers}. Add one short line, a pun on one answer if easy.]",
                "tokens": 60, "sentences": 2, "offer": "Another round, or a single puzzle?"}

    def adapt(self, up, down):
        if up and self.level < 10:
            self.level += 1
        elif down and self.level > 1:
            self.level -= 1

    # -- answers
    def right(self, word=None):
        """word: a valid answer other than the planned one, which the host accepts out loud."""
        pz = self.cur
        alt = self.rng.choice(VALID_ALT).format(G=word.capitalize(), g=word) + " " if word else ""
        hinted = self.hint_i > 0
        self.streak = 0 if hinted else self.streak + 1
        self.giveups = 0
        if self.round:
            self.score += 1
            a = " and ".join(pz.get("parts") or [pz["answer"]])
            return self.next_item(alt + self.rng.choice(RIGHT_QUICK).format(a=a, A=a.capitalize()))
        self.cur = None
        self.offered = True
        if self.streak >= 3:          # three clean solves in a row: one level up
            self.adapt(True, False)
            self.streak = 0
        ans = " and ".join(pz.get("parts") or [pz["answer"]]).capitalize()
        verdict = alt + self.rng.choice(SOLVED_HINTED if hinted else SOLVED).format(A=ans)
        if pz.get("kind") in OPS and not pz.get("bonus") and self.rng.random() < 0.35:
            b = self.p.bonus(pz["answer"], pz.get("cat"))
            if b:
                self.open(b)
                return {"say": f"{verdict} {b['clue']}"}
        # the verdict is spoken at once; the model's line follows while it plays (a short note reads fast)
        return {"say": verdict, "note": f"[Note: solved: {pz['reveal']} You already said it's right, so don't say so "
                                        f"again. Add one short warm line, a pun on the word if easy.]",
                "tokens": 60, "sentences": 2, "offer": self.rng.choice(OFFER_LINE)}

    def reveal(self):
        pz = self.cur
        self.streak = 0
        self.giveups += 1
        if self.giveups >= 2 and not (self.round and self.round.get("ladder")):   # the ladder sets it at the end
            self.adapt(False, True)
            self.giveups = 0
        if self.round:      # quick, as on the radio: just the word
            a = " and ".join(pz.get("parts") or [pz["answer"]])
            return self.next_item(f"{self.rng.choice(REVEAL_LEAD)} {a.capitalize()}.")
        text = f"{self.rng.choice(REVEAL_LEAD)} {pz['reveal']}"
        self.cur = None
        self.offered = True
        return {"say": text + " " + self.rng.choice(OFFER_LINE)}

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

    def set_level(self, lv):
        up = lv > self.level
        self.level = lv
        return self.rng.choice(LEVEL_UP if up else LEVEL_DOWN).format(n=lv)

    def present(self, t, offered=None, exact=False, avoid=None):
        """Whatever kind the player asked for (or was offered), at the current level."""
        if LADDER.search(t) or offered == "ladder" and not ROUND.search(t):
            return self.present_ladder()
        if CHALLENGE.search(t) or offered == "challenge" and not ROUND.search(t):
            return self.present_challenge()
        if ROUND.search(t) or offered == "round":
            return self.present_round(t)
        return self.present_single(t, exact=exact, avoid=avoid)

    # -- one turn
    def turn(self, text):
        t = text.strip()
        lv = level_asked(t, self.level)
        if self.cur:
            core = GUESS_LEAD.sub("", t)
            words = norm(core)
            g = grade(self.cur, t, self.p.lex)
            if g == "right":
                return self.right()
            if g == "half":
                return {"say": "That's half of it! Now the other one."}
            if STOP.search(t):
                pz, self.cur, self.round = self.cur, None, None
                return {"say": f"No problem. {self.rng.choice(REVEAL_LEAD)} {pz['reveal']}"}
            if REPEAT.search(t):
                again = (self.round["intro"] + " " if self.round and self.ri == 0 and
                         not self.round.get("ladder") else "") + self.cur["clue"]
                return {"say": "Sure. " + again}
            if GIVEUP.search(t) and lv is None:
                return self.reveal()
            if HINT.search(t):
                return self.hint()
            kind_change = KIND_CHANGE.search(t)
            if lv is not None or kind_change or NEW.search(t) or ROUND.search(t) or CHALLENGE.search(t) or \
                    LADDER.search(t) or ASK.search(t) and not words[3:]:
                if self.round and self.round.get("ladder") and lv is None and not (ROUND.search(t) or LADDER.search(t)):
                    return self.reveal()        # "next one" on the ladder: skip to the next question
                if self.round and not self.round.get("ladder") and lv is None and not \
                        (ROUND.search(t) or CHALLENGE.search(t) or LADDER.search(t) or kind_change):
                    return self.reveal()        # "next one" mid-round: skip to the next clue
                pz, self.cur, self.round = self.cur, None, None
                first = f"{self.rng.choice(REVEAL_LEAD)} {pz['answer'].capitalize()}. "
                if lv is not None:
                    first += self.set_level(lv) + " "
                nxt = self.present(t, exact=lv is not None, avoid=pz.get("kind") if kind_change else None)
                return {**nxt, "say": first + nxt.get("say", "")}
            if words and len(words) <= 4 and not is_question(t):
                return self.wrong(words, t)
            return {"note": f"[Note: a puzzle is open and unsolved: {self.open_clue()} The player said something "
                            f"that isn't a guess. Answer briefly without giving the answer away, then remind them "
                            f"they can guess, ask for a hint, or give up.]", "guard": self.cur, "tokens": 80,
                    "sentences": 3}
        offered, self.offered = self.offered, None
        if STOP.search(t):
            return {}
        kind_change = KIND_CHANGE.search(t)
        if is_question(t) and not REQUEST.search(t) and lv is None:
            return {}
        if lv is not None:
            line = self.set_level(lv)
            nxt = self.present(t, exact=True)
            return {**nxt, "say": f"{line} {nxt.get('say', '')}"}
        if LADDER.search(t) or CHALLENGE.search(t) or ROUND.search(t) or ASK.search(t) or kind_change or \
                self.p.category_for(t) and REQUEST.search(t):
            return self.present(t, avoid=self.last_kind if kind_change else None)
        if offered and YES.match(t):
            return self.present(t, offered=offered)
        if offered and NO.match(t):
            return {"note": "[Note: the player doesn't want another puzzle right now. Say that's fine in one short "
                            "sentence; you're happy to just chat.]", "tokens": 40, "sentences": 1}
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
