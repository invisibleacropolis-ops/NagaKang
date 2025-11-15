import json
from pathlib import Path

from tools import autosave_stress_harness


def test_autosave_stress_harness_produces_summary(tmp_path: Path, capsys) -> None:
    autosave_dir = tmp_path / "autosave"
    exit_code = autosave_stress_harness.main(
        [
            "--project-id",
            "demo",
            "--autosave-dir",
            str(autosave_dir),
            "--iterations",
            "3",
            "--interval-seconds",
            "0.1",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["checkpoints_written"] >= 1
    assert payload["latest_prompt"].startswith("Autosaved demo")
    autosave_project_dir = autosave_dir / "demo"
    assert autosave_project_dir.exists()
    assert any(child.name.endswith("layout.json") for child in autosave_project_dir.iterdir())
