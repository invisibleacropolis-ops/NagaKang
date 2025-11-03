# Documentation Structure & Style Guide

This index formalizes how project documentation is organized so contributors can navigate materials quickly while expanding on the comprehensive development plan.

## Directory Overview
- `docs/step1_product_requirements.md` – Vision, personas, requirements, PRD summary.
- `docs/step1_ux_flows.md` – Narrative UX flows, gesture considerations, and wireframe roadmap.
- `docs/step1_backlog_user_stories.md` – Prioritized user stories with acceptance criteria.
- `docs/step2_architecture_tech_choices.md` – (New) System architecture decisions, technology evaluations, and integration plans.
- `docs/assets/` – Source-controlled Mermaid files for architecture diagrams (component, sequence, failure-mode, controller routing) referenced by `docs/step2_architecture_diagrams.md`, plus future exported visuals.
- `docs/qa/` – Benchmark and QA artifacts (e.g., audio stress harness tables) that evidence progress on Plan §9 instrumentation goals. The canonical stress harness configuration lives in `docs/qa/stress_plan.json` with exported summaries under `docs/qa/artifacts/`.
- `tools/publish_diagrams.py` – Scriptable Mermaid-to-SVG pipeline used to keep `docs/step2_architecture_diagrams.md` in sync with rendered assets.
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
   - Maintain diagram source files in shared cloud workspaces (Figma/FigJam) with export references back to `docs/assets/`; run `poetry run python tools/publish_diagrams.py --renderer mmdc` to regenerate SVGs.
   - Capture benchmarking or testing outputs in dedicated subdirectories (e.g., `docs/qa/`) when we reach Steps 9–10. Use `python prototypes/audio_engine_skeleton.py --stress-plan docs/qa/stress_plan.json ...` to refresh latency tables and attach CSV/JSON artifacts to CI runs.

Following these conventions keeps the documentation system coherent as we progress through the roadmap.

## CI & Tooling Runbook
These commands reflect the expectations enforced by the GitHub Actions pipeline and should be executed via Poetry:

1. `poetry install --sync` – Install all project dependencies, including optional audio tooling such as NumPy.
2. `poetry run ruff check` – Lint the codebase to satisfy style and static analysis policies outlined in Plan §9.
3. `poetry run mypy` – Type-check the `src/` and `prototypes/` packages.
4. `poetry run pytest` – Execute the full test suite. Golden render fixtures live under `tests/fixtures/`; use `pytest -k audio_engine` to focus on the stress harness when iterating on DSP modules.

Record noteworthy benchmark outputs or failure diagnostics under `docs/qa/` to share with the broader engineering team.

## Update History
- 2025-11-02 – Added architecture diagram assets directory details and Step 2 references.
- 2025-11-05 – Documented `src/domain/`, Poetry configuration, and CI workflow additions from Step 2 tooling tasks.
- 2025-11-09 – Added repository abstractions, stress-test automation references, and expanded diagram index for Step 2 instrumentation work.
- 2025-11-12 – Captured CI runbook commands and referenced golden audio fixtures plus mock cloud repository guidance.
- 2025-11-15 – Added QA directory reference and benchmark documentation pointers tied to Step 2 instrumentation.
- 2025-11-16 – Documented automated stress harness exports and the Mermaid publishing pipeline utility.
