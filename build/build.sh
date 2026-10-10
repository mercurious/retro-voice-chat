#!/usr/bin/env bash
# Builds the release for an aarch64 ROCKNIX handheld: dist/retro-voice-chat/ and a tarball of it.
# Needs an arm64 Linux host with podman and git. Every source is fetched at a pinned commit and built in
# a container:
#   llamatalk      -> llamatalk/         llama-server, tts-server and models.sh (its own build/build.sh)
#   Frotz          -> games/dfrotz       the text-only interpreter (GPL-2.0-or-later), in build/Containerfile
#   Zork I-III     -> games/zorkN.z3     Infocom's compiled story files, MIT-licensed historicalsource repos
# Env: JOBS (default 3), MEM / MEMSWAP (container memory cap, default 3g / 8g),
#   LLAMATALK_SRC=<a llamatalk checkout at LLAMATALK_COMMIT> builds from it (and its build cache) instead of a fetch.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="$ROOT/build/work"; OUT="$ROOT/dist/retro-voice-chat"; IMAGE=retro-voice-chat-build
LLAMATALK=https://github.com/mercurious/llamatalk    LLAMATALK_COMMIT=091fd0054909ac0e9a67473b7642f89f725ce854
FROTZ=https://gitlab.com/DavidGriffith/frotz.git      FROTZ_COMMIT=042d7bcadc1e2a8090cf737c841d8b7fc14b6eff
ZORK1_COMMIT=97b7b3d68c075dd9af7da499c3e9690ada3471fd
ZORK2_COMMIT=3da9661098809788a99cef00f00c865c6c204f96
ZORK3_COMMIT=3ec9ed412b5f3cafe65d83c727d07db1fe4a86a8

fetch() {   # fetch <url> <commit> <dir>: that one commit, nothing else
  [ "$(git -C "$3" rev-parse HEAD 2>/dev/null)" = "$2" ] && return 0
  mkdir -p "$3"; git -C "$3" init -q
  git -C "$3" fetch -q --depth 1 "$1" "$2"
  git -C "$3" checkout -q --detach FETCH_HEAD
}

mkdir -p "$W"
LT=${LLAMATALK_SRC:-$W/llamatalk}
if [ -n "${LLAMATALK_SRC:-}" ]; then
  [ "$(git -C "$LT" rev-parse HEAD)" = $LLAMATALK_COMMIT ] && [ -z "$(git -C "$LT" status --porcelain)" ] \
    || { echo "LLAMATALK_SRC must be a clean checkout of llamatalk $LLAMATALK_COMMIT" >&2; exit 1; }
else fetch $LLAMATALK $LLAMATALK_COMMIT "$LT"; fi
JOBS=${JOBS:-3} "$LT/build/build.sh"
fetch $FROTZ $FROTZ_COMMIT "$W/frotz"
fetch https://github.com/historicalsource/zork1 $ZORK1_COMMIT "$W/zork1"
fetch https://github.com/historicalsource/zork2 $ZORK2_COMMIT "$W/zork2"
fetch https://github.com/historicalsource/zork3 $ZORK3_COMMIT "$W/zork3"

podman image exists $IMAGE || podman build -q -t $IMAGE "$ROOT/build"
podman run --rm --memory "${MEM:-3g}" --memory-swap "${MEMSWAP:-8g}" -e JOBS="${JOBS:-3}" -v "$W":/w:Z -w /w $IMAGE bash -c '
  set -e
  make -C frotz -s -j$JOBS dumb >/dev/null
  strip frotz/dfrotz
'

rm -rf "$OUT"; mkdir -p "$OUT/games"
cp -r "$LT/dist/llamatalk" "$OUT/"
cp "$W/frotz/dfrotz" "$OUT/games/"
for g in zork1 zork2 zork3; do cp "$W/$g/COMPILED/$g.z3" "$OUT/games/"; done
cp "$ROOT"/app/launch.sh "$ROOT"/app/retrovoice.py "$ROOT"/app/zgame.py "$ROOT"/app/trivia.json "$ROOT"/app/puzzles.py \
   "$ROOT"/install.sh "$ROOT"/README.md "$ROOT"/LICENSE "$ROOT"/THIRD_PARTY.md "$OUT/"
cp -r "$ROOT/ports" "$ROOT/extras" "$ROOT/test" "$ROOT/app/puzzle" "$ROOT/app/modes" "$OUT/"
rm -rf "$OUT/modes/__pycache__"
chmod +x "$OUT"/launch.sh "$OUT"/install.sh "$OUT"/test/*.sh "$OUT"/games/dfrotz
tar -C "$ROOT/dist" -czf "$ROOT/dist/retro-voice-chat-aarch64.tar.gz" retro-voice-chat
ls -la "$OUT" "$OUT/llamatalk/bin" "$OUT/games"; du -sh "$ROOT/dist/retro-voice-chat-aarch64.tar.gz"
