export type RunState = "starting" | "running" | "completed" | "failed" | "interrupted";
export type Overall = "as_expected" | "unexpected_results" | RunState;
export type Outcome =
  | "passed" | "expected_failure" | "unexpected_failure" | "unexpected_pass"
  | "pending" | "running";

export interface Totals {
  total: number; passed: number; failed: number; errored: number; timed_out: number; unexpected: number;
  completed?: number;
}
export interface MlSummary {
  classified: number; labels: Record<string, number>; needs_review: number; agree_with_rules: number;
}
export interface RunSummary {
  run_id: string; state: RunState; overall: Overall; error: string | null; project: string | null;
  started: string | null; finished: string | null; duration_seconds: number | null;
  totals: Totals | null; all_as_expected: boolean | null; unexpected_tests: string[]; ml: MlSummary | null;
}
export interface ProgressTest {
  name: string; description?: string; expect: string; state: "pending" | "running" | "done";
  status?: string; duration_seconds?: number; exit_code?: number | null; category?: string | null;
  matches_expectation?: boolean;
}
export interface RunDetail extends RunSummary {
  progress: { completed: number; total: number; current: string | null; tests: ProgressTest[] };
  environment: { platform: string; python: string; tools: { role: string; executable: string; path: string | null; version: string }[] } | null;
  console_tail: string; exit_code: number | null;
}
export interface RunList { runs: RunSummary[]; latest: string | null; active_run: string | null }

export interface Finding { line: number; category: string; snippet: string }
export interface MlPrediction { label: string; top_label?: string; confidence: number; needs_review?: boolean; note?: string }
export interface TestRecord {
  name: string; status: string | null; expected_status: string; outcome: Outcome; exit_code: number | null;
  timed_out?: boolean; duration_seconds: number | null; status_reason?: string; description?: string;
  tags?: string[]; command?: string[]; rule_category: string | null; findings: Finding[];
  parser_error?: string | null; ml_prediction: MlPrediction | null; log_available: boolean;
  log_truncated: boolean; log_bytes_total?: number | null;
}
export interface RunResults { run_id: string; state: RunState; tests: TestRecord[] }

export interface ConfigTest { name: string; description: string; expect: string; timeout_seconds: number; tags: string[] }
export interface ConfigInfo {
  id: string; path: string; valid: boolean; problems: string[]; project: string | null;
  ml_enabled?: boolean; max_log_bytes?: number; tests: ConfigTest[];
  tools?: { role: string; executable: string; found: boolean; path: string | null; version: string }[];
}

export interface LogChunk {
  text: string; offset: number; next_offset: number; size: number; has_more: boolean; start_line: number;
  test: string; run_id: string; log_truncated: boolean; log_bytes_total?: number | null; findings: Finding[];
}
export interface LogSearch {
  query: string; matches: { line: number; text: string }[]; total_matches: number; capped: boolean;
}

export interface ClassMetrics { precision: number; recall: number; f1: number; support: number }
export interface ModelMetrics {
  accuracy: number; macro_f1: number; per_class: Record<string, ClassMetrics>; confusion_matrix: number[][];
}
export interface MlEvaluation {
  evaluation: {
    n_samples: number; n_families: number; class_counts: Record<string, number>; source_types: string[];
    protocol: string; labels: string[]; rule_baseline: ModelMetrics; ml_model: ModelMetrics;
    ml_misclassified_examples: { text: string; true: string; predicted: string }[];
    rule_misclassified_examples: { text: string; true: string; predicted: string }[];
    inference_ms_per_sample: number; inference_sample_size: number; sklearn_version: string; evaluated_at: string;
  };
  labels: string[]; statement: string; limitations: string[]; baseline_higher: boolean; model_file_present: boolean;
}

export interface Comparison {
  before: string; after: string; compatible: boolean; warnings: string[];
  regressions: ChangeEntry[]; fixes: ChangeEntry[]; other_changes: ChangeEntry[];
  config_changed: string[]; only_before: string[]; only_after: string[]; text: string;
}
export interface ChangeEntry { name: string; before: string; after: string; expected: string }
