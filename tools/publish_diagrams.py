"""Utilities for exporting Mermaid diagrams to embeddable assets."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence


class DiagramPublishError(RuntimeError):
    """Raised when the diagram publishing pipeline encounters an error."""


def find_mermaid_sources(source_dir: Path) -> List[Path]:
    """Return all Mermaid source files beneath ``source_dir``."""

    return sorted(source_dir.rglob("*.mmd"))


def publish_diagrams(
    source_dir: Path,
    output_dir: Path | None,
    renderer: Sequence[str],
    *,
    dry_run: bool = False,
) -> List[Path]:
    """Render Mermaid diagrams to SVG using an external renderer command."""

    sources = find_mermaid_sources(source_dir)
    outputs: List[Path] = []
    for source in sources:
        destination_dir = output_dir or source.parent
        destination = destination_dir / f"{source.stem}.svg"
        outputs.append(destination)
        if dry_run:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [*renderer, "-i", str(source), "-o", str(destination)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as exc:  # pragma: no cover - depends on environment
            raise DiagramPublishError(f"Renderer command not found: {renderer[0]}") from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else ""
            raise DiagramPublishError(
                f"Renderer command {' '.join(renderer)} failed for {source}: {stderr}"
            ) from exc
    return outputs


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Mermaid diagrams to SVG assets")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("docs/assets"),
        help="Directory containing Mermaid .mmd sources",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional directory for rendered assets (defaults to alongside sources)",
    )
    parser.add_argument(
        "--renderer",
        nargs="+",
        default=["mmdc"],
        help="Renderer command to execute (defaults to Mermaid CLI 'mmdc')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which files would be generated without invoking the renderer",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    outputs = publish_diagrams(
        args.source,
        args.output,
        args.renderer,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        for path in outputs:
            print(path)


if __name__ == "__main__":  # pragma: no cover - manual execution utility
    main()
