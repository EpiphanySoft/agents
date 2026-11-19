#!/bin/bash
# Claude Code status line:
#   [refreshed] dir │ git branch │ model effort │ context % │ rate limits │ tokens spent
input=$(cat)

if ! command -v jq >/dev/null 2>&1; then
  # Degraded output without jq: directory only.
  dir=$(printf '%s' "$input" | sed -n 's/.*"current_dir"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1)
  [ -n "$dir" ] && printf '\033[36m%s\033[0m' "$(basename "$dir")"
  exit 0
fi

j() { printf '%s' "$input" | jq -r "$1 // empty"; }

# left: seconds until an epoch, compact: "2d 7h" from a day up, "1h 50m" below, "12m" below an hour.
left() {
  [ -n "$1" ] || return
  local s=$(( ${1%.*} - $(date +%s) ))
  [ "$s" -lt 0 ] && s=0
  local d=$(( s / 86400 )) h=$(( s % 86400 / 3600 )) m=$(( s % 3600 / 60 ))
  if [ "$d" -gt 0 ]; then printf '%dd %dh' "$d" "$h"
  elif [ "$h" -gt 0 ]; then printf '%dh %dm' "$h" "$m"
  else printf '%dm' "$m"
  fi
}

sep=$(printf '\033[2m │ \033[0m')
parts=()

parts+=("$(printf '\033[92m[%s]\033[0m' "$(TZ=America/Chicago date '+%Y-%m-%d %H:%M:%S')")")

dir=$(j '.workspace.current_dir')
[ -z "$dir" ] && dir=$(j '.cwd')
if [ -n "$dir" ]; then
  parts+=("$(printf '\033[36m%s\033[0m' "$(basename "$dir")")")

  if branch=$(git -C "$dir" --no-optional-locks symbolic-ref --short -q HEAD 2>/dev/null || git -C "$dir" --no-optional-locks rev-parse --short HEAD 2>/dev/null); then
    if [ -n "$(git -C "$dir" --no-optional-locks status --porcelain 2>/dev/null)" ]; then
      col=31
    else
      col=32
    fi
    parts+=("$(printf '\033[%sm%s\033[0m' "$col" "$branch")")
  fi
fi

model=$(j '.model.display_name')
effort=$(j '.effort.level')
m=""
[ -n "$model" ] && m=$(printf '\033[1;97m%s\033[0m' "$model")
[ -n "$effort" ] && m="${m:+$m }$(printf '\033[35m%s\033[0m' "$effort")"
[ -n "$m" ] && parts+=("$m")

ctx=$(j '.context_window.used_percentage')
[ -n "$ctx" ] && parts+=("$(printf '\033[33mctx %.0f%%\033[0m' "$ctx")")

rl=""
five=$(j '.rate_limits.five_hour.used_percentage')
if [ -n "$five" ]; then
  rl="5h:$(printf '%.0f' "$five")%"
  t=$(left "$(j '.rate_limits.five_hour.resets_at')")
  [ -n "$t" ] && rl="$rl ($t)"
fi
week=$(j '.rate_limits.seven_day.used_percentage')
if [ -n "$week" ]; then
  w="7d:$(printf '%.0f' "$week")%"
  t=$(left "$(j '.rate_limits.seven_day.resets_at')")
  [ -n "$t" ] && w="$w ($t)"
  rl="${rl:+$rl - }$w"
fi
[ -n "$rl" ] && parts+=("$(printf '\033[94m%s\033[0m' "$rl")")

out=""
for p in "${parts[@]}"; do
  out="${out:+$out$sep}$p"
done

# Tokens this session has spent, in gray at the end: input, cache writes and output summed over
# the transcript's replies (each counted once). Cache reads, the context re-read every turn, are left out.
tp=$(j '.transcript_path')
if [ -n "$tp" ] && [ -r "$tp" ]; then
  tok=$(grep -F '"usage"' "$tp" 2>/dev/null | jq -s '[.[] | select(.type=="assistant" and .message.usage) | {id:.message.id, u:.message.usage}]
        | unique_by(.id) | map(.u | (.input_tokens//0) + (.cache_creation_input_tokens//0) + (.output_tokens//0)) | add // 0' 2>/dev/null)
  if [ -n "$tok" ]; then
    tok=$(awk -v n="$tok" 'BEGIN { if (n >= 1e6) printf "%.1fM", n/1e6; else if (n >= 1e3) printf "%.1fk", n/1e3; else printf "%d", n }')
    out="${out:+$out$sep}$(printf '\033[90m%s tok\033[0m' "$tok")"
  fi
fi

printf '%s' "$out"
