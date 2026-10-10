# AutoTestX: Changelog

## [0.1.0] - 2026-10-10

### Features
- **Core Orchestration**: Python-based test runner supporting YAML/JSON configuration validation, process-group timeouts, and per-test isolation.
- **Log Parsing Engine**: Perl regular-expression log parser extracting line-indexed events (ERROR, WARNING, PASS, FAIL, ASSERT, FATAL, TIMEOUT).
- **RTL Simulation & Linting**: Icarus Verilog compilation and execution scripts for digital designs, paired with Tcl testbench scenario linting.
- **ML Failure Classification**: Scikit-learn TF-IDF + Logistic Regression classification pipeline evaluated against rule-based baselines with stratified group cross-validation.
- **Reporting**: Automated generation of interactive HTML reports, structured JSON results, and CSV summaries.
- **Web API & Dashboard**: Local FastAPI backend and modern React/Vite/Tailwind frontend dashboard providing test suite execution, live polling, log inspection, and regression comparison.
