import json

import pytest

from tools.run_s3_smoke_test import main

pytest.importorskip("moto", reason="moto is required for moto-backed smoke tests")


def test_run_s3_smoke_test_with_moto(tmp_path, capsys):
    cache_path = tmp_path / "cache"
    summary_json = tmp_path / "report.json"
    summary_markdown = tmp_path / "report.md"

    exit_code = main(
        [
            "--use-moto",
            "--bootstrap-bucket",
            "--cache-path",
            str(cache_path),
            "--summary-json",
            str(summary_json),
            "--summary-markdown",
            str(summary_markdown),
            "--identifier",
            "test-smoke",
        ]
    )

    captured = capsys.readouterr()
    assert "S3 Smoke Test" in captured.out
    assert exit_code == 0
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["status"] == "success"
    assert summary_markdown.read_text(encoding="utf-8").startswith("# S3 Smoke Test Report")


def test_run_s3_smoke_test_env_file(tmp_path, capsys):
    cache_path = tmp_path / "cache"
    summary_json = tmp_path / "report.json"
    summary_markdown = tmp_path / "report.md"
    env_file = tmp_path / "smoke.env"
    env_file.write_text(
        "\n".join(
            [
                "# staging credentials placeholder",
                "NAGAKANG_S3_BUCKET=env-bucket",
                "AWS_ACCESS_KEY_ID=demo",
                "AWS_SECRET_ACCESS_KEY=demo",
                "AWS_REGION=us-east-1",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--use-moto",
            "--bootstrap-bucket",
            "--cache-path",
            str(cache_path),
            "--summary-json",
            str(summary_json),
            "--summary-markdown",
            str(summary_markdown),
            "--identifier",
            "env-smoke",
            "--env-file",
            str(env_file),
        ]
    )

    assert exit_code == 0
    payload = json.loads(summary_json.read_text(encoding="utf-8"))
    assert payload["bucket"] == "env-bucket"
