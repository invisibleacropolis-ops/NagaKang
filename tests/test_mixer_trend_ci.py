import json

from tools import mixer_trend_ci


def test_mixer_trend_ci_generates_markdown_and_history(tmp_path):
    baseline = tmp_path / "baseline.json"
    output_json = tmp_path / "latest.json"
    output_markdown = tmp_path / "latest.md"
    history_json = tmp_path / "history.json"
    history_markdown = tmp_path / "history.md"

    exit_code = mixer_trend_ci.main(
        [
            "--baseline-json",
            str(baseline),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
            "--history-json",
            str(history_json),
            "--history-markdown",
            str(history_markdown),
            "--duration",
            "0.05",
            "--demo-automation",
            "--label",
            "baseline-capture",
            "--write-baseline",
        ]
    )
    assert exit_code == 0
    assert baseline.exists()
    markdown_text = output_markdown.read_text(encoding="utf-8")
    assert "Mixer Trend Snapshot" in markdown_text
    assert "Artifact digests" in markdown_text
    assert "Sampler manifest linkage" in markdown_text
    assert "Sampler manifest digest recorded" in markdown_text

    exit_code = mixer_trend_ci.main(
        [
            "--baseline-json",
            str(baseline),
            "--output-json",
            str(output_json),
            "--output-markdown",
            str(output_markdown),
            "--history-json",
            str(history_json),
            "--history-markdown",
            str(history_markdown),
            "--duration",
            "0.05",
            "--label",
            "follow-up",
        ]
    )
    assert exit_code == 0

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert "diff" in payload
    history_entries = json.loads(history_json.read_text(encoding="utf-8"))
    assert len(history_entries) == 2
    history_md = history_markdown.read_text(encoding="utf-8")
    assert "follow-up" in history_md
    assert history_entries[-1]["artifact_digests"]
    assert "sampler_manifest" in history_entries[-1]
    assert "docs/assets/audio/sampler_s3_manifest.json" in history_entries[-1]["artifact_digests"]
