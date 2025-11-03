import io
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Mapping

import pytest

from domain.models import Project
from domain.persistence import ProjectFileAdapter
from domain.repository import (
    InMemoryProjectRepository,
    LocalProjectRepository,
    MockCloudProjectRepository,
    ProjectNotFoundError,
    ProjectRepositoryError,
    ProjectSummary,
    S3ProjectRepository,
)


class StubS3Client:
    def __init__(self) -> None:
        self._buckets: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.exceptions = type("Exceptions", (), {"NoSuchKey": KeyError})

    def _bucket(self, name: str) -> Dict[str, Dict[str, Any]]:
        return self._buckets.setdefault(name, {})

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        Metadata: Dict[str, str] | None = None,
        ContentType: str | None = None,
    ) -> None:
        store = self._bucket(Bucket)
        store[Key] = {
            "Body": bytes(Body),
            "Metadata": Metadata or {},
            "LastModified": datetime.utcnow(),
        }

    def get_object(self, *, Bucket: str, Key: str) -> Dict[str, Any]:
        store = self._bucket(Bucket)
        try:
            record = store[Key]
        except KeyError as exc:
            raise KeyError(Key) from exc
        return {"Body": io.BytesIO(record["Body"]), "Metadata": record["Metadata"]}

    def head_object(self, *, Bucket: str, Key: str) -> Dict[str, Any]:
        store = self._bucket(Bucket)
        try:
            record = store[Key]
        except KeyError as exc:
            raise KeyError(Key) from exc
        return {"Metadata": record["Metadata"], "LastModified": record["LastModified"]}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        store = self._bucket(Bucket)
        if Key not in store:
            raise KeyError(Key)
        del store[Key]

    def list_objects_v2(self, *, Bucket: str, Prefix: str = "") -> Dict[str, Any]:
        store = self._bucket(Bucket)
        contents = []
        for key, record in store.items():
            if Prefix and not key.startswith(Prefix):
                continue
            contents.append({"Key": key, "LastModified": record["LastModified"]})
        return {"Contents": contents}


def _assert_summary(summary: ProjectSummary, project: Project) -> None:
    assert summary.identifier == project.metadata.id
    assert summary.name == project.metadata.name
    assert summary.updated_at == project.metadata.updated_at


def test_local_repository_round_trip(tmp_path: Path, example_project: Project) -> None:
    adapter = ProjectFileAdapter(tmp_path)
    repo = LocalProjectRepository(adapter)

    summary = repo.save(example_project)
    _assert_summary(summary, example_project)
    assert Path(summary.location).exists()

    restored = repo.load(example_project.metadata.id)
    assert restored == example_project

    listed = list(repo.list())
    assert len(listed) == 1
    _assert_summary(listed[0], example_project)


def test_local_repository_missing_project(tmp_path: Path) -> None:
    repo = LocalProjectRepository(ProjectFileAdapter(tmp_path))

    with pytest.raises(ProjectNotFoundError):
        repo.load("missing")

    with pytest.raises(ProjectNotFoundError):
        repo.delete("missing")


def test_in_memory_repository_behaves_like_remote(example_project: Project) -> None:
    repo = InMemoryProjectRepository()

    summary = repo.save(example_project)
    _assert_summary(summary, example_project)

    restored = repo.load(example_project.metadata.id)
    assert restored == example_project

    repo.delete(example_project.metadata.id)

    with pytest.raises(ProjectNotFoundError):
        repo.load(example_project.metadata.id)


def test_mock_cloud_repository_round_trip(tmp_path: Path, example_project: Project) -> None:
    adapter = ProjectFileAdapter(tmp_path)
    repo = MockCloudProjectRepository(adapter, bucket="test-bucket")

    summary = repo.save(example_project)
    _assert_summary(summary, example_project)
    assert summary.location == f"cloud://test-bucket/{example_project.metadata.id}"

    restored = repo.load(example_project.metadata.id)
    assert restored == example_project

    listed = list(repo.list())
    assert len(listed) == 1
    _assert_summary(listed[0], example_project)
    assert listed[0].location.startswith("cloud://test-bucket/")

    repo.delete(example_project.metadata.id)

    with pytest.raises(ProjectNotFoundError):
        repo.load(example_project.metadata.id)


