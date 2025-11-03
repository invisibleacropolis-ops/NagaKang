"""Utility to exercise the S3 repository adapter using environment credentials."""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:  # pragma: no cover - import path safeguard
    sys.path.insert(0, str(SRC_PATH))

from domain.models import InstrumentDefinition, InstrumentModule, Pattern, PatternStep, Project, ProjectMetadata
from domain.persistence import ProjectFileAdapter
from domain.repository import ProjectRepositoryError, S3ProjectRepository


@dataclass
class OperationResult:
    name: str
    duration_seconds: float
    details: dict[str, object]


@dataclass
class SmokeTestReport:
    status: str
    project_id: str
    bucket: Optional[str]
    prefix: Optional[str]
    total_duration_seconds: float
    operations: List[OperationResult]
    error: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["operations"] = [asdict(op) for op in self.operations]
        return payload


def build_sample_project(identifier: str) -> Project:
    metadata = ProjectMetadata(id=identifier, name="S3 Smoke Test Project")
    pattern = Pattern(
        id="pattern-1",
        name="Kick Loop",
        length_steps=16,
        steps=[PatternStep(note=36, velocity=110) for _ in range(16)],
    )
    instrument = InstrumentDefinition(
        id="instrument-1",
        name="Kick Synth",
        modules=[
            InstrumentModule(id="osc", type="sine", parameters={"frequency": 60.0}, inputs=[]),
            InstrumentModule(id="env", type="envelope", parameters={"attack": 0.01, "decay": 0.25}, inputs=["osc"]),
        ],
    )
    project = Project(metadata=metadata)
    project.add_pattern(pattern)
    project.add_instrument(instrument)
    project.append_to_song(pattern.id)
    return project


def execute_smoke_test(
    repository: S3ProjectRepository,
    project: Project,
    *,
    cleanup: bool = True,
) -> SmokeTestReport:
    operations: List[OperationResult] = []
    start_total = time.perf_counter()
    try:
        save_start = time.perf_counter()
        summary = repository.save(project)
        operations.append(
            OperationResult(
                name="save",
                duration_seconds=time.perf_counter() - save_start,
                details={"location": summary.location},
            )
        )

        load_start = time.perf_counter()
        loaded = repository.load(project.metadata.id)
        operations.append(
            OperationResult(
                name="load",
                duration_seconds=time.perf_counter() - load_start,
                details={"name": loaded.metadata.name},
            )
        )

        list_start = time.perf_counter()
        summaries = list(repository.list())
        operations.append(
            OperationResult(
                name="list",
                duration_seconds=time.perf_counter() - list_start,
                details={"count": len(summaries)},
            )
        )

        if cleanup:
            delete_start = time.perf_counter()
            repository.delete(project.metadata.id)
            operations.append(
                OperationResult(
                    name="delete",
                    duration_seconds=time.perf_counter() - delete_start,
                    details={"removed": True},
                )
            )

        total_duration = time.perf_counter() - start_total
        return SmokeTestReport(
            status="success",
            project_id=project.metadata.id,
            bucket=getattr(repository, "_bucket", None),
            prefix=getattr(repository, "_prefix", None),
            total_duration_seconds=total_duration,
            operations=operations,
        )
    except Exception as exc:  # pragma: no cover - defensive guard
        total_duration = time.perf_counter() - start_total
        return SmokeTestReport(
            status="error",
            project_id=project.metadata.id,
            bucket=getattr(repository, "_bucket", None),
            prefix=getattr(repository, "_prefix", None),
            total_duration_seconds=total_duration,
            operations=operations,
            error=str(exc),
        )
    finally:
        if cleanup:
            cache_path = repository._adapter.base_path / f"{project.metadata.id}{repository._extension}"  # type: ignore[attr-defined]
            if cache_path.exists():
                cache_path.unlink()


