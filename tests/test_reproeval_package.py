from __future__ import annotations

import pytest

from hy3_reproeval import __version__
from hy3_reproeval.cli import main


def test_reproeval_version_tracks_migrated_release() -> None:
    assert __version__ == "0.29.0"


def test_cli_prints_help_without_starting_server(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "serve-mcp" in output
    assert "evidence-grounded research reports" in output
