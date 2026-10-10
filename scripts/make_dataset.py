#!/usr/bin/env python3
"""Generate data/labeled_log_snippets.csv from hand-written message templates.

All samples are SYNTHETIC: wording is modelled on common simulator/tool messages (Icarus Verilog,
Verilator, UVM-style, generic wrappers) but no real or proprietary logs are used. Each template is a
"family"; its variants differ only in numbers/identifiers. `family_id` lets the evaluator keep all
variants of one family on the same side of a train/test split, which avoids near-duplicate leakage.

Usage: python scripts/make_dataset.py [--out data/labeled_log_snippets.csv] [--seed 1234] [--variants 4]
"""
import argparse
import csv
import random

TEMPLATES = {
    "compile_error": [
        "{f}:{n}: syntax error\n{f}:{n}: error: Malformed statement",
        "{f}:{n}: error: Unknown module type: {m}\n1 error(s) during elaboration.",
        "{f}:{n}: error: Unable to bind wire/reg/memory `{s}' in `tb.dut'",
        "ERROR: compilation failed\nI give up.",
        "Error-[SE] Syntax error\n  Following verilog source has syntax error :\n  \"{f}\", {n}: token is ';'",
        "%Error: {f}:{n}:{c}: syntax error, unexpected IDENTIFIER, expecting ';'",
        "elaboration aborted: design unit '{m}' could not be resolved in library work",
        "** Error: ({f}) {f}({n}): near \"endmodule\": syntax error, unexpected endmodule",
    ],
    "assertion_failure": [
        "ASSERT FAIL: expected {a}, got {b} at time {t}",
        "[{t}] Assertion violation: {s} stable property failed",
        "FAIL: {m} mismatch on {s}: expected 0x{h}, actual 0x{h2}",
        "Error: scoreboard check failed at {t}ns: data compare {a} != {b}",
        "UVM_ERROR @ {t}: reporter [CHK] output {s} did not match reference model value {a}",
        "assert property ({s}) failed\n  at {f}:{n}",
        "$fatal: tb check at {f}:{n}: counter value {a} violated invariant {s}",
        "TEST FAILED: {s} was {a} but should have been {b} after reset",
    ],
    "timeout": [
        "AUTOTESTX: TIMEOUT after {a}s; process group killed",
        "Simulation timed out after {t} ns without reaching $finish",
        "ERROR: watchdog expired at {t}: testbench did not complete",
        "no progress for {a} seconds; killing simulation",
        "Test exceeded maximum run time of {a}s",
        "TIMEOUT waiting for signal {s} to assert (limit {t} ns)",
        "The simulation did not terminate within the allotted {a} seconds",
        "Time-out: handshake on {s} never completed",
    ],
    "runtime_error": [
        "FATAL: {f}:{n}: index out of bounds\n       Time: {t}  Scope: tb.{s}",
        "Segmentation fault (core dumped)",
        "vvp: {f}:{n}: out of memory allocating {a} bytes",
        "Runtime error: division by zero in {m} at {t}",
        "Floating point exception while evaluating {s}",
        "Process terminated by signal {sig}",
        "Array index {a} out of range for {s}[{b}:0] at time {t}",
        "Stack overflow in recursive function {s} (depth {a})",
    ],
    "unknown": [
        "WARNING: license server response slow ({a} ms)",
        "Unexpected output format from wrapper script near line {n}",
        "exit status {a} with no diagnostic message",
        "something went wrong while preparing {s}",
        "Operation did not succeed; reason not provided",
        "Warning: deprecated option -{s} ignored\nsimulation ended",
        "Cannot determine cause; log truncated after {a} lines",
        "INFO: cleanup of {f} skipped",
    ],
}

FILES = ["tb.v", "counter.v", "alu.v", "fifo.v", "top.sv", "uart_tx.v", "dut_wrapper.sv"]
MODS = ["counter", "alu", "fifo_ctrl", "uart_rx", "regfile", "arbiter", "decoder"]
SIGS = ["count", "data_out", "valid", "ready", "state", "addr", "ack", "irq"]
OPTS = ["gno-io-range", "fast", "legacy", "x", "trace"]


def fill(template: str, rng: random.Random) -> str:
    sig = rng.choice(["SIGSEGV", "SIGABRT", "SIGBUS", "SIGKILL"])
    values = {
        "f": rng.choice(FILES), "n": rng.randint(2, 480), "c": rng.randint(1, 60),
        "m": rng.choice(MODS), "a": rng.randint(1, 5000), "b": rng.randint(1, 5000),
        "t": rng.randint(10, 900000), "h": f"{rng.randint(0, 255):02x}", "h2": f"{rng.randint(0, 255):02x}",
        "sig": sig, "s": rng.choice(SIGS),
    }
    if "-{s} ignored" in template:
        values["s"] = rng.choice(OPTS)
    return template.format(**values)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/labeled_log_snippets.csv")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--variants", type=int, default=4)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    rows, seen = [], set()
    for label, templates in TEMPLATES.items():
        for fam_idx, template in enumerate(templates, 1):
            made, attempts = 0, 0
            while made < args.variants and attempts < 200:
                attempts += 1
                text = fill(template, rng)
                if text in seen:
                    continue
                seen.add(text)
                made += 1
                rows.append({"sample_id": f"S{len(rows) + 1:04d}", "log_text": text, "label": label,
                             "source_type": "synthetic", "family_id": f"{label}-{fam_idx}",
                             "notes": "template-generated variant"})
    with open(args.out, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["sample_id", "log_text", "label", "source_type",
                                                "family_id", "notes"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
