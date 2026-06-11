"""Shared fixtures for saage.remote tests.

Everything offline by default: SAAGE_HOME is pointed at a tmp dir so no test
touches the real ~/.saage. Integration tests that need a live sshd (localhost)
are gated behind SAAGE_SSH_TESTS=1 + the `ssh` marker.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def saage_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "saage_home"
    home.mkdir()
    monkeypatch.setenv("SAAGE_HOME", str(home))
    return home


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        capture_output=True, text=True, check=check)


@pytest.fixture
def ws_repo(tmp_path) -> Path:
    """A small git repo standing in for a brownfield workspace (le-wm)."""
    repo = tmp_path / "ws_repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "train.py").write_text("print('train')\n")
    (repo / "config.yaml").write_text("epochs: 8\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")
    return repo
