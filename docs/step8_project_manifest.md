# Step 8 Project Manifest & Persistence Kickoff

This note opens Plan §8 (Project & Asset Management) by documenting the JSON
manifest schema, sampler import/export helpers, and the autosave expectations
that will guide subsequent persistence work. The deliverables in this document
are the final Step 7 prerequisites before sharing the Tracker/Mixer shell with
musician testers.

## Objectives Recap
- Close the remaining Step 7 verification by linking the GUI milestone to a
  documented manifest schema that outside engineers can consume while creating
  demo projects.
- Define a versioned project manifest that captures tracker patterns, mixer
  snapshots, and sampler assets with SHA-256 digests so QA can trace bundled
  files back to the canonical sampler manifest.
- Prototype import/export helpers that mirror the planned file-dialog filters
  and sampler asset transfer workflow.
- Record an autosave cadence plus crash-recovery strategy ahead of the Step 8
  persistence workstream.

## Manifest Schema Overview
The manifest lives beside exported project bundles as
`projects/<name>/project_manifest.json`. Each manifest is versioned so we can
introduce additive schema changes without breaking previously exported
projects.

```json
{
  "manifest_version": "1.0.0",
  "project": {
    "id": "demo-project",
    "name": "Demo Project",
    "bpm": 120.0,
    "swing": 0.1,
    "created_at": "2025-11-25T00:00:00+00:00",
    "updated_at": "2025-11-25T00:00:00+00:00"
  },
  "patterns": [
    {
      "pattern_id": "verse",
      "path": "patterns/verse.json",
      "sha256": "...",
      "length_steps": 64,
      "step_count": 40
    }
  ],
  "mixer_snapshots": [
    {
      "name": "Verse Snapshot",
      "path": "mixer/verse_snapshot.json",
      "sha256": "...",
      "snapshot_type": "master"
    }
  ],
  "sampler_assets": [
    {
      "asset_name": "choir_pad_soft.wav",
      "relative_path": "assets/choir_pad_soft.wav",
      "sha256": "...",
      "lufs_lu": -18.5,
      "source_uri": "s3://nagakang-audio-assets/..."
    }
  ]
}
```

### Implementation Reference
`src/domain/project_manifest.py` formalizes the schema above using Pydantic
models. `ProjectManifestBuilder` consumes a `domain.Project` instance and
collects pattern exports, mixer snapshots, and sampler assets (see
`PatternFileRecord`, `MixerSnapshotRecord`, and `SamplerAssetRecord`). Each
helper computes SHA-256 checksums by default so CI artifacts and QA exports can
point back to a traceable manifest entry.

Use `ProjectManifestBuilder.write(...)` to generate the JSON file alongside a
bundle. The builder automatically stores relative paths when a `base_path` is
provided, ensuring exported projects remain portable when copied between
machines.

## Import/Export Automation Hooks
`SamplerManifestIndex` loads the canonical sampler manifest located at
`docs/assets/audio/sampler_s3_manifest.json` and exposes two key helpers:

1. `copy_asset(...)` – Copies a user-selected file into the project bundle
   while validating the SHA-256 digest against the sampler manifest. The helper
   records LUFS metadata and the cloud URI/NAS path so QA can trace the
   original render. Pass `relative_to=<project_root>` to ensure the returned
   `SamplerAssetRecord` contains portable paths.
2. `dialog_filters()` – Generates the file-dialog filters surfaced to Kivy or
   desktop widgets. The helper inspects manifest suffixes so designers only see
   the relevant extensions (e.g., `*.wav`, `*.flac`).

`build_import_plan(...)` wraps the filter list plus a manifest asset count so
future GUI work can display contextual copy ("3 choir layers available") when
presenting the dialog to musicians.

### Project Export Service

`src/domain/project_export_service.py` collects patterns, mixer snapshots, and
sampler assets before serializing a manifest. The helper writes exported
patterns under `patterns/<pattern_id>.json`, copies mixer snapshots under
`mixer/`, mirrors sampler assets into `assets/`, and finally writes
`project_manifest.json` plus an optional `project.json`. The CLI
`tools/export_project_bundle.py` wraps the service so QA can run:

```
poetry run python tools/export_project_bundle.py \
  --project-file projects/demo.json \
  --bundle-root dist/projects/demo_bundle \
  --mixer-snapshot "Verse=exports/verse_snapshot.json,master" \
  --asset "choir_pad_soft.wav=imports/choir_pad_soft.wav"
```

The CLI enforces sampler-manifest parity before copying assets so exported
bundles inherit the LUFS/checksum metadata already maintained in
`docs/assets/audio/sampler_s3_manifest.json`.

### Project Import Service & CLI

`src/domain/project_import_service.py` performs the inverse operation. The
helper validates every manifest entry (patterns, mixer snapshots, sampler
assets), verifies SHA-256 digests, optionally copies the bundle into a new
working directory, and exposes a `Project` instance when `project.json` is
present.

`tools/import_project_bundle.py` wraps the service for QA drills:

```
poetry run python tools/import_project_bundle.py \
  --bundle-root dist/projects/demo_bundle \
  --destination-root projects/imported_demo
```

The CLI prints a JSON summary containing the manifest digest, asset names, and
file counts so testers can paste the output directly into rehearsal logs when
confirming bundle provenance.

### Autosave Stress Harness

`tools/autosave_stress_harness.py` simulates sustained preview batches against
`TrackerMixerRoot`, exercising the autosave cadence introduced earlier in this
document. The harness accepts manifest metadata, increments a synthetic time
source, and emits checkpoint/pruning statistics that QA can store next to their
bundle notes:

