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

## Baseline Review Cadence

To keep the committed baseline aligned with current performance expectations,
schedule a standing **weekly review** of the trend history artifacts. During
the review:

- Pull the latest CI artifacts for the stress harness comparison job.
- Inspect `stress_trend_history.md` for newly appended investigations or open
  regressions.
- Spot-check the JSON history for unexpected tolerance overrides or scenario
  additions.
- File a follow-up issue if regressions have lingered for more than two review
  cycles without a documented mitigation.

Ad-hoc reviews are also recommended immediately after merging DSP-intensive
changes or infrastructure updates that could shift performance envelopes.

## Tolerance & Baseline Update Procedure

When metrics fall outside the default tolerances (`abs_tol=1e-4`,
`rel_tol=5e-3`) but the delta is expected, follow this process before updating
the baseline artifacts under `docs/qa/artifacts/baseline/`:

1. Capture fresh candidate exports and run the comparison command with history
   logging enabled (see [Usage](#usage)).
2. Document the rationale for the change in `stress_trend_history.md`,
   including links to profiling data or pull requests.
3. Confirm the new numbers against the product requirements in
   [`README.md` Plan §9](../../../README.md) to ensure they meet latency and
   underrun targets.
4. Update the baseline CSV/JSON files and run the comparison again to confirm
   a clean pass.
5. Record the outcome in the
   [`review_checklist.md`](review_checklist.md) template and commit the filled
   entry alongside the updated baseline.

If the deltas are unexpected, keep the baseline untouched and use the
checklist to track investigation status until performance returns to the
expected window.
