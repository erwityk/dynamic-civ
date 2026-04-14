from pathlib import Path

import pytest

from engine.registry import Registry, register_builtins
from research.loader import ModLoadError, load_mod_file


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_valid_mod_registers_unit(tmp_path: Path):
    reg = Registry()
    register_builtins(reg)
    mod = _write(tmp_path, "ogre.py", '''
def register(api):
    api.register_unit(
        name="Magic Ogre", attack=5, defense=4, move=1, cost=60,
        shape="triangle", color=(120, 60, 160),
        description="A hulking sorcerous brute."
    )
''')
    names = load_mod_file(mod, reg)
    assert names == ["Magic Ogre"]
    assert "Magic Ogre" in reg.unit_types


def test_mod_with_disallowed_import_is_rejected(tmp_path: Path):
    reg = Registry()
    register_builtins(reg)
    mod = _write(tmp_path, "evil.py", '''
import os
def register(api):
    api.register_unit(name="X", attack=1, defense=1, move=1, cost=10,
        shape="circle", color=(0,0,0), description="x")
''')
    with pytest.raises(ModLoadError):
        load_mod_file(mod, reg)


def test_mod_cannot_overwrite_builtin(tmp_path: Path):
    reg = Registry()
    register_builtins(reg)
    mod = _write(tmp_path, "cheat.py", '''
def register(api):
    api.register_unit(name="Warrior", attack=10, defense=10, move=4, cost=5,
        shape="circle", color=(0,0,0), description="uber")
''')
    with pytest.raises(ModLoadError):
        load_mod_file(mod, reg)


def test_stats_are_clamped(tmp_path: Path):
    reg = Registry()
    register_builtins(reg)
    mod = _write(tmp_path, "big.py", '''
def register(api):
    api.register_unit(name="Giant", attack=9999, defense=9999, move=99, cost=1,
        shape="triangle", color=(9999, -5, 128), description="huge")
''')
    load_mod_file(mod, reg)
    g = reg.unit_types["Giant"]
    assert g.attack == 10
    assert g.defense == 10
    assert g.move == 4
    assert g.cost == 5  # min cost bound
    assert g.color == (255, 0, 128)


def test_mod_without_register_raises(tmp_path: Path):
    reg = Registry()
    register_builtins(reg)
    mod = _write(tmp_path, "empty.py", "x = 1\n")
    with pytest.raises(ModLoadError):
        load_mod_file(mod, reg)
