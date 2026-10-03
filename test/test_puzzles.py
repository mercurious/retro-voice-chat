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
print("FAILED" if fails else "OK", f"({fails} failures)")
sys.exit(1 if fails else 0)
