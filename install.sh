#!/bin/sh
# Retro Voice Chat installer. Runs ON the handheld, from the unpacked release directory.
#   ./install.sh [--no-smart] [--jack-mic] [--no-models]      ./install.sh --uninstall
#   --no-smart   skip gemma-4-E4B, the smart mode model (otherwise downloaded, and offered in SELECT)
#   --jack-mic   install the capture format pin the Flip 2's 3.5 mm headset mic needs (see README)
#   --no-models  skip the downloads (the models directory already has them)
# The models (9.2 GB, 4.4 GB with --no-smart) go to llamatalk's shared models directory, which every app that
# bundles llamatalk uses: models already there are not downloaded again. Which directory: RV_MODELS if set, else the
# shared one if this device has it, else the one an earlier install's Ports entry used, else ./models.
# Env: RV_MODELS, RV_PORTS (default /storage/roms/ports).
set -u
H=$(cd "$(dirname "$0")" && pwd); P=${RV_PORTS:-/storage/roms/ports}; LTM=$H/llamatalk/models.sh
WP=${HOME:-/storage}/.config/wireplumber/wireplumber.conf.d
ENTRIES="Retro Voice Chat.sh"
# earlier releases had an entry per persona and per model; they are now one app (SELECT switches both)
OLD="Retro Voice Chat (smart).sh|Retro Voice Zork.sh|Enigma Puzzles.sh|Enigma Puzzles (smart).sh"
# prototype launchers from the ollamadreno kit and the dev copies: matched by what they exec, not by name
STALE_RE="ollamadreno/voice/launch.sh|enigma-dev/launch.sh|rvc-dev/launch.sh"
SMART=1
JACK=""; MODELS=1
for a in "$@"; do
  case $a in
    --smart) SMART=1 ;; --no-smart) SMART="" ;; --jack-mic) JACK=1 ;; --no-models) MODELS="" ;;
    --uninstall)
      echo "$ENTRIES" | tr '|' '\n' | while read -r e; do rm -f "$P/$e"; done
      echo "$OLD" | tr '|' '\n' | while read -r e; do grep -qs "$H/launch.sh" "$P/$e" && rm -f "$P/$e"; done
      rm -f "$WP/51-retro-voice-capture-s16.conf"
      echo "Removed the Ports entries and the capture pin. This directory and the models (shared with other"
      echo "llamatalk apps) are still here:"; echo "  $H"; echo "  $("$LTM" path 2>/dev/null || echo "$H/models")"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

chmod +x "$H/launch.sh" "$H"/llamatalk/bin/* "$LTM" "$H/games/dfrotz" "$H"/test/*.sh 2>/dev/null
for f in llamatalk/bin/llama-server llamatalk/bin/tts-server llamatalk/models.sh retrovoice.py launch.sh; do
  [ -e "$H/$f" ] || { echo "missing $H/$f: this is not an unpacked release (see build/build.sh)" >&2; exit 1; }
done
# releases before llamatalk kept the servers in bin/ and the model list here
rm -f "$H/bin/llama-server" "$H/bin/tts-server" "$H/models.txt"; rmdir "$H/bin" 2>/dev/null

# the models directory (see the top)
M=${RV_MODELS:-}
[ -n "$M" ] || M=$("$LTM" path 2>/dev/null) || M=""
if [ -z "$M" ]; then
  O=$(sed -n 's/^RV_MODELS="\(.*\)" exec .*/\1/p' "$P/$ENTRIES" 2>/dev/null | head -1)
  [ -n "$O" ] && [ -d "$O" ] && M=$O
fi
[ -n "$M" ] || M=$H/models
SETS="asr e2b tts"; [ -n "$SMART" ] && SETS="$SETS e4b"
if [ -n "$MODELS" ]; then
  "$LTM" fetch --dir "$M" $SETS
elif [ -d "$M" ]; then
  "$LTM" use "$M"; "$LTM" check $SETS >/dev/null || echo "warning: $M still misses: $("$LTM" check $SETS | tr '\n' ' ')"
else
  echo "warning: no models directory yet ($M); run install.sh without --no-models"
fi

mkdir -p "$P"
for f in "$P"/*.sh; do
  [ -f "$f" ] && [ "$f" != "$P/$ENTRIES" ] && grep -qsE "$STALE_RE" "$f" && rm -f "$f" && echo "removed the old entry $f"
done
echo "$OLD" | tr '|' '\n' | while read -r e; do
  grep -qs "$H/launch.sh" "$P/$e" && rm -f "$P/$e" && echo "removed the old entry $P/$e"   # only this install's
done
echo "$ENTRIES" | tr '|' '\n' | while read -r e; do
  sed -e "s|@RV_HOME@|$H|g" "$H/ports/$e" > "$P/$e" && chmod +x "$P/$e" && echo "port $P/$e"
done

if [ -n "$JACK" ]; then
  mkdir -p "$WP" && cp "$H/extras/51-retro-voice-capture-s16.conf" "$WP/" \
    && echo "capture pin installed in $WP (takes effect after a reboot)"
fi
echo "Done. Refresh the game lists in EmulationStation; the entries are under Ports."
