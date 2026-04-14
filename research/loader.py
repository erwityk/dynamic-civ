from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

from engine.mod_api import ModAPI
from engine.registry import Registry

ALLOWED_IMPORTS = {"math", "random", "dataclasses", "engine.mod_api"}


class ModLoadError(Exception):
    pass


def _validate_imports(source: str, path: Path) -> None:
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise ModLoadError(f"syntax error: {e.msg} at line {e.lineno}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise ModLoadError(f"disallowed import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod.split(".")[0] not in ALLOWED_IMPORTS:
                raise ModLoadError(f"disallowed import from: {mod}")


def load_mod_file(path: Path, registry: Registry) -> list[str]:
    """Validate and load a single mod .py file. Returns list of registered names."""
    source = path.read_text(encoding="utf-8")
    _validate_imports(source, path)

    spec = importlib.util.spec_from_file_location(f"dynciv_mod_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ModLoadError(f"could not load spec for {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise ModLoadError(f"import failed: {e}") from e

    register_fn = getattr(module, "register", None)
    if not callable(register_fn):
        raise ModLoadError("mod file must define `def register(api): ...`")

    api = ModAPI(registry=registry, source_mod=path.name)
    try:
        register_fn(api)
    except Exception as e:
        raise ModLoadError(f"register() raised: {e}") from e

    if not api.registered:
        raise ModLoadError("register() did not register any unit or building")
    return api.registered


def find_new_mods(mod_dir: Path, already_loaded: set[str]) -> list[Path]:
    return sorted(
        p for p in mod_dir.glob("*.py")
        if p.name != "__init__.py" and p.name not in already_loaded
    )
