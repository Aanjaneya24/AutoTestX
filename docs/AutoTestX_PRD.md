# Product Requirements Document (PRD)

## AutoTestX --- Multi-Language RTL Test Automation and ML-Assisted Log Analysis

**Document version:** 1.0\
**Status:** Implementation-ready MVP specification\
**Primary audience:** Student developer / peer project team\
**Target users:** EDA automation, product validation, design
verification, and R&D-oriented entry-level roles\
**Planned MVP duration:** 10--14 days at approximately 2--3 focused
hours per day, assuming basic Python/programming experience\
**Project type:** Educational portfolio project; not a production-grade
EDA platform

------------------------------------------------------------------------

## 1. Executive Summary

AutoTestX is a small, configuration-driven framework that automates
a repeatable RTL simulation workflow. It runs a set of digital-design
test cases, collects execution output, parses logs, classifies known
failure patterns, and produces a report that an engineer can use to
review a regression run.

The MVP combines: - **Python** for orchestration, configuration, process
control, data handling, ML evaluation, and report generation. -
**Bash/Shell** for environment checks and invoking build/simulation
commands. - **Tcl** for defining or running test sequences where
appropriate. - **Perl** for regular-expression-based log parsing. -
**Verilog** for small example RTL designs and testbenches. -
**scikit-learn** for one carefully scoped ML experiment: classifying log
snippets into predefined failure categories. - **HTML/CSV/JSON** for
human-readable and machine-readable results.

The project must remain small enough for a fresher to implement and
explain. The ML component is an experimental assistant; it must not
claim to identify a true hardware root cause or predict defects without
evidence.

## 2. Problem Statement

Running tests manually is repetitive and makes results harder to compare
consistently. Logs can be long, failure messages can vary, and manual
summaries are easy to miss or format inconsistently.

AutoTestX addresses this narrow problem by providing one command
to: 1. validate the required tools and configuration; 2. execute a
configured set of RTL simulations; 3. capture each test's output, exit
status, and duration; 4. parse logs into structured events; 5. classify
supported failure patterns using rules and an optional ML model; 6.
generate a summary report with links or paths to detailed logs.

The MVP does not replace commercial EDA tools, verification engineers,
or debugging. It automates a small repeatable workflow around an
open-source simulator.

## 3. Goals and Non-Goals

### 3.1 Goals

**G1 --- One-command execution:** A user can run the configured
regression suite from the command line.

**G2 --- Configuration-driven tests:** Test commands and metadata live
in YAML or JSON, not scattered throughout Python source.

**G3 --- Reproducible results:** Every test has a status, duration, exit
code, log path, and run identifier.

**G4 --- Robust process handling:** The framework handles non-zero exit
codes, missing tools, malformed configuration, and timeouts without
silently marking tests as passed.

**G5 --- Multi-language integration:** Each language has a clear,
defensible responsibility rather than being included only as a resume
keyword.

**G6 --- Structured log analysis:** Raw logs are converted into
structured error/warning events and summarized.

**G7 --- Measured ML experiment:** An ML model classifies labeled log
snippets into a small set of failure categories, and its results are
compared with a simple rule-based baseline.

**G8 --- Useful reporting:** The framework generates HTML and JSON/CSV
summaries that make failed tests easy to inspect.

**G9 --- Portfolio quality:** The repository includes documentation,
example data, tests, limitations, and reproducible setup instructions.

### 3.2 Non-Goals for the MVP

The MVP will not: - implement a new RTL simulator or EDA tool; - replace
commercial Cadence or Siemens EDA products; - require paid licenses; -
support every HDL, simulator, operating system, or toolchain; - use deep
learning, LLMs, or cloud services; - claim automatic root-cause
diagnosis of hardware defects; - build an elaborate desktop dashboard; -
implement distributed execution, advanced scheduling, or large-scale
parallel infrastructure; - guarantee test prioritization improves
coverage or runtime; - flash, reset, or control physical hardware in the
initial version.

