# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Configuration-to-host wiring contracts for the optional Outfit plugin."""

from __future__ import annotations

import ast
import builtins
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI


def _settings(
    *,
    enabled: bool,
    primary_person_id: str | None,
    workspace_dir: Path,
) -> SimpleNamespace:
    return SimpleNamespace(
        features=SimpleNamespace(
            outfit=SimpleNamespace(
                enabled=enabled,
                primary_person_id=primary_person_id,
            )
        ),
        directories=SimpleNamespace(workspace_dir=workspace_dir),
    )


def test_activation_keeps_disabled_outfit_routes_absent(tmp_path) -> None:
    from miloco.life.outfit_host_activation import install_outfit_from_settings

    app = FastAPI()
    result = install_outfit_from_settings(
        app,
        settings=_settings(
            enabled=False,
            primary_person_id=None,
            workspace_dir=tmp_path,
        ),
        clock_ms=lambda: 2_000,
    )

    assert not result.installed
    assert result.reason == "disabled"
    assert not any(route.path.startswith("/api/outfit") for route in app.routes)


def test_activation_passes_explicit_feature_configuration_to_composition(
    tmp_path,
    monkeypatch,
) -> None:
    from miloco.life import outfit_host_activation
    from miloco.life.outfit_installation import OutfitInstallResult

    captured = {}

    def fake_install(app, *, config, clock_ms):
        captured["app"] = app
        captured["config"] = config
        captured["clock_ms"] = clock_ms
        return OutfitInstallResult(installed=True, reason="installed")

    monkeypatch.setattr(
        outfit_host_activation,
        "install_outfit_host_composition",
        fake_install,
    )
    app = FastAPI()
    result = outfit_host_activation.install_outfit_from_settings(
        app,
        settings=_settings(
            enabled=True,
            primary_person_id="primary-person",
            workspace_dir=tmp_path,
        ),
        clock_ms=lambda: 2_000,
    )

    assert result == OutfitInstallResult(installed=True, reason="installed")
    assert captured["app"] is app
    assert captured["config"].enabled is True
    assert captured["config"].primary_person_id == "primary-person"
    assert captured["config"].workspace_dir == tmp_path
    assert captured["clock_ms"]() == 2_000


def test_main_ignores_an_optional_outfit_import_failure(tmp_path, monkeypatch) -> None:
    main_path = Path(__file__).parents[1] / "src" / "miloco" / "main.py"
    namespace = {
        "FastAPI": FastAPI,
        "logger": type("Logger", (), {"warning": lambda *_args, **_kwargs: None})(),
    }
    function = next(
        node
        for node in ast.parse(main_path.read_text(encoding="utf-8")).body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_install_optional_outfit_plugin"
    )
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(main_path), "exec"),
        namespace,
    )
    original_import = builtins.__import__

    def reject_outfit_activation(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "miloco.life.outfit_host_activation":
            raise ImportError("optional adapter unavailable")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_outfit_activation)
    result = namespace["_install_optional_outfit_plugin"](
        FastAPI(),
        settings=_settings(
            enabled=True,
            primary_person_id="primary-person",
            workspace_dir=tmp_path,
        ),
    )

    assert result is None


def test_main_declares_a_lazy_optional_outfit_activation() -> None:
    """Keep main free of top-level Outfit imports on Windows and disabled hosts."""
    main_path = Path(__file__).parents[1] / "src" / "miloco" / "main.py"
    module = ast.parse(main_path.read_text(encoding="utf-8"))
    imports = [
        node.module
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module
    ]

    assert "miloco.life.outfit_host_activation" not in imports
    assert any(
        isinstance(node, ast.FunctionDef)
        and node.name == "_install_optional_outfit_plugin"
        for node in module.body
    )
