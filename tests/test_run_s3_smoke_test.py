from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from domain.persistence import ProjectFileAdapter
from domain.repository import S3ProjectRepository
from tools.run_s3_smoke_test import build_sample_project, execute_smoke_test


@pytest.fixture()
def moto_environment() -> None:
    with mock_aws():
        yield


def test_execute_smoke_test_success(tmp_path: Path, moto_environment: None) -> None:
    client = boto3.client("s3", region_name="us-east-1")
    bucket = "nagakang-smoke"
    client.create_bucket(Bucket=bucket)

    env = {
        "NAGAKANG_S3_BUCKET": bucket,
        "AWS_DEFAULT_REGION": "us-east-1",
        "NAGAKANG_S3_ENDPOINT_URL": client.meta.endpoint_url,
    }

    adapter = ProjectFileAdapter(tmp_path / "cache")
    repository = S3ProjectRepository.from_environment(adapter, env=env)

    project = build_sample_project("smoke-test")
    report = execute_smoke_test(repository, project, cleanup=True)

    assert report.status == "success"
    assert report.operations
    durations = [op.duration_seconds for op in report.operations]
    assert all(duration >= 0.0 for duration in durations)


def test_execute_smoke_test_handles_cleanup(tmp_path: Path, moto_environment: None) -> None:
    client = boto3.client("s3", region_name="us-east-1")
    bucket = "nagakang-smoke-cleanup"
    client.create_bucket(Bucket=bucket)

    env = {
        "NAGAKANG_S3_BUCKET": bucket,
        "AWS_DEFAULT_REGION": "us-east-1",
        "NAGAKANG_S3_ENDPOINT_URL": client.meta.endpoint_url,
    }

    adapter = ProjectFileAdapter(tmp_path / "cache")
    repository = S3ProjectRepository.from_environment(adapter, env=env)

    project = build_sample_project("cleanup-test")
    report = execute_smoke_test(repository, project, cleanup=True)

    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert not cache_files
    assert report.status == "success"
    assert {op.name for op in report.operations} >= {"save", "load", "delete"}