These can be future extensions only after the core workflow is reliable.

## 4. Target Users and Use Cases

### Primary user

A student or junior engineer who wants to run small RTL simulation
regressions and review results consistently.

### Secondary user

A reviewer/interviewer evaluating the candidate's scripting, debugging,
testing, software design, and basic ML evaluation skills.

### Core use cases

1.  As a user, I can check whether required tools are installed before
    starting a run.
2.  As a user, I can select a configured test suite and run it with one
    command.
3.  As a user, I can inspect a log for any failed test.
4.  As a user, I can see whether a failure was caused by compilation, an
    assertion/test failure, a timeout, a missing tool, or an unknown
    error.
5.  As a user, I can compare the current run's outcomes with a previous
    run.
6.  As a user, I can view ML classification results and understand when
    the model is uncertain.
7.  As a reviewer, I can reproduce the sample run by following the
    README.

## 5. Scope and Priorities

### P0 --- Required for MVP

-   Python CLI entry point.
-   YAML/JSON configuration validation.
-   Tool/environment preflight checks.
-   At least one small Verilog design and testbench.
-   Open-source simulator integration, initially Icarus Verilog or
    Verilator.
-   Shell script invocation and output capture.
-   At least one Tcl script with a documented test/flow role.
-   Perl log parser.
-   Per-test status, duration, exit code, and log file.
-   HTML plus JSON or CSV report.
-   Unit tests for key Python logic.
-   A small labeled log dataset and baseline-vs-ML evaluation.
-   README with installation, usage, sample output, and limitations.

### P1 --- Include if time permits

-   Comparison with the previous run.
-   Configurable retry for explicitly retryable failures.
-   GitHub Actions CI workflow.
-   Better report filtering and grouping.

### P2 --- Future work

-   Tkinter GUI.
-   Parallel test execution.
-   Physical-device / ESP32 integration.
-   Support for additional simulators and commercial tool adapters.
-   Test prioritization research.
-   More sophisticated log clustering or anomaly detection.

## 6. Technical Design

### 6.1 High-level workflow

1.  User invokes `python -m autotestx run --config configs/demo.yaml`.
2.  Python validates configuration and checks required tools.
3.  Python creates a unique run directory.
4.  Python calls the configured Shell wrapper to compile/run each test,
    passing arguments safely.
5.  Tcl may execute test sequences or act as a simulator-flow script
    where the selected tool supports it. For the open-source MVP,
    document the precise Tcl role; do not pretend a simulator uses Tcl
    if it does not.
6.  The framework records stdout, stderr, exit code, timeout, and
    duration.
7.  Perl parses raw logs and emits structured JSON records for supported
    patterns.
8.  Python merges test metadata and parser output, assigning
    deterministic statuses.
9.  Optional ML inference classifies extracted log snippets.
10. Python writes JSON/CSV/HTML reports and prints a concise terminal
    summary.

### 6.2 Important tool compatibility note

Not every simulator uses Tcl as its native control language. The
implementation must keep simulator-specific commands behind a small
adapter. Tcl should be used for a real, documented test-sequence or flow
task. If the selected open-source simulator cannot use the Tcl script
directly, use Tcl to generate/validate test scenarios or select a
compatible flow tool. Never claim native Tcl simulator control unless it
is actually implemented and tested.

### 6.3 Architecture components

**A. CLI and orchestrator (Python)** - Parse command-line arguments. -
Load and validate configuration. - Check dependencies. - Create run
directory. - Invoke commands with subprocess argument lists, not unsafe
shell string concatenation. - Enforce timeout and capture output. -
Normalize statuses and write results.

**B. Configuration layer** - Store test names, commands, timeout limits,
expected outcomes, tags, and log patterns. - Reject unknown or missing
required fields with clear errors. - Keep paths relative to the
repository or explicitly resolved.

