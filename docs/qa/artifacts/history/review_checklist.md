# Stress Harness Baseline Review Checklist

Use this template during scheduled trend history reviews or any ad-hoc
investigation triggered by CI regressions.

## Review Metadata
- **Date:**
- **Participants:**
- **Context / Trigger:** (e.g., weekly cadence, post-merge follow-up, CI failure URL)

## Pre-Review Steps
- [ ] Pulled latest `main` and synced committed baselines.
- [ ] Downloaded most recent CI artifacts for the stress harness comparison job.
- [ ] Generated fresh local exports (if applicable) using the command in
      `docs/qa/artifacts/README.md`.

## Evaluation
- [ ] Compared candidate exports against the baseline with history logging enabled.
- [ ] Reviewed `stress_trend_history.md` entries added since the last session.
- [ ] Confirmed default tolerances (`abs_tol=1e-4`, `rel_tol=5e-3`) or documented overrides below.
- [ ] Verified metrics continue to satisfy Plan §9 latency/underrun targets.

### Notes on Deviations / Tolerance Adjustments
```
```

## Outcomes
- [ ] Baseline unchanged.
- [ ] Baseline updated (attach PR/commit link and summary).
- [ ] Follow-up issue filed for lingering regressions (link below).

### Links & References
- Trend history entry:
- Profiling / analysis docs:
- Follow-up issue:

## Next Actions
- [ ] Update `stress_trend_history.md` with review summary.
- [ ] Notify QA/Performance channel if regressions remain unresolved.

---
Retain completed checklists in this directory alongside history artifacts so the
team can audit cadence compliance and capture institutional knowledge.
