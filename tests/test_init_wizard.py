"""Init wizard: every template renders to a config that load_config accepts."""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from evolution_kernel import init_wizard
from evolution_kernel.config import load_config


@pytest.mark.parametrize("idx,name", list(enumerate(init_wizard.TEMPLATES, start=1)))
def test_each_template_round_trips(tmp_path: Path, monkeypatch, capsys, idx: int, name: str) -> None:
    monkeypatch.chdir(tmp_path)
    answers = iter([f"unit test mission for {name}", str(idx), "src/, tests/"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    rc = init_wizard.main([])

    assert rc == 0, f"init failed for template {name}: {capsys.readouterr().err}"
    out = tmp_path / "evolution.yml"
    assert out.exists()
    cfg = load_config(str(out))
    assert cfg.mission.startswith("unit test mission")
    assert cfg.mutation_scope.allowed_paths == ("src/", "tests/")


def test_refuses_to_overwrite(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evolution.yml").write_text("placeholder\n")
    monkeypatch.setattr("builtins.input", lambda _prompt: "x")
    assert init_wizard.main([]) == 2
    assert "already exists" in capsys.readouterr().err


def test_bad_template_pick(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    answers = iter(["mission", "99", "src/"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert init_wizard.main([]) == 2
