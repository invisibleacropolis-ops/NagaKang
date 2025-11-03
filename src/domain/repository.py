"""Repository abstractions for project persistence backends.

These interfaces layer on top of :mod:`domain.persistence` to support
both local filesystem storage and future cloud synchronisation targets
outlined in the Comprehensive Development Plan (README §2, §8). The
implementations here are intentionally lightweight yet fully tested so
subsequent steps can expand capabilities without breaking callers.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Protocol, Tuple

from .models import Project
from .persistence import ProjectFileAdapter, ProjectSerializer


class ProjectRepositoryError(Exception):
    """Base error for repository failures."""


class ProjectNotFoundError(ProjectRepositoryError):
    """Raised when a requested project cannot be located."""


@dataclass(frozen=True)
class ProjectSummary:
    """Lightweight descriptor for enumerating stored projects."""

    identifier: str
    name: str
    updated_at: datetime
    location: str


class ProjectRepository(Protocol):
    """Minimal interface shared by local and remote repositories."""

    def save(self, project: Project) -> ProjectSummary:
        """Persist the project and return a :class:`ProjectSummary`."""

    def load(self, identifier: str) -> Project:
        """Retrieve a project by identifier."""

    def delete(self, identifier: str) -> None:
        """Remove the project from the backing store."""

    def list(self) -> Iterable[ProjectSummary]:
        """Iterate over available projects."""


class LocalProjectRepository(ProjectRepository):
    """Filesystem-backed repository using :class:`ProjectFileAdapter`."""

    def __init__(self, adapter: ProjectFileAdapter, *, extension: str = ".json") -> None:
        self._adapter = adapter
        self._extension = extension

    def _path_for(self, identifier: str) -> Path:
        return self._adapter.base_path / f"{identifier}{self._extension}"

    def save(self, project: Project) -> ProjectSummary:
        destination = self._adapter.save(project, f"{project.metadata.id}{self._extension}")
        return ProjectSummary(
            identifier=project.metadata.id,
            name=project.metadata.name,
            updated_at=project.metadata.updated_at,
            location=str(destination),
        )

    def load(self, identifier: str) -> Project:
        path = self._path_for(identifier)
        if not path.exists():
            raise ProjectNotFoundError(f"Project {identifier!r} not found at {path}")
        return self._adapter.load(path.name)

    def delete(self, identifier: str) -> None:
        path = self._path_for(identifier)
        if not path.exists():
            raise ProjectNotFoundError(f"Project {identifier!r} not found at {path}")
        path.unlink()

    def list(self) -> Iterable[ProjectSummary]:
        for file_path in sorted(self._adapter.base_path.glob(f"*{self._extension}")):
            payload = self._adapter.load(file_path.name)
            yield ProjectSummary(
                identifier=payload.metadata.id,
                name=payload.metadata.name,
                updated_at=payload.metadata.updated_at,
                location=str(file_path),
            )


class InMemoryProjectRepository(ProjectRepository):
    """Dictionary-backed repository suitable for tests or mocked cloud storage."""

    def __init__(self) -> None:
        self._storage: Dict[str, Project] = {}

    def save(self, project: Project) -> ProjectSummary:
        self._storage[project.metadata.id] = project.model_copy(deep=True)
        return ProjectSummary(
            identifier=project.metadata.id,
            name=project.metadata.name,
            updated_at=project.metadata.updated_at,
            location="in-memory",
        )

    def load(self, identifier: str) -> Project:
        try:
            project = self._storage[identifier]
        except KeyError as exc:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in memory") from exc
        return project.model_copy(deep=True)

    def delete(self, identifier: str) -> None:
        if identifier not in self._storage:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in memory")
        del self._storage[identifier]

    def list(self) -> Iterable[ProjectSummary]:
        for project in self._storage.values():
            yield ProjectSummary(
                identifier=project.metadata.id,
                name=project.metadata.name,
                updated_at=project.metadata.updated_at,
                location="in-memory",
            )


class MockCloudProjectRepository(ProjectRepository):
    """Simulated cloud repository with naive sync + conflict detection.

    The adapter serializes payloads to a local cache so integration code can
    exercise round-trips without needing credentials. A small amount of
    artificial latency can be configured to mimic remote calls during tests.
    """

    def __init__(
        self,
        adapter: ProjectFileAdapter,
        *,
        bucket: str = "naga-cloud",
        extension: str = ".json",
        network_latency: float = 0.0,
    ) -> None:
        self._adapter = adapter
        self._bucket = bucket
        self._extension = extension
        self._network_latency = network_latency
        self._objects: Dict[str, Dict[str, object]] = {}
        self._revisions: Dict[str, datetime] = {}

    def _simulate_latency(self) -> None:
        if self._network_latency > 0.0:
            time.sleep(self._network_latency)

    def _path_for(self, identifier: str) -> Path:
        return self._adapter.base_path / f"{identifier}{self._extension}"

    def save(self, project: Project) -> ProjectSummary:
        previous_revision = self._revisions.get(project.metadata.id)
        if previous_revision and project.metadata.updated_at < previous_revision:
            raise ProjectRepositoryError(
                "Stale project metadata detected; update local state before saving"
            )
        self._simulate_latency()
        payload = ProjectSerializer.to_dict(project)
        self._objects[project.metadata.id] = payload
        self._revisions[project.metadata.id] = project.metadata.updated_at
        self._adapter.save(project, f"{project.metadata.id}{self._extension}")
        return ProjectSummary(
            identifier=project.metadata.id,
            name=project.metadata.name,
            updated_at=project.metadata.updated_at,
            location=f"cloud://{self._bucket}/{project.metadata.id}",
        )

    def load(self, identifier: str) -> Project:
        self._simulate_latency()
        try:
            payload = self._objects[identifier]
        except KeyError as exc:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in cloud store") from exc
        project = ProjectSerializer.from_dict(payload)  # type: ignore[arg-type]
        self._adapter.save(project, f"{identifier}{self._extension}")
        return project

    def delete(self, identifier: str) -> None:
        self._simulate_latency()
        if identifier not in self._objects:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in cloud store")
        del self._objects[identifier]
        self._revisions.pop(identifier, None)
        cache_path = self._path_for(identifier)
        if cache_path.exists():
            cache_path.unlink()

    def list(self) -> Iterable[ProjectSummary]:
        for identifier, payload in sorted(self._objects.items()):
            project = ProjectSerializer.from_dict(payload)  # type: ignore[arg-type]
            yield ProjectSummary(
                identifier=identifier,
                name=project.metadata.name,
                updated_at=project.metadata.updated_at,
                location=f"cloud://{self._bucket}/{identifier}",
            )


class S3ProjectRepository(ProjectRepository):
    """S3-backed repository that mirrors remote objects into a local cache."""

    def __init__(
        self,
        adapter: ProjectFileAdapter,
        s3_client: Any,
        *,
        bucket: str,
        prefix: str = "projects/",
        extension: str = ".json",
        missing_exceptions: Optional[Tuple[type[BaseException], ...]] = None,
    ) -> None:
        self._adapter = adapter
        self._s3 = s3_client
        self._bucket = bucket
        self._prefix = prefix if prefix.endswith("/") or not prefix else f"{prefix.rstrip('/')}/"
        self._extension = extension
        if missing_exceptions is not None:
            self._missing_exceptions = missing_exceptions
        else:
            candidates: list[type[BaseException]] = [KeyError]
            no_such_key = getattr(getattr(s3_client, "exceptions", None), "NoSuchKey", None)
            if isinstance(no_such_key, type):
                candidates.append(no_such_key)
            self._missing_exceptions = tuple(candidates)

    @classmethod
    def from_environment(
        cls,
        adapter: ProjectFileAdapter,
        *,
        prefix: str = "projects/",
        extension: str = ".json",
        missing_exceptions: Optional[Tuple[type[BaseException], ...]] = None,
        env: Mapping[str, str] | None = None,
        client_factory: Callable[[Mapping[str, str]], Any] | None = None,
    ) -> "S3ProjectRepository":
        """Instantiate the repository using environment-provided credentials.

        The helper reads the following variables to construct a client:

        ``NAGAKANG_S3_BUCKET`` (required)
            Name of the target bucket storing project documents.
        ``NAGAKANG_S3_PREFIX`` (optional)
            Object prefix housing project files; defaults to ``projects/``.
        ``NAGAKANG_S3_EXTENSION`` (optional)
            File extension for stored documents; defaults to ``.json``.
        ``NAGAKANG_S3_ENDPOINT_URL`` (optional)
            Custom endpoint for self-hosted S3-compatible services.
        ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` / ``AWS_SESSION_TOKEN``
            Standard AWS credentials passed to ``boto3``.
        ``AWS_REGION`` / ``AWS_DEFAULT_REGION``
            Region forwarded to the client for latency-sensitive routing.

        A custom ``client_factory`` may be provided to integrate with alternate
        SDKs or to supply mocked clients during tests.
        """

        environment: Mapping[str, str]
        environment = env or os.environ
        bucket = environment.get("NAGAKANG_S3_BUCKET") or environment.get("AWS_S3_BUCKET")
        if not bucket:
            raise ProjectRepositoryError(
                "NAGAKANG_S3_BUCKET environment variable must be set to configure the S3 repository"
            )

        resolved_prefix = environment.get("NAGAKANG_S3_PREFIX", prefix)
        resolved_extension = environment.get("NAGAKANG_S3_EXTENSION", extension)

        if client_factory is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - depends on optional dependency
                raise ProjectRepositoryError(
                    "boto3 is required to configure S3ProjectRepository from the environment"
                ) from exc

            session = boto3.session.Session(
                aws_access_key_id=environment.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=environment.get("AWS_SECRET_ACCESS_KEY"),
                aws_session_token=environment.get("AWS_SESSION_TOKEN"),
                region_name=environment.get("AWS_REGION") or environment.get("AWS_DEFAULT_REGION"),
            )
            endpoint_url = environment.get("NAGAKANG_S3_ENDPOINT_URL")
            client_kwargs: Dict[str, Any] = {}
            if endpoint_url:
                client_kwargs["endpoint_url"] = endpoint_url
            s3_client = session.client("s3", **client_kwargs)
        else:
            s3_client = client_factory(environment)

        return cls(
            adapter,
            s3_client,
            bucket=bucket,
            prefix=resolved_prefix,
            extension=resolved_extension,
            missing_exceptions=missing_exceptions,
        )

    def _object_key(self, identifier: str) -> str:
        return f"{self._prefix}{identifier}{self._extension}" if self._prefix else f"{identifier}{self._extension}"

    def _path_for(self, identifier: str) -> Path:
        return self._adapter.base_path / f"{identifier}{self._extension}"

    def _read_body(self, body: Any) -> bytes:
        if body is None:
            raise ProjectRepositoryError("S3 response missing Body payload")
        if hasattr(body, "read"):
            return body.read()
        if isinstance(body, (bytes, bytearray)):
            return bytes(body)
        raise ProjectRepositoryError("Unsupported S3 body payload type")

    def _head_object(self, key: str) -> Optional[dict[str, Any]]:
        try:
            return self._s3.head_object(Bucket=self._bucket, Key=key)
        except self._missing_exceptions:
            return None
        except Exception as exc:  # pragma: no cover - defensive against provider errors
            error_response = getattr(exc, "response", {})
            error = error_response.get("Error") if isinstance(error_response, dict) else None
            code = error.get("Code") if isinstance(error, dict) else None
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise ProjectRepositoryError("Failed to inspect project metadata in S3") from exc

    def _remote_revision(self, key: str) -> Optional[datetime]:
        response = self._head_object(key)
        if response is None:
            return None
        metadata = response.get("Metadata", {})
        updated_at = metadata.get("updated_at")
        if isinstance(updated_at, str):
            try:
                return datetime.fromisoformat(updated_at)
            except ValueError:  # pragma: no cover - malformed provider metadata
                pass
        last_modified = response.get("LastModified")
        if isinstance(last_modified, datetime):
            return last_modified
        return None

    def _identifier_from_key(self, key: str) -> Optional[str]:
        if self._prefix and not key.startswith(self._prefix):
            return None
        trimmed = key[len(self._prefix) :] if self._prefix else key
        if not trimmed.endswith(self._extension):
            return None
        return trimmed[: -len(self._extension)]

    def save(self, project: Project) -> ProjectSummary:
        key = self._object_key(project.metadata.id)
        remote_revision = self._remote_revision(key)
        if remote_revision and project.metadata.updated_at <= remote_revision:
            raise ProjectRepositoryError(
                "Remote project is newer than local state; refresh before overwriting"
            )

        payload = json.dumps(ProjectSerializer.to_dict(project), separators=(",", ":")).encode("utf-8")
        metadata = {
            "updated_at": project.metadata.updated_at.isoformat(),
            "name": project.metadata.name,
        }
        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=payload,
                Metadata=metadata,
                ContentType="application/json",
            )
        except Exception as exc:  # pragma: no cover - depends on provider client
            raise ProjectRepositoryError("Failed to upload project to S3") from exc

        self._adapter.save(project, f"{project.metadata.id}{self._extension}")
        return ProjectSummary(
            identifier=project.metadata.id,
            name=project.metadata.name,
            updated_at=project.metadata.updated_at,
            location=f"s3://{self._bucket}/{key}",
        )

    def load(self, identifier: str) -> Project:
        key = self._object_key(identifier)
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
        except self._missing_exceptions as exc:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in S3 bucket {self._bucket}") from exc
        except Exception as exc:  # pragma: no cover - provider specific error
            raise ProjectRepositoryError("Failed to download project from S3") from exc

        body = self._read_body(response.get("Body"))
        payload = json.loads(body.decode("utf-8"))
        project = ProjectSerializer.from_dict(payload)
        self._adapter.save(project, f"{identifier}{self._extension}")
        return project

    def delete(self, identifier: str) -> None:
        key = self._object_key(identifier)
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
        except self._missing_exceptions as exc:
            raise ProjectNotFoundError(f"Project {identifier!r} not found in S3 bucket {self._bucket}") from exc
        except Exception as exc:  # pragma: no cover - provider specific error
            raise ProjectRepositoryError("Failed to delete project from S3") from exc

        cache_path = self._path_for(identifier)
        if cache_path.exists():
            cache_path.unlink()

    def list(self) -> Iterable[ProjectSummary]:
        try:
            response = self._s3.list_objects_v2(Bucket=self._bucket, Prefix=self._prefix)
        except Exception as exc:  # pragma: no cover - provider specific error
            raise ProjectRepositoryError("Failed to enumerate projects in S3") from exc

        contents = response.get("Contents", []) or []
        for entry in contents:
            key = entry.get("Key")
            if not isinstance(key, str):
                continue
            identifier = self._identifier_from_key(key)
            if identifier is None:
                continue
            head = self._head_object(key)
            if head is None:
                continue
            metadata = head.get("Metadata", {})
            revision: Optional[datetime] = None
            updated_field = metadata.get("updated_at")
            if isinstance(updated_field, str):
                try:
                    revision = datetime.fromisoformat(updated_field)
                except ValueError:  # pragma: no cover - malformed metadata
                    revision = None
            if revision is None:
                last_modified = head.get("LastModified") or entry.get("LastModified")
                if isinstance(last_modified, datetime):
                    revision = last_modified
            if revision is None:
                revision = datetime.utcnow()
            name = metadata.get("name") or identifier
            yield ProjectSummary(
                identifier=identifier,
                name=name,
                updated_at=revision,
                location=f"s3://{self._bucket}/{key}",
            )