def write_markdown(report: SmokeTestReport, destination: Path) -> None:
    lines = ["# S3 Smoke Test Report", ""]
    lines.append(f"Status: **{report.status}**")
    lines.append(f"Project ID: `{report.project_id}`")
    if report.bucket:
        lines.append(f"Bucket: `{report.bucket}`")
    if report.prefix:
        lines.append(f"Prefix: `{report.prefix}`")
    lines.append(f"Total duration: {report.total_duration_seconds:.4f} seconds")
    lines.append("")
    lines.append("## Operations")
    for op in report.operations:
        lines.append(f"- **{op.name}** – {op.duration_seconds:.4f}s, details: {json.dumps(op.details, sort_keys=True)}")
    if report.error:
        lines.append("")
        lines.append(f"## Error\n{report.error}")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an S3 smoke test using environment credentials")
    parser.add_argument("--cache-path", type=Path, default=Path(".smoke-cache"))
    parser.add_argument("--identifier", type=str, default=f"s3-smoke-{int(time.time())}")
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--summary-markdown", type=Path)
    parser.add_argument("--keep", action="store_true", help="Keep the remote object instead of deleting it")
    parser.add_argument("--bucket", type=str, help="Override the target bucket for the smoke test")
    parser.add_argument("--prefix", type=str, help="Override the object prefix for stored projects")
    parser.add_argument("--extension", type=str, help="Override the file extension used when persisting projects")
    parser.add_argument("--endpoint-url", type=str, help="Custom endpoint URL for S3-compatible services")
    parser.add_argument(
        "--bootstrap-bucket",
        action="store_true",
        help="Create the target bucket before executing the smoke test",
    )
    parser.add_argument(
        "--use-moto",
        action="store_true",
        help="Run against an in-memory moto S3 emulator when real credentials are unavailable",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


@contextmanager
def _maybe_mock_s3(enabled: bool):
    if not enabled:
        yield
        return
    try:
        from moto import mock_s3
        context_manager = mock_s3()
    except ImportError:
        try:
            from moto import mock_aws
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise ProjectRepositoryError("moto[s3] is required for --use-moto") from exc
        context_manager = mock_aws()
    with context_manager:
        yield


def _build_environment(args: argparse.Namespace) -> dict[str, str]:
    environment = dict(os.environ)
    if args.bucket:
        environment["NAGAKANG_S3_BUCKET"] = args.bucket
    if args.prefix:
        environment["NAGAKANG_S3_PREFIX"] = args.prefix
    if args.extension:
        environment["NAGAKANG_S3_EXTENSION"] = args.extension
    if args.endpoint_url:
        environment["NAGAKANG_S3_ENDPOINT_URL"] = args.endpoint_url
    if args.use_moto:
        environment.setdefault("NAGAKANG_S3_BUCKET", "naga-smoke-moto")
        environment.setdefault("AWS_ACCESS_KEY_ID", "mock")
        environment.setdefault("AWS_SECRET_ACCESS_KEY", "mock")
        environment.setdefault("AWS_REGION", "us-east-1")
    return environment


def _bootstrap_bucket(environment: Mapping[str, str]) -> None:
    bucket = environment.get("NAGAKANG_S3_BUCKET")
    if not bucket:
        raise ProjectRepositoryError("Bucket must be provided to bootstrap S3 storage")
    import boto3

    session = boto3.session.Session(
        aws_access_key_id=environment.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=environment.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=environment.get("AWS_SESSION_TOKEN"),
        region_name=environment.get("AWS_REGION") or environment.get("AWS_DEFAULT_REGION"),
    )
    client_kwargs: dict[str, Any] = {}
    endpoint_url = environment.get("NAGAKANG_S3_ENDPOINT_URL")
    if endpoint_url:
        client_kwargs["endpoint_url"] = endpoint_url
    client = session.client("s3", **client_kwargs)
    create_kwargs: dict[str, Any] = {"Bucket": bucket}
    region = session.region_name or environment.get("AWS_REGION") or environment.get("AWS_DEFAULT_REGION")
    if region and region != "us-east-1":
        create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    try:
        client.create_bucket(**create_kwargs)
    except client.exceptions.BucketAlreadyOwnedByYou:  # type: ignore[attr-defined]
        return
    except client.exceptions.BucketAlreadyExists:  # type: ignore[attr-defined]
        return


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    cache_path = args.cache_path
    cache_path.mkdir(parents=True, exist_ok=True)

    adapter = ProjectFileAdapter(cache_path)
    environment = _build_environment(args)

    with _maybe_mock_s3(args.use_moto):
        if args.bootstrap_bucket:
            try:
                _bootstrap_bucket(environment)
            except ProjectRepositoryError as exc:
                print(f"Failed to bootstrap bucket: {exc}")
                return 1
        try:
            repository = S3ProjectRepository.from_environment(adapter, env=environment)
        except ProjectRepositoryError as exc:
            print(f"Failed to configure S3 repository: {exc}")
            return 1

        if args.bootstrap_bucket and not args.use_moto:
            time.sleep(1.0)

        project = build_sample_project(args.identifier)
        report = execute_smoke_test(repository, project, cleanup=not args.keep)

    if args.summary_json:
        args.summary_json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    if args.summary_markdown:
        write_markdown(report, args.summary_markdown)

    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.status == "success" else 2


if __name__ == "__main__":  # pragma: no cover - manual execution utility
    raise SystemExit(main())