**C. Shell wrapper** - Check required tools and environment. - Invoke
compilation/simulation commands. - Return meaningful exit codes. - Avoid
destructive commands and hard-coded machine-specific paths.

**D. Tcl test/flow component** - Provide a small set of test scenarios
or flow-control procedures. - Record a result for each scenario. -
Clearly document interpreter/tool requirements. - Include a minimal
example that can be executed in the documented environment.

**E. Perl log parser** - Read a log file. - Identify known markers such
as `ERROR`, `WARNING`, `PASS`, `FAIL`, `ASSERT`, and timeout text. -
Extract line number, category, and a bounded message snippet. - Emit
valid JSON or TSV to a file/stdout. - Handle empty or missing logs
cleanly.

**F. ML classifier (Python / scikit-learn)** - Input: normalized log
snippet and optionally a few non-sensitive metadata fields. - Output:
predicted class and confidence/probability when supported. - Initial
labels: `compile_error`, `assertion_failure`, `timeout`,
`runtime_error`, `unknown`. - Use TF-IDF features and Logistic
Regression as a transparent baseline model. - Compare against a
rule-based classifier on a held-out test set. - Do not train/test on
near-duplicate snippets split across both sets if that would inflate
metrics. - If dataset size is too small, present the result as a
demonstration, not as a statistically strong model.

**G. Reporting** - Terminal summary. - JSON machine-readable report. -
CSV summary of test-level outcomes. - HTML report with overall totals,
per-test status, durations, categorized failures, and log paths. -
Clearly separate deterministic rule-based findings from ML predictions.

## 7. Functional Requirements and Acceptance Criteria

### FR-01: Configuration loading

**Requirement:** The user can specify a suite and test metadata in a
configuration file.

**Acceptance criteria:** - A valid sample config loads successfully. - A
malformed config produces a readable error and non-zero process exit. -
Missing required fields are reported with the field name. - No test is
executed when configuration validation fails.

### FR-02: Environment preflight

**Requirement:** Check required executables before running tests.

**Acceptance criteria:** - Detect whether Python, Perl, Tcl interpreter,
Shell, and selected simulator are available. - Report missing tools by
name. - Stop before execution if a required tool is missing. - Do not
require optional tools if their feature is disabled.

### FR-03: Test execution

**Requirement:** Execute each configured test and capture output.

**Acceptance criteria:** - Each test creates a log file. - Record start
time, duration, exit code, and status. - Non-zero exit codes are not
marked as PASS. - Timeout produces `TIMEOUT` and terminates the process
where feasible. - Paths and arguments containing spaces are handled
safely.

### FR-04: Log parsing

**Requirement:** Parse logs into structured events.

**Acceptance criteria:** - Recognize documented error/warning/pass/fail
patterns. - Emit valid structured output. - Include source log path and
line number when available. - Empty logs and unknown patterns do not
crash the parser. - Preserve the raw log for manual review.

### FR-05: Failure classification

**Requirement:** Assign an understandable category to failures.

**Acceptance criteria:** - Rule-based classification is available
regardless of whether ML is enabled. - ML output is stored separately
from the deterministic status. - Unknown or low-confidence cases are
labeled `unknown` or `needs_review`. - The report never presents a model
prediction as a verified root cause.

### FR-06: Reporting

**Requirement:** Generate usable run reports.

**Acceptance criteria:** - Show total, passed, failed, errored, and
timed-out tests. - Show per-test duration, exit code, status, and log
location. - Show parser findings and ML predictions separately. -
Generate JSON and HTML successfully for a sample run. - Report
generation handles zero tests and partial failures safely.

### FR-07: Run comparison

**Requirement (P1):** Compare two run summaries.

**Acceptance criteria:** - Identify tests that changed from pass to fail
or fail to pass. - Identify tests present only in one run. - Do not
infer a regression when test names/configurations are incompatible;
report the mismatch.

### FR-08: ML evaluation

**Requirement:** Evaluate the ML classifier with a baseline.

