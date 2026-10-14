from unittest.mock import Mock

import pytest

from src.infra.storage.s3.direct_upload import DirectUploadStorage, validate_parts
from src.infra.storage.s3.types import S3Config


@pytest.mark.parametrize(
    "config,endpoint,secure",
    [
        (S3Config(endpoint_url="http://localhost:9000"), "localhost:9000", False),
        (S3Config(region="eu-west-1"), "s3.eu-west-1.amazonaws.com", True),
    ],
)
def test_existing_download_backend_uses_the_same_endpoint_as_direct_upload(
    config, endpoint, secure, monkeypatch
):
    import minio

    from src.infra.storage.s3.backends.minio import MinioS3Backend

    client = Mock()
    monkeypatch.setattr(minio, "Minio", client)
    MinioS3Backend(config)._get_client()
    assert client.call_args.kwargs["endpoint"] == endpoint
    assert client.call_args.kwargs["secure"] is secure


def test_parts_must_match_the_authorized_file_and_chunk_layout():
    parts = [{"PartNumber": 1, "ETag": "a", "Size": 8}, {"PartNumber": 2, "ETag": "b", "Size": 3}]
    assert validate_parts(parts, 11, 8) == [
        {"PartNumber": 1, "ETag": "a"},
        {"PartNumber": 2, "ETag": "b"},
    ]
    for invalid in [
        parts[:1],
        parts[::-1],
        [dict(parts[0], Size=9), parts[1]],
        [dict(parts[0], PartNumber=2), parts[1]],
    ]:
        with pytest.raises(ValueError):
            validate_parts(invalid, 11, 8)


@pytest.mark.asyncio
async def test_s3_signatures_are_scoped_to_one_upload_and_part():
    adapter = DirectUploadStorage(S3Config(bucket_name="files"))
    client = Mock()
    client.generate_presigned_url.return_value = "https://storage/part"
    adapter._client = client
    assert await adapter.sign_part("document/user/key", "upload-id", 2, 3) == "https://storage/part"
    client.generate_presigned_url.assert_called_once_with(
        "upload_part",
        Params={
            "Bucket": "files",
            "Key": "document/user/key",
            "UploadId": "upload-id",
            "PartNumber": 2,
            "ContentLength": 3,
        },
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["aws", "aliyun"])
async def test_provider_signature_binds_the_part_content_length(provider):
    from urllib.parse import parse_qs, urlsplit

    adapter = DirectUploadStorage(
        S3Config(
            provider=provider,
            bucket_name="files",
            region="cn-hongkong" if provider == "aliyun" else "us-east-1",
            access_key="test-access-key",
            secret_key="test-secret-key",
        )
    )
    try:
        query = parse_qs(
            urlsplit(await adapter.sign_part("document/user/key", "upload-id", 1, 3)).query
        )
        signed_headers = query.get("X-Amz-SignedHeaders") or query.get("x-oss-additional-headers")
        assert signed_headers and "content-length" in signed_headers[0].split(";")
    finally:
        await adapter.close()
