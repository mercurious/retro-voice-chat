#!/bin/sh
# Retro Voice Chat launcher (a ROCKNIX Port, or over ssh with --headless).
# Starts the ASR / LLM / TTS servers pinned to the big cores, shows the UI full screen in foot on its own
# sway workspace, and on exit stops everything and returns to the previous workspace.
#   ASR  Qwen3-ASR-0.6B            cores 4-7 (only busy between turns)                  :8091
#   LLM  gemma-4-E2B (fast)        cores 4-5  |  gemma-4-E4B (smart): 4-7 prompt, 4-5 generate   :8092
#   TTS  Pocket TTS                cores 6-7 (2 threads, nice -10)                      :8093
# The core numbers are the SM8250's (0-3 little, 4-7 big).
# Env: RV_MODE=fast|smart (default: the menu's last choice) RV_MODELS=<dir> RV_LLM_MODEL=<gguf basename> RV_LLM_DRAFT=<mtp gguf|none>
#      RV_LLM_CPUS/RV_LLM_T/RV_LLM_TB RV_ASR_CPUS RV_TTS_CPUS RV_VOICE=<name> RV_SOURCE=<pulse source>
#      RV_FONT=<pt> RV_LLM_GPU=1 with RV_OCL_DIR=<llamadreno install> (LLM on the Adreno, OpenCL)
#      RV_START=chat|retro|enigma|zork (the mode to open in; default: the last one used)
#      RV_PERSONA=trixy|enigma and RV_START_GAME=1|2|3 (older launchers: open in that mode)

[ -f /etc/profile ] && . /etc/profile >/dev/null 2>&1
V=$(cd "$(dirname "$0")" && pwd); B=$V/bin; M=${RV_MODELS:-$V/models}; L=${RV_LOG_DIR:-$V/logs}
mkdir -p "$L"
export RV_LOG_DIR="$L" XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/0-runtime-dir} HOME=${HOME:-/storage}
export WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}
SWAYSOCK=$(ls "$XDG_RUNTIME_DIR"/sway-ipc.*.sock 2>/dev/null | head -1); export SWAYSOCK
ulimit -c 0     # a crashed server must not leave a multi-GB core file behind

# Modes. fast (default): gemma-4-E2B on two big cores, about 10 tokens/s; fits an 8 GB device with room
# to spare. smart: gemma-4-E4B, reads the prompt on all four big cores and generates on two (OpenMP binds
# thread i to core 4+i, so generation stays on 4-5 and leaves 6-7 to TTS); about 5.5 GB of RAM.
# In smart mode the batch threads (-tb 4) still run on 6-7 for the prompt and for every MTP verify step;
# at equal priority that cut TTS from 2.2x to 1.2x real time while a reply was being written (first words
# stuttered). TTS runs at nice -10: 1.9x during generation, LLM generation 6.5 -> 6.2 tok/s.
# The model is chosen in the app's SELECT menu (kept in prefs.json as "model"); RV_MODE overrides it for
# this launch. Switching asks this script to restart the LLM server (see the loop at the end).
PREFS=${RV_PREFS:-$V/prefs.json}
pref_model() { python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("model", ""))' "$PREFS" 2>/dev/null; }
RV_MODE=${RV_MODE:-$(pref_model)}
ENV_MODEL=${RV_LLM_MODEL:-}; ENV_DRAFT=${RV_LLM_DRAFT:-}; ENV_LABEL=${RV_MODEL_LABEL:-}
# smart (E4B, ~5.5 GB resident) is offered only where it leaves headroom: 10 GB of RAM or more (the 12 GB
# Flip 2 reports ~11.2 GB, the 8 GB one ~7.4 GB, where it was getting OOM-killed). RV_SMART=1|0 overrides.
RAM_MB=$(awk '/^MemTotal:/ {print int($2 / 1024)}' /proc/meminfo 2>/dev/null)
case ${RV_SMART:-} in 1) SMART_OK=1 ;; 0) SMART_OK="" ;; *) [ "${RAM_MB:-0}" -ge 10000 ] && SMART_OK=1 || SMART_OK="" ;; esac
AVAIL=fast; [ -n "$SMART_OK" ] && [ -f "$M/gemma-4-E4B_q4_0-it.gguf" ] && AVAIL="fast smart"
export RV_MODELS_AVAILABLE="$AVAIL"     # the menu offers these
OCL=${RV_OCL_DIR:-}
ASR_CPUS=${RV_ASR_CPUS:-4-7}; TTS_CPUS=${RV_TTS_CPUS:-6-7}

