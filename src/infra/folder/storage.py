"""Project storage layer for session organization."""

from datetime import datetime
from typing import Optional

from bson import ObjectId

from src.kernel.config import settings
from src.kernel.schemas.project import Project, ProjectCreate, ProjectUpdate


class ProjectStorage:
    """
    Project storage class using MongoDB.

    Manages projects for organizing user sessions, including the special "favorites" project.
    """

    PROJECT_COLLECTION = "projects"

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """Lazy-load MongoDB collection."""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[self.PROJECT_COLLECTION]
        return self._collection

    async def create(self, project_data: ProjectCreate, user_id: str) -> Project:
        """Create a new project."""
        now = datetime.now()

        project_dict = {
            "name": project_data.name,
            "type": project_data.type,
            "sort_order": project_data.sort_order,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(project_dict)
        project_dict["id"] = str(result.inserted_id)

        return Project(**project_dict)

    async def get_by_id(self, project_id: str, user_id: str) -> Optional[Project]:
        """Get a project by ID for a specific user."""
        try:
            project_dict = await self.collection.find_one(
                {"_id": ObjectId(project_id), "user_id": user_id}
            )
        except Exception:
            return None

        if not project_dict:
            return None

        project_dict["id"] = str(project_dict.pop("_id"))
        return Project(**project_dict)

    async def get_by_type(self, user_id: str, project_type: str) -> Optional[Project]:
        """Get a project by type for a specific user (e.g., 'favorites')."""
        project_dict = await self.collection.find_one({"user_id": user_id, "type": project_type})

        if not project_dict:
            return None

        project_dict["id"] = str(project_dict.pop("_id"))
        return Project(**project_dict)

    async def list_projects(self, user_id: str) -> list[Project]:
        """List all projects for a user, sorted by sort_order."""
        cursor = self.collection.find({"user_id": user_id}).sort("sort_order", 1)
        projects = []

        for project_dict in await cursor.to_list(length=100):
            project_dict["id"] = str(project_dict.pop("_id"))
            projects.append(Project(**project_dict))

        return projects

    async def update(
        self, project_id: str, user_id: str, project_data: ProjectUpdate
    ) -> Optional[Project]:
        """Update a project."""
        update_dict: dict = {"updated_at": datetime.now()}

        if project_data.name is not None:
            update_dict["name"] = project_data.name

        if project_data.sort_order is not None:
            update_dict["sort_order"] = project_data.sort_order

        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(project_id), "user_id": user_id},
                {"$set": update_dict},
                return_document=True,
            )
        except Exception:
            return None

        if not result:
            return None

        result["id"] = str(result.pop("_id"))
        return Project(**result)

    async def delete(self, project_id: str, user_id: str) -> bool:
        """Delete a project.

        Note: This does not delete the sessions in the project, only the project itself.
        """
        try:
            result = await self.collection.delete_one(
                {"_id": ObjectId(project_id), "user_id": user_id}
            )
            return result.deleted_count > 0
        except Exception:
            return False

    async def ensure_favorites_project(self, user_id: str) -> Project:
        """Ensure the favorites project exists for a user.

        Creates the favorites project if it doesn't exist.
        Returns the favorites project.
        """
        # Check if favorites project already exists
        existing = await self.get_by_type(user_id, "favorites")
        if existing:
            return existing

        # Create the favorites project
        now = datetime.now()
        project_dict = {
            "name": "Favorites",
            "type": "favorites",
            "sort_order": 0,  # Favorites always first
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(project_dict)
        project_dict["id"] = str(result.inserted_id)

        return Project(**project_dict)


# Singleton instance
_project_storage: Optional[ProjectStorage] = None


def get_project_storage() -> ProjectStorage:
    """Get project storage singleton."""
    global _project_storage
    if _project_storage is None:
        _project_storage = ProjectStorage()
    return _project_storage
