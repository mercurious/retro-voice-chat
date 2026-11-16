---
version: 1
slug: "app-retrovoice-py"
primary_target: "app/retrovoice.py"
related_targets: ["app/modes/base.py"]
---

## Scope

The whole full-screen terminal UI of `app/retrovoice.py` (foot, 106×30 cells at the default size 22 on the Flip 2): boot/title, main conversation screen, SELECT menu, error state. Mode: Operate.

## Audience and job

A ROCKNIX handheld player holding only the gamepad, at arm's length. At a glance: what the app is doing and what to press; what was said; how the machine is coping (speed, latency, context, memory, battery, model load); which host is on and which others exist.

## Constraints

Per-mode colour worlds stay. Button hints are always on screen. The credit moves to the title screen, typed in portmart's manner. Not busy, not generic hacker or neon, no CPU cost while the models run, text legible at arm's length. Every fact the old screen showed stays.

## Direction contract

THESIS: Every spoken turn is posted like an arcade score; the machine's performance is something you watch, not dig for. It refuses the default chat-client arrangement of a grey list, a transcript and a status bar, with stats buried in one dim line.

OWN-WORLD: Each host has a marquee: a solid truecolour field owning the left rail (cobalt for chat, deep phosphor for TRIXY, plum for ENIGMA, burnt amber for Zork) over the mode's own terminal ground. Rail modules use small inverted header tabs and a hairline rule, with no boxes. Arcade rank colours (gold, coral, cyan, violet) are used only on the BEST TURNS rows. Timing series: hear = cyan, think = gold, speak = bright neutral. ENIGMA's and Zork's host colours sit next to gold, so the host colour can't mark speaking. The bar segments carry the hue; the legend is dim. Display type is portmart's 5×7 half-block pixel font, used for the title wordmark and the one score number only. Buttons are portmart pills (◖A◗) in pad colours.

STORY: The player sees which host they are talking to and who else is on the bill. They watch each answer arrive and see exactly how long it took, broken into hearing, thinking and speaking. They trust the device because nothing about its state is hidden.

FIRST VIEWPORT: Left rail, 26 columns, as the marquee field. From the top: the app name; HOSTS (every mode, with a swatch in its own colour, ▶ on the active host; under SELECT this is the menu, with Voice and Model rows); LAST TURN as the time to first word in 4-row pixel digits; BEST TURNS, the session's top four times ranked in arcade colours; MACHINE (model and tok/s, context as a tape meter, free memory, battery with watts). Main column: host name and subtitle with the voice on the right; the transcript with speaker tags, each answered turn followed by a timing bar whose length is its exact duration (one cell per 0.25 s); the status line; button pills. The bottom row is portmart's breadcrumb bar: ◆ > ROCKNIX > device > mic > voice ── servers ✓.

FORM: Code-led terminal build. Signature move: the turn timing bar plus the score post. The title screen is an attract-mode screen: the hosts' colours chase letter by letter through the pixel wordmark like marquee bulbs while the servers load, each with a live line; then the credit types on portmart's ╰─ line. seed: seed:64bffab95c8bf364

RISK: Arcade costume. Hold to exactly one large number, no glow, no blinking except the new-score row for 3 s; it stays a working screen first.
