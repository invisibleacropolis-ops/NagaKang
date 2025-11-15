# Mixer Trend Artifacts

These artifacts pair the mixer diagnostics CLI with CI-friendly metadata so QA
leads can trace Step 6/7 mixer health without spelunking through local logs.
`tools/mixer_trend_ci.py` runs inside CI with the following command and stores
its outputs beside the audio renders called out in `docs/assets/audio`:

```
poetry run python tools/mixer_trend_ci.py \
    --baseline-json docs/qa/artifacts/mixer_trends/baseline/mixer_trend_baseline.json \
    --output-json docs/qa/artifacts/mixer_trends/latest_summary.json \
    --output-markdown docs/qa/artifacts/mixer_trends/latest_summary.md \
    --history-json docs/qa/artifacts/mixer_trends/history/mixer_trend_history.json \
    --history-markdown docs/qa/artifacts/mixer_trends/history/mixer_trend_history.md \
    --sampler-manifest docs/assets/audio/sampler_s3_manifest.json \
    --label ci-nightly --demo-automation
```

- `latest_summary.json` and `latest_summary.md` are published as workflow
  artifacts so UI/audio engineers can diff levels without downloading WAVs.
  Their SHA-256 digests are recorded in the Markdown summary and history entries
  so QA can prove parity between CI downloads and mirrored archives. The
  `sampler_s3_manifest.json` digest is logged alongside those entries so mixer
  metrics and the Step 3/4 reference renders can be matched during investigations
  without re-downloading the audio pack.
- The `baseline/` snapshot is checked in and only refreshed after confirming the
  deltas are intentional. Running the command with `--write-baseline` will update
  the file locally.
- The history JSON/Markdown logs give QA an append-only paper trail that can be
  pasted directly into release notes. Entries now capture the sampler manifest
  digest, asset count, and last-updated timestamp so renders and mixer metrics
  stay aligned.

When CI publishes the `latest_*` artifacts it also references the mixer trend
history (including artifact digests) in the job summary, linking back to this
directory for onboarding.
