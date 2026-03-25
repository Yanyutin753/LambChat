"""
S3 storage types - provider enum, config, and upload result.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class S3Provider(str, Enum):
    """S3-compatible storage providers"""

    AWS = "aws"
    ALIYUN = "aliyun"  # Alibaba Cloud OSS
    TENCENT = "tencent"  # Tencent Cloud COS
    MINIO = "minio"
    CUSTOM = "custom"
    LOCAL = "local"


class S3Config(BaseModel):
    """S3 storage configuration"""

    provider: S3Provider = S3Provider.AWS
    endpoint_url: Optional[str] = None  # Required for non-AWS providers
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-east-1"
    bucket_name: str = ""
    # URL configuration
    custom_domain: Optional[str] = None  # Custom CDN domain
    path_style: bool = False  # Use path-style URLs (required for MinIO)
    public_bucket: bool = (
        False  # Whether bucket is publicly readable (if False, use presigned URLs)
    )
    # Upload settings
    max_file_size: int = 10 * 1024 * 1024  # 10MB default
    internal_max_upload_size: int = 50 * 1024 * 1024  # 50MB default for internal uploads
    # URL expiration for presigned URLs (in seconds)
    presigned_url_expires: int = 7 * 24 * 3600  # 7 days default
    # Local storage settings
    storage_path: str = "./uploads"  # Base directory for local file storage
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [
            # Images
            "jpg",
            "jpeg",
            "png",
            "gif",
            "webp",
            "svg",
            "bmp",
            "ico",
            # Documents
            "pdf",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "txt",
            "md",
            # Archives
            "zip",
            "tar",
            "gz",
            # Code
            "json",
            "yaml",
            "yml",
            "xml",
            "csv",
        ]
    )

    def get_endpoint_url(self) -> Optional[str]:
        """Get endpoint URL based on provider"""
        if self.endpoint_url:
            return self.endpoint_url

        if self.provider == S3Provider.AWS:
            return None  # boto3 will use default AWS endpoints
        elif self.provider == S3Provider.ALIYUN:
            return f"https://oss-{self.region}.aliyuncs.com"
        elif self.provider == S3Provider.TENCENT:
            return f"https://cos.{self.region}.myqcloud.com"
        elif self.provider == S3Provider.MINIO:
            # MinIO requires endpoint_url
            return self.endpoint_url

        return self.endpoint_url

    def get_public_url(self, key: str) -> str:
        """Generate public URL for an object"""
        if self.custom_domain:
            return f"https://{self.custom_domain}/{key}"

        if self.path_style or self.provider == S3Provider.MINIO:
            endpoint = self.get_endpoint_url() or f"https://s3.{self.region}.amazonaws.com"
            return f"{endpoint}/{self.bucket_name}/{key}"
        else:
            # Virtual-hosted style
            if self.provider == S3Provider.ALIYUN:
                return f"https://{self.bucket_name}.oss-{self.region}.aliyuncs.com/{key}"
            elif self.provider == S3Provider.TENCENT:
                return f"https://{self.bucket_name}.cos.{self.region}.myqcloud.com/{key}"
            else:
                return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"


class UploadResult(BaseModel):
    """Result of a file upload"""

    key: str  # Object key in bucket
    url: str  # Public URL
    size: int  # File size in bytes
    content_type: str
    etag: Optional[str] = None
    last_modified: Optional[datetime] = None
