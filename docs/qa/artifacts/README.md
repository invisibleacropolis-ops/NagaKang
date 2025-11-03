# Stress Harness Artifacts

This directory stores generated outputs from the audio engine stress harness.
Continuous integration runs `poetry run python prototypes/audio_engine_skeleton.py \
    --stress-plan docs/qa/stress_plan.json \
    --export-json docs/qa/artifacts/stress_results.json \
    --export-csv docs/qa/artifacts/stress_results.csv`

during every build, publishing the JSON and CSV files as workflow artifacts.
Developers can refresh the exports locally with the same command when
investigating performance regressions. Generated files are ignored from source
control to avoid churn while still documenting the canonical invocation.

The `baseline/` subdirectory stores committed CSV/JSON exports captured from a
known-good run. CI compares freshly generated artifacts against this baseline
via `tools/compare_stress_results.py`, summarising the outcome in the job
summary and failing the build on regressions. Use the new history helpers to
track investigations:

- Append trend context with
  `--history-json docs/qa/artifacts/history/stress_trend_history.json` and
  `--history-markdown docs/qa/artifacts/history/stress_trend_history.md` so the
  team can trace when regressions were investigated and resolved.
- Refresh the baseline *only* after verifying that deltas are expected (e.g.,
  after intentional DSP changes or infrastructure updates). When you do so,
  record the rationale in the Markdown history file to preserve context for
  future reviews.
- If regressions appear unexpectedly, keep the history artifacts uncommitted
  and use them to collaborate on the root cause before touching the baseline.

See `docs/qa/artifacts/history/README.md` for a full rundown on maintaining the
trend logs and sharing them with the broader engineering group.
