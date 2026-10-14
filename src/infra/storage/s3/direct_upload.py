"""Provider-native multipart operations for browser uploads; credentials stay on the server."""

from typing import Any

from src.infra.async_utils import run_long_blocking_io
from src.infra.storage.s3.types import S3Config, S3Provider

PART_SIZE = 8 * 1024 * 1024
URL_EXPIRES = 3600
MAX_PARTS = 10000


def validate_parts(parts: list[dict], size: int, part_size: int = PART_SIZE) -> list[dict]:
    count = (size + part_size - 1) // part_size
    if len(parts) != count:
        raise ValueError("Incomplete multipart upload")
    for number, part in enumerate(parts, 1):
        expected = min(part_size, size - (number - 1) * part_size)
        if part["PartNumber"] != number or part["Size"] != expected or not part["ETag"]:
            raise ValueError("Uploaded parts do not match the authorized file")
    return [{"PartNumber": p["PartNumber"], "ETag": p["ETag"]} for p in parts]


class DirectUploadStorage:
    def __init__(self, config: S3Config):
        self.config = config
        self._client: Any = None

    def _get_client(self):
        if self._client is None:
            if self.config.provider == S3Provider.ALIYUN:
                import oss2

                endpoint = (
                    self.config.endpoint_url or f"https://oss-{self.config.region}.aliyuncs.com"
                )
                if not endpoint.startswith(("http://", "https://")):
                    endpoint = f"https://{endpoint}"
                self._client = oss2.Bucket(
                    oss2.AuthV2(self.config.access_key, self.config.secret_key),
                    endpoint,
                    self.config.bucket_name,
                    connect_timeout=30,
                )
            else:
                import boto3
                from botocore.config import Config

                s3_endpoint = self.config.endpoint_url or self.config.get_endpoint_url()
                if s3_endpoint and not s3_endpoint.startswith(("http://", "https://")):
                    s3_endpoint = f"https://{s3_endpoint}"
                self._client = boto3.client(
                    "s3",
                    endpoint_url=s3_endpoint,
                    aws_access_key_id=self.config.access_key,
                    aws_secret_access_key=self.config.secret_key,
                    region_name=self.config.region,
                    config=Config(
                        signature_version="s3v4",
                        connect_timeout=10,
                        read_timeout=30,
                        request_checksum_calculation="when_required",
                        response_checksum_validation="when_required",
                        s3={
                            "addressing_style": "path"
                            if self.config.path_style or self.config.provider == S3Provider.MINIO
                            else "virtual"
                        },
                    ),
                )
        return self._client

    async def create(self, key: str, content_type: str) -> str:
        def operation():
            client = self._get_client()
            if self.config.provider == S3Provider.ALIYUN:
                return client.init_multipart_upload(
                    key, headers={"Content-Type": content_type}
                ).upload_id
            return client.create_multipart_upload(
                Bucket=self.config.bucket_name,
                Key=key,
                ContentType=content_type,
            )["UploadId"]

        return await run_long_blocking_io(operation)

    async def sign_part(self, key: str, upload_id: str, number: int, size: int) -> str:
        def operation():
            client = self._get_client()
            if self.config.provider == S3Provider.ALIYUN:
                return client.sign_url(
                    "PUT",
                    key,
                    URL_EXPIRES,
                    headers={"Content-Length": str(size)},
                    additional_headers={"content-length"},
                    params={"uploadId": upload_id, "partNumber": str(number)},
                )
            return client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self.config.bucket_name,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": number,
                    "ContentLength": size,
                },
                ExpiresIn=URL_EXPIRES,
            )

        return await run_long_blocking_io(operation)

    async def list_parts(self, key: str, upload_id: str) -> list[dict]:
        def operation():
            client = self._get_client()
            if self.config.provider == S3Provider.ALIYUN:
                import oss2

                return [
                    {"PartNumber": p.part_number, "ETag": p.etag, "Size": p.size}
                    for p in oss2.PartIterator(client, key, upload_id)
                ]
            pages = client.get_paginator("list_parts").paginate(
                Bucket=self.config.bucket_name,
                Key=key,
                UploadId=upload_id,
            )
            return [p for page in pages for p in page.get("Parts", [])]

        return await run_long_blocking_io(operation)

    async def complete(self, key: str, upload_id: str, parts: list[dict]) -> None:
        def operation():
            client = self._get_client()
            if self.config.provider == S3Provider.ALIYUN:
                import oss2

                client.complete_multipart_upload(
                    key,
                    upload_id,
                    [oss2.models.PartInfo(p["PartNumber"], p["ETag"]) for p in parts],
                )
            else:
                client.complete_multipart_upload(
                    Bucket=self.config.bucket_name,
                    Key=key,
                    UploadId=upload_id,
                    MultipartUpload={"Parts": parts},
                )

        await run_long_blocking_io(operation)

    async def close(self) -> None:
        if self._client is not None:
            if self.config.provider != S3Provider.ALIYUN:
                await run_long_blocking_io(self._client.close)
            self._client = None

    async def abort(self, key: str, upload_id: str) -> None:
        def operation():
            client = self._get_client()
            try:
                if self.config.provider == S3Provider.ALIYUN:
                    client.abort_multipart_upload(key, upload_id)
                else:
                    client.abort_multipart_upload(
                        Bucket=self.config.bucket_name, Key=key, UploadId=upload_id
                    )
            except Exception as exc:
                code = getattr(exc, "code", None)
                response = getattr(exc, "response", {})
                if (
                    code != "NoSuchUpload"
                    and response.get("Error", {}).get("Code") != "NoSuchUpload"
                ):
                    raise

        await run_long_blocking_io(operation)
