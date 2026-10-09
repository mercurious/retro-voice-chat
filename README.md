# Retro Voice Chat

Push-to-talk voice chat with a local language model on a retro handheld. Hold a button, talk, and it answers
out loud. Everything runs on the device: no cloud, no account, no network once the models are downloaded.

One app, several modes; **SELECT** switches between them, and each has its own host, screen colours and
conversation:

| mode | what it is |
|---|---|
| **General Chat** | the model as itself, named after its family ("Gemma", or "Qwen" for a Qwen model) |
| **Retro Gaming** | TRIXY (say "Trixie"), a retro computer companion with a bank of checked trivia |
| **Enigma Puzzles** | ENIGMA, a word-puzzle host: puzzles, rounds and challenges. See [ENIGMA](#enigma-word-puzzles) |
| **Voice Zork** | Infocom's Zork I, II and III, played by voice. See [Zork](#zork) |

More can be added: see [Modes](#modes).

Built and tested on a **Retroid Pocket Flip 2** (Snapdragon 865 / SM8250, 8 GB) running **ROCKNIX**.

> **AI disclosure.** This project was written with Claude Code (Anthropic's Claude Opus 5.5 and Claude
> Fable 5.1). Most of the code and this README are model output, produced under the author's direction.
> The author chose what to build, ran it on the hardware, and made every listening and usability
> judgment recorded here. Measurements were taken on the device named above. Treat it as a working
> prototype, not a finished product.

```
gamepad (push-to-talk)
  -> microphone (PipeWire)
  -> speech recognition: Qwen3-ASR-0.6B, llama-server            big cores 4-7, port 8091
  -> language model: Gemma 4 E2B (or E4B), llama-server          big cores 4-5, port 8092
  -> sentence splitter
  -> speech: Pocket TTS, tts-server, streamed                    big cores 6-7, port 8093
  -> peak limiter -> speaker or headphones
```

## What to expect

Measured on the Flip 2 (8 GB), CPU only:

| | fast mode (default) | smart mode |
|---|---|---|
| language model | Gemma 4 E2B, QAT Q4_0 | Gemma 4 E4B, QAT Q4_0 |
| time to the first spoken word (typed test turns) | 3.0-4.9 s | 3.6-4.9 s |
| the same with speech recognition (spoken turns) | 4.9-6.0 s | not measured |
| generation speed | about 10 tokens/s | 5.5-7 tokens/s |
| speech recognition | 1.0-1.7 s per utterance | same |
| speech synthesis | about 2x real time | same |
| memory left while running | about 3.5 GB | about 2.3 GB |

Small models make things up. A bank of 40 checked retro-gaming trivia questions and a few honesty rules
keep TRIXY from inventing trivia, but do not rely on it for facts.

## Requirements

- An aarch64 handheld running ROCKNIX with the sway session (the UI runs in `foot`), PipeWire, and
  Python 3. Tested only on the Flip 2 with ROCKNIX 20260901. Other SM8250 devices (Retroid Pocket 5,
  Mini) are likely to work and are untested; other chips need different core numbers (`RV_*_CPUS`).
- 8 GB of RAM. Smart mode fits in 8 GB with little to spare (`RV_SMART=0` hides it).
- Storage: 4.4 GB for the models (9.2 GB with smart mode, `install.sh --no-smart` to skip it), about 17 MB for the programs.
- **A microphone.** This is the part most likely to trip you up on a Flip 2:

| microphone | on stock ROCKNIX |
|---|---|
| USB-C or Bluetooth headset | used first when present |
| 3.5 mm headset (TRRS) | records white noise until capture is pinned to 16-bit: `install.sh --jack-mic` (the pin ETK installs; not yet tested on its own) |
| built-in mic | not powered by the stock device tree; the app shows "no mic" |

  The built-in mic needs a device tree that routes and powers it. The author's
  [ETK](https://github.com/mercurious/etk) kit does that on its own kernel entries; stock ROCKNIX does
  not yet. Headphones without a mic therefore leave the app with nothing to listen with.

## Install

On the handheld (over ssh), in a directory with enough room, for example on the SD card:

```sh
tar xzf retro-voice-chat-aarch64.tar.gz && cd retro-voice-chat
./install.sh                  # downloads the models (4.4 GB), adds the Ports entries
./install.sh --jack-mic       # optional: the 3.5 mm headset mic fix; reboot afterwards
./install.sh --smart          # optional: also the larger model, 4.8 GB more
```

Then refresh the game lists in EmulationStation and start **Retro Voice Chat** from Ports: one entry for every
mode and both models. Installing over an earlier release removes its separate **(smart)**, **Enigma Puzzles**
and **Retro Voice Zork** entries.
`./install.sh --uninstall` removes the Ports entries and the mic fix; delete the directory to remove the
rest.

There is no release tarball yet. To make one, run `build/build.sh` on an arm64 Linux machine with podman:
it fetches llama.cpp, pockettts.cpp, Frotz and the Zork story files at pinned commits and builds
`dist/retro-voice-chat-aarch64.tar.gz`.

## Controls

The buttons are named by position, with the Flip 2's own letters.

| button | action |
|---|---|
| hold B (bottom face) or R1 | talk, release to send |
| A (right face) | stop / interrupt |
| X (top face) | next voice (27 Pocket TTS voices, then "random") |
| Y (left face) | repeat the last reply |
| Start | new conversation (in this mode) |
| Select | the menu: modes, voice and model. D-pad to choose, A to pick, B or Select to close |
| Select+Start, or Home | quit |
| D-pad up/down | scroll the transcript |

The top right corner shows the battery, the lower right how full the model's memory (context window) is.
The status line says which microphone is in use; plugging or pulling a headset updates it within about
two seconds.

**Voice.** X steps through the voices; after the last one comes **random**, a different voice each
session. Your choice is saved (`prefs.json` next to the app) and used the next time; until you choose,
it is random.

## The boot screen

While the models load, the screen shows what is running. The button hints and the mode's greeting appear
only once the model is ready, so nothing asks you to press a button that does not work yet.

```
  ·   v0.0.1 brought to you by mercurious assisted by claude
  ·   controller: built-in pad (via InputPlumber)
  ·   driver: none in use: the model runs on the CPU
  ·   llama.cpp: 0.5.0-dev (build 1, commit 6c7a87f), unpatched, CPU backend
  ·   tuning: LLM cores 4-5 x2 (prompt x2) · TTS cores 6-7 x2 (nice -10) · ASR cores 4-7 x4
  ·   load: CPU 6% · GPU off · RAM 44% of 7.4 GB
  ·   voice: javert (random)

GEMMA› Hi, I'm Gemma. Hold the B button or R1 and talk to me. Press select for other modes.
```

With the GPU option on, the driver line is what the driver reports about itself, for example
`llamadreno: Mesa 26.2.3 (git-94b0078f80) rusticl on FD650, OpenCL 3.1`. The GPU entry in `load` says
what the GPU is doing, not a percentage: this kernel exposes no GPU busy figure.

## Zork

Choose **Voice Zork** in the SELECT menu, or say "let's play Zork" (or "play Zork two", "Zork three") in any
mode. The games are Infocom's own story files, run by Frotz. The game writes every word of the story and keeps all
of its state; the language model never narrates.

- A line that already is a command ("Go north.", "Open the mailbox.") goes straight to the game. Anything
  else ("grab the leaflet and read it") goes to the language model, which turns it into game commands.
- Several moves fit in one line: "North, then take the egg, then up."
- The game's text is read aloud. "Save" and "restore" are the game's own; "quit the game" saves and goes
  back to the mode you came from. Switching modes saves the game too; coming back starts the last game
  played, and "restore" picks it up.

## Modes

**Switching.** SELECT opens the menu; the screen takes on each mode's colours as you move through it, and
A switches. You can also say it: "switch to puzzles", "go to retro gaming", "back to chat". A request only
another mode can answer moves there and is answered: "give me a puzzle" goes to ENIGMA, "let's play Zork two"
to Zork. Each mode keeps its own conversation and transcript, so going back picks up where you left off.
The app opens in the last mode used.

**Fast or smart.** The menu's **Model** row (shown when the smart model is installed) switches between fast
(Gemma 4 E2B) and smart (E4B). The model server restarts with the other model, which takes about as long as
starting the app; speech recognition and speech keep running, the conversation starts fresh, and the app
comes back in the same mode. The choice is kept for the next start.

**What it costs.** The model server holds one conversation at a time, so after a switch it reads the new
mode's prompt (and its conversation so far) again. The new mode's greeting is spoken at once while that
happens; a long conversation can take some seconds more before the first reply.

**Writing a mode.** A mode is one file in `app/modes/` with a subclass of `Mode` (`app/modes/base.py`) that
sets an `id`; it appears in the menu at its `order`. It names its host, prompt, greeting and colours, and
can hook into each turn: add hidden notes for the model (`before`, as Retro Gaming does with trivia), say
its own words with no model call (ENIGMA's puzzle book), screen what the model writes (`screen`), or take
the whole turn (`turn`, as Zork does). `chat.py` is the smallest example.

## ENIGMA: word puzzles

Choose **Enigma Puzzles** in the SELECT menu (or start with `RV_START=enigma`). Hold B and say what you'd like:

- "Give me a puzzle." One puzzle: an anagram, a letter change, a hidden word, a charade, a sound-alike...
  "A puzzle about birds" picks the category.
- "Let's do a round." A themed set of six or seven quick ones with a worked example first, read
  back to back, with the score at the end.
- "Give me a challenge." A two-step puzzle to chew on, like a listener challenge.
- "Ten questions that get harder." The ladder: one puzzle at each level from 1 to 10, a different kind each
  time, with the score at the end.
- Levels: "make it harder", "a bit easier", "level seven", "an intermediate one" (easy 2, intermediate 5,
  hard 7, expert 9). The status line shows the level. Topics: "a geography puzzle", "something about food".
- While a puzzle is open: just say your answer ("is it melon?", or spell it), "hint" (up to three, each
  closer), "say that again", "I give up", "next one", "harder", "easier".

**How it works.** A 2-4B model cannot make a fair letter puzzle: it reads words in chunks, not letters, so
its anagrams drop letters and its one-letter changes change two. So the code makes, checks, reads and
scores every puzzle (`app/puzzles.py`), and the model only hosts: it reacts to a solve, banters, and
answers questions about puzzles. A sentence the model writes that would give away an open answer is not
spoken. The puzzles come from:

- **generators**: letter operations (anagram, change / drop / add a letter, reversal, drop-and-rearrange,
  swapped first letters, consonyms, two-step chains) between common words and 49 hand-checked category lists
  (fruits, countries, U.S. states, instruments, presidents...), plus category puzzles (length and end letters,
  only two consonants, alphabetically between, acrostic rounds), two-letter prefixes and bonus puzzles. An
  answer is offered only if it is the one member its clue allows; obscure members never are. About 16,000
  puzzles, each rated 1-10.
- **a written bank** (`app/puzzle/bank/`): 150 single puzzles, 24 rounds and 40 challenges,
  original, each with machine-checked claims (`test/test_puzzles.py` fails if an anagram is not one, a
  hidden word is not hidden...). The sound-based ones (homophones, rhymes, spoonerisms) are the only
  claims not checked by code.

The code grades answers. A homophone the speech recognizer writes still counts ("pair" for *pear*, by the
CMU Pronouncing Dictionary, so "peer" does not), spelling an answer out works, any answer that satisfies the
puzzle is accepted out loud, and a wrong guess can hear which rule it broke (wrong length, two letters changed). Clues, hints, verdicts and reveals are the puzzle book's own words and play at once;
only the host's reactions wait for the model. The model's line after a solve is held to two finished
sentences (a sentence cut off by the token limit is never spoken), and if it starts making up a puzzle of its
own, which a small model does now and then despite its prompt, the puzzle book takes the turn and gives a real
one. Speech that the recognizer labels as another language (a short "yes" came back as Portuguese "sim") is
heard again with an English hint. The manner is a composite drawn from listening to two
radio puzzle programs (`app/puzzle/STYLE.md`); it is not an impression of either host, and no audio,
transcript or puzzle from them is in this repository.

Measured on the Flip 2, fast mode, typed turns: every puzzle turn (clue, hint, verdict, reveal, even a right
answer) starts playing in 0.6-0.9 s; the host's own line after a solve follows 0-3 s later, and plain chat
takes 2-5 s. The puzzle book loads and indexes in about 1.5 s while the model warms up. Smart mode's replies
took 4-6 s and gushed more; fast mode is the better host here.

**Speaking letters.** Pocket TTS garbles spelled words ("P-A-I-N-S" came back from a transcription test as
"PA ions", a lone "M." as "Monsieur"). The app rewrites only the audio: capitals with commas
("P, A, I, N, S"), "double-you" for W, and letter names after "the letter" ("the letter em"). The screen
keeps B-E-A-R.

## Volume

Pocket TTS speech is quiet next to a game, so the app makes it about 6 dB louder and caps the peaks with
a limiter (`RV_GAIN_DB`, default `12`, and `RV_CEIL_DB`, default `-1`). In listening tests on the Flip 2's
headphone jack at 60% volume that was judged loud enough and clean.

At 100% volume the Flip 2's headphone amp is on its top gain step and crackles on speech peaks. If you
listen that loud, set `RV_CEIL_DB=-6`, or turn the volume down.

## Settings

Environment variables for `launch.sh` (set them in a Ports entry):

| variable | meaning |
|---|---|
| `RV_MODE` | `fast` or `smart` for this launch (default: the menu's last choice, else fast) |
| `RV_MODELS` | the models directory |
| `RV_VOICE` | voice for this session, overriding the saved choice |
| `RV_SOURCE` | force a PipeWire source by name |
| `RV_GAIN_DB`, `RV_CEIL_DB` | voice level, see Volume |
| `RV_CONTEXT` | `trim` (default: forgets the oldest exchanges when memory fills) or `endurance` (never forgets) |
| `RV_START` | the mode to open in: `chat`, `retro`, `enigma` or `zork` (default: the last one used) |
| `RV_SYSTEM`, `RV_TEMP`, `RV_TRIVIA` | the opening mode's prompt, temperature, trivia bank |
| `RV_LLM_MODEL`, `RV_LLM_DRAFT`, `RV_LLM_CPUS`, `RV_LLM_T`, `RV_LLM_TB` | another model, MTP draft head, core pinning and threads |
| `RV_ASR_CPUS`, `RV_TTS_CPUS` | cores for speech recognition and synthesis |
| `RV_START_GAME` | `1`-`3`: start in that Zork |
| `RV_PERSONA` | `trixy` or `enigma`: open in Retro Gaming or Enigma Puzzles (older name for `RV_START`) |
| `RV_PUZZLE_SEED` | fix ENIGMA's puzzle choices (for repeatable tests) |
| `RV_FONT` | UI font size |
| `RV_LLM_GPU`, `RV_OCL_DIR` | run the language model on the Adreno GPU, see below |

## The GPU option

With a separate OpenCL build of llama.cpp and a private Mesa rusticl driver (the planned `llamadreno`
kit), `RV_LLM_GPU=1` runs the language model on the Adreno 650. It works, but on an 8 GB Flip 2 it does
not make conversation faster: the first word arrives at the same time, generation is the same speed, and
it costs about 3 GB more memory. The larger model does not fit at all. It reads long prompts about twice
as fast, which only matters when the conversation's memory is re-read. It is off by default and nothing
here depends on it.

## Testing without talking

`test/test_say.sh <label> <prompts.txt>` runs typed turns through the language model and speech
synthesis and prints timings; `SILENT=1` plays into a null sink. Commands can also be written to the
FIFO `/tmp/retrovoice.ctl`: `ptt_down`, `ptt_up`, `inject <wav>`, `say <text>`, `stop`, `voice [name]`,
`repeat`, `new`, `mode <id>`, `menu`, `btn <name>` (a press and release: `up`, `down`, `east` for A,
`south` for B, `select`...), `quit`. Each turn in `logs/turns.jsonl` names its mode. Per-turn metrics go to `logs/turns.jsonl`.

ENIGMA: `python3 test/test_puzzles.py` checks the whole puzzle book on any machine (every bank claim, every
generated puzzle's uniqueness, grading and the session logic). `test/enigma.txt` is a typed session;
`python3 test/make_solve_script.py 7 > test/enigma_solve.txt` writes one in which the player solves
puzzles, to run with `RV_START=enigma RV_PUZZLE_SEED=7 test/test_say.sh <label> test/enigma_solve.txt`.

## Status

Works on the author's Flip 2. Not yet tested: a ROCKNIX install without the author's ETK kit, the
20261001 ROCKNIX release, USB-C microphones on the current build, any other handheld. Reports from other
devices are welcome; please say what hardware and ROCKNIX version you ran it on.

## Licence

MIT, see `LICENSE`. The programs and story files a release bundles, and the models the installer
downloads, have their own licences: see `THIRD_PARTY.md`.