**Acceptance criteria:** - Dataset labels and data source are
documented. - Use a reproducible random seed where applicable. - Report
macro-F1, per-class precision/recall, and a confusion matrix. - Compare
against a rule-based baseline. - Explain dataset size, class imbalance,
limitations, and examples of misclassification. - Do not claim
improvement unless the measured evaluation supports it.

## 8. Example Configuration

The exact commands must be adapted and tested for the selected simulator
and operating system.

``` yaml
project:
  name: autotestx-demo
  simulator: iverilog

settings:
  output_dir: reports/runs
  default_timeout_seconds: 30
  enable_ml_classification: true

tools:
  simulator: iverilog
  runtime: vvp
  python: python3
  perl: perl
  tclsh: tclsh

tests:
  - name: counter_basic
    description: Check basic counter behavior
    command:
      - bash
      - scripts/run_simulation.sh
      - examples/counter
    timeout_seconds: 30
    tags: [smoke, rtl]

  - name: counter_reset
    description: Check reset behavior
    command:
      - bash
      - scripts/run_simulation.sh
      - examples/counter_reset
    timeout_seconds: 30
    tags: [reset, rtl]
```

The runner must validate the schema and pass command arguments as an
array. Avoid executing arbitrary config strings with `shell=True`. Treat
any command configuration as trusted local project code, not as a safe
format for untrusted users.

## 9. Proposed Repository Structure

``` text
autotestx/
├── README.md
├── LICENSE
├── requirements.txt
├── pyproject.toml
├── configs/
│   └── demo.yaml
├── src/
│   └── autotestx/
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       ├── preflight.py
│       ├── runner.py
│       ├── models.py
│       ├── log_analysis.py
│       ├── ml_classifier.py
│       ├── report.py
│       └── compare.py
├── scripts/
│   ├── preflight.sh
│   ├── run_simulation.sh
│   └── parse_logs.pl
├── tcl/
│   └── demo_tests.tcl
├── rtl/
│   ├── counter.v
│   └── tb_counter.v
├── data/
│   ├── sample_logs/
│   └── labeled_log_snippets.csv
├── tests/
│   ├── test_config.py
│   ├── test_runner.py
│   ├── test_log_analysis.py
│   ├── test_ml_classifier.py
│   └── test_report.py
├── docs/
│   ├── architecture.md
│   └── ml_evaluation.md
└── reports/
    └── .gitkeep
```

Generated run outputs should generally be ignored by Git; include only
small, sanitized example logs and reports.

## 10. CLI Design

Proposed commands:

``` bash
# Check tools and environment
python -m autotestx doctor

# Validate configuration without running tests
python -m autotestx validate --config configs/demo.yaml

# Run the configured suite
python -m autotestx run --config configs/demo.yaml

# Compare two previous run summaries
python -m autotestx compare --before reports/runs/run_a/results.json \
                           --after reports/runs/run_b/results.json

# Evaluate the ML model
python -m autotestx evaluate-ml --dataset data/labeled_log_snippets.csv
```

These commands are interface goals. Implement only the commands that
exist; documentation must not advertise unimplemented commands.

## 11. Data and ML Plan

### 11.1 Dataset

Create a small, clearly labeled dataset from synthetic or openly
shareable sample logs. Include multiple examples per class and variation
in wording. Clearly identify synthetic examples. Do not include
proprietary customer logs or confidential data.

Suggested fields: - `sample_id` - `log_text` - `label` - `source_type`
(`synthetic` or `public_example`) - optional `notes`

### 11.2 Baseline

Implement simple rules first, such as matching known compiler error
markers, assertion failures, and timeout messages. This creates a
transparent baseline and may be sufficient for highly structured logs.

### 11.3 ML model

Use a scikit-learn pipeline: 1. normalize log text conservatively; 2.
transform text with TF-IDF; 3. train Logistic Regression; 4. evaluate on
held-out data; 5. save the model and metadata only if the evaluation
setup is documented.

### 11.4 Evaluation

