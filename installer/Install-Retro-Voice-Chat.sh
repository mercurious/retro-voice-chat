#!/bin/sh
# Install Retro Voice Chat, as a ROCKNIX Port: copy this one file into the ports folder (roms/ports, over the network
# share or on the SD card), refresh the game list, and start it from Ports. Full screen, gamepad only, no ssh: it
# downloads the latest Retro Voice Chat release from GitHub, checks its SHA-256, unpacks it and runs its install.sh,
# which downloads the models (several GB: WiFi on, and the handheld on its charger) and adds the Retro Voice Chat
# entry. Then it renames itself Update-Retro-Voice-Chat: start that to update to a newer release. The 3.5 mm headset
# mic fix (install.sh --jack-mic) is not part of it: see the README.
# Where: an installed Retro Voice Chat is updated in place; otherwise it goes next to the models other llamatalk apps
# already downloaded, else wherever has the most room. Log: /storage/retro-voice-chat-installer.log
# Env (for testing): PORTS, LOG, INSTALL_ARGS (passed to install.sh, e.g. --no-models), IN_FOOT=1 (no window).
NAME=retro-voice-chat TITLE="Retro Voice Chat" REPO=mercurious/retro-voice-chat ENTRY="Retro Voice Chat.sh" LAUNCH=launch.sh
PORTS=${PORTS:-/storage/roms/ports}; LOG=${LOG:-/storage/$NAME-installer.log}; ST=/tmp/$NAME-installer.status
[ -f /etc/profile ] && . /etc/profile >/dev/null 2>&1
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/0-runtime-dir} WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-1} HOME=${HOME:-/storage}
SELF=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")

if [ -z "${IN_FOOT:-}" ] && command -v foot >/dev/null; then   # show it: a fullscreen terminal, like the app's menu
  SWAYSOCK=$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock 2>/dev/null | head -1); export SWAYSOCK
  ( for i in 1 2 3 4 5 6; do sleep 0.5; swaymsg '[app_id="llamatalk-installer"] fullscreen enable' >/dev/null 2>&1 && break; done ) &
  IN_FOOT=1 exec foot --app-id=llamatalk-installer -f "monospace:size=16" -o colors.background=030a03 \
    -o colors.foreground=33ff66 sh "$SELF"
fi

wait_button() {   # until any gamepad button, or $1 seconds
  python3 - "$1" <<'PY' 2>/dev/null || sleep "$1"
import os, select, struct, sys, time
end, fds = time.time() + float(sys.argv[1]), []
for e in sorted(os.listdir("/sys/class/input")):
    try:
        name = open("/sys/class/input/%s/device/name" % e).read().lower()
        keys = open("/sys/class/input/%s/device/capabilities/key" % e).read().split()
    except OSError: continue
    bits = int("".join("%016x" % int(w, 16) for w in keys), 16) if keys else 0
    if e.startswith("event") and bits >> 304 & 1 and "keyboard" not in name:   # BTN_SOUTH: a gamepad
        try: fds.append(os.open("/dev/input/" + e, os.O_RDONLY | os.O_NONBLOCK))
        except OSError: pass
while time.time() < end:
    for fd in select.select(fds, [], [], 0.5)[0]:
        data = os.read(fd, 24 * 64)
        for k in range(0, len(data) - 23, 24):
            _, _, typ, code, val = struct.unpack("qqHHi", data[k:k + 24])
            if typ == 1 and val == 1: sys.exit(0)
PY
}

main() {
  fail() { [ -n "${H:-}" ] && rmdir "$H" 2>/dev/null; echo; echo "NOT INSTALLED: $*"; echo "The log: $LOG"; echo 1 > "$ST"; exit 1; }
  echo "$TITLE installer"; echo
  H=$(sed -n "s|^.*exec \"\(.*\)/$LAUNCH\"\$|\1|p" "$PORTS/$ENTRY" 2>/dev/null | head -1)
  if [ -n "$H" ] && [ -d "$H" ]; then echo "Updating $H"
  else
    M=$(cat "$HOME/.config/llamatalk/models-dir" 2>/dev/null)
    if [ -n "$M" ] && [ -d "$M" ]; then B=$(dirname "$M")
    else B=$(for d in /storage/games-external /storage/games-internal /storage; do
               [ -d "$d" ] && df -Pk "$d" | awk -v d="$d" 'NR == 2 { print $4, d }'; done | sort -rn | head -1 | cut -d' ' -f2-)
    fi
    [ -n "$B" ] || fail "no place to install: no /storage here"
    H=$B/$NAME; echo "Installing to $H"
  fi
  B=$(dirname "$H"); mkdir -p "$H" || fail "cannot write to $B"
  echo "Free there: $(df -Pk "$B" | awk 'NR == 2 { printf "%.1f GB", $4 / 1048576 }')"; echo

  TAG=$(curl -sI -m 20 "https://github.com/$REPO/releases/latest" | tr -d '\r' | sed -n 's|^[Ll]ocation: .*/tag/||p')
  [ -n "$TAG" ] || fail "GitHub cannot be reached. Is WiFi on?"
  HAVE=$(cat "$H/VERSION" 2>/dev/null)
  if [ "v$HAVE" = "$TAG" ]; then echo "$TITLE $HAVE is the latest release: checking the install."
  else
    echo "Downloading $TITLE ${TAG#v}${HAVE:+ (installed: $HAVE)}"
    T=$B/.$NAME-installer; U=https://github.com/$REPO/releases/download/$TAG/$NAME-aarch64.tar.gz
    rm -rf "$T"; mkdir -p "$T" || fail "cannot write to $B"
    curl -fL --retry 3 -m 600 -o "$T/$NAME-aarch64.tar.gz" "$U" && curl -fsSL -o "$T/$NAME-aarch64.tar.gz.sha256" "$U.sha256" \
      || fail "the download failed"
    (cd "$T" && sha256sum -c "$NAME-aarch64.tar.gz.sha256") || fail "the download is damaged (SHA-256 mismatch)"
    tar -xzf "$T/$NAME-aarch64.tar.gz" -C "$T" && cp -a "$T/$NAME/." "$H/" || fail "unpacking failed (is $B full?)"
    rm -rf "$T"
  fi
  echo; (cd "$H" && ./install.sh ${INSTALL_ARGS:-} </dev/null) || fail "$H/install.sh failed"
  echo 0 > "$ST"
}

rm -f "$ST"; main 2>&1 | tee "$LOG"
if [ "$(cat "$ST" 2>/dev/null)" = 0 ]; then
  case $(basename "$SELF") in Install-*) mv -f "$SELF" "$(dirname "$SELF")/Update-${SELF##*/Install-}" ;; esac
  curl -s -m 5 http://127.0.0.1:1234/reloadgames >/dev/null 2>&1   # EmulationStation: show the new entries
  printf '\nDONE: start %s from Ports.\nPress any button.' "$TITLE"; wait_button 120
else
  printf '\nPress any button.'; wait_button 600
fi
