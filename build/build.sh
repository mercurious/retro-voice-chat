#!/usr/bin/env bash
# Builds the release for an aarch64 ROCKNIX handheld: dist/retro-voice-chat/ and a tarball of it.
# Needs an arm64 Linux host with podman and git. Every source is fetched at a pinned commit and built in
# the container (build/Containerfile):
#   llama.cpp      -> bin/llama-server   CPU only, unpatched
#   pockettts.cpp  -> bin/tts-server     + build/pockettts-pt-threads.patch (thread count from PT_THREADS)
#   Frotz          -> games/dfrotz       the text-only interpreter (GPL-2.0-or-later)
#   Zork I-III     -> games/zorkN.z3     Infocom's compiled story files, MIT-licensed historicalsource repos
# Env: JOBS (default 3), MEM / MEMSWAP (container memory cap, default 3g / 8g).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="$ROOT/build/work"; OUT="$ROOT/dist/retro-voice-chat"; IMAGE=retro-voice-chat-build
LLAMA=https://github.com/ggml-org/llama.cpp          LLAMA_COMMIT=6c7a87f7e5e5cd75b8a641c3471f2dee84a6ed17
POCKET=https://github.com/ServeurpersoCom/pockettts.cpp POCKET_COMMIT=e6215096f35cdb4c81c6be452ce7b31225fed8ff
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
fetch $LLAMA $LLAMA_COMMIT "$W/llama.cpp"
fetch $POCKET $POCKET_COMMIT "$W/pockettts.cpp"
git -C "$W/pockettts.cpp" submodule update -q --init --depth 1
git -C "$W/pockettts.cpp" apply --check "$ROOT/build/pockettts-pt-threads.patch" 2>/dev/null \
  && git -C "$W/pockettts.cpp" apply "$ROOT/build/pockettts-pt-threads.patch"
grep -q PT_THREADS "$W/pockettts.cpp/src/backend.h" || { echo "PT_THREADS patch did not apply" >&2; exit 1; }
fetch $FROTZ $FROTZ_COMMIT "$W/frotz"
fetch https://github.com/historicalsource/zork1 $ZORK1_COMMIT "$W/zork1"
fetch https://github.com/historicalsource/zork2 $ZORK2_COMMIT "$W/zork2"
fetch https://github.com/historicalsource/zork3 $ZORK3_COMMIT "$W/zork3"

podman image exists $IMAGE || podman build -q -t $IMAGE "$ROOT/build"
podman run --rm --memory "${MEM:-3g}" --memory-swap "${MEMSWAP:-8g}" -e JOBS="${JOBS:-3}" -v "$W":/w:Z -w /w $IMAGE bash -c '
  set -e
  ARCH="-DGGML_NATIVE=OFF -DGGML_CPU_ARM_ARCH=armv8.2-a+dotprod+fp16 -DGGML_OPENMP=ON -DBUILD_SHARED_LIBS=OFF"
  [ -f b-llama/build.ninja ] || cmake -S llama.cpp -B b-llama -G Ninja -DCMAKE_BUILD_TYPE=Release $ARCH \
    -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF >/dev/null
  cmake --build b-llama -j$JOBS --target llama-server
  [ -f b-pocket/build.ninja ] || cmake -S pockettts.cpp -B b-pocket -G Ninja -DCMAKE_BUILD_TYPE=Release $ARCH >/dev/null
  cmake --build b-pocket -j$JOBS --target tts-server
  make -C frotz -s -j$JOBS dumb >/dev/null
  strip b-llama/bin/llama-server frotz/dfrotz
  strip "$(find b-pocket -name tts-server -type f | head -1)"
'

rm -rf "$OUT"; mkdir -p "$OUT/bin" "$OUT/games"
cp "$W/b-llama/bin/llama-server" "$OUT/bin/"
cp "$(find "$W/b-pocket" -name tts-server -type f | head -1)" "$OUT/bin/"
cp "$W/frotz/dfrotz" "$OUT/games/"
for g in zork1 zork2 zork3; do cp "$W/$g/COMPILED/$g.z3" "$OUT/games/"; done
cp "$ROOT"/app/launch.sh "$ROOT"/app/retrovoice.py "$ROOT"/app/zgame.py "$ROOT"/app/trivia.json \
   "$ROOT"/install.sh "$ROOT"/models.txt "$ROOT"/README.md "$ROOT"/LICENSE "$ROOT"/THIRD_PARTY.md "$OUT/"
cp -r "$ROOT/ports" "$ROOT/extras" "$ROOT/test" "$OUT/"
chmod +x "$OUT"/launch.sh "$OUT"/install.sh "$OUT"/test/*.sh "$OUT"/bin/* "$OUT"/games/dfrotz
tar -C "$ROOT/dist" -czf "$ROOT/dist/retro-voice-chat-aarch64.tar.gz" retro-voice-chat
ls -la "$OUT" "$OUT/bin" "$OUT/games"; du -sh "$ROOT/dist/retro-voice-chat-aarch64.tar.gz"
