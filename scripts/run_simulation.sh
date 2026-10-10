#!/usr/bin/env bash
# Compile and run one Verilog test with Icarus Verilog.
# Usage: run_simulation.sh <test_dir>
#   <test_dir> must contain tb.v (top module "tb"); the DUT is rtl/counter.v.
# Env: AUTOTESTX_BUILD_DIR  scratch dir for the compiled image (default: mktemp)
#      IVERILOG / VVP       override simulator executables
# Exit: 0 pass, 1 test/simulation failure, 2 compile error, 64 usage, 127 tool missing.
set -u

IVERILOG="${IVERILOG:-iverilog}"
VVP="${VVP:-vvp}"

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <test_dir>" >&2
    exit 64
fi
test_dir="$1"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for tool in "$IVERILOG" "$VVP"; do
    command -v "$tool" >/dev/null 2>&1 || { echo "ERROR: required tool not found: $tool" >&2; exit 127; }
done
[ -f "$test_dir/tb.v" ] || { echo "ERROR: $test_dir/tb.v not found" >&2; exit 64; }

if [ -n "${AUTOTESTX_BUILD_DIR:-}" ]; then
    build_dir="$AUTOTESTX_BUILD_DIR"; mkdir -p "$build_dir"; cleanup=""
else
    build_dir="$(mktemp -d)"; cleanup="$build_dir"
fi
trap '[ -n "$cleanup" ] && rm -rf "$cleanup"' EXIT

image="$build_dir/sim.vvp"
echo "INFO: compiling $test_dir"
"$IVERILOG" -g2012 -o "$image" "$root/rtl/counter.v" "$test_dir/tb.v" || { echo "ERROR: compilation failed" >&2; exit 2; }

echo "INFO: running simulation"
# exec so a timeout signal reaches vvp directly (the trap above is skipped, so clean up first when temp).
if [ -n "$cleanup" ]; then "$VVP" "$image"; rc=$?; exit $rc; fi
exec "$VVP" "$image"
