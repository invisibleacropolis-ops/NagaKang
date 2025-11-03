"""Utilities for exporting Mermaid diagrams to embeddable assets."""
from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence


class DiagramPublishError(RuntimeError):
    """Raised when the diagram publishing pipeline encounters an error."""


DEFAULT_MERMAID_VERSION = "10.9.0"

def find_mermaid_sources(source_dir: Path) -> List[Path]:
    """Return all Mermaid source files beneath ``source_dir``."""

    return sorted(source_dir.rglob("*.mmd"))


def _verify_renderer_version(renderer: Sequence[str], expected_version: str) -> str:
    command = [renderer[0], "--version"]
    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - depends on environment
        raise DiagramPublishError(f"Renderer command not found: {renderer[0]}") from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover - defensive guard
        stderr = exc.stderr or ""
        raise DiagramPublishError(
            f"Failed to query renderer version using {' '.join(command)}: {stderr}"
        ) from exc

    version_output = (result.stdout or result.stderr or "").strip()
    if expected_version not in version_output:
        raise DiagramPublishError(
            f"Renderer version mismatch: expected {expected_version} but received '{version_output}'"
        )
    return version_output


def publish_diagrams(
    source_dir: Path,
    output_dir: Path | None,
    renderer: Sequence[str],
    *,
    dry_run: bool = False,
    expected_version: str | None = None,
    puppeteer_cache: Path | None = None,
) -> List[Path]:
    """Render Mermaid diagrams to SVG using an external renderer command."""

    sources = find_mermaid_sources(source_dir)
    outputs: List[Path] = []
    if not dry_run and expected_version:
        _verify_renderer_version(renderer, expected_version)
    for source in sources:
        destination_dir = output_dir or source.parent
        destination = destination_dir / f"{source.stem}.svg"
        outputs.append(destination)
        if dry_run:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        command = [*renderer, "-i", str(source), "-o", str(destination)]
        env = None
        if puppeteer_cache is not None:
            cache_path = puppeteer_cache
            cache_path.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.setdefault("PUPPETEER_CACHE_DIR", str(cache_path))
            env.setdefault("PUPPETEER_DOWNLOAD_PATH", str(cache_path))
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
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
    parser.add_argument(
        "--expected-version",
        type=str,
        default=DEFAULT_MERMAID_VERSION,
        help="Required Mermaid CLI version (set to empty string to skip)",
    )
    parser.add_argument(
        "--skip-version-check",
        action="store_true",
        help="Disable renderer version validation (not recommended outside experiments)",
    )
    parser.add_argument(
        "--puppeteer-cache",
        type=Path,
        default=None,
        help="Directory for caching the Puppeteer Chromium download used by Mermaid CLI",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> None:
    args = parse_args(argv)
    expected_version: str | None
    if args.skip_version_check or not args.expected_version:
        expected_version = None
    else:
        expected_version = args.expected_version
    outputs = publish_diagrams(
        args.source,
        args.output,
        args.renderer,
        dry_run=args.dry_run,
        expected_version=expected_version,
        puppeteer_cache=args.puppeteer_cache,
    )
    if args.dry_run:
        for path in outputs:
            print(path)


if __name__ == "__main__":  # pragma: no cover - manual execution utility
    main()
