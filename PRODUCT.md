# Product

<!-- impeccable:product-schema 1 -->

## Platform

terminal

This value is outside the schema's `web`/`ios`/`android`/`adaptive` list on purpose. The app is a full-screen terminal UI: ANSI and 256-colour text in `foot`, under sway on a ROCKNIX handheld. There is no browser, no native toolkit and no touch input. Users act through the gamepad and their voice. The screen is a small landscape display (Retroid Pocket Flip 2), so the layout has to cope with narrow terminal widths. `App.render` and `fit_hints` in `app/retrovoice.py` already degrade for narrow screens.

## Users

ROCKNIX handheld hobbyists. They install the app from the Ports folder (`installer/Install-Retro-Voice-Chat.sh`) and use it away from a desk, holding only the handheld. They hold a button, talk, and hear an answer. They use it to chat with a local model, ask retro-gaming trivia, play word puzzles, or play Zork by voice. No keyboard is involved.

## Product Purpose

Push-to-talk voice chat with a language model that runs entirely on a gaming handheld. Speech recognition, the model and speech synthesis all run on the device. One app hosts several modes, each with its own host, screen colours and conversation: General Chat, Retro Gaming (TRIXY), Enigma Puzzles (ENIGMA) and Voice Zork. Success means it answers aloud within a few seconds and stays honest about what it knows. It must also work on the hardware the README names.

## Positioning

A voice companion that is fully local and gamepad-driven, built for a retro gaming handheld. Facts, puzzles and game state come from code, not from the model. TRIXY answers from a bank of checked trivia. ENIGMA's puzzles are generated and checked mechanically. Zork runs on the real Infocom story files through `dfrotz`. The model provides the voice; the code provides the truth.

## Operating Context

- Device: Retroid Pocket Flip 2 (SM8250, 8 GB) running ROCKNIX 20260901. Other SM8250 devices are untested.
- Launched from EmulationStation's Ports list, fullscreen on sway workspace `97:voice`. Quit returns the user to the frontend.
- Input: gamepad buttons (hold B or R1 to talk, A to stop, Y to repeat, X for the next voice, START for a new chat, SELECT for the mode menu, SELECT+START to quit) and voice commands ("switch to …").
- Audio: a USB-C or Bluetooth headset, or a 3.5 mm headset after `install.sh --jack-mic`. The built-in mic is not powered on stock ROCKNIX, and the app shows "no mic".
- Typical latency: 3–6 s to the first spoken word, measured on the device.

## Capabilities and Constraints

- Fully offline after install: no cloud, no account, no telemetry. Models are downloaded once into llamatalk's shared models directory.
- Every action must be reachable from the gamepad or by voice. Never require a keyboard or touch.
- Fast mode (Gemma 4 E2B) and smart mode (E4B). Smart mode only fits in 8 GB with little to spare.
- The CPU is shared between three local servers (ports 8091–8093). UI work must not compete with them, so render cheaply (about 10 fps of text).
- Instrumentation is a first-class feature, not debug output. Users must always be able to see what the system is doing and how it is performing: model loading and boot progress, the current state (LISTENING, HEARING, THINKING, SPEAKING), the input level, the active model and voice, speed and latency, battery, memory, and errors. Today this appears in the header, the status line and the bottom line. Per-turn timings go to `logs/turns.jsonl`.
- Status: a working prototype, tested on one device.

## Brand Commitments

- Name: **Retro Voice Chat**. The host names are fixed: TRIXY (said "Trixie"), ENIGMA, and the model family name in General Chat ("Gemma", "Qwen").
- Each mode has its own terminal palette (`bg`, `fg`, `colors` in `app/modes/*.py`): night sky (chat), phosphor green (retro), ink and newsprint (enigma), amber terminal (zork).
- ENIGMA's manner is a composite defined in `app/puzzle/STYLE.md`. It is never an impression of real radio hosts and never uses their shows' titles or signature lines.
- The AI disclosure in `README.md` stays. Measured numbers stay tied to a named device and ROCKNIX version.
- Identity: published under the pseudonymous `mercurious` account. Never add the maintainer's real name, institution or other accounts (see `AGENTS.md`).

## Evidence on Hand

- On-device measurements in `README.md` ("What to expect", Volume, ENIGMA).
- 40 checked retro-gaming trivia questions in `app/trivia.json`. The curated puzzle bank is in `app/puzzle/bank/`.
- No testimonials, user counts, press or benchmarks against other products exist. Do not invent any.

## Product Principles

1. **Local or nothing.** Nothing leaves the device, and there is nothing to sign up for.
2. **Hands on the pad.** Every interaction works by button or voice, at a glance on a small screen.
3. **Honest over fluent.** Facts, puzzles and game state come from code. When the model doesn't know, it says so.
4. **Show the machine.** Make loading, state, speed, battery and failures visible and legible. The user should never wonder whether the app is working.
5. **Measured, not claimed.** Performance and compatibility claims come from named-device runs.

## Accessibility & Inclusion

Voice is the main channel, and the gamepad is the fallback for every action. On-screen text must stay legible in each mode palette on a small, bright handheld display. State must never be shown by colour alone: the status line pairs glyphs and words (`● LISTENING`, `✖`).
