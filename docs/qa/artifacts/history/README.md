# Stress Harness Trend History

The stress harness comparison utility (`tools/compare_stress_results.py`) can
now append structured history entries so engineers can trace how performance
metrics evolve over time. Store persisted records in this directory when
investigating regressions or when intentionally refreshing the baseline.

## Usage

1. Generate fresh stress harness exports per README §9 and
   `docs/qa/artifacts/README.md`.
2. Compare the results against the committed baseline while appending history
   artifacts:

   ```bash
   poetry run python tools/compare_stress_results.py \
       --baseline-json docs/qa/artifacts/baseline/stress_results.json \
       --candidate-json docs/qa/artifacts/stress_results.json \
       --baseline-csv docs/qa/artifacts/baseline/stress_results.csv \
       --candidate-csv docs/qa/artifacts/stress_results.csv \
       --summary-path docs/qa/artifacts/history/latest_trend_summary.md \
       --history-json docs/qa/artifacts/history/stress_trend_history.json \
       --history-markdown docs/qa/artifacts/history/stress_trend_history.md
   ```

3. Commit the updated `stress_trend_history.json`/`.md` files when performance
   expectations change. Otherwise, include the generated history artifacts in
   investigation notes or attach them to CI logs without committing.

The JSON log captures machine-readable context (timestamp, tolerance, paths,
and any issues) while the Markdown log provides human-readable summaries that
can be linked in incident reports.

## When to Refresh the Baseline

Refer to `docs/qa/artifacts/README.md` for detailed guidance. In short:

- **Investigate first** when trend history flags regressions that are not tied
  to an intentional DSP or infrastructure change.
- **Refresh the baseline** only after confirming the new metrics represent an
  expected improvement or a deliberate trade-off.
- **Document the reasoning** in the Markdown history file so future engineers
  understand why tolerances shifted.

History artifacts keep instrumentation work (Plan §9) transparent and make it
easy to surface trend insights during Step 3/4 performance reviews.
