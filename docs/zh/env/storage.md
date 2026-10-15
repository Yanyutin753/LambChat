# 存储配置

文件存储和上传设置。LambChat 支持本地文件系统存储和 S3 兼容对象存储。

## S3 对象存储

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `S3_ENABLED` | `false` | 否 | 启用 S3 对象存储。 |
| `S3_PROVIDER` | `aws` | 否 | S3 提供商：`aws`、`aliyun`、`tencent`、`minio`、`custom`。 |
| `S3_ENDPOINT_URL` | _(空)_ | 否 | S3 端点 URL。**MinIO 和自定义提供商必须填写。** |
| `S3_ACCESS_KEY` | _(空)_ | 是 | S3 访问密钥。 |
| `S3_SECRET_KEY` | _(空)_ | 是 | S3 密钥。 |
| `S3_REGION` | `us-east-1` | 否 | S3 区域。 |
| `S3_BUCKET_NAME` | _(空)_ | 否 | S3 存储桶名称。 |
| `S3_CUSTOM_DOMAIN` | _(空)_ | 否 | 自定义 CDN 域名。 |
| `S3_PATH_STYLE` | `false` | 否 | 使用路径样式寻址。**MinIO 必须开启。** |
| `S3_MAX_FILE_SIZE` | `10485760`（10MB） | 否 | 最大文件上传大小（字节）。 |
| `S3_INTERNAL_UPLOAD_MAX_SIZE` | `52428800`（50MB） | 否 | 最大内部上传大小（字节）。 |
| `S3_PUBLIC_BUCKET` | `false` | 否 | 存储桶是否公开可访问。 |
| `S3_PRESIGNED_URL_EXPIRES` | `604800`（7 天） | 否 | 预签名 URL 过期时间（秒）。 |

## 本地存储

本地存储仅适用于单实例开发或测试。多副本部署必须使用 S3 兼容对象存储，并设置
`ENABLE_LOCAL_FILESYSTEM_FALLBACK=false`，避免某个 Pod 写入的文件无法被另一个
Pod 读取。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `LOCAL_STORAGE_PATH` | `./uploads` | 本地文件存储路径。当 `S3_ENABLED=false` 时使用。 |
| `ENABLE_LOCAL_FILESYSTEM_FALLBACK` | `true` | 当 S3 不可用时启用本地文件系统回退。 |

## 文件上传限制

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `FILE_UPLOAD_MAX_SIZE_IMAGE` | `10` | 最大图片文件大小（MB）。 |
| `FILE_UPLOAD_MAX_SIZE_VIDEO` | `100` | 最大视频文件大小（MB）。 |
| `FILE_UPLOAD_MAX_SIZE_AUDIO` | `50` | 最大音频文件大小（MB）。 |
| `FILE_UPLOAD_MAX_SIZE_DOCUMENT` | `50` | 最大文档文件大小（MB）。 |
| `FILE_UPLOAD_MAX_FILES` | `10` | 每次上传的最大文件数。 |

## 示例

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

### 阿里云 OSS

```bash
S3_ENABLED=true
S3_PROVIDER=aliyun
S3_ACCESS_KEY=your_access_key
S3_SECRET_KEY=your_secret_key
S3_REGION=oss-cn-hangzhou
S3_BUCKET_NAME=lambchat-files
```

## 浏览器直传

启用对象存储后，共享文件上传服务通过短期预签名 URL 将文件分块直接传到存储桶。8 MiB 以内只传一个分块，更大的文件按 8 MiB 切块；失败分块最多重试两次。取消会中止当前请求并通知后端清理。本地存储及 TIFF/BMP/ICO 图片转码继续使用原后端上传路径，个人头像上传也保留原路径。

后端检查上传者权限和角色大小限制，合并前从存储服务列出实际分块；合并后流式读取对象，计算可信 SHA-256，保留按用户隔离的去重。处理阶段因此会产生一次对象读取流量。前端不会获得存储密钥。任务状态持久化到 MongoDB，可跨 API 实例处理；过期任务每五分钟清理一次。

直传完成期间，附件卡片每 500 毫秒查询一次本人任务，根据已校验字节数显示服务端处理百分比。合并等无法量化的阶段保留处理中提示；最终完成前不显示 100%，完成或取消后停止查询。回退后端上传时保留处理中提示，不显示估算百分比。

每个分块的签名绑定其授权字节数；浏览器自动发送 `Content-Length`，存储服务会拒绝大小不符的 PUT。取消标记与完成准入使用原子更新，防止跨 API 实例的竞争漏掉取消。

存储桶端点必须能被浏览器通过 HTTPS 访问。为实际使用的网页、桌面和移动端 Origin 配置存储桶 CORS。AWS S3 配置示例（替换域名）：

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

OSS 使用对应的存储桶跨域设置。后端通过存储服务 ListParts 获取可信 ETag。网络不可达或超时重试耗尽后，客户端先清理分块，再使用现有的鉴权后端上传路径，保留进度与取消。旧服务端没有直传接口时也使用该路径。权限、签名和服务错误仍会显示给用户。

任务绑定创建时的存储配置（提供商、端点、区域、存储桶），配置变更后需重新上传。存储桶应设置 **AbortIncompleteMultipartUpload** 生命周期规则（OSS 对应未完成分片上传过期规则），建议一天后清理，覆盖创建上传任务后尚未保存 ID 就崩溃及后端长期不可用的情况。停用旧存储配置前，应先在原桶完成过期任务清理。后端需保留原有对象元数据、读取、删除权限，以及分块创建、列举、合并和中止权限。
