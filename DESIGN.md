---
name: Retro Voice Chat
description: A full-screen terminal marquee for push-to-talk voice chat on a ROCKNIX handheld, where every spoken turn is posted like an arcade score.
colors:
  bar-ground: "#0f1216"
  rule-slate: "#2a3038"
  muted-steel: "#9ca3b0"
  bright-neutral: "#e8eaf0"
  signal-cyan: "#00dbe4"
  crumb-pink: "#ff4fd8"
  alarm-red: "#ff5f5f"
  warn-amber: "#ffb000"
  ok-green: "#4ade80"
  hear-cyan: "#5fd7ff"
  think-gold: "#ffd75f"
  rank-coral: "#ff8f6b"
  rank-violet: "#d7a1ff"
  pad-b-red: "#ff5a6e"
  pad-x-blue: "#5aa9ff"
  pad-system-sand: "#d4c090"
  pill-ink: "#05060a"
  chat-ground: "#0b1020"
  chat-text: "#d8e2f6"
  chat-host: "#87afff"
  chat-dim: "#5f5f87"
  chat-player: "#ffd7af"
  chat-status: "#5fafaf"
  chat-field: "#1d3270"
  chat-ink: "#e8eeff"
  chat-quiet: "#a9b8e6"
  retro-ground: "#030a03"
  retro-text: "#33ff66"
  retro-host: "#00ff00"
  retro-dim: "#008700"
  retro-player: "#ffaf00"
  retro-status: "#00d7d7"
  retro-field: "#0d4a1e"
  retro-ink: "#d2ffdc"
  retro-quiet: "#86d39b"
  enigma-ground: "#0e0b1a"
  enigma-text: "#f2e3c0"
  enigma-host: "#ffd787"
  enigma-dim: "#af875f"
  enigma-player: "#87d7ff"
  enigma-status: "#d7af87"
  enigma-field: "#45285e"
  enigma-ink: "#f6ead0"
  enigma-quiet: "#c6b1d6"
  zork-ground: "#0c0800"
  zork-text: "#ffb000"
  zork-host: "#ffaf00"
  zork-dim: "#875f00"
  zork-player: "#ffffd7"
  zork-status: "#d78700"
  zork-field: "#4d2c00"
  zork-ink: "#ffe2a8"
  zork-quiet: "#d9ab62"
typography:
  display:
    fontFamily: "F57 half-block pixel font (screen.py, drawn with ▀▄█)"
    fontSize: "4lh"
    lineHeight: 1
    letterSpacing: "1ch"
  headline:
    fontFamily: "monospace"
    fontSize: "22pt"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "1ch"
  title:
    fontFamily: "monospace"
    fontSize: "22pt"
    fontWeight: 700
    lineHeight: 1
  body:
    fontFamily: "monospace"
    fontSize: "22pt"
    fontWeight: 400
    lineHeight: 1
  label:
    fontFamily: "monospace"
    fontSize: "22pt"
    fontWeight: 400
    lineHeight: 1
spacing:
  cell: "1ch"
  gutter: "2ch"
  rail: "26ch"
  rail-tab-inset: "2ch"
  rail-content-inset: "3ch"
  hint-gap: "3ch"
