"""User-related schemas."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class OAuthProvider(str, Enum):
    """OAuth provider types."""

    GOOGLE = "google"
    GITHUB = "github"
    APPLE = "apple"


class UserBase(BaseModel):
    """Base user schema."""

    username: str = Field(..., min_length=1, max_length=50)
    email: EmailStr
    avatar_url: Optional[str] = None  # Data URI for avatar (data:image/xxx;base64,...)
    oauth_provider: Optional[OAuthProvider] = None  # OAuth provider (google, github, apple)
    oauth_id: Optional[str] = None  # OAuth provider user ID


class UserCreate(UserBase):
    """Schema for creating a user."""

    password: Optional[str] = Field(None, min_length=6)  # Optional for OAuth users
    roles: List[str] = Field(default_factory=list)


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    model_config = ConfigDict(extra="ignore")

    username: Optional[str] = Field(None, min_length=1, max_length=50)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    avatar_url: Optional[str] = None  # Data URI for avatar (data:image/xxx;base64,...)
    roles: Optional[List[str]] = None
    is_active: Optional[bool] = None
    oauth_provider: Optional[OAuthProvider] = None
    oauth_id: Optional[str] = None


class User(UserBase):
    """User model (public view)."""

    id: str
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """Paginated user list response."""

    users: List[User]
    total: int
    skip: int
    limit: int
    has_more: bool


class UserInDB(User):
    """User model with sensitive data (database view)."""

    password_hash: str


class TokenPayload(BaseModel):
    """JWT Token payload."""

    sub: str  # user_id
    username: str
    roles: List[str] = Field(default_factory=list)
    permissions: List[str] = Field(default_factory=list)
    exp: Optional[datetime] = None
    iat: Optional[datetime] = None


class Token(BaseModel):
    """Token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginRequest(BaseModel):
    """Login request (supports username or email)."""

    username: str  # 可以是用户名或邮箱
    password: str
