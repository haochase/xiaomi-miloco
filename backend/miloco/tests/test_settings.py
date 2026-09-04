# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""miloco.config.settings 单元测试。

- schema 自身合法性（jsonschema Draft 2020-12）
- Pydantic 模型与 settings.schema.json 字段对齐
- reset_settings() 后 env 覆盖生效
- 旧扁平 config.json 字段触发迁移异常
"""

from __future__ import annotations

import json
from pathlib import Path

import miloco.config.settings as settings_module
import pytest
import yaml
from jsonschema import Draft202012Validator
from miloco.config import SETTINGS_SCHEMA, get_settings, reset_settings
from miloco.config.settings import MilocoSettings, WeatherSettings


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """每个用例独立 $MILOCO_HOME，避免读到用户真实 config.json。"""
    monkeypatch.setenv("MILOCO_HOME", str(tmp_path))
    reset_settings()
    yield
    reset_settings()


def _load_schema() -> dict:
    return json.loads(SETTINGS_SCHEMA.read_text(encoding="utf-8"))


def test_schema_is_valid_draft_2020_12() -> None:
    schema = _load_schema()
    Draft202012Validator.check_schema(schema)


def test_outfit_settings_is_publicly_exported() -> None:
    """可选插件可显式导入 OutfitSettings，而不依赖内部模块实现。"""
    assert "OutfitSettings" in settings_module.__all__


def test_weather_settings_is_publicly_exported() -> None:
    """宿主天气组合可以显式导入 WeatherSettings。"""
    assert "WeatherSettings" in settings_module.__all__


def _collect_schema_fields(schema: dict, prefix: str = "") -> dict[str, dict]:
    """把 schema.properties 展开成扁平的 {dotted.path: field_spec}。"""
    out: dict[str, dict] = {}
    for name, spec in schema.get("properties", {}).items():
        key = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
        out[key] = spec
        if spec.get("type") == "object" and "properties" in spec:
            out.update(_collect_schema_fields(spec, key))
    return out


def _collect_pydantic_fields(
    model_json_schema: dict, prefix: str = ""
) -> dict[str, dict]:
    """展开 Pydantic model_json_schema() 的 properties（处理 $ref/$defs）。"""
    defs = model_json_schema.get("$defs", {})

    def resolve(spec: dict) -> dict:
        if "$ref" in spec:
            name = spec["$ref"].rsplit("/", 1)[-1]
            return defs.get(name, {})
        return spec

    def walk(props: dict, prefix: str, out: dict[str, dict]) -> None:
        for name, spec in props.items():
            spec = resolve(spec)
            key = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
            out[key] = spec
            if spec.get("type") == "object" and "properties" in spec:
                walk(spec["properties"], key, out)

    out: dict[str, dict] = {}
    walk(model_json_schema.get("properties", {}), prefix, out)
    return out


def _schema_types(spec: dict) -> set[str] | None:
    """将 JSON Schema 的 type 或 anyOf 规范化为类型集合。"""
    field_type = spec.get("type")
    if isinstance(field_type, str):
        return {field_type}
    if isinstance(field_type, list) and all(
        isinstance(value, str) for value in field_type
    ):
        return set(field_type)

    any_of = spec.get("anyOf")
    if not isinstance(any_of, list):
        return None
    types = {
        option["type"]
        for option in any_of
        if isinstance(option, dict) and isinstance(option.get("type"), str)
    }
    return types or None


def test_pydantic_matches_settings_schema() -> None:
    """schema.json 中声明的每个字段都必须在 MilocoSettings 中存在且类型/默认值一致。"""
    schema = _load_schema()
    schema_fields = _collect_schema_fields(schema)

    pydantic_schema = MilocoSettings.model_json_schema()
    pyd_fields = _collect_pydantic_fields(pydantic_schema)

    for path, spec in schema_fields.items():
        assert path in pyd_fields, (
            f"settings.schema.json 字段 {path} 未在 Pydantic 模型中出现"
        )
        pyd = pyd_fields[path]
        schema_types = _schema_types(spec)
        if schema_types is not None and spec.get("type") != "object":
            assert _schema_types(pyd) == schema_types, (
                f"{path} 类型不匹配："
                f"schema={sorted(schema_types)} vs "
                f"pydantic={sorted(_schema_types(pyd) or set())}"
            )
        if "default" in spec:
            assert pyd.get("default") == spec["default"], (
                f"{path} 默认值不匹配：schema={spec['default']!r} vs pydantic={pyd.get('default')!r}"
            )


def test_env_override_applies_after_reset(monkeypatch) -> None:
    s1 = get_settings()
    assert s1.server.url == "http://127.0.0.1:1810"

    monkeypatch.setenv("MILOCO_SERVER__URL", "http://example.com:9000")
    reset_settings()
    s2 = get_settings()
    assert s2.server.url == "http://example.com:9000"


def test_tier_u_dump_enable_default_false() -> None:
    """生产默认 perception.tier_u_dump_enable=false, 调试端点关闭。"""
    s = get_settings()
    assert s.perception.tier_u_dump_enable is False


def test_tier_u_dump_enable_env_override(monkeypatch) -> None:
    """支持环境变量 MILOCO_PERCEPTION__TIER_U_DUMP_ENABLE 切换。"""
    monkeypatch.setenv("MILOCO_PERCEPTION__TIER_U_DUMP_ENABLE", "true")
    reset_settings()
    assert get_settings().perception.tier_u_dump_enable is True


def test_features_default_off() -> None:
    """pet_recognition 默认关（住户需在 web 显式开）；grounding 子开关默认开。"""
    s = get_settings()
    assert s.features.pet_recognition is False
    assert s.features.pet_head_grounding is True
    assert s.features.pet_body_grounding is True


def test_features_env_override(monkeypatch) -> None:
    """支持 MILOCO_FEATURES__* 环境变量开启实验功能。"""
    monkeypatch.setenv("MILOCO_FEATURES__PET_RECOGNITION", "true")
    monkeypatch.setenv("MILOCO_FEATURES__PET_HEAD_GROUNDING", "true")
    reset_settings()
    s = get_settings()
    assert s.features.pet_recognition is True
    assert s.features.pet_head_grounding is True


def test_weather_defaults_are_disabled_and_location_free() -> None:
    """跟踪默认配置不启用天气，也不保存用户真实城市。"""
    weather = get_settings().weather

    assert weather.enabled is False
    assert weather.provider == "open_meteo"
    assert weather.city_name is None
    assert weather.country_code == "CN"
    assert weather.refresh_interval_seconds == 1_800
    assert weather.validity_seconds == 3_600


def test_weather_env_override_normalizes_beijing_and_country(monkeypatch) -> None:
    """私有部署可通过嵌套环境变量配置北京市。"""
    monkeypatch.setenv("MILOCO_WEATHER__ENABLED", "true")
    monkeypatch.setenv("MILOCO_WEATHER__CITY_NAME", "  北京市  ")
    monkeypatch.setenv("MILOCO_WEATHER__COUNTRY_CODE", " cn ")
    reset_settings()

    weather = get_settings().weather

    assert weather.enabled is True
    assert weather.city_name == "北京市"
    assert weather.country_code == "CN"


def test_enabled_weather_requires_nonblank_city() -> None:
    """启用天气但没有城市时必须关闭失败。"""
    with pytest.raises(ValueError, match="city_name"):
        WeatherSettings.model_validate({"enabled": True, "city_name": "  \t  "})


def test_weather_rejects_unlisted_provider() -> None:
    """配置不得注入任意 provider、模块或 URL。"""
    with pytest.raises(ValueError):
        WeatherSettings.model_validate(
            {
                "enabled": True,
                "provider": "https://private.invalid/weather",
                "city_name": "北京市",
            }
        )


def test_weather_rejects_endpoint_and_unknown_configuration() -> None:
    """天气配置不能覆盖固定 endpoint 或注入未审查字段。"""
    with pytest.raises(ValueError):
        WeatherSettings.model_validate(
            {
                "base_url": "https://private.invalid/weather",
                "module_path": "private.weather.Provider",
            }
        )


@pytest.mark.parametrize("country_code", ["", "C", "CHN", "C1", "中国"])
def test_weather_rejects_invalid_country_codes(country_code: str) -> None:
    with pytest.raises(ValueError, match="country_code"):
        WeatherSettings.model_validate({"country_code": country_code})


@pytest.mark.parametrize(
    "weather",
    [
        {"refresh_interval_seconds": 299},
        {"refresh_interval_seconds": 86_401},
        {"validity_seconds": 599},
        {"validity_seconds": 86_401},
        {"refresh_interval_seconds": 1_800, "validity_seconds": 1_800},
        {"refresh_interval_seconds": 3_600, "validity_seconds": 1_800},
    ],
)
def test_weather_rejects_unsafe_refresh_and_validity_windows(
    weather: dict[str, int],
) -> None:
    with pytest.raises(ValueError):
        WeatherSettings.model_validate(weather)


def test_outfit_feature_defaults() -> None:
    """Outfit 默认关闭，且不预设主使用者。"""
    outfit = get_settings().features.outfit
    assert outfit.enabled is False
    assert outfit.primary_person_id is None
    assert outfit.audit_hmac_key is None
    assert outfit.audit_hmac_key_version == "v1"


def test_outfit_feature_env_override_normalizes_primary_person_id(monkeypatch) -> None:
    """嵌套环境变量可开启 Outfit，并将主使用者 ID 去除首尾空白。"""
    monkeypatch.setenv("MILOCO_FEATURES__OUTFIT__ENABLED", "true")
    monkeypatch.setenv("MILOCO_FEATURES__OUTFIT__PRIMARY_PERSON_ID", "  chase  ")
    reset_settings()

    outfit = get_settings().features.outfit
    assert outfit.enabled is True
    assert outfit.primary_person_id == "chase"


def test_outfit_feature_normalizes_blank_primary_person_id_to_none() -> None:
    """空白主使用者 ID 不使配置加载失败，而是归一为 None。"""
    settings = MilocoSettings(
        features={"outfit": {"enabled": True, "primary_person_id": "  \t  "}}
    )
    assert settings.features.outfit.primary_person_id is None


def test_outfit_audit_secret_env_override_is_masked(monkeypatch) -> None:
    secret = "h6-secret-value-that-is-at-least-32-bytes"
    monkeypatch.setenv("MILOCO_FEATURES__OUTFIT__AUDIT_HMAC_KEY", secret)
    monkeypatch.setenv(
        "MILOCO_FEATURES__OUTFIT__AUDIT_HMAC_KEY_VERSION", " audit-v2 "
    )
    reset_settings()

    settings = get_settings()
    outfit = settings.features.outfit
    assert outfit.audit_hmac_key is not None
    assert outfit.audit_hmac_key.get_secret_value() == secret
    assert outfit.audit_hmac_key_version == "audit-v2"
    serialized_outputs = (
        repr(settings),
        repr(outfit),
        repr(settings.model_dump()),
        settings.model_dump_json(),
        json.dumps(MilocoSettings.model_json_schema()),
    )
    assert all(secret not in output for output in serialized_outputs)


def test_outfit_audit_blank_secret_normalizes_to_none() -> None:
    settings = MilocoSettings(
        features={"outfit": {"audit_hmac_key": "  \t  "}}
    )

    assert settings.features.outfit.audit_hmac_key is None


@pytest.mark.parametrize(
    "version",
    ("", "   ", "unsafe version", "-leading", "v" * 33),
)
def test_outfit_audit_key_version_rejects_unsafe_values(version: str) -> None:
    with pytest.raises(ValueError):
        MilocoSettings(
            features={"outfit": {"audit_hmac_key_version": version}}
        )


def test_outfit_audit_validation_error_masks_secret_input() -> None:
    secret = "validation-secret-that-must-never-be-rendered"

    with pytest.raises(ValueError) as exc_info:
        MilocoSettings(
            features={
                "outfit": {
                    "audit_hmac_key": secret,
                    "audit_hmac_key_version": "unsafe version",
                }
            }
        )

    assert secret not in str(exc_info.value)
    assert secret not in repr(exc_info.value)


def test_outfit_audit_schema_and_yaml_contain_placeholders_only() -> None:
    schema = _load_schema()
    outfit_schema = schema["properties"]["features"]["properties"]["outfit"]
    key_schema = outfit_schema["properties"]["audit_hmac_key"]
    version_schema = outfit_schema["properties"]["audit_hmac_key_version"]
    defaults = yaml.safe_load(
        (Path(settings_module.__file__ or "").with_name("settings.yaml")).read_text(
            encoding="utf-8"
        )
    )

    assert _schema_types(key_schema) == {"string", "null"}
    assert key_schema["default"] is None
    assert key_schema["writeOnly"] is True
    assert version_schema["default"] == "v1"
    assert defaults["features"]["outfit"]["audit_hmac_key"] is None
    assert defaults["features"]["outfit"]["audit_hmac_key_version"] == "v1"


def test_outfit_database_paths_are_derived_beneath_absolute_workspace(
    tmp_path: Path,
) -> None:
    settings = MilocoSettings(directories={"storage": str(tmp_path)})
    root = settings.directories.workspace_dir / "outfit"
    database_paths = tuple(root / name for name in ("wardrobe.db", "audit.db", "usage.db"))

    assert root.is_absolute()
    assert all(path.is_absolute() and path.parent == root for path in database_paths)
    assert "database_path" not in settings.features.outfit.__class__.model_fields


def test_notify_dedup_window_default() -> None:
    """通知去重窗口默认 60s。"""
    assert get_settings().notify.dedup_window_sec == 60.0


def test_notify_dedup_window_env_override(monkeypatch) -> None:
    """支持 env / config.json 覆盖去重窗口。"""
    monkeypatch.setenv("MILOCO_NOTIFY__DEDUP_WINDOW_SEC", "30")
    reset_settings()
    assert get_settings().notify.dedup_window_sec == 30.0


def test_notify_dedup_window_negative_loads_not_rejected(monkeypatch) -> None:
    """负值不被 pydantic 拒绝（避免误配一个字段崩整个 settings 加载）；
    <=0 交由 MessageDeduper 当作「关闭去重」，与 TS getNotifyDedupWindowMs 归零一致。"""
    monkeypatch.setenv("MILOCO_NOTIFY__DEDUP_WINDOW_SEC", "-5")
    reset_settings()
    assert get_settings().notify.dedup_window_sec == -5.0


def test_directory_paths_derive_from_miloco_home(tmp_path: Path) -> None:
    s = get_settings()
    assert s.directories.workspace_dir == tmp_path
    assert s.directories.image_dir == tmp_path / "images"
    assert s.directories.log_dir == tmp_path / "log"
    assert s.directories.miot_cache_dir == tmp_path / "miot_cache"


def test_model_defaults_align_with_schema() -> None:
    s = get_settings()
    assert s.model.omni.model == "xiaomi/mimo-v2.5"
    assert s.model.omni.base_url == "https://api.xiaomimimo.com/v1"
    assert s.model.omni.api_key == ""
    assert s.agent.webhook_url == "http://127.0.0.1:18789/miloco/webhook"
    assert s.agent.auth_bearer == ""
    assert s.server.python_bin == ""
    assert s.debug is False


# SSL 已废弃：backend 永远 HTTP，跨网加密走反代。原 ssl_enabled / ssl_certfile /
# ssl_keyfile computed_field 已删除，对应 5 个测试一并移除。tls_certfile / tls_keyfile
# 字段保留仅用于触发 utils/uvicorn.py 的 deprecation warning。


class TestServerUrlHostPortValidator:
    """server.url 与 server.host/port 一致性校验。"""

    def _make(self, **overrides) -> MilocoSettings:
        """构造 MilocoSettings 并触发 model_validator。"""
        base = {
            "server": {"url": "http://127.0.0.1:1810", "host": "127.0.0.1", "port": 1810},
        }
        for k, v in overrides.items():
            base["server"][k] = v
        return MilocoSettings(**base)

    def test_matching_config_no_warning(self, caplog):
        """默认配置完全一致，不触发 warning。"""
        import logging

        with caplog.at_level(logging.WARNING):
            self._make()
        assert not any("配置不一致" in r.message for r in caplog.records)

    def test_port_mismatch_warns(self, caplog):
        """url 端口与 server.port 不一致时触发 warning。"""
        import logging

        with caplog.at_level(logging.WARNING):
            self._make(port=1811)
        assert any("配置不一致" in r.message for r in caplog.records)

    def test_host_mismatch_warns(self, caplog):
        """url host 与 server.host 不一致时触发 warning。"""
        import logging

        with caplog.at_level(logging.WARNING):
            self._make(host="192.168.1.100")
        assert any("配置不一致" in r.message for r in caplog.records)

    def test_bind_all_only_checks_port(self, caplog):
        """host=0.0.0.0 时，url host 不同不告警，仅检查 port。"""
        import logging

        with caplog.at_level(logging.WARNING):
            self._make(host="0.0.0.0", url="http://192.168.1.50:1810")
        assert not any("配置不一致" in r.message for r in caplog.records)

    def test_bind_all_port_mismatch_warns(self, caplog):
        """host=0.0.0.0 但端口不一致时仍触发 warning。"""
        import logging

        with caplog.at_level(logging.WARNING):
            self._make(host="0.0.0.0", port=9999)
        assert any("配置不一致" in r.message for r in caplog.records)

    def test_localhost_normalized_no_warning(self, caplog):
        """localhost 与 127.0.0.1 视为等价，不触发 warning。"""
        import logging

        with caplog.at_level(logging.WARNING):
            self._make(url="http://localhost:1810", host="127.0.0.1")
        assert not any("配置不一致" in r.message for r in caplog.records)

    def test_default_port_http_no_warning(self, caplog):
        """http://host 不带端口时推断 80，与 port=80 匹配。"""
        import logging

        with caplog.at_level(logging.WARNING):
            self._make(url="http://127.0.0.1", port=80)
        assert not any("配置不一致" in r.message for r in caplog.records)
