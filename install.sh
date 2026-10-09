#!/bin/sh
# Retro Voice Chat installer. Runs ON the handheld, from the unpacked release directory (put it where
# there is room: the models are 4.4 GB, 9.2 GB with --smart).
#   ./install.sh [--smart] [--jack-mic] [--no-models]      ./install.sh --uninstall
#   --smart      download gemma-4-E4B for smart mode (then offered in the app's SELECT menu). Automatic on a
#                device with 10 GB of RAM or more (12 GB Flip 2); skipped on 8 GB, where launch.sh would not
#                offer it anyway. --no-smart skips it everywhere.
#   --jack-mic   install the capture format pin the Flip 2's 3.5 mm headset mic needs (see README)
#   --no-models  skip the downloads (RV_MODELS already has them)
# Env: RV_MODELS (default ./models), RV_PORTS (default /storage/roms/ports).
set -u
H=$(cd "$(dirname "$0")" && pwd); M=${RV_MODELS:-$H/models}; P=${RV_PORTS:-/storage/roms/ports}
WP=${HOME:-/storage}/.config/wireplumber/wireplumber.conf.d
ENTRIES="Retro Voice Chat.sh"
# earlier releases had an entry per persona and per model; they are now one app (SELECT switches both)
OLD="Retro Voice Chat (smart).sh|Retro Voice Zork.sh|Enigma Puzzles.sh|Enigma Puzzles (smart).sh"
# prototype launchers from the ollamadreno kit and the dev copies: matched by what they exec, not by name
STALE_RE="ollamadreno/voice/launch.sh|enigma-dev/launch.sh|rvc-dev/launch.sh"
# smart mode (E4B, ~5.5 GB resident) needs the headroom of a 12 GB device; an 8 GB one runs fast mode only
RAM_MB=$(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo 2>/dev/null)
SMART=""; [ "${RAM_MB:-0}" -ge 10000 ] && SMART=1
JACK=""; MODELS=1
for a in "$@"; do
  case $a in
    --smart) SMART=1 ;; --no-smart) SMART="" ;; --jack-mic) JACK=1 ;; --no-models) MODELS="" ;;
    --uninstall)
      echo "$ENTRIES" | tr '|' '\n' | while read -r e; do rm -f "$P/$e"; done
      echo "$OLD" | tr '|' '\n' | while read -r e; do grep -qs "$H/launch.sh" "$P/$e" && rm -f "$P/$e"; done
      rm -f "$WP/51-retro-voice-capture-s16.conf"
      echo "Removed the Ports entries and the capture pin. The models and this directory are still here:"
      echo "  $M"; echo "  $H"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

chmod +x "$H/launch.sh" "$H"/bin/* "$H/games/dfrotz" "$H"/test/*.sh 2>/dev/null
for f in bin/llama-server bin/tts-server retrovoice.py launch.sh; do
  [ -e "$H/$f" ] || { echo "missing $H/$f: this is not an unpacked release (see build/build.sh)" >&2; exit 1; }
done

if [ -n "$MODELS" ]; then
  mkdir -p "$M" && cd "$M" || exit 1
  echo "RAM ${RAM_MB:-?} MB: $([ -n "$SMART" ] && echo 'fast and smart modes' || echo 'fast mode only (smart needs a 12 GB device; --smart forces it)')"
  need=5; [ -n "$SMART" ] && need=10
  free=$(df -Pk . | awk 'NR==2 {print int($4 / 1048576)}')
  [ "$free" -lt "$need" ] && echo "warning: $free GB free in $M, the downloads need about $need GB"
  grep -v '^#' "$H/models.txt" | while read -r set repo file as; do
    [ -z "$set" ] && continue
    [ "$set" = smart ] && [ -z "$SMART" ] && continue
    as=${as:-$file}
    [ -f "$as" ] && { echo "have $as"; continue; }
    echo "get  $as"
    curl -fL --retry 5 -C - -o "$as.part" "https://huggingface.co/$repo/resolve/main/$file" && mv "$as.part" "$as" \
      || echo "FAILED $as (run install.sh again to resume)"
  done
  cd "$H" || exit 1
fi

mkdir -p "$P"
for f in "$P"/*.sh; do
  [ -f "$f" ] && [ "$f" != "$P/$ENTRIES" ] && grep -qsE "$STALE_RE" "$f" && rm -f "$f" && echo "removed the old entry $f"
done
echo "$OLD" | tr '|' '\n' | while read -r e; do
  grep -qs "$H/launch.sh" "$P/$e" && rm -f "$P/$e" && echo "removed the old entry $P/$e"   # only this install's
done
echo "$ENTRIES" | tr '|' '\n' | while read -r e; do
  sed -e "s|@RV_HOME@|$H|g" -e "s|@RV_MODELS@|$M|g" "$H/ports/$e" > "$P/$e" && chmod +x "$P/$e" && echo "port $P/$e"
done

if [ -n "$JACK" ]; then
  mkdir -p "$WP" && cp "$H/extras/51-retro-voice-capture-s16.conf" "$WP/" \
    && echo "capture pin installed in $WP (takes effect after a reboot)"
fi
echo "Done. Refresh the game lists in EmulationStation; the entries are under Ports."
