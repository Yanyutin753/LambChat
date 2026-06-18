"""Feedback static plugin boundary."""

from typing import Any

__all__ = [
    "FEEDBACK_PLUGIN_ID",
    "PluginMigrationAssessment",
    "PluginMigrationGateEvidence",
    "assess_feedback_plugin_migration",
    "build_feedback_plugin_manifest",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)

    from src.plugins.feedback import manifest

    return getattr(manifest, name)
