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

GRADE_COLORS: Mapping[str, str] = {
    "bold": "#b71c1c",
    "balanced": "#388e3c",
    "soft": "#1e88e5",
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


__all__ = ["build_loudness_widget", "show_loudness_widget"]
