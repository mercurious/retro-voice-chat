# Third-party software and data

This repository holds its own code (MIT, see `LICENSE`) and two third-party data sets that ENIGMA's puzzle
book uses:

| component | in this repository as | upstream | licence |
|---|---|---|---|
| English Speller Database (SCOWL) word lists | `app/puzzle/common.txt`, `app/puzzle/extra.txt` | https://github.com/en-wl/wordlist | MIT-like, notice in `app/puzzle/WORDLIST-LICENSE.txt` |
| CMU Pronouncing Dictionary (trimmed, stress marks removed) | `app/puzzle/sounds.txt` | https://github.com/cmusphinx/cmudict | BSD-2-Clause-style, in `app/puzzle/SOUNDS-LICENSE.txt` |

The category lists, puzzle bank and style notes in `app/puzzle/` are this project's own work (MIT). The
style notes were written from listening to two radio puzzle programs; no audio, transcript or puzzle from
them is included.

A release tarball built by
`build/build.sh` also contains the binaries and story files below, each built or copied from the pinned
commit named in that script.

| component | in the tarball as | upstream | licence |
|---|---|---|---|
| llama.cpp | `bin/llama-server` | https://github.com/ggml-org/llama.cpp | MIT |
| pockettts.cpp (with its ggml submodule) | `bin/tts-server` | https://github.com/ServeurpersoCom/pockettts.cpp | MIT |
| Frotz (dumb interface) | `games/dfrotz` | https://gitlab.com/DavidGriffith/frotz | GPL-2.0-or-later |
| Zork I, II, III story files | `games/zork1.z3`, `zork2.z3`, `zork3.z3` | https://github.com/historicalsource/zork1 (and `zork2`, `zork3`) | MIT |

- **pockettts.cpp** is built with one small patch, `build/pockettts-pt-threads.patch` (the thread count
  can be set with `PT_THREADS`).
- **Frotz** is GPL software. `dfrotz` is built unmodified; its complete source is the commit pinned in
  `build/build.sh`. The app runs it as a separate program.
- **The story files** are Infocom's own compiled games, from the source releases under the MIT licence.

## Models

The installer downloads the models from Hugging Face (`models.txt`); none are redistributed here. Each
has its own licence or terms of use on its model card, which you accept by downloading it:

- `google/gemma-4-E2B-it-qat-q4_0-gguf`, `google/gemma-4-E4B-it-qat-q4_0-gguf`
- `ggml-org/Qwen3-ASR-0.6B-GGUF`
- `Serveurperso/pocket-tts-GGUF`
