#!/usr/bin/env bash
# Makes a draft GitHub release v<VERSION> of what is on origin/main: builds it from scratch (build/build.sh), checks the
# tarball, and uploads it with its SHA-256. The release stays a draft until someone publishes it on GitHub; the tag is
# made then.
# Needs what build/build.sh needs, plus gh with write access to the repo (GH_TOKEN works).
# Env: as build/build.sh (ENGINE=docker builds with docker); DRY=1 builds and checks the current commit without
#   uploading (any branch); PREBUILT=1 does not build: it checks and uploads the tarball already in dist/, built by
#   DRY=1 from this same commit on another machine (a build server) and copied here.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
NAME=retro-voice-chat; REPO=mercurious/$NAME; VER=$(cat VERSION); TAG=v$VER
TGZ=dist/$NAME-aarch64.tar.gz; INST="installer/Install-Retro-Voice-Chat.sh"   # the one-file Ports installer, attached as is
die() { echo "release: $*" >&2; exit 1; }

[ -z "$(git status --porcelain)" ] || die "the tree has uncommitted changes"
if [ -z "${DRY:-}" ]; then
  git fetch -q origin main
  [ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || die "HEAD is not origin/main"
  gh release view "$TAG" -R $REPO >/dev/null 2>&1 && die "$TAG already exists (raise VERSION)"
fi

if [ -z "${PREBUILT:-}" ]; then
  rm -rf build/work   # a release compiles everything from the pinned sources, nothing from an earlier build
  build/build.sh
fi
[ -f "$TGZ" ] || die "no $TGZ"
sh -n "$INST" || die "$INST does not parse"
BUILT=$(tar -xzOf "$TGZ" $NAME/BUILD.txt)
[ "$(echo "$BUILT" | head -1)" = "$NAME $VER $(git rev-parse HEAD)" ] || die "$TGZ is not $NAME $VER from this commit"
LIST=$(tar -tzf "$TGZ")
BAD=$(echo "$LIST" | grep -E '__pycache__|/logs/|/state/|/models/|prefs\.json|\.(zip|7z|nes|a26|gguf|state[0-9]*|srm|core)$' || true)
[ -z "$BAD" ] || die "the tarball carries files it must not: $BAD"
tar -xzOf "$TGZ" | grep -aE '192\.168\.[0-9]+\.[0-9]+' >/dev/null && die "the tarball carries a LAN address"
(cd dist && sha256sum "$(basename "$TGZ")" > "$(basename "$TGZ").sha256")
echo "release: $TGZ $(du -h "$TGZ" | cut -f1), $(echo "$LIST" | wc -l) files, $(cut -c1-16 "$TGZ.sha256")..."

[ -n "${DRY:-}" ] && { echo "release: DRY=1, not uploaded"; exit 0; }
NOTES=$(printf '%s\n' "$NAME $VER for aarch64 ROCKNIX handhelds, built and tested on a Retroid Pocket Flip 2." "" \
  "Install: see the README, section Install. Check the download with \`sha256sum -c $(basename "$TGZ").sha256\`." "" \
  '```' "$BUILT" '```')
gh release create "$TAG" -R $REPO --draft --target "$(git rev-parse HEAD)" --title "$NAME $VER" --notes "$NOTES" \
  "$TGZ" "$TGZ.sha256" "$INST"
