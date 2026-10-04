#!/usr/bin/env python3
"""Writes a typed test session for test_say.sh in which the player solves puzzles, by playing the same session
here with the same seed (RV_PUZZLE_SEED) and the same puzzle book as the device.
Usage: python3 test/make_solve_script.py <seed> > test/enigma_solve.txt"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
import puzzles as P

s = P.Session(P.Puzzles(sys.argv[1] if len(sys.argv) > 1 else "7"))
lines = []


def say(line):
    lines.append(line)
    s.turn(line)


say("Give me a puzzle.")
say(f"Is it {s.cur['answer']}?")
say("Sure, another one.")
say("Hmm, can I get a hint?")
say(f"Oh! {s.cur['answer'].capitalize()}.")
say("Let's do an on-air round.")
while s.round:
    i = s.ri
    if i == 1:
        say("No idea, pass.")
    elif i == 3:
        say("Is it banana?")
        say(f"{s.cur['answer']}")
    else:
        say(f"{s.cur['answer']}!")
say("That was fun. Who makes up your puzzles?")
say("Let's do ten questions that get progressively harder.")
while s.round:
    pz = s.cur
    say("pass" if s.ri in (4, 8) else " and ".join(pz.get("parts") or [pz["answer"]]) + ".")
say("Give me a real challenge.")
say("Can I have a hint?")
say(" and ".join(s.cur.get("parts") or [s.cur["answer"]]) + "?")
print("\n".join(lines))