components:
  pill-a:
    backgroundColor: "{colors.ok-green}"
    textColor: "{colors.pill-ink}"
    typography: "{typography.title}"
    padding: "0 1ch"
    height: "1lh"
  pill-b:
    backgroundColor: "{colors.pad-b-red}"
    textColor: "{colors.pill-ink}"
    typography: "{typography.title}"
    padding: "0 1ch"
    height: "1lh"
  pill-x:
    backgroundColor: "{colors.pad-x-blue}"
    textColor: "{colors.pill-ink}"
    typography: "{typography.title}"
    padding: "0 1ch"
    height: "1lh"
  pill-y:
    backgroundColor: "{colors.warn-amber}"
    textColor: "{colors.pill-ink}"
    typography: "{typography.title}"
    padding: "0 1ch"
    height: "1lh"
  pill-r1:
    backgroundColor: "{colors.muted-steel}"
    textColor: "{colors.pill-ink}"
    typography: "{typography.title}"
    padding: "0 1ch"
    height: "1lh"
  pill-system:
    backgroundColor: "{colors.pad-system-sand}"
    textColor: "{colors.pill-ink}"
    typography: "{typography.title}"
    padding: "0 1ch"
    height: "1lh"
  breadcrumb-bar:
    backgroundColor: "{colors.bar-ground}"
    textColor: "{colors.bright-neutral}"
    typography: "{typography.body}"
    height: "1lh"
    width: "100%"
  marquee-chat:
    backgroundColor: "{colors.chat-field}"
    textColor: "{colors.chat-ink}"
    width: "{spacing.rail}"
  marquee-tab-chat:
    backgroundColor: "{colors.chat-ink}"
    textColor: "{colors.chat-field}"
    typography: "{typography.title}"
    padding: "0 1ch"
  marquee-retro:
    backgroundColor: "{colors.retro-field}"
    textColor: "{colors.retro-ink}"
    width: "{spacing.rail}"
  marquee-tab-retro:
    backgroundColor: "{colors.retro-ink}"
    textColor: "{colors.retro-field}"
    typography: "{typography.title}"
    padding: "0 1ch"
  marquee-enigma:
    backgroundColor: "{colors.enigma-field}"
    textColor: "{colors.enigma-ink}"
    width: "{spacing.rail}"
  marquee-tab-enigma:
    backgroundColor: "{colors.enigma-ink}"
    textColor: "{colors.enigma-field}"
    typography: "{typography.title}"
    padding: "0 1ch"
  marquee-zork:
    backgroundColor: "{colors.zork-field}"
    textColor: "{colors.zork-ink}"
    width: "{spacing.rail}"
  marquee-tab-zork:
    backgroundColor: "{colors.zork-ink}"
    textColor: "{colors.zork-field}"
    typography: "{typography.title}"
    padding: "0 1ch"
---

# Design System: Retro Voice Chat

## Overview

**Creative North Star: "The Arcade Marquee"**

The screen is a cabinet front for a voice companion. Each host owns a lit marquee down the left rail: a solid truecolour field over the mode's own terminal ground. The working screen sits to the right of it, and every spoken turn is posted like a score: a timing bar sized to the turn's real duration, the time to first word as one large pixel number, and the session's best times on a ranked board. The machine's state (models, speed, context, memory, battery, servers) is always on the glass, never in a log.

This is a terminal, not a web page. The medium is a grid of cells in `foot` (fontconfig `monospace`, size 22: 106×30 cells on the Retroid Pocket Flip 2). Every frame is drawn into `screen.Buffer` and written once; only rows that changed are resent. Colour is truecolour `#rrggbb` for the shared chrome and the marquees, and xterm-256 indexes for each mode's text palette. The terminal's own background and foreground are switched per mode with OSC 11/10. The density is that of a working instrument panel, and nothing animates unless it reports something.

The pixel font, the ◖A◗ button pills, the ◆ > breadcrumb status bar and the ╰─ credit line come from the maintainer's other ROCKNIX app, portmart, so the two read as one family on the same handheld. Nothing else of portmart's identity carries over. The arcade costume is held in check: there is one large number, no glow, and the only highlight that times out is the new-score row.

**Key Characteristics:**
- One truecolour marquee field per host, 26 columns wide, on the left. Everything else sits on the mode's terminal ground.
- Turns are measured visibly. Hear, think and speak are drawn as ━ segments at one cell per 0.25 s.
- The 5×7 half-block pixel font is used for exactly two things: the title wordmark and the LAST TURN number.
- Modules are inverted header tabs plus a hairline rule. There are no boxes.
- Every state pairs a glyph with a word (● LISTENING, ♪ SPEAKING, ✖ error, ✓ servers).
- The chrome is fixed: the status line, two rows of button pills and the breadcrumb bar sit at the bottom on every screen.

## Colors

Each mode is a complete colour world: a dark terminal ground, a 256-colour text palette and one saturated marquee field. A thin layer of shared truecolour chrome (bar, pills, timing, ranks and alarms) stays the same across all four.