pick_model() {
  case " $AVAIL " in *" $RV_MODE "*) ;; *) RV_MODE=fast ;; esac
  export RV_MODE
  if [ "$RV_MODE" = smart ]; then
    DEF_MODEL=gemma-4-E4B_q4_0-it; DEF_CPUS=4-7; DEF_TB=4; DEF_LABEL="E4B smart"; DEF_DRAFT=mtp-gemma-4-E4B-it-Q4_0
    export OMP_PROC_BIND=close OMP_PLACES="{4},{5},{6},{7}"
  else
    DEF_MODEL=gemma-4-E2B_q4_0-it; DEF_CPUS=4-5; DEF_TB=2; DEF_LABEL="E2B fast"; DEF_DRAFT=""
    unset OMP_PROC_BIND OMP_PLACES
  fi
  LLM_MODEL=${ENV_MODEL:-$DEF_MODEL}
  export RV_LLM_MODEL=$LLM_MODEL     # general chat is named after the model's family (Gemma, Qwen...)
  LLM_DRAFT=${ENV_DRAFT:-${DEF_DRAFT:-none}}   # MTP head: +10-30% on E4B; slower on E2B at 2 threads
  LLM_CPUS=${RV_LLM_CPUS:-$DEF_CPUS}; LLM_T=${RV_LLM_T:-2}; LLM_TB=${RV_LLM_TB:-$DEF_TB}
  # RV_LLM_GPU=1: the LLM runs on the Adreno through an OpenCL build of llama.cpp and a private rusticl
  # driver (the llamadreno kit, RV_OCL_DIR: ocl/env.sh + bin-ocl/llama-server). One host thread, flash
  # attention off, no MTP head. No gain for conversation on an 8 GB Flip 2 (see README); ASR and TTS stay
  # on the CPU.
  if [ -n "${RV_LLM_GPU:-}" ]; then
    LLM_CPUS=${RV_LLM_CPUS:-4-5}; LLM_T=${RV_LLM_T:-1}; LLM_DRAFT=${ENV_DRAFT:-none}; DEF_LABEL="$DEF_LABEL GPU"
  fi
  export RV_MODEL_LABEL=${ENV_LABEL:-$DEF_LABEL}
}
pick_model
if [ -n "${RV_LLM_GPU:-}" ]; then
  [ -f "$OCL/ocl/env.sh" ] && [ -x "$OCL/bin-ocl/llama-server" ] || {
    echo "retrovoice: RV_LLM_GPU needs RV_OCL_DIR with ocl/env.sh and bin-ocl/llama-server" >&2; exit 1; }
fi

# everything it needs, or a line that says what is missing
for f in "$B/llama-server" "$B/tts-server" "$M/Qwen3-ASR-0.6B-Q8_0.gguf" "$M/mmproj-Qwen3-ASR-0.6B-Q8_0.gguf" \
         "$M/$LLM_MODEL.gguf" "$M/pocket-tts-english_2026-09-Q8_0.gguf" "$M/pocket-tts-english_2026-09-voices.gguf"; do
  [ -e "$f" ] || { echo "retrovoice: missing $f (run install.sh; RV_MODELS points at the models)" >&2; exit 1; }
done

