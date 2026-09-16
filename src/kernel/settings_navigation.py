"""Settings information architecture shared with API clients."""

from src.kernel.schemas.setting import SettingCategory, SettingItem, SettingsNavigationGroup

SETTINGS_NAVIGATION = (
    SettingsNavigationGroup(
        id="experience", categories=[SettingCategory.FRONTEND, SettingCategory.SESSION]
    ),
    SettingsNavigationGroup(
        id="intelligence",
        categories=[SettingCategory.AGENT, SettingCategory.LLM, SettingCategory.SCHEDULED_TASK],
    ),
    SettingsNavigationGroup(
        id="memory",
        categories=[
            SettingCategory.MEMORY,
            SettingCategory.MEMORY_EMBEDDING,
            SettingCategory.MEMORY_SEARCH,
            SettingCategory.MEMORY_STORAGE,
        ],
    ),
    SettingsNavigationGroup(
        id="capabilities",
        categories=[
            SettingCategory.TOOLS,
            SettingCategory.SKILLS,
            SettingCategory.SANDBOX,
            SettingCategory.FILE_UPLOAD,
            SettingCategory.DOCUMENT_PARSE,
            SettingCategory.AUDIO_TRANSCRIPTION,
        ],
    ),
    SettingsNavigationGroup(
        id="access",
        categories=[
            SettingCategory.USER,
            SettingCategory.SECURITY,
            SettingCategory.OAUTH,
            SettingCategory.CAPTCHA,
            SettingCategory.EMAIL,
        ],
    ),
    SettingsNavigationGroup(
        id="infrastructure",
        categories=[
            SettingCategory.MONGODB,
            SettingCategory.REDIS,
            SettingCategory.CHECKPOINT,
            SettingCategory.LONG_TERM_STORAGE,
            SettingCategory.S3,
            SettingCategory.TRACING,
        ],
    ),
)


def build_settings_navigation(
    settings: dict[str, list[SettingItem]],
) -> list[SettingsNavigationGroup]:
    """Only expose categories present after the service's permission filtering."""
    result = []
    for group in SETTINGS_NAVIGATION:
        categories = [category for category in group.categories if settings.get(category.value)]
        if categories:
            result.append(SettingsNavigationGroup(id=group.id, categories=categories))
    return result
