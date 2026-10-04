#!/usr/bin/env python3
"""Checks ENIGMA's puzzle book on any machine (no models needed): python3 test/test_puzzles.py
- every bank puzzle's mechanical claims hold (anagrams are anagrams, hidden words are hidden, ...)
- generated puzzles: each answer is in its category, follows from its source word, and is the only member
  that does; hints and reveals are consistent
- the session logic: grading, hints, rounds, give-ups, and that clues never contain their answers"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import puzzles as P

fails = 0


def bad(msg):
    global fails
    fails += 1
    print("FAIL", msg)


book = P.Puzzles(seed=1)
lex = book.lex

# bank
bank = P.load_bank()
ids = set()
free = 0
for b in bank:
    if b.get("id") in ids:
        bad(f"duplicate id {b.get('id')}")
    ids.add(b.get("id"))
    for e in P.check_puzzle(b, lex):
        bad(e)
    items = b["items"] if b.get("type") == "round" else [b]
    free += sum(any(c.get("op") == "free" for c in i.get("check", [])) for i in items)
print(f"bank: {len(bank)} entries ({sum(b.get('type') == 'round' for b in bank)} rounds, "
      f"{sum(bool(b.get('challenge')) for b in bank)} challenges), {free} items rest on a 'free' claim")

# generators
book.warm()
n = 0
book.pool()
for (op, cat), pairs in book._index.items():
    c = lex.cats[cat]
    rivals = {m for m in c["all"] if m.isalpha()}
    for member, srcs in pairs:
        if member not in c["single"]:
            bad(f"{op}/{cat}: {member} is not a fair member")
        for s in srcs:
            n += 1
            if not P.fits(op, s, member):
                bad(f"{op}/{cat}: {s} does not give {member}")
            others = [m for m in rivals if m != member and P.fits(op, s, m)]
            if others:
                bad(f"{op}/{cat}: {s} also gives {others}")
            if s in lex.block or s not in lex.common:
                bad(f"{op}/{cat}: source {s} is not a clean common word")
print(f"generators: {n} (source, answer) pairs checked")

# the other generated kinds: each claim holds and the answer is the only one in its list
pool = book.pool()
kinds = {}
for e in pool:
    rating, kind, c, ans, x = e
    kinds[kind] = kinds.get(kind, 0) + 1
    if not 1 <= rating <= 10:
        bad(f"{kind} {ans}: rating {rating}")
    if kind in P.OPS:
        continue
    cat = lex.cats.get(c)
    members = sorted(m for m in cat["all"] if m.isalpha()) if cat else []
    if kind == "startend":
        rivals = [m for m in members if (len(m), m[0], m[-1]) == (len(ans), ans[0], ans[-1])]
    elif kind == "consonants":
        rivals = [m for m in members if set(P.skeleton(m)) == set(x)]
        if set(P.skeleton(ans)) != set(x) or len(x) != 2:
            bad(f"consonants: {ans} is not only {x}")
    elif kind == "between":
        rivals = [m for m in cat["all"] if x[0] < m < x[1]]
    elif kind == "prefix2":
        a_, b_ = x
        rivals = [q for q in P.ONSETS if q + a_ in lex.common and q + b_ in lex.common]
        ans_ = ans
        if not (ans + a_ in lex.common and ans + b_ in lex.common):
            bad(f"prefix2: {ans}+{a_}/{b_} are not words")
        rivals = [ans] if rivals == [ans] else rivals
    else:
        bad(f"unknown kind {kind}")
        continue
    if rivals != [ans]:
        bad(f"{kind}/{c}: {ans} is not the only answer: {rivals}")
    it = book.build(e)
    if P.leaks(it["clue"], it):
        bad(f"{kind}: the clue gives away {ans}: {it['clue']}")
print("pool:", len(pool), "rated puzzles,", ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
for lv in range(1, 11):
    if not any(e[0] == lv for e in pool):
        bad(f"no generated puzzle at level {lv}")

# session
s = P.Session(P.Puzzles(seed=3))
r = s.turn("give me a puzzle")
pz = s.cur
if not r.get("say") or not pz:
    bad("no puzzle presented")
else:
    if P.leaks(pz["clue"], pz):
        bad(f"clue contains its answer: {pz['clue']}")
    h = s.turn("can I have a hint")
    if s.hint_i != 1 or pz["hints"][0] not in h.get("say", ""):
        bad(f"hint: {h}")
    w = s.turn("is it zzzz")
    if w.get("note") or s.cur is not pz:
        bad(f"a wrong guess should keep the puzzle: {w}")
    ok = s.turn(f"I think it's {pz['answer']}")
    if not ok.get("note") or s.cur is not None:
        bad(f"the right answer was not accepted: {ok}")
r = s.turn("let's do a round")
if not s.round:
    bad(f"no round: {r}")
else:
    n_items = len(s.round["items"])
    first = s.cur
    s.turn(first["answer"].upper() + "!")
    if s.score != 1:
        bad("round answer not counted")
    for _ in range(n_items - 1):
        last = s.turn("pass")
    if s.round or not last.get("note"):
        bad(f"round did not end: {last}")
for spoken, want in (("M E L O N", "right"), ("melons", "right"), ("lemon", "wrong"), ("M-E-L-O-N", "right")):
    if P.grade({"answer": "melon"}, spoken) != want:
        bad(f"grade {spoken!r} != {want}")
# the recognizer's homophones count; the clue's own word never does
for pz, spoken, want in (({"answer": "tern", "clue": "Add one letter to Ten, T-E-N, to get a bird."}, "turn", "right"),
                         ({"answer": "pear", "clue": "Change one letter in Bear, B-E-A-R, to get a fruit."}, "pair", "right"),
                         ({"answer": "moose", "clue": "Change one letter in Mouse, M-O-U-S-E, to get an animal."},
                          "mouse", "wrong"),
                         ({"answer": "melon"}, "lemon", "wrong")):
    if P.grade(pz, spoken) != want:
        bad(f"grade {spoken!r} for {pz['answer']} != {want}")
# a wrong guess hears why: the wrong length, one letter off, a valid answer outside the plan is accepted
t = P.Session(P.Puzzles(seed=8))
fruit = lambda: {"kind": "change", "cat": "fruit", "source": "bear", "clue": "Change one letter in Bear, B-E-A-R, "
                 "to get a fruit.", "answer": "pear", "accept": [], "hints": ["h"], "reveal": "Pear.", "level": 1}
t.cur = fruit()
if "letters" not in t.turn("melon").get("say", ""):
    bad("a wrong-length guess was not told its length")
t.cur = fruit()
if t.turn("peer").get("say") not in P.NEAR:
    bad("a guess one letter off was not called close")
t.cur = {**fruit(), "answer": "pear", "source": "lime", "kind": "change",
         "clue": "Change one letter in Lime, L-I-M-E, to get a fruit."}
r = t.turn("lime")
if t.cur is None:
    bad("the clue's own word was accepted")
if P.grade({"answer": "sage rage", "parts": ["sage", "rage"]}, "sage?") != "half":
    bad("half credit")
q = P.Session(P.Puzzles(seed=5))
for line in ("What's the hardest puzzle you've ever seen?", "That was fun. Who makes up your puzzles?"):
    if q.turn(line):
        bad(f"a question about puzzles started one: {line}")
for line in ("Can you give me a puzzle?", "How about a round about fruit?"):
    q.cur = q.round = None
    if not q.turn(line).get("say"):
        bad(f"a request phrased as a question was not answered with a puzzle: {line}")
# levels: asked for by number, by name, relatively; questions about hard puzzles don't count
for line, lv, want in (("level six please", 4, 6), ("give me an intermediate one", 4, 5), ("make it harder", 4, 6),
                       ("a little harder", 4, 5), ("too hard, easier please", 6, 4), ("something expert level", 4, 9),
                       ("What's the hardest puzzle you've ever seen?", 4, None),
                       ("ten questions that get harder", 4, None)):
    if P.level_asked(line, lv) != want:
        bad(f"level_asked({line!r}) = {P.level_asked(line, lv)}, want {want}")
# the ladder: ten questions climbing from level one; the score sets the level at the end
lad = P.Session(P.Puzzles(seed=14))
r = lad.turn("let's do ten questions that get progressively harder")
ratings = []
for i in range(10):
    if not lad.round or not lad.round.get("ladder"):
        bad(f"the ladder ended early at {i}")
        break
    ratings.append(lad.cur.get("rating"))
    last = lad.turn(" and ".join(lad.cur.get("parts") or [lad.cur["answer"]]) if i < 6 else "pass")
if lad.round or "6 of 10" not in last.get("say", ""):
    bad(f"ladder end: {last}")
if any(abs((r or 0) - (i + 1)) > 1 for i, r in enumerate(ratings)):
    bad(f"ladder ratings do not climb 1-10: {ratings}")
if lad.level != 6:
    bad(f"after 6 of 10 the level should be 6, is {lad.level}")
# a topic picks categories; a model sentence inventing a puzzle is caught, praise is not
if not set(book.category_for("a geography puzzle please") or []) >= {"country", "state"}:
    bad("geography is not a topic")
for line, want in (("Anagram: T R A P E Z E.", True), ("Here's a riddle for you: what has keys?", True),
                   ("Take the letters of 'listen' and rearrange them to form a word that means to pay attention.", True),
                   ("You're a master of anagrams.", False), ("Want another one?", False),
                   ("Senator rearranged gives treason, what a twist.", False)):
    if bool(P.INVENTED.search(line)) != want:
        bad(f"INVENTED on {line!r} != {want}")
for line, want in (("I'm here whenever you're ready for another challenge.", "challenge"),
                   ("Would you like another round?", "round"), ("Want another?", True), ("I love puzzles.", None)):
    if P.offer_kind(line) != want:
        bad(f"offer_kind({line!r}) = {P.offer_kind(line)}, want {want}")
# a misheard long answer counts unless the misheard word is a real word
for spoken, ans, want in (("Sophia", "sofia", "right"), ("Venin", "benin", "right"), ("melon", "lemon", "wrong")):
    if P.grade({"answer": ans}, spoken, lex) != want:
        bad(f"fuzzy grade {spoken} for {ans} != {want}")
print("FAILED" if fails else "OK", f"({fails} failures)")
sys.exit(1 if fails else 0)