Report: - macro-F1; - per-class precision and recall; - confusion
matrix; - number of samples per class; - baseline score; - model
score; - inference time on a stated test sample, if measured.

A high score on a tiny synthetic dataset is not evidence of real-world
generalization. Include failure examples and discuss whether rules or ML
are better for each category.

### 11.5 ML limitations

The model classifies text patterns, not physical silicon defects. It may
fail on unseen messages, new tool versions, truncated logs, and rare
failure categories. The report should allow engineers to inspect the
underlying evidence.

## 12. Non-Functional Requirements

-   **Reliability:** Failures are recorded explicitly; no silent pass.
-   **Reproducibility:** Store configuration snapshot, tool versions,
    timestamp, and run ID.
-   **Maintainability:** Separate configuration, execution, parsing,
    classification, and reporting modules.
-   **Portability:** Target Linux first; document other-platform
    limitations.
-   **Security:** Avoid unsafe shell construction; do not execute
    untrusted configs; do not commit secrets.
-   **Performance:** The framework should add limited overhead compared
    with the simulation runtime. Measure rather than claim a specific
    improvement.
-   **Usability:** A new user should be able to follow the README to run
    a sample suite.
-   **Traceability:** Every reported failure should link to the raw log
    and relevant line where available.

## 13. Testing Strategy

### Unit tests

-   valid/invalid config;
-   missing executable;
-   process success/failure/timeout;
-   Perl parser handling of known, unknown, and empty logs;
-   classifier output and low-confidence handling;
-   report generation with zero, passing, failing, and timed-out tests;
-   run comparison.

### Integration tests

-   run a known passing RTL test;
-   run a deliberately failing test;
-   run a test that times out;
-   verify each outcome appears correctly in JSON and HTML;
-   verify raw logs remain available.

### Test data

Include controlled sample logs for: - successful simulation; -
compilation failure; - assertion failure; - timeout; - runtime error; -
unknown error.

### Definition of done

A clean checkout can run the documented sample workflow on the
documented environment, and the resulting report correctly reflects
deliberately passing and failing examples.

## 14. Two-Week Work Plan

### Days 1--2: Environment and scope

-   Choose Linux or WSL as the primary environment.
-   Install Python, Perl, Tcl, Icarus Verilog or Verilator, and Git.
-   Run one manual simulation.
-   Write the first README and a small RTL example.

**Exit criterion:** A known-good simulation can be run manually.

### Days 3--4: Python CLI and configuration

-   Create package structure.
-   Implement config loading and validation.
-   Add preflight checks.
-   Implement one-command execution and per-test logs.

**Exit criterion:** The Python runner can execute one passing and one
failing command.

### Days 5--6: RTL test execution

-   Add sample RTL and testbench.
-   Create a Shell wrapper for compile/run.
-   Record exit codes, duration, and timeouts.

**Exit criterion:** Passing, failing, and timed-out test cases are
distinguished.

### Days 7--8: Tcl and Perl integration

-   Add a small Tcl test/flow script with a documented purpose.
-   Implement Perl log parsing to structured output.
-   Add parser tests.

**Exit criterion:** A log can be converted to structured failure events
reproducibly.

### Days 9--10: Reporting

-   Produce terminal summary and JSON/CSV.
-   Generate HTML report with per-test details and raw-log paths.
-   Add test-level run identifiers and tool versions.

**Exit criterion:** One command creates a readable report for the whole
suite.

### Days 11--12: ML experiment

-   Build and document labeled log snippets.
-   Implement rule baseline and TF-IDF + Logistic Regression.
-   Evaluate with a held-out split and metrics.

**Exit criterion:** Results and limitations are documented; ML
predictions do not override actual test status.

### Days 13--14: Quality and presentation

-   Add integration tests and error handling.
-   Write setup, usage, architecture, and ML evaluation docs.
-   Capture a sample report and terminal output.
-   Review the project as if explaining it in an interview.

