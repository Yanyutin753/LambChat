"""
健康检查路由
"""

from fastapi import APIRouter

from src.kernel.config import settings
from src.kernel.schemas.agent import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查"""
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
    )


@router.get("/ready")
async def readiness_check():
    """就绪检查"""
    return {"status": "ready"}
