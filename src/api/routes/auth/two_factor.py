"""Authenticator pairing and second-factor sign-in."""

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from src.api.deps import get_current_user_required
from src.infra.auth.two_factor import TwoFactorService, rate_limit
from src.kernel.schemas.user import PairingToken, Token, TokenPayload

from .utils import _get_client_ip

router = APIRouter(prefix="/2fa")


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class FactorRequest(PasswordRequest):
    code: str = Field(min_length=1, max_length=64)


class VerifyRequest(BaseModel):
    for_pairing: bool = False
    challenge_token: str = Field(min_length=40, max_length=128)
    code: str = Field(min_length=1, max_length=64)


def _private(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post("/verify", response_model=Token | PairingToken)
async def verify(body: VerifyRequest, request: Request, response: Response):
    _private(response)
    await rate_limit("verify-ip", _get_client_ip(request), 30)
    return await TwoFactorService().complete_login(
        body.challenge_token, body.code, for_pairing=body.for_pairing
    )


@router.post("/setup")
async def setup(
    body: PasswordRequest,
    response: Response,
    identity: TokenPayload = Depends(get_current_user_required),
):
    _private(response)
    service = TwoFactorService()
    user = await service.get_user(identity.sub)
    return await service.setup(user, body.password)


@router.post("/enable")
async def enable(
    body: FactorRequest,
    response: Response,
    identity: TokenPayload = Depends(get_current_user_required),
):
    _private(response)
    service = TwoFactorService()
    user = await service.get_user(identity.sub)
    return await service.enable(user, body.password, body.code)


@router.post("/disable")
async def disable(
    body: FactorRequest,
    response: Response,
    identity: TokenPayload = Depends(get_current_user_required),
):
    _private(response)
    service = TwoFactorService()
    user = await service.get_user(identity.sub)
    return await service.manage(user, body.password, body.code, disable=True)


@router.post("/recovery-codes")
async def recovery_codes(
    body: FactorRequest,
    response: Response,
    identity: TokenPayload = Depends(get_current_user_required),
):
    _private(response)
    service = TwoFactorService()
    user = await service.get_user(identity.sub)
    return await service.manage(user, body.password, body.code)
