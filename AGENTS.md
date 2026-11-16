# Repository Guidelines

## Project Overview

Retro Voice Chat is push-to-talk voice chat with local models on a Retroid Pocket Flip 2 (aarch64, ROCKNIX, CPU only by default). It ships as a ROCKNIX Ports entry. It has four modes: General Chat, Retro Gaming (TRIXY), Enigma Puzzles (ENIGMA) and Voice Zork. The user switches modes with SELECT or by voice. The servers and models come from the sibling project **llamatalk**, pinned in `build/build.sh`. The models are downloaded at install and never committed.

## Architecture & Data Flow

```
gamepad/FIFO → InputThread → App.q → main loop (render ~10 fps)
PTT span → MicStream (parec ring buffer) → transcribe() → ASR llama-server :8091
  → switch_target() / mode.claims() → mode.turn()  (Zork)
                                    → chat_turn(): mode.before() → stream_reply() SSE → LLM llama-server :8092
  → split_sentences() → mode.screen() → speak() → tts_q → speaker_loop → tts-server :8093
  → Limiter → Player (pacat)
```

- **`app/retrovoice.py`** is a monolith. It contains `App` (state, UI, routing), `InputThread`, `MicStream`, `Player`, `Limiter`, `transcribe`, `stream_reply`/`complete`, `split_sentences` and `clean_for_speech`.
- **Threads, not async.** These run as daemon threads: `InputThread`, `work_loop` (consumes `work_q`), `speaker_loop` (consumes `tts_q`), `MicStream._pump`, `Player._feed` and `boot`. Shared state is guarded by explicit locks (`kv_lock`, `cap_lock`, `Player.lock`, `MicStream.lock`, `Zork.lock`).
- **Interrupts use a generation counter.** Every interrupt bumps `App.gen`, and queued work tagged with an old `gen` is dropped. New queued work must carry `gen` and check it.
- **HTTP** goes through stdlib `urllib` to OpenAI-style endpoints: `/v1/audio/transcriptions`, `/v1/chat/completions` and `/v1/audio/speech`. Zork's `complete()` uses a GBNF `grammar` to get JSON commands.
- **Modes are plugins.** `app/modes/__init__.py:discover()` imports every module except `base` and collects `Mode` subclasses that have a truthy `id`, sorted by `(order, id)`. The menu and the "switch to …" voice aliases pick up new modes automatically.
  - Hooks are defined in `app/modes/base.py`: `setup`, `warm`, `available`, `claims`, `enter`, `leave`, `turn`, `before`, `screen`, `after`, `reset`, `status`, `ready_line`, `close` and `system()`.
  - `before()` returns a dict with the keys `say`, `note`, `tokens`, `sentences`, `guard`, `offer` and `after`. The LLM is called only when there is a `note` or no `say`.
- **Puzzles come from code, not the model.** `app/puzzles.py` builds and checks every puzzle: `Lexicon`, the generators, `Puzzles` and the `Session` state machine. The LLM only supplies the voice. `app/puzzle/STYLE.md` defines ENIGMA's manner.
- **Zork.** `app/zgame.py:ZGame` drives `dfrotz` over pipes.
- **`app/launch.sh`**:
  - Picks the model: `RV_MODE`, then the `model` key in `prefs.json`, then `fast`. `smart` (E4B) is used only if its GGUF exists.
  - Refuses to start if ports 8091–8093 are busy.
  - Starts the three servers and opens a fullscreen `foot` window on sway.
  - Restarts the LLM and the app when the app writes `logs/restart`.

## Key Directories

| Path | Purpose |
|---|---|
| `app/` | Runtime: `retrovoice.py`, `puzzles.py`, `zgame.py`, `launch.sh`, `trivia.json` |
| `app/modes/` | One file per mode (`chat.py` is the minimal example) |
| `app/puzzle/` | Word lists (SCOWL, trimmed CMU dict), `categories.json`, curated `bank/{singles,challenges,rounds}.json`, `STYLE.md` |
| `build/` | `Containerfile` (ubuntu:24.04), `build.sh` (cross-build), `release.sh` (draft GitHub release), `es-art.py` (redraws `ports/images/`, needs Pillow); `build/work/` is scratch |
| `installer/` | One-file on-device Ports installer/updater |
| `ports/` | Ports entry template (`@RV_HOME@` substituted by `install.sh`), its ES artwork in `images/` (header `<image>`, icon `<marquee>`) and `gamelist.py`, which `install.sh` uses to upsert the `gamelist.xml` entry |
| `extras/` | WirePlumber S16LE capture pin for the 3.5 mm mic (`--jack-mic`) |
| `test/` | Puzzle checks, installer sandbox test, on-device prompt driver and scripts |
| `dist/`, `research/`, `logs/`, `prefs.json` | Gitignored; never commit (`research/` holds podcast audio and must stay local) |

