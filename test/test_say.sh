#!/bin/sh
# Runs ON the handheld: headless content + latency test through the LLM and TTS (skips ASR): quits any
# running retrovoice, launches with the caller's RV_* env, sends each line of <prompts.txt> with the
# "say" hook, waiting for READY between turns, and prints reply, hidden answer key and timings.
# Usage: RV_MODE=smart test/test_say.sh <label> <prompts.txt>
#   SILENT=1  play into a null sink (nothing comes out of the speaker; timings are the same)
#   QUIT=1    quit the app when done
V=$(cd "$(dirname "$0")/.." && pwd); cd "$V"; lab=${1:-test}; P=${2:-test/trivia.txt}
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/0-runtime-dir}
mkdir -p logs
[ -p /tmp/retrovoice.ctl ] && echo quit > /tmp/retrovoice.ctl
i=0; while netstat -tln | grep -qE ":809[123] "; do i=$((i+1)); [ $i -gt 60 ] && { echo "ABORT: old instance still up"; exit 1; }; sleep 1; done
NULLMOD=""
if [ -n "${SILENT:-}" ]; then
  NULLMOD=$(pactl load-module module-null-sink sink_name=rvnull) || { echo "ABORT: no null sink"; exit 1; }
  export PULSE_SINK=rvnull
fi
n0=$(cat logs/turns.jsonl 2>/dev/null | wc -l); e0=$(cat logs/events.log 2>/dev/null | wc -l)
f0=$(dmesg | grep -c "gpu fault"); h0=$(dmesg | grep -c "offending task"); k0=$(dmesg | grep -c "Killed process")
nohup ./launch.sh --headless > logs/headless.log 2>&1 < /dev/null &
i=0; until tail -n +$((e0 + 1)) logs/events.log 2>/dev/null | grep -q "llm warm-up" && grep -aq "== READY" logs/headless.log 2>/dev/null; do i=$((i+1)); [ $i -gt 400 ] && { echo "ABORT: no READY"; tail -5 logs/headless.log; break; }; sleep 1; done
if [ $i -le 400 ]; then
echo "[$lab] ready after ${i}s  $(tail -n +$((e0 + 1)) logs/events.log | grep -a "llm warm-up" | tail -1 | sed 's/.*\] //')  mem avail $(free -m | awk '/Mem/{print $7}') MB  swap used $(free -m | awk '/Swap/{print $3}') MB"
sleep 5
while IFS= read -r line; do
  [ -z "$line" ] && continue
  c0=$(cat logs/turns.jsonl | wc -l); echo "say $line" > /tmp/retrovoice.ctl
  i=0; until [ $(cat logs/turns.jsonl | wc -l) -gt $c0 ] || [ $i -gt 180 ]; do i=$((i+1)); sleep 1; done
  i=0; until tail -n 1 logs/events.log | grep -q "state -> READY" || [ $i -gt 90 ]; do i=$((i+1)); sleep 1; done; sleep 1
done < "$P"
tail -n +$((n0 + 1)) logs/turns.jsonl | python3 -c '
import json, sys
for l in sys.stdin:
    t = json.loads(l)
    p = t.get("tts") or []
    spd = sum(x[1] for x in p) / max(1e-6, sum(x[2] for x in p))
    print("  think %.1fs first-word %ss %4.1f tok/s tts %.2fx stalls %s (%.1fs) ctx %s | Q: %s" % (t["ttft_s"], t["first_audio_s"], t["tok_s"] or 0, spd, t.get("gaps"), t.get("gap_s", 0), t.get("ctx", ["?"])[0], t["user"]))
    print("      A: %s" % t["raw"].replace(chr(10), " "))'
# prompt reading speed per request, from the server log (turns.jsonl only has generation speed)
grep -a "prompt eval time" logs/llm.log | awk '{for (i = 1; i <= NF; i++) if ($i == "tokens") {n = $(i-1); break}; print "  prompt " n " tok, " $(NF-3) " t/s"}' | tail -n 12
fi
echo "  mem avail $(free -m | awk '/Mem/{print $7}') MB  swap used $(free -m | awk '/Swap/{print $3}') MB"
echo "  new: gpu faults $(( $(dmesg | grep -c "gpu fault") - f0 )), gpu hangs $(( $(dmesg | grep -c "offending task") - h0 )), oom kills $(( $(dmesg | grep -c "Killed process") - k0 ))"
if [ -n "${QUIT:-}${NULLMOD}" ]; then
  [ -p /tmp/retrovoice.ctl ] && echo quit > /tmp/retrovoice.ctl
  i=0; while netstat -tln | grep -qE ":809[123] "; do i=$((i+1)); [ $i -gt 60 ] && break; sleep 1; done
fi
[ -n "$NULLMOD" ] && pactl unload-module "$NULLMOD"
