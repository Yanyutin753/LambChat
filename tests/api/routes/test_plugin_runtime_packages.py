from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from src.api.routes.plugin_runtime_packages import (
    _archived_package_response,
    _attach_descriptor_metadata,
    _merge_manifest_frontend,
    _merge_manifest_resources,
    _package_descriptor_response,
    _package_manifest_with_static_fallback,
    _static_fallback_fields,
)


class _Frontend:
    def __init__(self, values: dict):
        self.values = values

    def model_dump(self, **kwargs):
        if kwargs.get("exclude_defaults"):
            return {key: value for key, value in self.values.items() if value}
        return self.values

    def model_copy(self, *, update):
        return _Frontend(update)


class _Manifest:
    def __init__(self, **values):
        self.__dict__.update(values)
        self.copied_update = None

    def model_copy(self, *, update):
        copied = _Manifest(**self.__dict__)
        copied.copied_update = update
        return copied


class _Layout:
    data_template = {"exists": True}

    def model_dump(self):
        return {"has_backend": True}


def _descriptor():
    return SimpleNamespace(
        plugin_id="demo",
        source_type="installed",
        folder=Path("plugins/demo"),
        manifest_path=Path("plugins/demo/plugin.yaml"),
        data_dir=Path("plugin-data/demo"),
        validated_at=datetime(2026, 7, 11, tzinfo=UTC),
        valid=True,
        errors=(),
        layout=_Layout(),
    )


def _manifest_fields(*, populated: bool):
    value = ["present"] if populated else []
    return {
        "settings": value,
        "legacy_system_settings": value,
        "routers": value,
        "tools": value,
        "lifespan_hooks": value,
        "scheduler_jobs": value,
        "event_listeners": value,
        "migrations": value,
        "resources": value,
        "frontend": _Frontend({"routes": value}),
    }


def test_static_fallback_fields_reports_every_missing_manifest_surface() -> None:
    package_manifest = _Manifest(**_manifest_fields(populated=False))
    static_manifest = _Manifest(**_manifest_fields(populated=True))

    assert _static_fallback_fields(package_manifest, static_manifest) == [
        "settings",
        "legacy_system_settings",
        "routers",
        "tools",
        "lifespan_hooks",
        "scheduler_jobs",
        "event_listeners",
        "migrations",
        "resources",
        "frontend",
    ]


def test_package_manifest_preserves_package_authority_and_records_fallbacks() -> None:
    package_manifest = _Manifest(
        **_manifest_fields(populated=False),
        package_config_defaults={"enabled": True},
        package_data_template={"exists": True},
        package_frontend_assets={"slots": []},
    )
    static_manifest = _Manifest(**_manifest_fields(populated=True))

    result = _package_manifest_with_static_fallback(
        package_manifest,
        static_manifest=static_manifest,
        descriptor=_descriptor(),
    )

    assert result.copied_update["package_manifest_authority"] == "folder_package"
    assert result.copied_update["package_static_fallback_used"] is True
    assert result.copied_update["package_static_fallback_fields"] == _static_fallback_fields(
        package_manifest, static_manifest
    )


def test_descriptor_metadata_and_responses_preserve_package_evidence() -> None:
    descriptor = _descriptor()
    manifest = _Manifest()

    result = _attach_descriptor_metadata(manifest, descriptor)
    assert Path(result.copied_update["package_source_path"]) == Path("plugins/demo")
    assert result.copied_update["package_layout"] == {"has_backend": True}
    assert result.copied_update["package_data_template"] == {"exists": True}

    response = _package_descriptor_response(descriptor)
    assert response.plugin_id == "demo"
    assert response.valid is True
    assert response.layout == {"has_backend": True}


def test_manifest_merges_deduplicate_resources_and_frontend_contributions() -> None:
    route_a = SimpleNamespace(type="route", id="a")
    route_a_duplicate = SimpleNamespace(type="route", id="a")
    route_b = SimpleNamespace(type="route", id="b")
    manifest = SimpleNamespace(
        resources=[route_a],
        frontend=_Frontend(
            {
                "routes": ["/a"],
                "panels": [{"id": "existing", "renderer": "Existing"}],
            }
        ),
    )
    package_manifest = SimpleNamespace(
        resources=[route_a_duplicate, route_b],
        frontend=_Frontend(
            {
                "routes": ["/a", "/b"],
                "panels": [
                    {"id": "existing", "renderer": "Duplicate"},
                    {"id": "new", "renderer": "New"},
                ],
            }
        ),
    )

    assert _merge_manifest_resources(manifest, package_manifest) == [route_a, route_b]
    frontend = _merge_manifest_frontend(manifest, package_manifest)
    assert frontend.values["routes"] == ["/a", "/b"]
    assert frontend.values["panels"] == [
        {"id": "existing", "renderer": "Existing"},
        {"id": "new", "renderer": "New"},
    ]


def test_archived_package_response_preserves_integrity_and_errors() -> None:
    item = SimpleNamespace(
        archive_id="archive-1",
        plugin_id="demo",
        archive_path="archive/demo",
        manifest_path="archive/demo/plugin.yaml",
        data_dir="archive/demo/data",
        archived_at=datetime(2026, 7, 11, tzinfo=UTC),
        integrity=SimpleNamespace(model_dump=lambda: {"sha256": "abc"}),
        valid=False,
        errors=["checksum mismatch"],
    )

    response = _archived_package_response(item)
    assert response.archive_id == "archive-1"
    assert response.integrity == {"sha256": "abc"}
    assert response.errors == ["checksum mismatch"]
