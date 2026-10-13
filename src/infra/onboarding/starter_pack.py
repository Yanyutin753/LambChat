"""Install editable starter skills once; publish shared, copyable personas."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from src.infra.logging import get_logger
from src.infra.persona_preset.storage import PersonaPresetStorage
from src.infra.skill.storage import SkillStorage
from src.infra.user.storage import UserStorage
from src.infra.utils.datetime import utc_now, utc_now_iso
from src.kernel.config import settings

logger = get_logger(__name__)
ROOT = Path(__file__).parent


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


async def ensure_starter_personas() -> None:
    storage = PersonaPresetStorage()
    for item in load_catalog():
        preset_id = ObjectId(hashlib.sha256(item["skill_name"].encode()).hexdigest()[:24])
        now = utc_now()
        doc = {
            "_id": preset_id,
            "name": item["name"]["en"],
            "description": item["description"]["en"],
            "scope": "global",
            "visibility": "public",
            "status": "published",
            "owner_user_id": None,
            "avatar": item["icon"],
            "tags": ["starter"],
            "starter_search_text": " ".join(
                [*item["name"].values(), *item["description"].values()]
            ),
            "system_prompt": item["system_prompt"],
            "skill_names": item["skill_names"],
            "mcp_server_names": [],
            "starter_prompts": [{"text": text} for text in item["starter_prompts"]],
            "version": 1,
            "usage_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        try:
            await storage.collection.update_one(
                {"_id": preset_id}, {"$setOnInsert": doc}, upsert=True
            )
        except DuplicateKeyError:
            # Another startup worker inserted the same deterministic preset.
            pass


async def ensure_user_starter_pack(user_id: str) -> None:
    if not settings.ENABLE_SKILLS:
        return
    users = UserStorage().collection
    user_key = {"_id": ObjectId(user_id)}
    user = await users.find_one(user_key, {"metadata.starter_skills": 1})
    if not user:
        return
    completed = set((user.get("metadata") or {}).get("starter_skills", []))
    storage = SkillStorage()
    files = storage._get_files_collection()
    for item in load_catalog():
        name = item["skill_name"]
        if name in completed:
            continue
        key = {"user_id": user_id, "skill_name": name}
        existing = await files.find_one(key)
        meta = await files.find_one({**key, "file_path": "__meta__"})
        try:
            metadata = json.loads(meta["content"]) if meta else {}
        except (ValueError, TypeError):
            metadata = {}
        is_partial_starter = isinstance(metadata, dict) and metadata.get("starter_pack") == 1
        if not existing or is_partial_starter:
            now = utc_now_iso()
            skill_files = {
                path.relative_to(ROOT / "skills" / name).as_posix(): path.read_text(
                    encoding="utf-8"
                )
                for path in sorted((ROOT / "skills" / name).rglob("*"))
                if path.is_file() and "__pycache__" not in path.parts
            }
            if "SKILL.md" not in skill_files:
                raise ValueError(f"Starter skill {name} is missing SKILL.md")
            skill_files = {
                "__meta__": json.dumps(
                    {
                        "installed_from": "manual",
                        "starter_pack": 1,
                        "created_at": now,
                        "updated_at": now,
                    }
                ),
                **skill_files,
            }
            for path, content in skill_files.items():
                try:
                    await files.update_one(
                        {**key, "file_path": path},
                        {
                            "$setOnInsert": {
                                **key,
                                "file_path": path,
                                "content": content,
                                "created_at": now,
                                "updated_at": now,
                            }
                        },
                        upsert=True,
                    )
                except DuplicateKeyError:
                    pass
            await storage.invalidate_user_cache(user_id)
        # Remember skipped collisions too; deletion must not reinstall user content.
        await users.update_one(user_key, {"$addToSet": {"metadata.starter_skills": name}})


async def initialize_user_starter_pack(user_id: str) -> None:
    """Onboarding failure must not turn a successfully created account into a failed signup."""
    try:
        await ensure_user_starter_pack(user_id)
    except Exception:
        logger.exception(
            "Starter pack initialization failed for user %s; retry on next /me", user_id
        )


def localize_starter_persona(preset, language: str):
    """Translate untouched starter labels, preserving user/admin customization."""
    language = language.split("-")[0].split(",")[0].lower() if isinstance(language, str) else "en"
    for item in load_catalog():
        ident = hashlib.sha256(item["skill_name"].encode()).hexdigest()[:24]
        preset_id = getattr(preset, "id", getattr(preset, "preset_id", None))
        if preset_id != ident or getattr(preset, "scope", "global") != "global":
            continue
        updates = {}
        for field in ("name", "description"):
            if getattr(preset, field, None) == item[field]["en"]:
                updates[field] = item[field].get(language, item[field]["en"])
        return preset.model_copy(update=updates)
    return preset


def localize_starter_skill(skill, language: str):
    language = language.split("-")[0].split(",")[0].lower() if isinstance(language, str) else "en"
    for item in load_catalog():
        if (
            skill.skill_name == item["skill_name"]
            and skill.description == item["description"]["en"]
        ):
            return skill.model_copy(
                update={"description": item["description"].get(language, item["description"]["en"])}
            )
    return skill
