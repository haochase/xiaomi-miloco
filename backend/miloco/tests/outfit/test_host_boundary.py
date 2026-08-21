# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Architecture guardrails for the Outfit plugin boundary."""

import ast
from pathlib import Path

import pytest

OUTFIT_SOURCE = Path(__file__).parents[2] / "src" / "miloco" / "outfit"
FORBIDDEN_HOST_MODULES = frozenset(
    {"miloco.main", "miloco.miot", "miloco.observability"}
)


def test_outfit_does_not_import_host_singletons_or_device_policy() -> None:
    assert _find_forbidden_host_imports(OUTFIT_SOURCE) == []


@pytest.mark.parametrize(
    ("relative_path", "source", "expected_import"),
    [
        ("host_import.py", "import miloco.main\n", "miloco.main"),
        ("host_import.py", "from miloco import main\n", "miloco.main"),
        ("host_import.py", "from miloco import miot\n", "miloco.miot"),
        (
            "host_import.py",
            "from miloco import observability\n",
            "miloco.observability",
        ),
        ("host_import.py", "import miloco.main.bootstrap\n", "miloco.main.bootstrap"),
        (
            "host_import.py",
            "from miloco.miot.client import Client\n",
            "miloco.miot.client",
        ),
        ("host_import.py", "from ..main import Runtime\n", "miloco.main"),
        ("host_import.py", "from .. import main\n", "miloco.main"),
        ("host_import.py", "from .. import miot\n", "miloco.miot"),
        (
            "host_import.py",
            "from .. import observability\n",
            "miloco.observability",
        ),
        (
            "subpackage/host_import.py",
            "from ...main import Runtime\n",
            "miloco.main",
        ),
        (
            "subpackage/host_import.py",
            "from ... import main\n",
            "miloco.main",
        ),
        ("subpackage/host_import.py", "from .. import main\n", None),
    ],
)
def test_outfit_import_scanner_recursively_catches_host_import_forms(
    tmp_path: Path,
    relative_path: str,
    source: str,
    expected_import: str | None,
) -> None:
    source_file = tmp_path / relative_path
    source_file.parent.mkdir(parents=True, exist_ok=True)
    source_file.write_text(source, encoding="utf-8")

    expected_violations = (
        []
        if expected_import is None
        else [f"{Path(relative_path).as_posix()}:1: {expected_import}"]
    )
    assert _find_forbidden_host_imports(tmp_path) == expected_violations


def _find_forbidden_host_imports(source_root: Path) -> list[str]:
    violations: list[str] = []
    for source_file in sorted(source_root.rglob("*.py")):
        module = ast.parse(
            source_file.read_text(encoding="utf-8"), filename=str(source_file)
        )
        relative_path = source_file.relative_to(source_root).as_posix()
        source_package = _source_package(
            source_root=source_root, source_file=source_file
        )
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _is_forbidden_host_module(alias.name):
                        violations.append(
                            f"{relative_path}:{node.lineno}: {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                for imported_module in _resolved_import_modules(
                    source_package=source_package, node=node
                ):
                    if _is_forbidden_host_module(imported_module):
                        violations.append(
                            f"{relative_path}:{node.lineno}: {imported_module}"
                        )
    return violations


def _is_forbidden_host_module(module: str | None) -> bool:
    return module is not None and any(
        module == forbidden_module or module.startswith(f"{forbidden_module}.")
        for forbidden_module in FORBIDDEN_HOST_MODULES
    )


def _source_package(*, source_root: Path, source_file: Path) -> tuple[str, ...]:
    relative_parts = source_file.relative_to(source_root).parts[:-1]
    return ("miloco", "outfit", *relative_parts)


def _resolved_import_modules(
    *,
    source_package: tuple[str, ...],
    node: ast.ImportFrom,
) -> tuple[str, ...]:
    base_module = _resolved_import_base(source_package=source_package, node=node)
    if base_module is None:
        return ()
    if _is_forbidden_host_module(base_module):
        return (base_module,)
    return tuple(f"{base_module}.{alias.name}" for alias in node.names)


def _resolved_import_base(
    *,
    source_package: tuple[str, ...],
    node: ast.ImportFrom,
) -> str | None:
    if node.level == 0:
        return node.module

    parent_package_length = len(source_package) - node.level + 1
    if parent_package_length <= 0:
        return None
    parts = source_package[:parent_package_length]
    if node.module is not None:
        parts += tuple(node.module.split("."))
    return ".".join(parts)
