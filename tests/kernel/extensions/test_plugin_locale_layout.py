from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOTS = (
    REPO_ROOT / "plugins" / "system",
    REPO_ROOT / "plugins" / "preinstalled",
)
PLUGIN_DATA_ROOT = REPO_ROOT / "plugin-data"


def _frontend_manifests() -> list[Path]:
    manifests: list[Path] = []
    for root in PLUGIN_ROOTS:
        manifests.extend(sorted(root.glob("*/frontend/plugin.json")))
    return manifests


def _json_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_i18n_plugins_ship_default_locale_in_plugin_package() -> None:
    missing_default_locale: list[str] = []

    for manifest_path in _frontend_manifests():
        manifest = _json_object(manifest_path)
        frontend = manifest.get("frontend")
        assert isinstance(frontend, dict)
        namespaces = frontend.get("i18n_namespaces") or []
        assert isinstance(namespaces, list)
        if not namespaces:
            continue

        default_locale = manifest_path.parent / "locales" / "en.json"
        if not default_locale.exists():
            missing_default_locale.append(manifest_path.parents[1].name)
            continue

        assert _json_object(default_locale)

    assert missing_default_locale == []


def test_plugin_package_locales_are_default_language_only() -> None:
    non_default_package_locales: list[str] = []

    for manifest_path in _frontend_manifests():
        locale_dir = manifest_path.parent / "locales"
        if not locale_dir.exists():
            continue
        for locale_file in sorted(locale_dir.glob("*.json")):
            if locale_file.name != "en.json":
                non_default_package_locales.append(str(locale_file.relative_to(REPO_ROOT)))

    assert non_default_package_locales == []


def test_plugin_data_locales_are_supplemental_only() -> None:
    default_locale_overrides = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted(PLUGIN_DATA_ROOT.glob("*/frontend/locales/en.json"))
    ]

    assert default_locale_overrides == []


def test_frontend_loads_plugin_data_locale_overrides_after_bundled_defaults() -> None:
    source = (REPO_ROOT / "frontend" / "src" / "i18n" / "pluginLocales.ts").read_text(
        encoding="utf-8"
    )
    i18n_source = (REPO_ROOT / "frontend" / "src" / "i18n" / "index.ts").read_text(
        encoding="utf-8"
    )

    assert "../../../plugins/system/*/frontend/locales/*.json" in source
    assert "../../../plugins/preinstalled/*/frontend/locales/*.json" in source
    assert "../../../plugin-data/*/frontend/locales/*.json" in source
    assert "loadSupplementalPluginLocaleResources" in source
    assert "mergePluginLocaleResourceSets(" in source
    assert "loadPluginLocaleResources()" in i18n_source
