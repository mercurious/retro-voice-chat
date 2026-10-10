#!/bin/sh
# install.sh in a sandbox: a copy of the release, a temp HOME and Ports folder, a file:// mirror for the models (small
# fake files). Checks where the models go: an upgrade keeps the earlier entry's directory, a fresh install fetches into
# ./models, and an install on a device with a shared llamatalk directory reuses it. No network, no real paths touched.
# Usage: test/test_install.sh [unpacked release dir]   (default: dist/retro-voice-chat; runs on the host or the handheld)
R=${1:-$(cd "$(dirname "$0")/.." && pwd)/dist/retro-voice-chat}
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export LT_HF=file://$T/hf RV_PORTS=$T/ports; unset RV_MODELS LLAMATALK_MODELS XDG_CONFIG_HOME
grep -v '^#' "$R/llamatalk/models.txt" | while read -r set repo file as; do
  [ -n "$set" ] && mkdir -p "$T/hf/$repo/resolve/main" && echo "$file" > "$T/hf/$repo/resolve/main/$file"
done
n=0; bad=0
ok() { n=$((n + 1)); if [ "$1" = 0 ]; then echo "ok   $2"; else echo "FAIL $2"; bad=$((bad + 1)); fi; }
fresh() { rm -rf "$T/app" "$T/ports" "$T/home"; cp -r "$R" "$T/app"; mkdir -p "$T/ports"; export HOME=$T/home; }
E="$T/ports/Retro Voice Chat.sh"

# 1. upgrade: the earlier release's entry named its models directory, which has every model; it had bin/ too
fresh; mkdir -p "$T/old" "$T/app/bin"; for f in "$T"/hf/*/*/resolve/main/*; do cp "$f" "$T/old/"; done
touch "$T/app/bin/llama-server" "$T/app/bin/tts-server"
printf '#!/bin/sh\nRV_MODELS="%s" exec "%s/launch.sh"\n' "$T/old" "$T/app" > "$E"
"$T/app/install.sh" > "$T/out1" 2>&1; ok $? "upgrade: install.sh runs"
[ "$("$T/app/llamatalk/models.sh" path)" = "$T/old" ]; ok $? "upgrade: the old models directory is now the shared one"
grep -q '^get ' "$T/out1"; [ $? = 1 ]; ok $? "upgrade: nothing downloaded"
[ ! -e "$T/app/bin" ]; ok $? "upgrade: the old bin/ is gone"
grep -q "exec \"$T/app/launch.sh\"" "$E" && ! grep -q RV_MODELS "$E"; ok $? "upgrade: the entry runs launch.sh, no RV_MODELS"

# 2. fresh install, no shared directory and no earlier entry: ./models, the sets of fast + smart mode
fresh; "$T/app/install.sh" > "$T/out2" 2>&1; ok $? "fresh: install.sh runs"
[ "$("$T/app/llamatalk/models.sh" path)" = "$T/app/models" ]; ok $? "fresh: ./models is the shared one"
[ "$(ls "$T/app/models" | wc -l)" = 6 ]; ok $? "fresh: six models (asr e2b tts e4b)"

# 3. another llamatalk app made the shared directory first, with e2b and tts only: reuse it, fetch the rest
fresh; mkdir -p "$T/shared" "$T/home/.config/llamatalk"; echo "$T/shared" > "$T/home/.config/llamatalk/models-dir"
for f in "$T"/hf/google/gemma-4-E2B*/resolve/main/* "$T"/hf/Serveurperso/*/resolve/main/*; do cp "$f" "$T/shared/"; done
"$T/app/install.sh" --no-smart > "$T/out3" 2>&1; ok $? "shared: install.sh --no-smart runs"
[ "$(grep -c '^get ' "$T/out3")" = 2 ]; ok $? "shared: only the two asr files downloaded"
[ ! -e "$T/app/models" ] && [ ! -e "$T/shared/gemma-4-E4B_q4_0-it.gguf" ]; ok $? "shared: no ./models, no e4b"

# 4. --no-models on a device with nothing: a warning, the entry still written
fresh; "$T/app/install.sh" --no-models > "$T/out4" 2>&1; ok $? "no models: install.sh runs"
grep -q 'warning: no models directory' "$T/out4" && [ -f "$E" ]; ok $? "no models: warns, writes the entry"

echo "$((n - bad))/$n passed"; [ $bad = 0 ]