**Exit criterion:** A reviewer can reproduce the demo and the developer
can explain every module.

If Tcl/Perl or simulator setup takes longer than expected, defer the ML
component or dashboard rather than leaving the core workflow unreliable.

## 15. Success Metrics

Measure these on the final demo: - percentage of configured tests that
execute and receive a recorded status; - accuracy of status mapping for
controlled pass/fail/timeout cases; - percentage of parser fixtures
correctly categorized; - report-generation success for both passing and
failing runs; - ML macro-F1 and per-class recall compared with the rule
baseline; - time required for a reviewer to set up and reproduce the
demo.

Do not invent performance numbers. Record actual results, test
conditions, dataset size, and limitations.

## 16. Risks and Mitigations

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  Too much scope for two weeks        Deliver P0 workflow first; defer
                                      GUI and parallelism

  Tcl does not fit selected simulator Define a real standalone test/flow
                                      role or use a compatible tool;
                                      document integration honestly

  ML dataset too small                Use synthetic examples
                                      transparently, report sample
                                      counts, avoid broad claims

  Rules outperform ML                 Report that result honestly;
                                      discuss where ML might help with
                                      varied logs

  Simulator differs across machines   Pin/document tool versions and
                                      include preflight checks

  False pass due to parser behavior   Base test status primarily on
                                      process status and explicit test
                                      outcomes, not ML

  Unsafe command execution            Use subprocess argument arrays and
                                      trusted local configs

  Interview questions expose gaps     Keep implementation small enough to
                                      understand and explain completely
  -----------------------------------------------------------------------

## 17. Demo Script

A 3--5 minute demonstration should show: 1. `doctor` detects the
environment. 2. `validate` checks the sample configuration. 3. `run`
executes one passing and one intentionally failing RTL test. 4. The
terminal summary shows accurate statuses. 5. The HTML report links to
raw logs and lists parser findings. 6. The ML evaluation page or output
shows the baseline, model metrics, and a misclassified example. 7. The
presenter explains what the system can and cannot infer.

## 18. Resume Guidance

Use resume bullets only after the features are implemented and verified.
A possible template is:

**AutoTestX --- RTL Regression Automation & ML-Based Log
Classification** \| Python, Tcl, Perl, Bash, Verilog, scikit-learn -
Built a configuration-driven framework to execute RTL simulations and
capture test status, runtime, exit codes, and logs. - Integrated
Perl-based log parsing and generated structured regression reports for
pass, fail, and timeout cases. - Evaluated a TF-IDF/Logistic Regression
classifier against a rule-based baseline for simulation-log
categorization, reporting macro-F1 and per-class results.

Replace or remove any bullet that does not accurately describe the
finished implementation. Add numeric results only when measured and
reproducible.

## 19. Interview Questions the Developer Should Be Able to Answer

-   Why is Python the orchestrator rather than the Shell script?
-   What specific task does Perl do that Python does not already handle?
-   What does the Tcl component execute, and how is it connected to the
    simulator?
-   How do you avoid unsafe shell command construction?
-   How are timeouts and child processes handled?
-   What determines PASS versus FAIL?
-   Why is the ML model not allowed to override a test result?
-   How did you split the dataset to avoid leakage?
-   Why use macro-F1 instead of accuracy alone?
-   When does a rule-based parser outperform ML?
-   What would be needed to use commercial EDA tools?
-   What are the current limitations?

## 20. Final Product Definition

AutoTestX is complete when a user can run a small RTL regression
suite with one command, get reproducible per-test results and logs,
parse failures with Perl, demonstrate a real and documented Tcl
component, generate an HTML/JSON report, and evaluate one ML log
classifier against a transparent baseline.

**Build order:** reliable automation first, structured log parsing
second, reports third, ML evaluation fourth. Do not add a GUI or
advanced features until the end-to-end workflow works.

**Product principle:** A small, tested, reproducible project that the
developer fully understands is more valuable than a large project with
superficial integrations.
