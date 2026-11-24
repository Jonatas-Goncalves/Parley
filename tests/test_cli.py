from __future__ import annotations

import sys

from parley import __version__
from parley.__main__ import main


def test_version_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["parley", "--version"])
    assert main() == 0
    assert capsys.readouterr().out.strip() == f"Parley {__version__}"


def test_version_command(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["parley", "version"])
    assert main() == 0
    assert capsys.readouterr().out.strip() == f"Parley {__version__}"


def test_help_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["parley", "--help"])
    assert main() == 0
    output = capsys.readouterr().out
    assert "Usage: parley" in output
    assert "--version" in output
    assert "--debug" in output
