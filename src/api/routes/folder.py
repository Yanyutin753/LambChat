"""
文件夹路由

所有文件夹操作都需要认证，用户只能访问自己的文件夹。
"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.deps import get_current_user_required
from src.infra.folder.storage import get_folder_storage
from src.infra.session.storage import SessionStorage
from src.kernel.schemas.folder import Folder, FolderCreate, FolderUpdate
from src.kernel.schemas.user import TokenPayload

router = APIRouter()


@router.get("", response_model=list[Folder])
async def list_folders(
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    列出所有文件夹

    自动确保收藏文件夹存在。
    """
    storage = get_folder_storage()

    # Ensure favorites folder exists
    await storage.ensure_favorites_folder(user.sub)

    folders = await storage.list_folders(user.sub)
    return folders


@router.post("", response_model=Folder, status_code=status.HTTP_201_CREATED)
async def create_folder(
    folder_data: FolderCreate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    创建文件夹

    不允许创建 type="favorites" 的文件夹。
    """
    storage = get_folder_storage()

    # Prevent creating favorites folder manually
    if folder_data.type == "favorites":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能创建收藏文件夹",
        )

    folder = await storage.create(folder_data, user.sub)
    return folder


@router.patch("/{folder_id}", response_model=Folder)
async def update_folder(
    folder_id: str,
    folder_data: FolderUpdate,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新文件夹（重命名）

    只能更新自己拥有的文件夹。
    """
    storage = get_folder_storage()

    # Check if folder exists and belongs to user
    folder = await storage.get_by_id(folder_id, user.sub)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在",
        )

    updated_folder = await storage.update(folder_id, user.sub, folder_data)
    if not updated_folder:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="更新失败",
        )

    return updated_folder


@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: str,
    user: TokenPayload = Depends(get_current_user_required),
):
    """
    删除文件夹

    - 不能删除收藏文件夹
    - 文件夹内的会话会被移动到未分类
    """
    storage = get_folder_storage()

    # Check if folder exists and belongs to user
    folder = await storage.get_by_id(folder_id, user.sub)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文件夹不存在",
        )

    # Prevent deleting favorites folder
    if folder.type == "favorites":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除收藏文件夹",
        )

    # Clear folder_id for all sessions in this folder
    session_storage = SessionStorage()
    await session_storage.clear_folder_id(folder_id, user.sub)

    # Delete the folder
    success = await storage.delete(folder_id, user.sub)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除失败",
        )

    return {"status": "deleted"}
