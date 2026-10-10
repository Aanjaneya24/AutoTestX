"""Command-line interface: doctor, validate, run, compare, evaluate-ml."""
from __future__ import annotations

import argparse
import json
import re
import signal
import sys
from pathlib import Path

from .compare import compare_runs, format_comparison, load_results
from .config import ConfigError, load_config, resolve
from .preflight import check_tools, missing, missing_support_files
from .report import text_summary


def _load(path):
    try:
        return load_config(path)
    except ConfigError as exc:
        print(f"Configuration error in {path}:", file=sys.stderr)
        for p in exc.problems:
            print(f"  - {p}", file=sys.stderr)
        return None


def _print_tools(statuses) -> None:
    for s in statuses:
        state = f"{s.path}  {s.version}".strip() if s.found else "MISSING"
        print(f"  {s.role:<13}{s.executable:<10}{state}")


def _support_files_ok() -> bool:
    gone = missing_support_files()
    if gone:
        print("Bundled scripts not found: " + ", ".join(gone) +
              "\nRun from the source checkout or use an editable install (pip install -e .).", file=sys.stderr)
    return not gone


def cmd_doctor(args) -> int:
    if not _support_files_ok():
        return 3
    if args.config:
        config = _load(args.config)
        if config is None:
            return 2
        tools, ml = config.tools, config.enable_ml_classification
    else:
        tools, ml = {"simulator": "iverilog", "runtime": "vvp", "python": "python3",
                     "perl": "perl", "tclsh": "tclsh", "bash": "bash"}, True
    statuses = check_tools(tools, ml)
    print("Tool check:")
    _print_tools(statuses)
    gone = missing(statuses)
    if gone:
        print("Missing: " + ", ".join(f"{s.role} ({s.executable})" for s in gone), file=sys.stderr)
        return 1
    print("All required tools found.")
    return 0


def cmd_validate(args) -> int:
    config = _load(args.config)
    if config is None:
        return 2
    print(f"OK: {len(config.tests)} tests in project '{config.project_name}' (root {config.root})")
    return 0


def _make_classifier(config):
    """Return (classify_fn_or_None, note). ML failure never aborts a run."""
    if not config.enable_ml_classification:
        return None, None
    model_path = resolve(config, config.ml_model_path)
    if not Path(model_path).is_file():
        return None, f"ML enabled but model not found at {model_path}; run `evaluate-ml` first. Continuing without ML."
    try:
        from .ml_classifier import LogClassifier
        clf = LogClassifier.load(model_path, config.ml_confidence_threshold)
    except Exception as exc:  # noqa: BLE001 - any load problem must not break the deterministic run
        return None, f"ML model could not be loaded ({exc}). Continuing without ML."
    import sklearn
    trained_with = clf.metadata.get("sklearn_version")
    warn = (f"model was trained with scikit-learn {trained_with}, running {sklearn.__version__}; "
            "re-run `evaluate-ml` to retrain" if trained_with and trained_with != sklearn.__version__ else None)
    return clf.predict, warn


def cmd_run(args) -> int:
    config = _load(args.config)
    if config is None:
        return 2
    if not _support_files_ok():
        return 3
    statuses = check_tools(config.tools, config.enable_ml_classification)
    gone = missing(statuses)
    if gone:
        print("Cannot start: required tools missing: " + ", ".join(f"{s.role} ({s.executable})" for s in gone),
              file=sys.stderr)
        return 3
    if args.run_id is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", args.run_id):
        print("error: --run-id must be 1-64 characters of letters, digits, '.', '_' or '-'", file=sys.stderr)
        return 2
    classify, note = _make_classifier(config)
    if note:
        print(f"NOTE: {note}", file=sys.stderr)
    from .runner import run_suite

    def _stop(signum, _frame):          # turn SIGTERM into the same clean-up path as Ctrl-C
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _stop)
    try:
        summary = run_suite(config, run_id=args.run_id, classify=classify, tool_statuses=statuses,
                            progress=lambda r: print(f"  [{r.status:<7}] {r.name} ({r.duration_seconds:.2f}s)"))
    except KeyboardInterrupt:
        print("interrupted: the run was stopped before it finished", file=sys.stderr)
        return 130
    except FileExistsError:
        print(f"error: run id {args.run_id!r} already exists", file=sys.stderr)
        return 4
    except OSError as exc:
        print(f"error: cannot write run output under {resolve(config, config.output_dir)}: {exc}", file=sys.stderr)
        return 4
    print(text_summary(summary))
    return 0 if summary["all_as_expected"] else 1


def cmd_compare(args) -> int:
    try:
        before, after = load_results(args.before), load_results(args.after)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    result = compare_runs(before, after)
    print(format_comparison(result, before["run_id"], after["run_id"]))
    return 1 if result["regressions"] else (0 if result["compatible"] else 2)


def cmd_evaluate_ml(args) -> int:
    try:
        from .ml_classifier import evaluate, train_and_save
        result = evaluate(args.dataset)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ImportError as exc:
        print(f"error: scikit-learn is required for evaluate-ml ({exc})", file=sys.stderr)
        return 3
    print(f"Dataset: {result['n_samples']} samples, {result['n_families']} families, "
          f"counts {result['class_counts']}")
    print(f"Protocol: {result['protocol']}")
    for key, title in (("rule_baseline", "Rule baseline"), ("ml_model", "TF-IDF + LogisticRegression")):
        m = result[key]
        print(f"\n{title}: macro-F1={m['macro_f1']}  accuracy={m['accuracy']}")
        for label, c in m["per_class"].items():
            print(f"  {label:<18} P={c['precision']:.2f} R={c['recall']:.2f} F1={c['f1']:.2f} n={c['support']}")
    print(f"\nInference: {result['inference_ms_per_sample']} ms/sample "
          f"(n={result['inference_sample_size']}, single-sample predict_proba)")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
        print(f"Wrote {args.out}")
    if not args.no_save_model:
        train_and_save(args.dataset, args.model_out)
        print(f"Saved model trained on all samples to {args.model_out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="autotestx", description="AutoTestX: RTL regression automation")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("doctor", help="check required tools")
    d.add_argument("--config", help="check the tools named in this config (default: standard set)")
    d.set_defaults(func=cmd_doctor)

    v = sub.add_parser("validate", help="validate a config without running tests")
    v.add_argument("--config", required=True)
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="run the configured suite")
    r.add_argument("--config", required=True)
    r.add_argument("--run-id", help="use this run id (default: generated); must not already exist")
    r.set_defaults(func=cmd_run)

    c = sub.add_parser("compare", help="compare two results.json files")
    c.add_argument("--before", required=True)
    c.add_argument("--after", required=True)
    c.set_defaults(func=cmd_compare)

    e = sub.add_parser("evaluate-ml", help="evaluate the ML classifier against the rule baseline")
    e.add_argument("--dataset", default="data/labeled_log_snippets.csv")
    e.add_argument("--out", help="write full evaluation JSON here")
    e.add_argument("--model-out", default="models/log_classifier.joblib")
    e.add_argument("--no-save-model", action="store_true")
    e.set_defaults(func=cmd_evaluate_ml)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
