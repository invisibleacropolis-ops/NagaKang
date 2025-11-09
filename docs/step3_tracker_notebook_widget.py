"""Notebook helper that renders tracker loudness rows for musicians."""

from __future__ import annotations

from typing import Iterable, Mapping

try:  # pragma: no cover - optional dependency for notebooks
    import ipywidgets as widgets
except ImportError:  # pragma: no cover - optional dependency
    widgets = None  # type: ignore

try:  # pragma: no cover - optional dependency for notebooks
    from IPython.display import display
except ImportError:  # pragma: no cover - optional dependency
    display = None  # type: ignore

try:  # pragma: no cover - optional dependency for waveform caching
    import numpy as _np
except ImportError:  # pragma: no cover - numpy is optional in notebooks
    _np = None  # type: ignore

from collections import OrderedDict
from typing import Iterable, Iterator, Mapping, MutableMapping

if False:  # pragma: no cover - imported for type checking only
    from tracker.playback_worker import PreviewRender


class PreviewRenderCache:
    """Cache lightweight preview summaries for tracker notebook dashboards."""

    def __init__(
        self,
        *,
        max_entries: int = 24,
        waveform_points: int = 64,
    ) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        if waveform_points <= 0:
            raise ValueError("waveform_points must be positive")
        self._max_entries = int(max_entries)
        self._waveform_points = int(waveform_points)
        self._cache: "OrderedDict[str, MutableMapping[str, object]]" = OrderedDict()

    def __len__(self) -> int:  # pragma: no cover - trivial container helper
        return len(self._cache)

    def __iter__(self) -> Iterator[Mapping[str, object]]:  # pragma: no cover
        return iter(self.rows())

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def waveform_points(self) -> int:
        return self._waveform_points

    def add_preview(self, preview: "PreviewRender") -> Mapping[str, object]:
        """Insert a preview into the cache, trimming old entries as needed."""

        key = self._preview_key(preview)
        summary = preview.to_summary()
        label = summary.get("mutation_id") or f"#{summary.get('index')}"
        summary["label"] = label
        summary["waveform_preview"] = self._downsample_waveform(preview.window_buffer)
        summary["window_seconds"] = float(summary.get("window_seconds", 0.0))
        summary["peak_amplitude"] = float(summary.get("peak_amplitude", 0.0))
        summary["rms_amplitude"] = float(summary.get("rms_amplitude", 0.0))
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = summary
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        return summary

    def rows(self) -> list[Mapping[str, object]]:
        """Return cached preview summaries in insertion order."""

        return [dict(row) for row in self._cache.values()]

    def clear(self) -> None:
        """Clear all cached preview entries."""

        self._cache.clear()

    def _preview_key(self, preview: "PreviewRender") -> str:
        request = preview.request
        return f"{request.mutation_id}:{request.index}:{preview.start_frame}:{preview.end_frame}"

    def _downsample_waveform(self, buffer) -> list[float]:  # pragma: no cover - small helper
        if _np is None:
            return []
        array = _np.asarray(buffer)
        if array.size == 0:
            return []
        if array.ndim > 1:
            array = array.mean(axis=1)
        total = array.size
        if total <= self._waveform_points:
            return array.astype(float).tolist()
        positions = _np.linspace(0, total - 1, num=self._waveform_points)
        downsampled = _np.interp(positions, _np.arange(total), array)
        return downsampled.astype(float).tolist()

GRADE_COLORS: Mapping[str, str] = {
    "bold": "#b71c1c",
    "balanced": "#388e3c",
    "soft": "#1e88e5",
}

SMOOTHING_COLORS: Mapping[str, str] = {
    "applied": "#006064",
    "pending": "#5d4037",
}


def _format_row_text(row: Mapping[str, object]) -> str:
    return (
        f"{row['label']}: RMS {row['rms_text']} | {row['lufs_text']} "
        f"→ dynamics {row['dynamic_grade']}"
    )


def _fallback_render(rows: Iterable[Mapping[str, object]]) -> str:
    lines = [
        "Tracker Loudness Overview",
        "---------------------------",
    ]
    for row in rows:
        lines.append(_format_row_text(row))
    return "\n".join(lines)


