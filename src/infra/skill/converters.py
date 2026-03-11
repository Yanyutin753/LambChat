"""
Document conversion functions for skill storage
"""

import copy
from typing import Any

from src.kernel.schemas.skill import SkillResponse, SkillSource, SystemSkill, UserSkill


def doc_to_system_skill(doc: dict[str, Any]) -> SystemSkill:
    """Convert MongoDB document to SystemSkill"""
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")

    if created_at and hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    if updated_at and hasattr(updated_at, "isoformat"):
        updated_at = updated_at.isoformat()

    return SystemSkill(
        name=doc["name"],
        description=doc.get("description", ""),
        content=doc.get("content", ""),
        files=doc.get("files", {}),
        enabled=doc.get("enabled", True),
        source=SkillSource(doc.get("source", "manual")),
        github_url=doc.get("github_url"),
        version=doc.get("version"),
        is_system=True,
        created_at=created_at,
        updated_at=updated_at,
        updated_by=doc.get("updated_by"),
    )


def doc_to_user_skill(doc: dict[str, Any]) -> UserSkill:
    """Convert MongoDB document to UserSkill"""
    created_at = doc.get("created_at")
    updated_at = doc.get("updated_at")

    if created_at and hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    if updated_at and hasattr(updated_at, "isoformat"):
        updated_at = updated_at.isoformat()

    return UserSkill(
        name=doc["name"],
        description=doc.get("description", ""),
        content=doc.get("content", ""),
        files=doc.get("files", {}),
        enabled=doc.get("enabled", True),
        source=SkillSource(doc.get("source", "manual")),
        github_url=doc.get("github_url"),
        version=doc.get("version"),
        user_id=doc["user_id"],
        is_system=False,
        created_at=created_at,
        updated_at=updated_at,
    )


def doc_to_response(doc: dict[str, Any], is_system: bool, can_edit: bool) -> SkillResponse:
    """Convert MongoDB document to SkillResponse"""
    # Deep copy to avoid modifying original
    doc_copy = copy.deepcopy(doc)

    # Convert datetime to ISO string if needed
    created_at = doc_copy.get("created_at")
    updated_at = doc_copy.get("updated_at")

    if created_at and hasattr(created_at, "isoformat"):
        created_at = created_at.isoformat()
    if updated_at and hasattr(updated_at, "isoformat"):
        updated_at = updated_at.isoformat()

    return SkillResponse(
        name=doc_copy["name"],
        description=doc_copy.get("description", ""),
        content=doc_copy.get("content", ""),
        files=doc_copy.get("files", {}),
        enabled=doc_copy.get("enabled", True),
        source=SkillSource(doc_copy.get("source", "manual")),
        github_url=doc_copy.get("github_url"),
        version=doc_copy.get("version"),
        is_system=is_system,
        can_edit=can_edit,
        created_at=created_at,
        updated_at=updated_at,
    )


def doc_to_effective_dict(doc: dict[str, Any], is_system: bool = True) -> dict[str, Any]:
    """Convert MongoDB document to effective dict format"""
    result = {
        "name": doc["name"],
        "description": doc.get("description", ""),
        "content": doc.get("content", ""),
        "is_system": is_system,
    }
    if doc.get("github_url"):
        result["github_url"] = doc["github_url"]
    if doc.get("version"):
        result["version"] = doc["version"]
    return result


def doc_to_export_dict(doc: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB document to export dict format"""
    result = {
        "description": doc.get("description", ""),
        "content": doc.get("content", ""),
        "enabled": doc.get("enabled", True),
        "source": doc.get("source", "manual"),
    }
    if doc.get("github_url"):
        result["github_url"] = doc["github_url"]
    if doc.get("version"):
        result["version"] = doc["version"]
    return result