## Development Commands

```sh
python3 test/test_puzzles.py                  # puzzle bank/generators/Session; prints "OK (0 failures)"; ~5 s
test/test_install.sh [dist/retro-voice-chat]  # installer in a temp HOME, fake models, no network; "N/13 passed"

build/build.sh                                # arm64 Linux host, podman → dist/retro-voice-chat-aarch64.tar.gz
ENGINE=docker JOBS=4 MEM=4g build/build.sh
LLAMATALK_SRC=/path/to/llamatalk build/build.sh   # must be clean at LLAMATALK_COMMIT

DRY=1 build/release.sh                        # build + tarball checks, no upload, any branch
PREBUILT=1 build/release.sh                   # upload a dist/ tarball built elsewhere
build/release.sh                              # clean tree, HEAD == origin/main, gh auth → draft v$(cat VERSION)

# on device (ROCKNIX)
./install.sh [--no-smart] [--jack-mic] [--no-models] | --uninstall
./launch.sh --headless
RV_START=enigma RV_PUZZLE_SEED=7 test/test_say.sh mylabel test/enigma_solve.txt
python3 test/make_solve_script.py 7 > test/enigma_solve.txt
echo "say what is choplifter" > /tmp/retrovoice.ctl   # FIFO drives a running app without a mic
```

There is no lint or format tooling and no CI.

## Code Conventions & Common Patterns

- **Python 3 standard library only.** No `requirements.txt` and no pip dependencies; keep it that way, because the device has no package manager for Python libraries. Modules import each other as top-level names (`import puzzles`, `import zgame`) because `app/` is on `sys.path`.
- **Style.** 4-space indent and lines of about 120 columns. Compact multi-statement lines are common. Every module starts with a purpose docstring. Names: `snake_case` functions, `CamelCase` classes, `UPPER` constants and env-derived settings. Match the surrounding density rather than reformatting.
- **Configuration.** Every setting is an `RV_*` env var read at module top with a default, e.g. `RV_LLM_URL`, `RV_START`, `RV_PUZZLE_SEED`, `RV_GAIN_DB`. A new env var needs a row in the README Settings table.
- **Errors.** HTTP failures become `RuntimeError(llm_error())`. `work_loop` catches per-turn exceptions, shows `error: …` and returns to READY. Best-effort file I/O swallows `OSError`. `threading.excepthook` logs to `logs/events.log`.
- **Persistence.** Write files atomically with `.tmp` plus `os.replace`, as `save_prefs` does. `prefs.json` holds `voice`, `mode`, `model` and `zork`.
- **Adding a mode.**
  1. Create `app/modes/<name>.py` with a `Mode` subclass. It needs a unique lowercase `id`, an `order` and `label`/`prompt`/`greet`; add `aliases` and `heard` regex fixes if needed.
  2. Gate missing assets in `available()`.
  3. Update the README mode table and the `RV_START` values.
- **Puzzle content.**
  - Every bank entry needs `check` ops (`words`, `change`, `anagram`) that pass `check_puzzle`. Run `test/test_puzzles.py` after any edit to `app/puzzles.py` or `app/puzzle/`.
  - ENIGMA lines (`LEAD_*`, `HINT_*`, `SOLVED*`, …) follow `STYLE.md`. No material copied from the radio shows.
- **Shell scripts.** `build/*.sh` are bash with `set -euo pipefail`. Everything that runs on the device (`install.sh`, `installer/`, `ports/`, `launch.sh`, `test_install.sh`) is POSIX `sh`, because ROCKNIX has no guaranteed bash. Pinned sources use commit hashes, not tags.

## Important Files

- `app/retrovoice.py`: entry point, main loop, `--headless` flag and the control FIFO (`RV_CTL`, default `/tmp/retrovoice.ctl`).
- `app/launch.sh`: server startup and restart loop, the runtime's real entry point.
- `app/modes/base.py`: the mode contract.
- `app/puzzles.py`: ENIGMA engine. The docstring's reference to `puzzle/bank_check.py` is stale; the checker is `check_puzzle`.
- `build/build.sh`: pins for llamatalk, Frotz and Zork; assembles the tarball and writes `BUILD.txt`.
- `build/release.sh`: tarball guards. It rejects `__pycache__`, `logs/`, `prefs.json`, `*.gguf`, ROMs and saves, and any `192.168.*` address.
- `VERSION`: release version; the tag is `v$VERSION`.
- `README.md` and `THIRD_PARTY.md`: user docs and the licences of bundled data. Bundling new data or binaries requires a `THIRD_PARTY.md` entry plus a licence file next to the data.