def build_loudness_widget(rows: Iterable[Mapping[str, object]]):
    """Return an ipywidget visualising tracker loudness, or text fallback."""

    rows = list(rows)
    if widgets is None:
        return _fallback_render(rows)

    header = widgets.HTML(
        value="<b>Tracker Loudness Overview</b>",
        layout=widgets.Layout(margin="0 0 6px 0"),
    )
    row_widgets = []
    for row in rows:
        grade = str(row.get("dynamic_grade", "balanced"))
        color = GRADE_COLORS.get(grade, "#424242")
        label = widgets.HTML(
            value=f"<span style='font-weight:600'>{row['label']}</span>",
            layout=widgets.Layout(width="160px"),
        )
        dynamics = widgets.HTML(
            value=(
                f"<div style='background:{color};color:white;padding:4px 8px;border-radius:4px;'>"
                f"{row['rms_text']} · {row['lufs_text']} · {grade.title()}"
                "</div>"
            ),
            layout=widgets.Layout(flex="1"),
        )
        row_widgets.append(
            widgets.HBox(
                [label, dynamics],
                layout=widgets.Layout(margin="2px 0"),
            )
        )
    container = widgets.VBox([header, *row_widgets])
    container.layout.border = "1px solid #d1d1d1"
    container.layout.padding = "8px"
    container.layout.width = "100%"
    return container


def show_loudness_widget(rows: Iterable[Mapping[str, object]]) -> None:
    """Display the loudness widget in notebooks, falling back to text."""

    widget = build_loudness_widget(rows)
    if widgets is not None and display is not None:
        display(widget)
    else:
        print(widget)


def _format_smoothing_row_text(row: Mapping[str, object]) -> str:
    beat = row.get("beat", 0.0)
    identifier = row.get("identifier") or row.get("event_id")
    label = identifier or row.get("label", "")
    strategy = row.get("strategy", "none")
    segment_total = int(row.get("segment_total") or row.get("segments") or 0)
    breakdown = row.get("segment_breakdown")
    if isinstance(breakdown, Mapping) and breakdown:
        segment_text = ", ".join(f"{name}={value}" for name, value in breakdown.items())
    else:
        segment_text = str(segment_total)
    state = "applied" if row.get("applied") else "pending"
    event_index = row.get("event_index")
    index_suffix = f" · #{event_index}" if event_index is not None else ""
    return (
        f"{label} @ {beat:.2f} beats → {strategy} ({segment_total} segments [{segment_text}], {state}{index_suffix})"
    )


def _fallback_render_smoothing(rows: Iterable[Mapping[str, object]]) -> str:
    lines = [
        "Automation Smoothing Overview",
        "-------------------------------",
    ]
    for row in rows:
        lines.append(_format_smoothing_row_text(row))
    return "\n".join(lines)


def _format_preview_render_row(row: Mapping[str, object]) -> str:
    label = row.get("label") or row.get("mutation_id") or f"#{row.get('index')}"
    start = float(row.get("start_beat", 0.0))
    duration = float(row.get("duration_beats", 0.0))
    end = start + duration
    peak = float(row.get("peak_amplitude", 0.0))
    rms = float(row.get("rms_amplitude", 0.0))
    seconds = float(row.get("window_seconds", 0.0))
    return (
        f"{label} · beats {start:.2f}–{end:.2f} ({duration:.2f} span) · "
        f"{seconds:.3f}s window · peak {peak:.3f} · rms {rms:.3f}"
    )


def _fallback_render_previews(rows: Iterable[Mapping[str, object]]) -> str:
    lines = [
        "Preview Render Overview",
        "------------------------",
    ]
    for row in rows:
        lines.append(_format_preview_render_row(row))
    return "\n".join(lines)


def build_preview_render_widget(rows: Iterable[Mapping[str, object]]):
    """Render cached preview slices for notebook dashboards."""

    rows = list(rows)
    if not rows:
        return "No preview renders captured yet."
    if widgets is None:
        return _fallback_render_previews(rows)

    header = widgets.HTML(
        value="<b>Preview Render Overview</b>",
        layout=widgets.Layout(margin="12px 0 6px 0"),
    )
    entries = []
    for row in rows:
        waveform = row.get("waveform_preview")
        if isinstance(waveform, list) and waveform:
            waveform_text = ", ".join(f"{value:.2f}" for value in waveform[:8])
            waveform_html = f"<br/><small>Waveform sample: [{waveform_text}…]</small>"
        else:
            waveform_html = ""
        start = float(row.get("start_beat", 0.0))
        duration = float(row.get("duration_beats", 0.0))
        end = start + duration
        row_html = widgets.HTML(
            value=(
                f"<div style='padding:4px 8px;border-radius:4px;border:1px solid #d1d1d1;'>"
                f"<b>{row.get('label')}</b> · "
                f"Beats {start:.2f}–{end:.2f} ({duration:.2f} span)<br/>"
                f"{float(row.get('window_seconds', 0.0)):.3f}s window · peak {float(row.get('peak_amplitude', 0.0)):.3f} · "
                f"rms {float(row.get('rms_amplitude', 0.0)):.3f}"
                f"{waveform_html}"
                "</div>"
            ),
            layout=widgets.Layout(margin="2px 0"),
        )
        entries.append(row_html)
    return widgets.VBox([header, *entries], layout=widgets.Layout(width="100%"))


