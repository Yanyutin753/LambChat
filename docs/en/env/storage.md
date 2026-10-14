# Storage Configuration

File storage and upload settings. LambChat supports local filesystem storage and S3-compatible object storage.

## S3 Object Storage

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `S3_ENABLED` | `false` | No | Enable S3 object storage. |
| `S3_PROVIDER` | `aws` | No | S3 provider: `aws`, `aliyun`, `tencent`, `minio`, `custom`. |
| `S3_ENDPOINT_URL` | _(empty)_ | No | S3 endpoint URL. **Required for MinIO and custom providers.** |
| `S3_ACCESS_KEY` | _(empty)_ | Yes | S3 access key. |
| `S3_SECRET_KEY` | _(empty)_ | Yes | S3 secret key. |
| `S3_REGION` | `us-east-1` | No | S3 region. |
| `S3_BUCKET_NAME` | _(empty)_ | No | S3 bucket name. |
| `S3_CUSTOM_DOMAIN` | _(empty)_ | No | Custom CDN domain for public URLs. |
| `S3_PATH_STYLE` | `false` | No | Use path-style addressing. **Required for MinIO.** |
| `S3_MAX_FILE_SIZE` | `10485760` (10MB) | No | Maximum file upload size in bytes. |
| `S3_INTERNAL_UPLOAD_MAX_SIZE` | `52428800` (50MB) | No | Maximum internal upload size in bytes. |
| `S3_PUBLIC_BUCKET` | `false` | No | Whether the bucket is publicly accessible. |
| `S3_PRESIGNED_URL_EXPIRES` | `604800` (7 days) | No | Presigned URL expiration in seconds. |

## Local Storage

Local storage is for single-instance development or testing only. In a
multi-replica deployment, use S3-compatible object storage and set
`ENABLE_LOCAL_FILESYSTEM_FALLBACK=false` so one pod never writes files that
another pod cannot read.

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCAL_STORAGE_PATH` | `./uploads` | Path for local file storage. Used when `S3_ENABLED=false`. |
| `ENABLE_LOCAL_FILESYSTEM_FALLBACK` | `true` | Enable local filesystem fallback when S3 is unavailable. |

## File Upload Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `FILE_UPLOAD_MAX_SIZE_IMAGE` | `10` | Maximum image file size in MB. |
| `FILE_UPLOAD_MAX_SIZE_VIDEO` | `100` | Maximum video file size in MB. |
| `FILE_UPLOAD_MAX_SIZE_AUDIO` | `50` | Maximum audio file size in MB. |
| `FILE_UPLOAD_MAX_SIZE_DOCUMENT` | `50` | Maximum document file size in MB. |
| `FILE_UPLOAD_MAX_FILES` | `10` | Maximum number of files per upload. |

## Examples

### AWS S3

```bash
S3_ENABLED=true
S3_PROVIDER=aws
S3_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE
S3_SECRET_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
S3_REGION=us-east-1
S3_BUCKET_NAME=lambchat-files
```

### MinIO

```bash
S3_ENABLED=true
S3_PROVIDER=minio
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=lambchat
S3_PATH_STYLE=true
```

### Aliyun OSS

```bash
S3_ENABLED=true
S3_PROVIDER=aliyun
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
S3_REGION=oss-cn-hangzhou
S3_BUCKET_NAME=lambchat-files
```

## Browser direct uploads

With object storage enabled, the shared file uploader sends file parts directly to the bucket using short-lived signed URLs. Files up to 8 MiB use one part; larger files are split into 8 MiB parts. Failed parts are retried up to twice, and cancel aborts the current request and asks the backend to clean up. Local storage and TIFF/BMP/ICO image conversion retain the existing backend upload path; profile-avatar uploads also retain their existing path.

Each part signature binds its authorized byte count. Browsers supply `Content-Length` automatically, and storage rejects PUTs with a different size. Atomic cancellation flags and completion admission prevent cancellation races across API replicas.

The backend checks the owner's permissions and role limits, lists the actual uploaded parts before merging, and streams the finished object to compute the trusted SHA-256 used for owner-scoped deduplication. This adds one object read during the processing stage. The browser never receives bucket credentials. Ticket state is stored in MongoDB for multiple API replicas; expired uploads are cleaned every five minutes.

The bucket endpoint must be reachable from the browser over HTTPS. Configure bucket CORS for each actual web, desktop, or mobile origin. An AWS S3 example (replace the origin):

```json
{
  "CORSRules": [{
    "AllowedOrigins": ["https://app.example.com", "tauri://localhost", "http://tauri.localhost", "capacitor://localhost", "http://localhost", "https://localhost"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }]
}
```

OSS uses its equivalent bucket CORS settings. The backend retrieves authoritative ETags through the provider's ListParts API. After exhausted network or timeout retries, the client cleans up multipart state and uses the existing authenticated backend upload path, preserving progress and cancellation. Older servers without direct-upload endpoints also use that path. Permission, signature, and service errors remain visible.

The storage identity (provider, endpoint, region, bucket) is bound to each ticket; configuration changes require a new upload. Configure an **AbortIncompleteMultipartUpload** bucket lifecycle rule (OSS: its multipart-upload expiration rule), preferably after one day. This covers a process crash between creating a provider upload and saving its ID, and long backend outages. Periodic cleanup must run against the original bucket before retiring a storage configuration. Existing metadata, object read/delete, and multipart create/list/complete/abort permissions must remain available to the backend.
