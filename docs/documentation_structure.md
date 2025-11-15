# Documentation Structure & Style Guide

This index formalizes how project documentation is organized so contributors can navigate materials quickly while expanding on the comprehensive development plan.

## Directory Overview
- `docs/step1_product_requirements.md` – Vision, personas, requirements, PRD summary.
- `docs/step1_ux_flows.md` – Narrative UX flows, gesture considerations, and wireframe roadmap.
- `docs/step1_backlog_user_stories.md` – Prioritized user stories with acceptance criteria.
- `docs/step2_architecture_tech_choices.md` – (New) System architecture decisions, technology evaluations, and integration plans.
- `docs/step3_audio_engine_framework.md` – Musician-centric kickoff for the Step 3 audio engine and module scaffolding.
- `docs/step3_pattern_bridge_walkthrough.md` – Pattern bridge flow showing sampler layering, beat loudness tables, and CLI usage for rehearsal prep.
- `docs/step6_mixer_kickoff.md` – Effects/routing kickoff documenting mixer graph primitives, auxiliary routing tests, and Kivy layout strategy per Plan §6.
- `docs/step6_mixer_kivy_mock.py` – Prototype MixerGraph → Kivy adapter illustrating strip state binding, subgroup metering, return-bus presets, and insert reordering affordances.
- `docs/step7_gui_shell.md` – Step 7 kickoff covering the preview orchestrator, tracker/mixer layout contracts, tracker grid & loudness widgets, transport/tutorial bindings, and widget adapters promoted from the mock into production.
- `tools/mixer_diagnostics.py` – CLI for rendering the Step 6 demo graph, exporting subgroup meters, return levels, and mixer automation events for QA.
- `docs/qa/artifacts/mixer_trends/README.md` – Mixer trend artifact workflow tying `mixer_trend_ci.py` outputs to the shared audio reference pack and CI publishing expectations.
- `docs/assets/` – Source-controlled Mermaid files for architecture diagrams (component, sequence, failure-mode, controller routing) referenced by `docs/step2_architecture_diagrams.md`, plus future exported visuals. UI captures such as `docs/assets/ui/transport_strip_annotations.svg` document Step 7 bindings for external designers.
- `docs/qa/` – Benchmark and QA artifacts (e.g., audio stress harness tables) that evidence progress on Plan §9 instrumentation goals. The canonical stress harness configuration lives in `docs/qa/stress_plan.json` with exported summaries stored in `docs/qa/artifacts/`.
- `tools/publish_diagrams.py` – Scriptable Mermaid-to-SVG pipeline used to keep `docs/step2_architecture_diagrams.md` in sync with rendered assets.
- `tools/mixer_trend_ci.py` – CI helper that captures mixer diagnostics summaries, diffs them against the committed baseline, and appends Markdown/JSON history entries for QA releases.
- `src/domain/` – Production-ready data models, repository abstractions, and persistence helpers superseding the prototypes per Step 2 roadmap.
- `.github/workflows/ci.yml` – Continuous integration pipeline invoking Poetry, Ruff, Mypy, and Pytest for baseline quality gates.
- `pyproject.toml` – Poetry configuration defining dependencies, lint/type-check tooling, and pytest defaults.
- `README.md` – Comprehensive development plan overview and onboarding context.
- `EngineerLog.md` – Session-by-session progress tracker, completion metrics, and TODOs.

## Style Conventions
1. **Structure**
   - Use top-level headings (`#`) to denote major plan steps (e.g., Step 2) and secondary headings (`##`) for subtopics.
   - Provide bullet lists for requirement enumerations and numbered lists for process flows or layered architectures.

2. **Traceability**
   - Reference relevant comprehensive plan sections when making decisions (e.g., "Plan §2: System Architecture").
   - Cross-link related documents via relative paths at the end of sections when actionable follow-up exists.

3. **Versioning & Updates**
   - Append an "Update History" section to major documents once iterative revisions begin; include date, author, and summary.
   - When superseding guidance, retain prior decisions under a "Deprecated" subheading rather than deleting outright.

4. **Accessibility & External Sharing**
   - Favor descriptive alt-text for embedded diagrams or screenshots and store binary assets in `docs/assets/` with readable filenames.
   - Ensure tables include header rows and avoid color-only distinctions to align with Step 1 accessibility commitments.