PIDS=""; PRIOR_WS=""
cleanup() {
  trap - EXIT INT TERM HUP
  for p in $PIDS; do kill "$p" 2>/dev/null; done
  for p in $PIDS; do while kill -0 "$p" 2>/dev/null; do sleep 0.2; done; done
  [ -n "$PRIOR_WS" ] && swaymsg "workspace $PRIOR_WS" >/dev/null 2>&1
  rm -f /tmp/retrovoice.ctl
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

port_pid() { netstat -tlnp 2>/dev/null | awk -v p=":$1 " '$0 ~ p {split($7, a, "/"); print a[1]; exit}'; }

# refuse to double-start
for p in 8091 8092 8093; do
  if [ -n "$(port_pid $p)" ]; then echo "retrovoice: port $p already in use, is it running?" >&2; exit 1; fi
done

# Flip 2, headset mic inserted: make sure its soundwire port is on (UCM's Headset enable sequence does the
# same; a stale mixer state once left it off, which delivers pure digital silence)
JACK=$(for e in /sys/class/input/event*; do [ "$(cat $e/device/name 2>/dev/null)" = "RetroidPocket Headset Jack" ] && basename $e; done)
if [ -n "$JACK" ] && command -v evtest >/dev/null; then
  timeout 3 evtest --query /dev/input/$JACK EV_SW SW_MICROPHONE_INSERT
  [ $? = 10 ] && amixer -q -c0 cset name='ADC2 Switch' 1 2>/dev/null
fi

# Each mode's prompt is saved here when the app switches away from it, and loaded when it comes back
# (RV_SLOT_SAVE in retrovoice.py). Only this session's: another model's would not fit.
KV=$L/kv; export RV_SLOT_SAVE=1

# --cache-ram 0 on both llama-servers: their host-RAM prompt cache (default 8 GiB) keeps a copy of every
# prompt it moves away from. ASR moves away on every utterance (2.1 GB for a 1 GB model after ~80 turns);
# the LLM does it at the history trim, and on an 8 GB device that copy got it OOM-killed.
env -u OMP_PROC_BIND -u OMP_PLACES taskset -c $ASR_CPUS $B/llama-server -m $M/Qwen3-ASR-0.6B-Q8_0.gguf --mmproj $M/mmproj-Qwen3-ASR-0.6B-Q8_0.gguf \
  -dev none -t 4 -c 4096 -np 1 --cache-ram 0 --host 127.0.0.1 --port 8091 > $L/asr.log 2>&1 &
PIDS="$PIDS $!"

start_llm() {
DRAFT=""
[ "$LLM_DRAFT" != none ] && [ -f "$M/$LLM_DRAFT.gguf" ] && DRAFT="-md $M/$LLM_DRAFT.gguf --spec-type draft-mtp"

# What the boot screen says about the stack; retrovoice.py prints these lines as they are.
SPEECH="TTS cores $TTS_CPUS x2 (nice -10) · ASR cores $ASR_CPUS x4"
if [ -n "${RV_LLM_GPU:-}" ]; then
  # ask the driver and the OpenCL build what they are, before the LLM server takes the GPU
  DRV=$( (. $OCL/ocl/env.sh; timeout 20 $OCL/ocl/clinfo 2>/dev/null) | awk -F'  +' '
    $2 == "Driver Version" && !v {v = $3} $2 == "Device Name" && !d {d = $3} $2 == "Device Version" && !o {o = $3}
    END {sub(/ +$/, "", o); if (v) printf "Mesa %s rusticl on %s, %s", v, d, o}')
  VER=$( (. $OCL/ocl/env.sh; $OCL/bin-ocl/llama-server --version 2>&1) | sed -n 's/^version: //p')
  export RV_INFO_DRIVER="llamadreno: ${DRV:-OpenCL driver (version not read)}"
  export RV_INFO_LLAMA="${VER:-version not read}, llamadreno OpenCL build"
  export RV_INFO_TUNING="LLM on the Adreno (1 host thread on cores $LLM_CPUS, flash attention off) · $SPEECH"
else
  VER=$($B/llama-server --version 2>&1 | sed -n 's/^version: //p')
  export RV_INFO_DRIVER="none in use: the model runs on the CPU"
  export RV_INFO_LLAMA="${VER:-version not read}, unpatched, CPU backend"
  export RV_INFO_TUNING="LLM cores $LLM_CPUS x$LLM_T (prompt x$LLM_TB)${DRAFT:+, MTP draft head} · $SPEECH"
fi
rm -rf "$KV"; mkdir -p "$KV"     # saved prompts belong to the model that wrote them
if [ -n "${RV_LLM_GPU:-}" ]; then
  # the driver is only visible to this one process
  ( . $OCL/ocl/env.sh
    exec env -u OMP_PROC_BIND -u OMP_PLACES taskset -c $LLM_CPUS $OCL/bin-ocl/llama-server -m $M/$LLM_MODEL.gguf $DRAFT \
      -ngl 99 -fa off -t $LLM_T -c 8192 -np 1 --jinja -rea off --cache-ram 0 --slot-save-path "$KV/" --host 127.0.0.1 --port 8092 ) > $L/llm.log 2>&1 &
else
  taskset -c $LLM_CPUS $B/llama-server -m $M/$LLM_MODEL.gguf $DRAFT -dev none -t $LLM_T -tb $LLM_TB -fa on -c 8192 -np 1 \
    --jinja -rea off --cache-ram 0 --slot-save-path "$KV/" --host 127.0.0.1 --port 8092 > $L/llm.log 2>&1 &
fi
LLM_PID=$!
PIDS="$PIDS $LLM_PID"
}
start_llm

env -u OMP_PROC_BIND -u OMP_PLACES GGML_BACKEND=CPU PT_THREADS=2 nice -n -10 taskset -c $TTS_CPUS $B/tts-server --model $M/pocket-tts-english_2026-09-Q8_0.gguf \
  --voices $M/pocket-tts-english_2026-09-voices.gguf --voice "${RV_VOICE:-alba}" \
  --host 127.0.0.1 --port 8093 > $L/tts.log 2>&1 &
PIDS="$PIDS $!"

# The app asks for another model by writing its name to $L/restart and exiting: the LLM server is restarted
# with it (ASR and TTS keep running) and the app opens again, in the mode it was in.
RESTART=$L/restart; rm -f "$RESTART"
next_model() {
  [ -f "$RESTART" ] || return 1
  RV_MODE=$(cat "$RESTART"); rm -f "$RESTART"
  ENV_MODEL=""; ENV_DRAFT=""; ENV_LABEL=""      # the menu's choice replaces a launcher's model override
  kill $LLM_PID 2>/dev/null; while kill -0 $LLM_PID 2>/dev/null; do sleep 0.2; done
  PIDS=$(echo " $PIDS " | sed "s/ $LLM_PID / /")
  pick_model; start_llm
}

if [ "${1:-}" = "--headless" ]; then
  while :; do
    env -u OMP_PROC_BIND -u OMP_PLACES python3 $V/retrovoice.py --headless; rc=$?
    next_model || exit $rc
  done
fi

# UI: foot, full screen, on its own workspace
PRIOR_WS=$(swaymsg -t get_workspaces -r 2>/dev/null | python3 -c \
  'import json,sys; print(next((w["name"] for w in json.load(sys.stdin) if w.get("focused")), ""))' 2>/dev/null)
swaymsg "workspace 97:voice" >/dev/null 2>&1
while :; do
  ( for i in 1 2 3 4 5 6 7 8 9 10; do
      sleep 0.5; swaymsg '[app_id="retrovoice"] fullscreen enable' >/dev/null 2>&1 && break
    done ) &
  # each mode sets its own colours as it opens (modes/*.py); this is only the first frame
  BG=000000; FG=e0e0e0
  foot --app-id=retrovoice -f "monospace:size=${RV_FONT:-22}" \
    -o colors.background=$BG -o colors.foreground=$FG -o colors.alpha=1.0 \
    env -u OMP_PROC_BIND -u OMP_PLACES python3 $V/retrovoice.py
  next_model || break
done
