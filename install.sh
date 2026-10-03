#!/bin/sh
# Retro Voice Chat installer. Runs ON the handheld, from the unpacked release directory (put it where
# there is room: the models are 4.4 GB, 9.2 GB with --smart).
#   ./install.sh [--smart] [--jack-mic] [--no-models]      ./install.sh --uninstall
#   --smart      also download gemma-4-E4B for smart mode and add its Ports entry
#   --jack-mic   install the capture format pin the Flip 2's 3.5 mm headset mic needs (see README)
#   --no-models  skip the downloads (RV_MODELS already has them)
# Env: RV_MODELS (default ./models), RV_PORTS (default /storage/roms/ports).
set -u
H=$(cd "$(dirname "$0")" && pwd); M=${RV_MODELS:-$H/models}; P=${RV_PORTS:-/storage/roms/ports}
WP=${HOME:-/storage}/.config/wireplumber/wireplumber.conf.d
ENTRIES="Retro Voice Chat.sh|Retro Voice Chat (smart).sh|Retro Voice Zork.sh|Enigma Puzzles.sh|Enigma Puzzles (smart).sh"
SMART=""; JACK=""; MODELS=1
for a in "$@"; do
  case $a in
    --smart) SMART=1 ;; --jack-mic) JACK=1 ;; --no-models) MODELS="" ;;
    --uninstall)
      echo "$ENTRIES" | tr '|' '\n' | while read -r e; do rm -f "$P/$e"; done
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
echo "$ENTRIES" | tr '|' '\n' | while read -r e; do
  case $e in *smart*) [ -z "$SMART" ] && [ ! -f "$M/gemma-4-E4B_q4_0-it.gguf" ] && continue ;; esac
  sed -e "s|@RV_HOME@|$H|g" -e "s|@RV_MODELS@|$M|g" "$H/ports/$e" > "$P/$e" && chmod +x "$P/$e" && echo "port $P/$e"
done

if [ -n "$JACK" ]; then
  mkdir -p "$WP" && cp "$H/extras/51-retro-voice-capture-s16.conf" "$WP/" \
    && echo "capture pin installed in $WP (takes effect after a reboot)"
fi
echo "Done. Refresh the game lists in EmulationStation; the entries are under Ports."
