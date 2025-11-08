# Step 3 Tracker UI Mock – Loudness Dashboard Embedding

This guide mirrors the rehearsal notebook widget so the forthcoming tracker UI
mock can reuse the same loudness affordances without waiting for the full Kivy
implementation. Apply the palette and spacing tokens here when sketching the
Step 3 dashboard views.

## Dynamic grade palette

| Grade    | Hex     | Usage notes                                                  |
| -------- | ------- | ------------------------------------------------------------ |
| Bold     | `#b71c1c` | Highlight choruses or big drops averaging louder than −10 dBFS. |
| Balanced | `#388e3c` | Default target range (−10 ➜ −18 dBFS) for verses and bridges. |
| Soft     | `#1e88e5` | Verses or intros that need reinforcement (< −18 dBFS).         |
| Neutral  | `#424242` | Fallback when no grade is available (missing data, silence). |

Colour tokens match `docs/step3_tracker_notebook_widget.py::GRADE_COLORS`. Keep
these values in a shared theming module so the notebook widget, tracker mock,
and future desktop UI remain visually in sync.

## Badge styling

- Background: grade colour from the table above.
- Text: `#FFFFFF`, bold, 13 px, uppercase.
- Padding: `4px 8px`; border radius: `8px`.
- Copy stack: `"{rms_text} · {lufs_text} · {grade.title()}"` as seen in the
  notebook widget HTML renderer.

## Layout skeleton

```
┌───────────────────────────────────────────────────────────┐
│ Tracker Loudness Overview                                 │
├────────────┬──────────────────────────────────────────────┤
│ Beats 0–1  │ [-14.0/-13.8 dBFS · -13.0 LUFS · Balanced]    │
│ Beats 1–2  │ [-20.1/-19.9 dBFS · -21.5 LUFS · Soft]        │
│ Beats 2–3  │ [-10.3/-10.0 dBFS · -11.2 LUFS · Bold]        │
└────────────┴──────────────────────────────────────────────┘
```

- Header uses `600` weight text with a 6 px bottom margin.
- Row gap: 4 px; row padding: 2 px top/bottom.
- Column widths: 160 px label column, flexible badge column.
- Outer container border: `1px solid #d1d1d1`; padding: `8px`.

### Kivy snippet

Embed the palette directly into the mock `kv` file:

```kv
<LoudnessBadge@BoxLayout>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(32)
    spacing: dp(8)
    Label:
        text: root.label
        size_hint_x: None
        width: dp(160)
        bold: True
    Label:
        text: root.badge_text
        color: 1, 1, 1, 1
        canvas.before:
            Color:
                rgba: root.grade_color
            RoundedRectangle:
                pos: self.pos
                size: self.size
                radius: [dp(8)]
```

- Drive `grade_color` from the shared palette in
  `docs/step3_tracker_notebook_widget.py::GRADE_COLORS`.
- Pair the loudness column with a second `BoxLayout` that lists smoothing badges
  using the teal/brown colours defined in
  `docs/step3_tracker_notebook_widget.py::SMOOTHING_COLORS`.

## Implementation checklist

1. Mirror the notebook helper by mapping `PatternPerformanceBridge.tracker_loudness_rows`
   directly into the mock.
2. Honour the `dynamic_grade` key even when rows fall outside Bold/Balanced/Soft
   (default to Neutral colour).
3. Surface the same RMS/LUFS strings to keep rehearsal screenshots and UI mocks
   interchangeable for documentation.
4. Capture annotated screenshots once the mock is wired so the asset pack can
   ship alongside the Windows installer preview. Store the Windows HiDPI capture
   under `docs/assets/ui/windows_hidpi_tracker_dashboard.png` for the release
   playbook.
