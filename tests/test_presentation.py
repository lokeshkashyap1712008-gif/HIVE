from pathlib import Path

from pptx import Presentation

from hive.presentation import build_presentation


def test_build_presentation_creates_pptx(tmp_path: Path):
    output = tmp_path / "demo.pptx"

    result = build_presentation(
        "AI assistant for startup founders",
        output_path=str(output),
        slide_count=4,
        use_llm=False,
    )

    assert result == str(output)
    assert output.exists()
    assert output.stat().st_size > 0

    deck = Presentation(str(output))
    assert len(deck.slides) == 4
