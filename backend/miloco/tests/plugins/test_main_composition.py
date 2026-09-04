# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Static and clean-import contracts for the main plugin composition seam."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from miloco.config.settings import MilocoSettings
from miloco.plugins.builtin import build_builtin_plugin_factories
from miloco.plugins.host_composition import HostPluginRuntime

_MAIN_PATH = Path(__file__).parents[2] / "src" / "miloco" / "main.py"


def _main_tree() -> tuple[str, ast.Module]:
    source = _MAIN_PATH.read_text(encoding="utf-8")
    return source, ast.parse(source)


def _call_lines(tree: ast.AST, name: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            isinstance(node.func, ast.Name)
            and node.func.id == name
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == name
        )
    ]


def _attribute_call_line(tree: ast.AST, receiver: str, method: str) -> int:
    return next(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == receiver
    )


def test_main_static_imports_are_generic_and_policy_neutral() -> None:
    _source, tree = _main_tree()
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    string_constants = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert "miloco.plugins.builtin" in imports
    assert "miloco.plugins.host_composition" in imports
    assert "miloco.weather.composition" in imports
    assert not any(
        imported == "miloco.outfit" or imported.startswith("miloco.outfit.")
        for imported in imports
    )
    assert not any(
        "outfit_v2" in value or "/api/outfit" in value for value in string_constants
    )


def test_main_wires_runtime_after_manager_and_stops_it_before_core_teardown() -> None:
    source, tree = _main_tree()
    initialize_line = _call_lines(tree, "initialize")[0]
    weather_build_line = _call_lines(tree, "build_host_weather_runtime")[0]
    weather_start_line = _attribute_call_line(tree, "weather_runtime", "start")
    build_line = _call_lines(tree, "build_builtin_plugin_factories")[0]
    runtime_line = _call_lines(tree, "HostPluginRuntime")[0]
    start_line = _attribute_call_line(tree, "plugin_runtime", "start")
    yield_line = next(
        node.lineno for node in ast.walk(tree) if isinstance(node, ast.Yield)
    )
    runtime_stop_line = (
        source[: source.index("await _app.state.plugin_runtime.stop")].count("\n") + 1
    )
    weather_stop_line = (
        source[: source.index("await _app.state.weather_runtime.stop")].count("\n")
        + 1
    )
    core_stop_line = _call_lines(tree, "stop_engine")[0]

    assert (
        initialize_line
        < weather_build_line
        < weather_start_line
        < build_line
        < runtime_line
        < start_line
        < yield_line
    )
    assert yield_line < runtime_stop_line < weather_stop_line < core_stop_line
    assert "_app.state.weather_runtime = weather_runtime" in source
    assert "weather_runtime_start_failed" in source
    assert "weather_runtime_stop_failed" in source
    assert "_app.state.plugin_runtime = plugin_runtime" in source
    assert "plugin_runtime_start_failed" in source
    assert "plugin_runtime_stop_failed" in source
    assert "_app.state.outfit" not in source


def test_default_main_import_does_not_import_outfit_or_create_outfit_paths(
    tmp_path: Path,
) -> None:
    root = tmp_path / "main-disabled-home"
    code = """
import json
import os
import sys
import types
from pathlib import Path

fcntl = types.ModuleType("fcntl")
fcntl.LOCK_EX = 1
fcntl.LOCK_UN = 2
fcntl.flock = lambda *_args: None
sys.modules["fcntl"] = fcntl
if not hasattr(os, "sysconf"):
    os.sysconf = lambda _name: 4096
import miloco.main

root = Path(sys.argv[1])
print(json.dumps({
    "outfit_imported": any(
        name == "miloco.outfit" or name.startswith("miloco.outfit.")
        for name in sys.modules
    ),
    "outfit_dir_exists": (root / "outfit").exists(),
    "weather_runtime_imported": any(
        name in {
            "miloco.weather.http_transport",
            "miloco.weather.open_meteo",
            "miloco.weather.repository",
            "miloco.weather.runtime",
            "miloco.weather.service",
        }
        for name in sys.modules
    ),
    "weather_dir_exists": (root / "weather").exists(),
}))
"""
    env = os.environ.copy()
    env["MILOCO_HOME"] = str(root)
    env["MILOCO_DIRECTORIES__STORAGE"] = str(root)
    env["MILOCO_FEATURES__OUTFIT__ENABLED"] = "false"
    env["MILOCO_WEATHER__ENABLED"] = "false"
    completed = subprocess.run(
        [sys.executable, "-c", code, str(root)],
        cwd=Path(__file__).parents[2],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "outfit_imported": False,
        "outfit_dir_exists": False,
        "weather_runtime_imported": False,
        "weather_dir_exists": False,
    }


@pytest.mark.asyncio
async def test_enabled_builtin_routes_mount_once_before_spa_and_remove_on_shutdown(
    tmp_path: Path,
) -> None:
    class _PersonService:
        def exists(self, person_id: str) -> bool:
            return person_id == "chase"

    settings = MilocoSettings(
        directories={"storage": str(tmp_path)},
        features={
            "outfit": {
                "enabled": True,
                "primary_person_id": "chase",
                "audit_hmac_key": "k" * 32,
            }
        },
    )
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/{full_path:path}", name="spa_handler")
    async def spa_handler(full_path: str) -> dict[str, str]:
        return {"path": full_path}

    runtime = HostPluginRuntime(
        build_builtin_plugin_factories(settings, _PersonService())
    )

    await runtime.start(app)
    await runtime.start(app)

    paths = [getattr(route, "path", None) for route in app.router.routes]
    assert paths.count("/api/outfit/capability") == 1
    assert paths.count("/api/outfit/admin/usage/today") == 1
    assert paths.count("/api/outfit/wardrobe/drafts") == 2
    assert paths.count("/api/outfit/wardrobe/items/available") == 1
    assert paths.count("/api/outfit/wardrobe/drafts/{draft_id}/confirm") == 1
    assert "/api/outfit/recommendations" not in paths
    assert paths.index("/api/outfit/capability") < paths.index(
        "/api/outfit/admin/usage/today"
    )
    wardrobe_draft_indexes = [
        index
        for index, path in enumerate(paths)
        if path == "/api/outfit/wardrobe/drafts"
    ]
    assert paths.index("/api/outfit/admin/usage/today") < wardrobe_draft_indexes[0]
    assert wardrobe_draft_indexes[-1] < paths.index(
        "/api/outfit/wardrobe/items/available"
    )
    assert paths.index("/api/outfit/wardrobe/items/available") < paths.index(
        "/api/outfit/wardrobe/drafts/{draft_id}/confirm"
    )
    assert paths.index("/api/outfit/wardrobe/drafts/{draft_id}/confirm") < paths.index(
        "/{full_path:path}"
    )

    await runtime.stop(app)
    await runtime.stop(app)

    remaining_paths = [getattr(route, "path", None) for route in app.router.routes]
    assert "/health" in remaining_paths
    assert "/{full_path:path}" in remaining_paths
    assert "/api/outfit/capability" not in remaining_paths
    assert "/api/outfit/admin/usage/today" not in remaining_paths
    assert "/api/outfit/wardrobe/drafts" not in remaining_paths
    assert "/api/outfit/wardrobe/items/available" not in remaining_paths
    assert "/api/outfit/wardrobe/drafts/{draft_id}/confirm" not in remaining_paths
