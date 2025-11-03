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
