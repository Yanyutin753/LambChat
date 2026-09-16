from src.kernel.schemas.setting import SettingCategory, SettingItem, SettingType
from src.kernel.settings_navigation import SETTINGS_NAVIGATION, build_settings_navigation


def test_navigation_covers_every_category_exactly_once():
    categories = [category for group in SETTINGS_NAVIGATION for category in group.categories]
    assert len(categories) == len(set(categories))
    assert set(categories) == set(SettingCategory)


def test_navigation_only_exposes_categories_in_the_permission_filtered_response():
    setting = SettingItem(
        key="EXAMPLE",
        value=True,
        type=SettingType.BOOLEAN,
        category=SettingCategory.SCHEDULED_TASK,
    )
    groups = build_settings_navigation({"scheduled_task": [setting], "redis": []})
    assert len(groups) == 1
    assert groups[0].id == "intelligence"
    assert groups[0].categories == [SettingCategory.SCHEDULED_TASK]


def test_navigation_responses_do_not_mutate_the_shared_catalog():
    setting = SettingItem(
        key="A", value=True, type=SettingType.BOOLEAN, category=SettingCategory.FRONTEND
    )
    first = build_settings_navigation({"frontend": [setting]})
    first[0].categories.clear()
    assert build_settings_navigation({"frontend": [setting]})[0].categories == [
        SettingCategory.FRONTEND
    ]