def test_mock_cloud_repository_detects_stale_writes(tmp_path: Path, example_project: Project) -> None:
    adapter = ProjectFileAdapter(tmp_path)
    repo = MockCloudProjectRepository(adapter)

    repo.save(example_project)

    stale = example_project.model_copy(deep=True)
    stale.metadata.updated_at -= timedelta(days=1)

    with pytest.raises(ProjectRepositoryError):
        repo.save(stale)


def test_s3_repository_round_trip(tmp_path: Path, example_project: Project) -> None:
    adapter = ProjectFileAdapter(tmp_path / "cache")
    client = StubS3Client()
    repo = S3ProjectRepository(adapter, client, bucket="bucket", prefix="projects/")

    summary = repo.save(example_project)
    _assert_summary(summary, example_project)
    assert summary.location == f"s3://bucket/projects/{example_project.metadata.id}.json"
    assert (tmp_path / "cache" / f"{example_project.metadata.id}.json").exists()

    restored = repo.load(example_project.metadata.id)
    assert restored == example_project

    listed = list(repo.list())
    assert len(listed) == 1
    _assert_summary(listed[0], example_project)

    repo.delete(example_project.metadata.id)
    with pytest.raises(ProjectNotFoundError):
        repo.load(example_project.metadata.id)


def test_s3_repository_detects_stale_writes(tmp_path: Path, example_project: Project) -> None:
    adapter = ProjectFileAdapter(tmp_path)
    client = StubS3Client()
    repo = S3ProjectRepository(adapter, client, bucket="bucket")

    repo.save(example_project)

    stale = example_project.model_copy(deep=True)
    stale.metadata.updated_at -= timedelta(seconds=5)

    with pytest.raises(ProjectRepositoryError):
        repo.save(stale)

    updated = example_project.model_copy(deep=True)
    updated.metadata.updated_at += timedelta(seconds=5)
    repo.save(updated)


def test_s3_repository_missing_entries(tmp_path: Path) -> None:
    adapter = ProjectFileAdapter(tmp_path)
    client = StubS3Client()
    repo = S3ProjectRepository(adapter, client, bucket="bucket")

    with pytest.raises(ProjectNotFoundError):
        repo.load("missing")

    with pytest.raises(ProjectNotFoundError):
        repo.delete("missing")


def test_s3_repository_from_environment_uses_factory(tmp_path: Path, example_project: Project) -> None:
    adapter = ProjectFileAdapter(tmp_path)
    client = StubS3Client()

    def factory(env: Mapping[str, str]) -> StubS3Client:
        assert env["NAGAKANG_S3_BUCKET"] == "bucket"
        assert env["NAGAKANG_S3_PREFIX"] == "remote/projects"
        assert env["NAGAKANG_S3_EXTENSION"] == ".json"
        return client

    env = {
        "NAGAKANG_S3_BUCKET": "bucket",
        "NAGAKANG_S3_PREFIX": "remote/projects",
        "NAGAKANG_S3_EXTENSION": ".json",
    }
    repo = S3ProjectRepository.from_environment(
        adapter,
        env=env,
        client_factory=factory,
    )

    summary = repo.save(example_project)
    assert summary.location.endswith(f"/remote/projects/{example_project.metadata.id}.json")


def test_s3_repository_from_environment_requires_bucket(tmp_path: Path) -> None:
    adapter = ProjectFileAdapter(tmp_path)

    with pytest.raises(ProjectRepositoryError):
        S3ProjectRepository.from_environment(adapter, env={})

