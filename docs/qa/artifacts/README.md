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
summary and failing the build on regressions. Update the baseline only after
intentionally changing the stress harness or its expected performance profile.
