from __future__ import annotations

import pytest

from hy3_reproeval import __version__
from hy3_reproeval.cli import main


def test_reproeval_version_tracks_migrated_release() -> None:
    assert __version__ == "0.38.0"


def test_cli_prints_help_without_starting_server(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "serve-mcp" in output
    assert "run-judge-experiment" in output
    assert "prepare-annotation-packet" in output
    assert "prepare-adjudication-packet" in output
    assert "finalize-adjudication-packet" in output
    assert "build-real-paper-pilot" in output
    assert "verify-real-paper-sources" in output
    assert "generate-real-paper-references" in output
    assert "validate-reference-reviews" in output
    assert "verify-results-export" in output
    assert "export-human-consensus-results" in output
    assert "verify-human-consensus-results" in output
    assert "render-results-figures" in output
    assert "verify-results-figures" in output
    assert "evidence-grounded research reports" in output