def build_automation_smoothing_widget(rows: Iterable[Mapping[str, object]]):
    rows = list(rows)
    if widgets is None:
        return _fallback_render_smoothing(rows)

    header = widgets.HTML(
        value="<b>Automation Smoothing Overview</b>",
        layout=widgets.Layout(margin="12px 0 6px 0"),
    )
    row_widgets = []
    for row in rows:
        state = "applied" if row.get("applied") else "pending"
        color = SMOOTHING_COLORS.get(state, "#424242")
        label_token = str(row.get("identifier", row.get("label", "")))
        segment_total = int(row.get("segment_total") or row.get("segments") or 0)
        breakdown = row.get("segment_breakdown")
        if isinstance(breakdown, Mapping) and breakdown:
            breakdown_text = ", ".join(f"{name}={value}" for name, value in breakdown.items())
            breakdown_html = f"<br/><small>Segments: {segment_total} total ({breakdown_text})</small>"
        else:
            breakdown_html = f"<br/><small>Segments: {segment_total}</small>"
        label = widgets.HTML(
            value=f"<span style='font-weight:600'>{label_token}</span>",
            layout=widgets.Layout(width="160px"),
        )
        details = widgets.HTML(
            value=(
                f"<div style='background:{color};color:white;padding:4px 8px;border-radius:4px;'>"
                f"Beat {float(row.get('beat', 0.0)):.2f} · "
                f"{str(row.get('strategy', 'none')).title()} · "
                f"{segment_total} segments"
                f"{breakdown_html}"
                "</div>"
            ),
            layout=widgets.Layout(flex="1"),
        )
        row_widgets.append(
            widgets.HBox(
                [label, details],
                layout=widgets.Layout(margin="2px 0"),
            )
        )
    container = widgets.VBox([header, *row_widgets])
    container.layout.border = "1px solid #d1d1d1"
    container.layout.padding = "8px"
    container.layout.width = "100%"
    return container


def build_tracker_dashboard(
    loudness_rows: Iterable[Mapping[str, object]],
    smoothing_rows: Iterable[Mapping[str, object]] | None = None,
    preview_rows: Iterable[Mapping[str, object]] | None = None,
):
    """Compose loudness and optional smoothing widgets into a dashboard."""

    loudness_rows = list(loudness_rows)
    smoothing_rows = list(smoothing_rows or [])
    preview_rows = list(preview_rows or [])
    if widgets is None:
        loudness = _fallback_render(loudness_rows)
        smoothing = _fallback_render_smoothing(smoothing_rows) if smoothing_rows else ""
        preview = _fallback_render_previews(preview_rows) if preview_rows else ""
        return "\n\n".join(filter(None, [loudness, smoothing, preview]))

    loudness_widget = build_loudness_widget(loudness_rows)
    sections = [loudness_widget]
    if smoothing_rows:
        smoothing_widget = build_automation_smoothing_widget(smoothing_rows)
        sections.append(smoothing_widget)
    if preview_rows:
        preview_widget = build_preview_render_widget(preview_rows)
        sections.append(preview_widget)
    return widgets.VBox(sections, layout=widgets.Layout(width="100%"))


def show_tracker_dashboard(
    loudness_rows: Iterable[Mapping[str, object]],
    smoothing_rows: Iterable[Mapping[str, object]] | None = None,
    preview_rows: Iterable[Mapping[str, object]] | None = None,
) -> None:
    widget = build_tracker_dashboard(loudness_rows, smoothing_rows, preview_rows)
    if widgets is not None and display is not None:
        display(widget)
    else:
        print(widget)


__all__ = [
    "PreviewRenderCache",
    "build_loudness_widget",
    "build_automation_smoothing_widget",
    "build_tracker_dashboard",
    "build_preview_render_widget",
    "show_loudness_widget",
    "show_tracker_dashboard",
]
