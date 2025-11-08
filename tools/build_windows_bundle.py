#!/usr/bin/env python3
"""Prototype PyInstaller driver for the Step 3 Windows installer."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENTRY = PROJECT_ROOT / "prototypes" / "audio_engine_skeleton.py"
DEFAULT_DIST = PROJECT_ROOT / "dist" / "nagakang"
DEFAULT_BUILD = PROJECT_ROOT / "build" / "pyinstaller"


def _format_data_argument(src: Path, dest: str) -> str:
    separator = ";" if os.name == "nt" else ":"
    return f"{src}{separator}{dest}"


def _run_pyinstaller(args: Sequence[str]) -> None:
    cli = shutil.which("pyinstaller")
    if cli:
        subprocess.run([cli, *args], check=True)
        return
    try:  # pragma: no cover - executed only when PyInstaller module is present
        import PyInstaller.__main__ as pyinstaller_main
    except ImportError as exc:  # pragma: no cover - defensive guard
        raise SystemExit(
            "PyInstaller is not installed. Install it with 'pip install pyinstaller' "
            "inside your Poetry environment."
        ) from exc
    pyinstaller_main.run(list(args))


def build_bundle(
    *,
    entry: Path,
    name: str,
    dist_dir: Path,
    build_dir: Path,
    icon: Path | None,
    data_mappings: Iterable[tuple[Path, str]],
    dry_run: bool,
) -> None:
    dist_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    args: list[str] = [
        "--name",
        name,
        "--noconfirm",
        "--clean",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
    ]
    for src, dest in data_mappings:
        args.extend(["--add-data", _format_data_argument(src, dest)])
    if icon is not None:
        args.extend(["--icon", str(icon)])

    args.append(str(entry))

    if dry_run:
        print("[DRY RUN] pyinstaller", " ".join(args))
        return

    _run_pyinstaller(args)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bundle the NagaKang prototype for MSI packaging.",
    )
    parser.add_argument(
        "--entry",
        type=Path,
        default=DEFAULT_ENTRY,
        help="Python entry script to bundle (default: prototypes/audio_engine_skeleton.py)",
    )
    parser.add_argument(
        "--name",
        default="NagaKang",
        help="Executable name inside the PyInstaller dist folder.",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=DEFAULT_DIST,
        help="Output directory for the bundled application.",
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=DEFAULT_BUILD,
        help="Scratch directory for PyInstaller build artifacts.",
    )
    parser.add_argument(
        "--icon",
        type=Path,
        help="Optional .ico file for the Windows executable.",
    )
    parser.add_argument(
        "--extra-data",
        action="append",
        default=[],
        metavar="SRC=DEST",
        help="Additional files or folders to include in the bundle (PyInstaller --add-data syntax).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the PyInstaller command without executing it.",
    )
    return parser.parse_args(argv)


def _parse_data_mappings(raw_mappings: Iterable[str]) -> list[tuple[Path, str]]:
    mappings: list[tuple[Path, str]] = []
    for mapping in raw_mappings:
        if "=" not in mapping:
            raise SystemExit(f"Invalid --extra-data mapping '{mapping}'. Use SRC=DEST format.")
        src_str, _, dest = mapping.partition("=")
        src_path = Path(src_str).resolve()
        if not src_path.exists():
            raise SystemExit(f"Extra data path '{src_path}' does not exist.")
        mappings.append((src_path, dest))
    return mappings


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    entry = args.entry.resolve()
    if not entry.exists():
        raise SystemExit(f"Entry script '{entry}' does not exist.")

    icon: Path | None = args.icon.resolve() if args.icon else None
    if icon is not None and not icon.exists():
        raise SystemExit(f"Icon '{icon}' does not exist.")

    data_mappings = _parse_data_mappings(args.extra_data)
    build_bundle(
        entry=entry,
        name=args.name,
        dist_dir=args.dist_dir.resolve(),
        build_dir=args.build_dir.resolve(),
        icon=icon,
        data_mappings=data_mappings,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
