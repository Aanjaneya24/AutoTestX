#!/usr/bin/env bash
# Report availability and version of tools.
# Usage: preflight.sh <tool> [<tool> ...]
# Output (TSV, one line per tool): name <TAB> path-or-MISSING <TAB> first line of version output
for tool in "$@"; do
    path="$(command -v "$tool" 2>/dev/null)" || path=""
    if [ -z "$path" ]; then
        printf '%s\tMISSING\t\n' "$tool"
        continue
    fi
    case "$(basename "$tool")" in
        vvp)      ver="$("$tool" -V 2>&1 | head -n1)" ;;
        iverilog) ver="$("$tool" -V 2>&1 | head -n1)" ;;
        perl)     ver="$("$tool" -e 'print "perl $^V"' 2>&1 | head -n1)" ;;
        tclsh)    ver="tcl $(echo 'puts [info patchlevel]' | "$tool" 2>&1 | head -n1)" ;;
        bash)     ver="$("$tool" --version 2>&1 | head -n1)" ;;
        *)        ver="$("$tool" --version 2>&1 | head -n1)" ;;
    esac
    printf '%s\t%s\t%s\n' "$tool" "$path" "$ver"
done