5. **Tooling Notes**
   - Maintain diagram source files in shared cloud workspaces (Figma/FigJam) with export references back to `docs/assets/`; run `poetry run python tools/publish_diagrams.py --renderer mmdc --expected-version 10.9.0` to regenerate SVGs with the pinned CLI enforced in CI.
   - Capture benchmarking or testing outputs in dedicated subdirectories (e.g., `docs/qa/`) when we reach Steps 9–10. Use `poetry run python prototypes/audio_engine_skeleton.py --stress-plan docs/qa/stress_plan.json --export-json docs/qa/artifacts/stress_results.json --export-csv docs/qa/artifacts/stress_results.csv` to refresh latency tables, then run `poetry run python tools/compare_stress_results.py --baseline-json docs/qa/artifacts/baseline/stress_results.json --candidate-json docs/qa/artifacts/stress_results.json --baseline-csv docs/qa/artifacts/baseline/stress_results.csv --candidate-csv docs/qa/artifacts/stress_results.csv --history-json docs/qa/artifacts/history/stress_trend_history.json --history-markdown docs/qa/artifacts/history/stress_trend_history.md --summary-path docs/qa/artifacts/history/latest_trend_summary.md` to confirm metrics remain within tolerance and append a traceable history entry. Mixer-specific trends now share the same philosophy; see `docs/qa/artifacts/mixer_trends/README.md` for the CI command that writes JSON/Markdown summaries next to the audio reference pack.
   - When validating remote credentials, execute `poetry run python tools/run_s3_smoke_test.py --identifier smoke-check --summary-markdown docs/qa/s3_validation/smoke_check.md --summary-json docs/qa/s3_validation/smoke_check.json --bootstrap-bucket` with real credentials. Supply `--env-file .env.staging` so non-developers can copy/paste secrets without modifying shell profiles. For local drills use `--use-moto` to run against the in-memory emulator without touching production buckets.
   - To avoid re-downloading Chromium on every diagram export, supply `--puppeteer-cache .cache/puppeteer` (or another shared location) when running `tools/publish_diagrams.py`. The cache path is respected both locally and in CI thanks to the `PUPPETEER_CACHE_DIR` support wired into the helper.

Following these conventions keeps the documentation system coherent as we progress through the roadmap.

## CI & Tooling Runbook
These commands reflect the expectations enforced by the GitHub Actions pipeline and should be executed via Poetry:

1. `poetry install --sync` – Install all project dependencies, including optional audio tooling such as NumPy.
2. `poetry run ruff check` – Lint the codebase to satisfy style and static analysis policies outlined in Plan §9.
3. `poetry run mypy` – Type-check the `src/` and `prototypes/` packages.
4. `poetry run pytest` – Execute the full test suite. Golden render fixtures live under `tests/fixtures/`; use `pytest -k audio_engine` to focus on the stress harness when iterating on DSP modules.
5. `poetry run python prototypes/audio_engine_skeleton.py --stress-plan docs/qa/stress_plan.json --export-json docs/qa/artifacts/stress_results.json --export-csv docs/qa/artifacts/stress_results.csv` – Regenerate benchmark artifacts captured by CI for manual inspection.
6. `poetry run python tools/publish_diagrams.py --renderer mmdc --expected-version 10.9.0` – Rebuild Mermaid diagrams after editing `.mmd` sources using the pinned CLI release enforced by CI.
7. `poetry run python tools/compare_stress_results.py --baseline-json docs/qa/artifacts/baseline/stress_results.json --candidate-json docs/qa/artifacts/stress_results.json --baseline-csv docs/qa/artifacts/baseline/stress_results.csv --candidate-csv docs/qa/artifacts/stress_results.csv` – Validate stress harness exports against the committed baseline before pushing instrumentation updates.
8. `poetry run python tools/run_s3_smoke_test.py --identifier local-smoke --summary-markdown docs/qa/s3_validation/local_smoke.md --summary-json docs/qa/s3_validation/local_smoke.json` – Exercise the environment-configured S3 repository and record latency notes alongside QA artifacts.
9. `poetry run python tools/mixer_trend_ci.py --baseline-json docs/qa/artifacts/mixer_trends/baseline/mixer_trend_baseline.json --output-json docs/qa/artifacts/mixer_trends/latest_summary.json --output-markdown docs/qa/artifacts/mixer_trends/latest_summary.md --history-json docs/qa/artifacts/mixer_trends/history/mixer_trend_history.json --history-markdown docs/qa/artifacts/mixer_trends/history/mixer_trend_history.md --demo-automation` – Capture mixer trend deltas using the committed baseline and publish Markdown/JSON artifacts alongside the sampler manifest.

Record noteworthy benchmark outputs or failure diagnostics under `docs/qa/` to share with the broader engineering team.

## Update History
- 2025-11-02 – Added architecture diagram assets directory details and Step 2 references.
- 2025-11-05 – Documented `src/domain/`, Poetry configuration, and CI workflow additions from Step 2 tooling tasks.
- 2025-11-09 – Added repository abstractions, stress-test automation references, and expanded diagram index for Step 2 instrumentation work.
- 2025-11-12 – Captured CI runbook commands and referenced golden audio fixtures plus mock cloud repository guidance.
- 2025-11-15 – Added QA directory reference and benchmark documentation pointers tied to Step 2 instrumentation.
- 2025-11-16 – Documented automated stress harness exports and the Mermaid publishing pipeline utility.
- 2025-11-18 – Added stress harness trend comparison workflow, S3 smoke test utility, and Mermaid CLI version pinning guidance.
- 2025-11-19 – Documented the Step 3 audio engine kickoff, .env-based staging smoke test workflow, and Puppeteer cache reuse in CI.
- 2025-11-24 – Added mixer trend artifact references, S3 sampler manifest pointers, and the `mixer_trend_ci.py` runbook entry for CI instrumentation.