```
poetry run python tools/autosave_stress_harness.py \
  --project-id demo \
  --autosave-dir ./tmp/.autosave \
  --iterations 12 \
  --interval-seconds 0.5 \
  --manifest dist/projects/demo_bundle/project_manifest.json \
  --asset-count 5
```

The summary includes the latest recovery prompt so GUI engineers can confirm the
manifest checksum/asset count surfaced to musicians matches the autosave JSON
payload.

### QA Hand-off Pack

To keep remote musicians in sync with today’s workflow, pair exported bundles
with a rehearsal-ready README containing:

1. The CLI commands used to generate/export/import the bundle.
2. Autosave stress harness output (checkpoints written, pruned count).
3. A LUFS/canonical hash table sourced from
   `docs/assets/audio/sampler_s3_manifest.json`:

| Asset | LUFS (LU) | Peak (dBFS) | Manifest SHA-256 |
| --- | --- | --- | --- |
| `choir_pad_soft.wav` | -20.6 | -3.1 | `a96353c5bdcc504c` |
| `strings_vs_choir_blend.wav` | -16.4 | -1.7 | `dbd0c7432f7d5f8c` |
| `gospel_stab_short.wav` | -15.4 | -4.2 | `eb89270f71c7d2f5` |

4. A checklist reminding testers to:
   - Run `tools/import_project_bundle.py` and archive the JSON summary.
   - Launch the tracker shell, confirm the autosave recovery prompt references
     the manifest digest, and capture a screenshot if QA requires visual proof.
   - Upload `.autosave/<project_id>` plus the exported manifest copy when filing
     crash reports so engineering can replay the session verbatim.

## Autosave & Recovery Outline
To keep Tracker/Mixer sessions resilient during the Step 8 workstream we will:

- **Autosave cadence** – Persist a rolling project snapshot every 90 seconds or
  whenever the musician commits a transport/preview mutation. Autosaves live
  under `.autosave/<project_id>/<timestamp>.json` relative to the project
  bundle.
- **Crash checkpoints** – Record a checkpoint immediately before an import
  operation mutates the manifest (e.g., before copying a new sampler asset).
  The checkpoint contains the previous manifest plus any unsaved tracker
  mutations so QA can reproduce crashes when testing import flows.
- **Backup naming** – Autosave filenames follow
  `<YYYYMMDD>-<HHMMSS>-<mutation_id>.json` so we can line them up with the
  tracker/mixer logs collected during Step 7. The oldest file beyond the last
  five autosaves is pruned automatically, keeping disk usage predictable for
  testers on resource-constrained tablets.
- **Recovery UX** – On launch, the GUI shell inspects `.autosave/` and surfaces
  the freshest autosave entry, including the manifest checksum plus the list of
  sampler assets recorded at the time of the crash.

These expectations now live beside the Step 7 GUI contracts so persistence
contributors can begin wiring autosave timers and crash recovery UI.

### GUI Import Dialog & Autosave Integration

`TrackerMixerRoot.configure_sampler_manifest(...)` now loads
`SamplerManifestIndex` instances, stores the dialog filters produced by
`build_import_plan(...)`, and surfaces the filter list plus asset counts through
`TrackerPanelState.import_dialog_filters` and `import_asset_count`. The transport
widgets receive this state automatically so KV designers can reference the
available choir layers when presenting the import dialog.

`TrackerMixerRoot.enable_autosave(...)` wires the documented 90-second cadence by
writing `.autosave/<project_id>/<timestamp>-layout.json` snapshots that describe
the last preview summary, tutorial tip count, and manifest asset availability.
When a manifest path is provided the helper copies it alongside each autosave so
crash recovery flows preserve the exact bundle metadata that testers need to
restore projects. The transport/tutorial column now displays the most recent
autosave prompt ("Autosaved demo at 20251127-153000") via
`TransportControlsWidget.recovery_prompt`.

`TrackerMixerRoot.import_project_bundle(...)` wraps
:class:`domain.project_import_service.ProjectImportService`, copying manifests,
patterns, and sampler assets into a destination directory before surfacing the
result inside `TrackerPanelState`. The tracker state now exposes
`import_manifest_sha256`, `import_bundle_root`, and
`import_sampler_asset_names`, letting GUI bindings display digest/asset details
without querying the CLI JSON directly. `TransportControlsWidget` mirrors this
information via the new `import_summary` property and automatically appends it
to the autosave prompt so QA logs record both the checkpoint timestamp and the
bundle digest that was loaded moments before a crash drill.

`docs/qa/autosave/README.md` captures a real `tools/autosave_stress_harness.py`
run against the choir demo manifest. The JSON summary exported by the harness
(`docs/qa/autosave/runs/choir_demo_summary.json`) sits beside the generated
`.autosave/choir_demo/` checkpoints so QA leads can download one folder and
verify pruned-count telemetry against the layout/manifest copies referenced by
the transport prompt.

## Next Steps
1. Implement a dedicated `ProjectExportService` that serializes patterns,
   mixer snapshots, and manifest metadata in a single CLI command for QA.
2. Extend the GUI shell with the autosave timer hooks described above, surfacing
   recovery prompts through the tutorial/transport column.
3. Prototype the inverse (`ProjectImportService`) so tester feedback sessions
   can load zipped bundles plus manifests without editing JSON manually.

## Update History
- 2025-11-28 – Added the import CLI/service details, autosave stress harness,
  and QA hand-off checklist for musician testing.
- 2025-11-27 – Added export service/CLI, import-plan GUI bindings, and autosave
  wiring for the musician testing hand-off.
- 2025-11-26 – Initial schema, helper references, and autosave expectations for
  the Step 8 kickoff.
