import sys
from pathlib import Path

from tools.publish_diagrams import find_mermaid_sources, publish_diagrams


def test_publish_diagrams_invokes_renderer(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    source = assets / "example.mmd"
    source.write_text("graph TD; A-->B;", encoding="utf-8")

    renderer = tmp_path / "renderer.py"
    renderer.write_text(
        """
import sys
from pathlib import Path

args = sys.argv
source = Path(args[args.index('-i') + 1])
destination = Path(args[args.index('-o') + 1])
destination.write_text('rendered:' + source.read_text(encoding='utf-8'), encoding='utf-8')
""",
        encoding="utf-8",
    )

    outputs = publish_diagrams(
        assets,
        tmp_path / "out",
        [sys.executable, str(renderer)],
    )

    assert outputs == [tmp_path / "out" / "example.svg"]
    assert outputs[0].read_text(encoding="utf-8").startswith("rendered:")


def test_find_mermaid_sources_and_dry_run(tmp_path):
    (tmp_path / "assets").mkdir()
    files = [tmp_path / "assets" / name for name in ("a.mmd", "b.mmd")]
    for file in files:
        file.write_text("graph TD; A-->B;", encoding="utf-8")

    sources = find_mermaid_sources(tmp_path / "assets")
    assert sources == sorted(files)

    outputs = publish_diagrams(tmp_path / "assets", tmp_path / "out", ["mmdc"], dry_run=True)
    assert outputs == [tmp_path / "out" / "a.svg", tmp_path / "out" / "b.svg"]
    for output in outputs:
        assert not output.exists()
