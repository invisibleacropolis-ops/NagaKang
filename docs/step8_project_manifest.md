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

## Next Steps
1. Implement a dedicated `ProjectExportService` that serializes patterns,
   mixer snapshots, and manifest metadata in a single CLI command for QA.
2. Extend the GUI shell with the autosave timer hooks described above, surfacing
   recovery prompts through the tutorial/transport column.
3. Prototype the inverse (`ProjectImportService`) so tester feedback sessions
   can load zipped bundles plus manifests without editing JSON manually.

## Update History
- 2025-11-26 – Initial schema, helper references, and autosave expectations for
  the Step 8 kickoff.