### Primary
The primary is per host: the marquee field, its ink and its quiet text. Together they paint the left rail and nothing else.
- **Cobalt** (#1d3270), **Ice** (#e8eeff), **Haze** (#a9b8e6): General Chat's marquee.
- **Deep Phosphor** (#0d4a1e), **Mint** (#d2ffdc), **Sage** (#86d39b): TRIXY's marquee.
- **Plum** (#45285e), **Parchment** (#f6ead0), **Lilac** (#c6b1d6): ENIGMA's marquee.
- **Burnt Amber** (#4d2c00), **Lamp Cream** (#ffe2a8), **Honey** (#d9ab62): Zork's marquee.

### Secondary
Each mode's 256-colour palette is `colors = (host, dim, player, status)` in `app/modes/<id>.py`, with the terminal ground and text in `bg`/`fg`.
- **Host** (chat 111 Periwinkle, retro 46 Pure Green, enigma 222 Wheat Gold, zork 214 Amber): host name and header, host speaker tag and lines, the status word, the turn total, the host's swatch in HOSTS and its name on the title bill. It also colours the title wordmark's chase.
- **Dim** (chat 60 Dusk Slate, retro 28 Shadow Green, enigma 137 Sepia, zork 94 Umber): the subtitle, the voice label, rules under the header and above the status line, hint labels, the timing legend, the empty part of the mic meter, and boot lines that are waiting.
- **Player** (chat 223 Peach, retro 214 Amber, enigma 117 Sky, zork 230 Cream): the YOU tag and the player's lines.
- **Status** (chat 73 Teal, retro 44 Cyan, enigma 180 Tan, zork 172 Ochre): system lines (`·` tag) in the transcript.
- **Ground / Text** (Night Sky #0b1020 / Starlight #d8e2f6; Phosphor Black #030a03 / Phosphor Green #33ff66; Ink #0e0b1a / Newsprint #f2e3c0; Amber Black #0c0800 / Amber #ffb000): the terminal's own background and default foreground, set with OSC 11/10. While the SELECT menu is open, it previews the highlighted mode.

### Tertiary
The measurement and ranking colours, shared by every mode:
- **Hear Cyan** (#5fd7ff): the hear segment of the timing bar, and rank 3.
- **Think Gold** (#ffd75f): the think (or parser) segment, and rank 1.
- **Bright Neutral** (#e8eaf0): the speak segment, the credit text and ROCKNIX on the bar.
- **Rank Coral** (#ff8f6b), **Rank Violet** (#d7a1ff): ranks 2 and 4 on BEST TURNS.

### Neutral
- **Bar Ground** (#0f1216): the breadcrumb bar's fill along the bottom row.
- **Rule Slate** (#2a3038): the bar's `>` separators and its ── run, and the ╰─ credit hook.
- **Muted Steel** (#9ca3b0): the voice segment on the bar, the version line, `·` separators, the `/` and `+` between pills, and the R1 and ▲▼ pills.
- **Signal Cyan** (#00dbe4): the device name on the bar, the bar's right side while healthy, and a boot step that is running.
- **Crumb Pink** (#ff4fd8): the ◆ that starts the breadcrumb bar, and nothing else.
- **Alarm Red** (#ff5f5f), **Warn Amber** (#ffb000), **OK Green** (#4ade80): failure, warning and success. They mark ✖ errors and servers that are down, the mic segment (green with a source, amber without), context and battery thresholds, ✓ on a boot step, and ● LISTENING.
- **Pad colours** (B Red #ff5a6e, X Blue #5aa9ff, System Sand #d4c090; A uses OK Green, Y uses Warn Amber, R1 and ▲▼ use Muted Steel) with **Pill Ink** (#05060a) on top: the button caps, taken from portmart.

### Named Rules
**The Host Owns the Rail Rule.** The marquee field is the only large solid colour on screen and belongs to the host on view. A new mode brings its own `marquee = (field, ink, quiet)` and its own `bg`, `fg` and `colors`, and borrows from no other mode.

**The Rank Colours Stay on the Board Rule.** Gold, coral, cyan and violet as ranks appear only on BEST TURNS rows. LAST TURN is drawn in the marquee ink even when it sets a record. Hear-cyan and think-gold appear elsewhere only as timing segments.

**The Speak Is Neutral Rule.** Speaking is drawn in Bright Neutral, never in a host colour: ENIGMA's and Zork's host colours sit next to gold and would merge with the think segment.

**The Glyph and Word Rule.** No state is shown by colour alone. Red is always ✖ plus a message, the mic meter sits next to ● LISTENING, and servers read ✓ or ✖ with their names.

## Typography

**Display Font:** F57, portmart's 5×7 pixel font, drawn with half blocks (▀ ▄ █), two pixel rows per cell, so a glyph is 5 cells wide and 4 rows tall.
**Body Font:** the terminal's `monospace` (fontconfig alias) at foot size 22.

**Character:** One cell size for everything. Hierarchy comes from weight, capitals, letter-spacing, colour and, twice per screen at most, the pixel font.

### Hierarchy
- **Display** (pixel, 4 rows, 1-pixel gap between glyphs): the RETRO VOICE CHAT wordmark on the title screen, falling back to RETRO VOICE below 95 columns, and the LAST TURN number (`1.9`, capped at 99.9; nothing is drawn before the first timed turn).
- **Headline** (bold, caps, letter-spaced with single spaces): the host name in the header (`▓▒░ T R I X Y ░▒▓`, between the shaded blocks its title has) and the highlighted row's name in the SELECT panel.
- **Title** (bold caps): speaker tags right-aligned to the current host's name length (at least 4 cells) and ending in `›`, rail module tabs, the rail's RETRO VOICE CHAT label, status words (READY, LISTENING, THINKING, SPEAKING), boot step labels (ASR/LLM/TTS), the host bill and the turn total.
- **Body** (regular): transcript lines wrapped to the column, panel copy, MACHINE values.
- **Label** (regular, in Dim or Quiet): subtitles, hint labels, the timing legend, MACHINE keys, the note under the score.

### Named Rules
**The Two Big Things Rule.** The pixel font is used for the wordmark and the score and nowhere else. The SELECT panel spells the host name in letter-spaced bold text, not pixels.

**The Caps Are Labels Rule.** Capitals mark names and states (hosts, YOU, module tabs, status words). Sentences, hints and readings stay in lower case.

## Layout

The grid is the terminal's: 106×30 cells on the Flip 2 at size 22. Rows are counted from the bottom, so the chrome stays fixed whatever the height.

**Main screen** (rail shown when the terminal is at least 80 columns by 18 rows):
- **Rail**: columns 0–25, rows 0 to rows−2, filled with the marquee field. Row 0 holds RETRO VOICE CHAT in bold ink at column 2. Modules start at row 2, each one a tab at column 2 followed by its rows, with one blank row between modules. Content is inset to column 3, and right-aligned values end at column 23. The modules are HOSTS (one row per mode, or per menu row), LAST TURN (5 rows: 4 for the pixel number with an `s` beside it, then the note), BEST TURNS (4) and MACHINE (6). When the screen is too short, BEST TURNS is dropped first, then LAST TURN.
- **Main column** starts at column 28 (rail plus a 2-cell gutter) and ends one cell from the right edge. Row 0 is the header: host name, the subtitle 3 cells after it, and `voice …` right-aligned. Row 1 is a dim ─ rule. The transcript, or the SELECT panel, runs from row 2 to rows−6. Row rows−5 is a dim ─ rule, rows−4 the status line, and rows−3 and rows−2 the button pills.
- **Bottom row** (rows−1): the breadcrumb bar, full width.

**Transcript rhythm:** one blank row between speakers. A turn's timing row sits directly under the host's last line, indented to the text column. Consecutive system lines stay together. The transcript scrolls from the bottom.

**Title screen:** the wordmark is centred, and its top sits 3 rows into a vertically centred 26-row block. Measured from the wordmark's top row, the version line is at +5, the host bill (names joined by `·`) at +7 and the boot list from +10. The boot list is a 50-column block centred on the screen: the label at +0, what is loading at +5 (at most 34 characters), the glyph at +40 and the time at +42. One line in Dim follows after a blank row: `local language models powered by llamatalk runtime` (the driver, llama.cpp and tuning details go to the transcript only). The breadcrumb bar is on rows−2 and the ╰─ credit on rows−1.

**Narrow and short screens:**
- Below 80×18 the rail disappears and the main column starts at column 1. The breadcrumb bar's right side then carries what the rail showed, in short form: first-word time, bat, ctx, tok/s and mem, then cpu. Items are dropped from the end until the line fits.
- Bar segments are dropped from the end, down to the ◆.
- Hint pills wrap to at most two rows, and the least-needed hints are dropped first.

### Named Rules
**The Fixed Floor Rule.** The bottom five rows (rule, status line, two pill rows, breadcrumb bar) are the same on every booted screen. A new screen draws into the transcript region, not around it.

## Elevation & Depth

The system is flat. There are no shadows and no box frames. Depth comes from three tonal moves: the marquee field set against the terminal ground; inverted tabs and the active HOSTS row, which swap field and ink; and the new best-turn row, filled with a mix of field and ink at 18% (chat #42548a, retro #306b40, enigma #654b73, zork #6d4d1e).

### Named Rules
**The No Box Rule.** Modules are separated by an inverted tab and a ─ hairline in the quiet colour. Never wrap a region in box-drawing corners.

## Shapes

The grid is square-celled and rectilinear. The only rounded form is the button pill: half-disc caps ◖ ◗ drawn in the pad colour around a label in Pill Ink on that colour. Horizontal lines are ─ for rules and ━ for timing. Small squares (■) are host swatches and ▮▯ are meter cells. ▶ marks the active host and the ready line.

## Components

### Button Pills
Physical and literal: each pill is the button as printed on the pad.
- **Shape:** ◖LABEL◗, one row tall. The caps are the pad colour on the cell's ground, and the label is bold Pill Ink on the pad colour.
- **Colours:** A OK Green, B Pad Red, X Pad Blue, Y Warn Amber, R1 and ▲▼ Muted Steel, SELECT and START System Sand.
- **Combinations:** alternatives are joined with `/` (B/R1) and chords with `+` (SELECT+START), both in Muted Steel. The label follows one cell after, in Dim, and groups are 3 cells apart.
- **Behaviour:** hints are ranked by priority and shown in a set order. The B/R1 talk hint is hidden when there is no mic. The menu has its own set (▲▼ choose, A select, B back).

### Breadcrumb Bar
portmart's status bar on the bottom row: a Bar Ground fill; ◆ in bold Crumb Pink; then ROCKNIX in Bright Neutral, the device in Signal Cyan, the mic (green, or amber with no source) and the voice in Muted Steel, separated by `>` in Rule Slate. On the title screen the extra segment is the host name in its host colour. A ─ run in Rule Slate fills the gap to a right-aligned summary: `cpu N% · servers ✓` in Signal Cyan, or `✖ ASR LLM` in Alarm Red when servers are down.

### Marquee Rail Modules
- **Tab:** ` TITLE ` in bold field-on-ink, followed by a ─ rule in Quiet that ends at column 23.
- **HOSTS:** each row shows ▶ (the mode in use), a ■ swatch in that host's colour, the name, and the last word of its subtitle right-aligned in Quiet. The active or highlighted row is inverted to ink, and its swatch takes the field colour. Modes that are not installed show their name in Quiet and `—` in place of the subtitle. Under SELECT the list adds Voice and Model rows.
- **LAST TURN:** the time to first word in pixel digits, in ink (Quiet with no turn yet). Underneath, in Quiet, `to first word · <how>`; for 3 s after a record it reads `1ST BEST TURN` in bold ink.
- **BEST TURNS:** `1ST  NAME`, with the time right-aligned. Each row is in its rank colour, and the new row is bold on the tint fill for 3 s. With no turns yet it reads `no times yet`.
- **MACHINE:** model and fast/smart, speed, context as an 8-cell ▮▯ meter with a percentage and token counts, free memory, and battery with watts or its charging state. Keys are in Quiet and values in ink. Context turns amber at 60% and red at 85%. Battery turns amber at 50% or below and red at 20% or below, unless it is charging.

### Turn Timing Bar
The signature component. Under each answered turn, ━ segments for hear (Hear Cyan), think or `parser` (Think Gold) and speak (Bright Neutral), each one cell per 0.25 s and at least one cell. A long turn is scaled down to fit, but never stretched. Parts under 0.05 s get no cell and no number. Then comes the legend (names in Dim, numbers in the default foreground) and, right-aligned, the total in bold host colour, or `not voiced`.

### Status Line
One row (rows−4), a glyph and word in bold, then detail:
- **READY:** `▶ READY` (or the mode's own status, such as the Zork room) in host colour, with the mic in Dim.
- **LISTENING:** `● LISTENING` in bold Alarm Red, then a 30-cell meter (▮ in host colour, ▯ in Dim), the elapsed seconds and `release to send`.
- **HEARING / THINKING:** the spinner, the word and `…` in host colour, then the note.
- **SPEAKING:** `♪ SPEAKING` in host colour, then `A to stop` in Dim.
- **ERROR:** `✖ message` in bold Alarm Red.
- **Menu:** `☰ HOSTS`, then `SELECT or B to go back` in Dim.

### SELECT Panel
It replaces the transcript: the highlighted row's name in letter-spaced bold host colour, then its blurb in the default foreground two rows down, then the action in Dim two rows below that (`A to switch: it keeps its own conversation`, `you are here`, `not installed`). The terminal colours and the rail preview the highlighted mode.

### Title Screen and Credit
The attract screen shown while the models load. Behind it, one of three backdrops, the next each launch (`prefs.json` keeps the last; `RV_BACKDROP` forces one), all squares of 2 columns by 1 row in shades between the mode's ground and its text colour, at 6 brightness levels: **ripple**, a checkerboard whose lit squares brighten and fade in rings spreading from the centre (3–15% toward the text colour); **breathe**, a lattice of squares (` ·▪■`) that grow and brighten, alternate squares in counter-phase; **sweep**, the lattice with a wave of size and brightness rolling diagonally (glyphs 8–30% toward the text colour). Each row of text sits on a band of clean ground two cells wider than the text on each side, so the squares move around the words. The wordmark arrives one letter every 0.04 s, then the host colours chase through it letter by letter at 2 Hz, like marquee bulbs. Each boot step's status is shown as `·` waiting (Dim), spinner running (Signal Cyan, elapsed seconds), `✓` done (OK Green, seconds taken) or `✖ did not start` (Alarm Red). The bottom row is portmart's credit line: `╰─` in Rule Slate, then the credit typed at 0.03 s per character in Bright Neutral, starting 0.8 s in, with a █ cursor. SELECT+START quit pills sit on the right when they fit.

### Motion
- Frames are drawn at most 10 a second while listening or after a change, about 6 a second for the header throb and spinners, and 4 a second on the title screen (its backdrop repaints nearly every row, about 20 ms a frame on a little core). Only changed rows are sent. Nothing is redrawn while idle.
- The spinner is ◐◓◑◒, turning at 4 Hz.
- The header's shaded blocks throb with the host: listening, they swell with the mic level; hearing and thinking, a swell runs outward from the name once a second; speaking, they pulse twice a second. Their colour moves between Dim and Host with them. Idle and in the menu they stand still in Host.
- The 3 s highlight is the only highlight that times out. Nothing blinks.

## Do's and Don'ts

### Do:
- **Do** give a new mode a full world in `app/modes/<id>.py`: `bg`/`fg` hex, `colors = (host, dim, player, status)` as 256-colour indexes, and `marquee = (field, ink, quiet)` in truecolour. Keep the field dark and saturated enough that ink and quiet read on it (shipped: ink 9.5–10.4:1, quiet 5.9–6.2:1).
- **Do** check that the dim index stays readable on the new ground. Dim carries hint labels and the timing legend. Shipped values range from 3.1:1 (chat) to 6.0:1 (enigma).
- **Do** draw new screens into `screen.Buffer` with `put`/`rput`/`fill`/`pill`, so the row-diff output keeps redraws cheap.
- **Do** pair every new state with a glyph and a word, and use Alarm Red, Warn Amber and OK Green for those meanings only.
- **Do** keep the button hints on screen and reuse the pad colours from `screen.PAD` for any new button.
- **Do** give anything measured a number with a unit (s, tok/s, GB, W, %), right-aligned when it sits in a column.

### Don't:
- **Don't** use the pixel font for anything but the wordmark and the LAST TURN number.
- **Don't** use rank colours outside BEST TURNS, or a host colour for the speak segment.
- **Don't** frame modules or panels with box-drawing corners. Use a tab and a ─ hairline.
- **Don't** add a second large number, glow, or blinking. The 3 s best-turn tint is the only highlight that times out.
- **Don't** let one mode's palette leak into another's rail or text. The menu previews a mode by switching to its whole world.
- **Don't** carry portmart's identity beyond the shared pixel font, pills, breadcrumb bar and credit line.
