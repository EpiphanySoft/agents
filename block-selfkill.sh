#!/bin/bash                                                                                                                                                                         
# PreToolUse(Bash) hook: refuse kill commands that can take down the shell/script running them.                                                                                     
# Exit 2 = block; stderr is shown to Claude so it can retry with a safe form.                                                                                                       
                                                                                                                                                                                  
cmd=$(jq -r '.tool_input.command // ""')                                                                                                                                            
                                                                                                                                                                                  
block() { echo "Blocked: $1" >&2; exit 2; }                                                                                                                                         
                                                                                                                                                                                      
# Split into simple-command segments on ; & | newline so one rule can't leak across commands.                                                                                       
while IFS= read -r seg; do
    # 1. pkill -f (any flag cluster containing f, or --full): the pattern is matched against full
    #    command lines, including this shell's own `bash -c "<this command>"`. A pattern wrapped in a
    #    one-character class, e.g. '[f]oo', does not match its own text, so that form is allowed.
    if grep -Eq '(^|[[:space:](`])pkill([[:space:]]|$)' <<<"$seg" \
       && grep -Eq '[[:space:]](-[a-zA-Z0-9]*f[a-zA-Z0-9]*|--full)([[:space:]]|$)' <<<"$seg" \
       && ! grep -Eq "[\"']?[^[:space:]]*\[[[:alnum:]]\][^[:space:]]*" <<<"$seg"; then
      block "'pkill -f' matches full command lines, including this shell's own, and can kill the session or script running it. Find the PID first (pgrep -x NAME, lsof -ti :PORT),
  check it, then 'kill PID'. If a pattern is unavoidable, bracket one character: pkill -f '[f]oo'."
    fi

    # 2. kill aimed at everything (-1), the process group (0 / -0), or ourselves ($$, $PPID). The target
    #    must be the LAST argument, so 'kill -0 1234' (is it alive?) and 'kill -1 1234' (SIGHUP) pass.
    if grep -Eq '(^|[[:space:](`])kill([[:space:]]+-[A-Za-z0-9_]+)*[[:space:]]+(-1|-0|0|\$\$|\$\{\$\}|\$PPID|\$\{PPID\})([[:space:]]+[0-9]*>.*)?[[:space:]]*$' <<<"$seg"; then
      block "this kill targets every process (-1), the whole process group (0), or this shell itself (\$\$ / \$PPID). Kill a specific, verified PID instead."
    fi
done < <(tr ';&|' '\n\n\n' <<<"$cmd")

exit 0