## Runtime/Tooling Preferences

- **Target:** aarch64 ROCKNIX (glibc 2.41), sway/Wayland, PipeWire (`parec`/`pacat`), evdev gamepads. The container builds on ubuntu:24.04 (glibc 2.39) so the binaries run on the device.
- **Native binaries** (`llama-server`, `tts-server`, `dfrotz`) are built only through `build/build.sh` with podman or docker. Do not compile them on the host by hand.
- **Releases** are `gh release create --draft`. Before any `gh` command, follow the identity rules below.
- **Commits:** subjects are long, descriptive and in sentence case, with an optional `Topic: ` prefix (`ENIGMA: …`, `release.sh: …`). Branches are kebab-case topics (`ports-installer`, `smart-on-8gb`).

## Testing & QA

- **Automated:**
  - `test/test_puzzles.py` is a plain-assert script with a `bad()` counter and a nonzero exit on failure. It is not pytest. Add checks in the same style, keep the final `OK`/`FAILED` line, and make sure it passes before committing.
  - `test/test_install.sh` covers the installer's model-directory logic. Add numbered `ok $? "…"` blocks inside the `$T` sandbox.
- **On device, manual:** `test/test_say.sh` sends each line of a `.txt` script (`trivia.txt`, `verify.txt`, `modes.txt`, `enigma.txt`) as `say` over the FIFO. It reports per-turn timings and GPU/OOM `dmesg` deltas, read by a person; there are no assertions. It needs the three servers and `logs/turns.jsonl`.
- **Not covered:** ASR and the audio path, button handling, the non-ENIGMA modes (beyond `modes.txt`), `launch.sh` and the build. Treat changes in these areas as needing a device run. If behaviour changes would affect the measured numbers in the README sections "What to expect", Volume and ENIGMA, re-measure them or flag them as stale.

## Git identity firewall

The maintainer has two GitHub identities that must never cross. Each repo belongs to exactly
one of them, and the owner of its `origin` remote decides which. Every commit, push, issue,
PR and doc in this repo uses this repo's identity only.

**Lane: `mercurious` (pseudonymous).** This repo is `mercurious/retro-voice-chat` (public).

- Commit as `mercurious <dutch.money@gmail.com>`. That is already this repo's `user.email`.
- Keep the maintainer's real name, institution and other accounts out of everything here:
  code, docs, commit messages, issues and PRs. Nothing in this repo may link this identity to
  the other one.
- `gh` usually has the other account active. Before pushing, or if a push fails with
  "Repository not found" or 403, run `gh auth switch --user mercurious`. When you're done,
  switch back to the account that `gh auth status` showed as active before.

On the maintainer's machines, a Claude Code `PreToolUse` hook enforces this:
`~/.claude/hooks/git-identity-firewall.py`, registered on `Bash` in `~/.claude/settings.json`
(self-tests: `python3 ~/.claude/hooks/test_git_identity_firewall.py`). It runs before
`git commit|merge|rebase|cherry-pick|am|revert|push`, including inside `ssh HOST '...'`, and
before `gh repo create --push` and `gh pr create`. It reads the origin owner, the configured
`user.email`, and any `-c user.*`, `--author` or `GIT_*_EMAIL` override. It denies the command
when that identity doesn't belong to the owner's lane. The owner-to-email map is `RULES` in the
script. A repo with no remote is allowed.

If the hook denies a command, the identity is wrong. Fix `user.email`, or ask the maintainer.
Don't route around the hook: no overrides, no other shells, no rewriting the remote. Agents
other than Claude Code aren't covered by that hook, but they are covered by the next one.

A second firewall runs inside git itself, so it covers every tool (Claude Code, gemini, copilot,
a plain shell): the global `core.hooksPath` is `~/.config/git/identity-firewall/hooks`, the
logic is in `firewall.py`, and the self-tests are in `test_firewall.py`. `pre-commit` and
`commit-msg` block the other lane's names and email addresses in staged changes, file paths
and commit messages, and check the commit identity. `pre-push` checks every outgoing commit.
Git has no global identity (`user.useConfigOnly`), so each repo needs its own `user.name`
and `user.email` (`git config --local`). The repo's own hooks in `.git/hooks` still run after
the firewall. Never pass `--no-verify` or change `core.hooksPath`; only the maintainer may
bypass a block.
