# 文件上传功能设计文档

## 概述

为 LambChat 添加完整的文件上传功能，支持按文件类型（图片/视频/音频/文档）细分权限控制，通过动态代理接口确保文件链接永不过期。

## 1. 权限系统扩展

### 1.1 新增权限

| 权限 | 说明 | 文件类型 |
|------|------|---------|
| `file:upload:image` | 上传图片 | jpg, jpeg, png, gif, webp, svg, bmp, ico |
| `file:upload:video` | 上传视频 | mp4, webm, mov, avi, mkv, wmv, flv |
| `file:upload:audio` | 上传音频 | mp3, wav, ogg, aac, flac, m4a, wma |
| `file:upload:document` | 上传文档 | pdf, doc, docx, xls, xlsx, ppt, pptx, txt, md, csv, rtf |

### 1.2 向后兼容

- 保留原有 `file:upload` 权限作为总开关
- 拥有 `file:upload` 权限的用户默认拥有所有细分权限

### 1.3 权限元数据

```python
PERMISSION_METADATA = {
    # ... 现有权限
    "file:upload:image": {
        "label": "上传图片",
        "description": "允许上传图片文件（jpg, png, gif 等）",
        "category": "file"
    },
    "file:upload:video": {
        "label": "上传视频",
        "description": "允许上传视频文件（mp4, webm 等）",
        "category": "file"
    },
    "file:upload:audio": {
        "label": "上传音频",
        "description": "允许上传音频文件（mp3, wav 等）",
        "category": "file"
    },
    "file:upload:document": {
        "label": "上传文档",
        "description": "允许上传文档文件（pdf, word, excel 等）",
        "category": "file"
    },
}
```

## 2. 系统设置配置

### 2.1 配置项

设置分类：`file_upload`

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `max_size_image` | int | 10 | 图片最大大小（MB） |
| `max_size_video` | int | 100 | 视频最大大小（MB） |
| `max_size_audio` | int | 50 | 音频最大大小（MB） |
| `max_size_document` | int | 50 | 文档最大大小（MB） |
| `max_files_per_upload` | int | 10 | 单次上传文件数量上限 |
| `allowed_extensions` | object | 见下方 | 各类型允许的扩展名白名单 |

### 2.2 默认扩展名配置

```json
{
  "image": ["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico"],
  "video": ["mp4", "webm", "mov", "avi", "mkv", "wmv", "flv"],
  "audio": ["mp3", "wav", "ogg", "aac", "flac", "m4a", "wma"],
  "document": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "rtf"]
}
```

## 3. 后端 API 设计

### 3.1 动态代理接口

**端点**: `GET /api/upload/file/{key}`

**流程**:
```
用户请求 → 权限校验 → 生成 presigned URL (5分钟) → 302 重定向
```

**响应**:
- 成功：302 重定向到 S3 presigned URL
- 失败：401 未授权 / 404 文件不存在

**示例**:
```
请求: GET /api/upload/file/uploads/user123/2026/03/abc123.jpg
响应: 302 Found
      Location: https://s3.amazonaws.com/bucket/uploads/user123/2026/03/abc123.jpg?X-Amz-Signature=...
```

### 3.2 上传接口改动

**端点**: `POST /api/upload/upload`

**改动点**:
1. 根据 MIME 类型判断文件类别
2. 检查用户是否有对应的 `file:upload:{category}` 权限
3. 检查文件大小是否超过该类型的限制
4. 上传到 S3，返回代理接口的 URL

**响应格式**:
```json
{
  "key": "uploads/user123/2026/03/abc123.jpg",
  "url": "/api/upload/file/uploads/user123/2026/03/abc123.jpg",
  "name": "example.jpg",
  "type": "image",
  "mimeType": "image/jpeg",
  "size": 12345
}
```

### 3.3 配置接口

**端点**: `GET /api/upload/config`

**响应格式**:
```json
{
  "maxSize": {
    "image": 10,
    "video": 100,
    "audio": 50,
    "document": 50
  },
  "maxFilesPerUpload": 10,
  "allowedExtensions": {
    "image": ["jpg", "jpeg", "png", ...],
    "video": ["mp4", "webm", ...],
    "audio": ["mp3", "wav", ...],
    "document": ["pdf", "doc", ...]
  }
}
```

## 4. 前端组件设计

### 4.1 组件结构

```
components/chat/
├── FileUploadButton.tsx    # 上传按钮
├── AttachmentPreview.tsx   # 附件预览区域
└── FileMessage.tsx         # 消息中的文件展示
```

### 4.2 FileUploadButton 组件

**功能**:
- 点击触发文件选择
- 支持拖拽上传
- 根据用户权限过滤可选文件类型
- 多文件选择支持

**位置**: 聊天输入框左侧，MCP 和 Skill 按钮的左边

### 4.3 AttachmentPreview 组件

**功能**:
- 显示待发送的附件列表
- 每个附件显示：预览/图标、文件名、大小、删除按钮
- 图片：缩略图预览
- 视频：视频封面预览
- 音频：音频图标 + 时长
- 文档：文件类型图标 + 文件名 + 大小

### 4.4 FileMessage 组件

**功能**:
- 在消息中展示已发送的文件
- 图片/视频/音频：内嵌预览播放器
- 文档：卡片样式（图标、文件名、大小、下载按钮）

## 5. 消息数据结构

### 5.1 附件类型定义

```typescript
interface MessageAttachment {
  id: string;           // 文件唯一标识
  key: string;          // S3 存储 key
  name: string;         // 原始文件名
  type: 'image' | 'video' | 'audio' | 'document';
  mimeType: string;     // MIME 类型
  size: number;         // 文件大小（bytes）
  url: string;          // 代理接口 URL /api/upload/file/{key}
}
```

### 5.2 消息结构扩展

```typescript
interface ChatMessage {
  // ... 现有字段
  attachments?: MessageAttachment[];  // 附件列表
}
```

## 6. 文件存储规范

### 6.1 存储路径

```
uploads/{user_id}/{year}/{month}/{uuid}.{ext}
```

**示例**: `uploads/user123/2026/03/abc123-def4-5678.jpg`

### 6.2 元数据存储

文件元数据存储在 MongoDB `files` 集合：

```javascript
{
  _id: ObjectId,
  key: "uploads/user123/2026/03/abc123.jpg",
  name: "example.jpg",
  type: "image",
  mimeType: "image/jpeg",
  size: 12345,
  userId: "user123",
  createdAt: ISODate("2026-03-01T00:00:00Z")
}
```

## 7. 国际化

### 7.1 新增翻译键

```json
{
  "fileUpload": {
    "title": "上传文件",
    "dragDrop": "拖拽文件到这里或点击上传",
    "uploading": "上传中...",
    "uploadSuccess": "上传成功",
    "uploadFailed": "上传失败",
    "noPermission": "没有权限上传此类型的文件",
    "fileTooLarge": "文件大小超过限制",
    "tooManyFiles": "一次最多上传 {{count}} 个文件",
    "removeAttachment": "移除附件",
    "categories": {
      "image": "图片",
      "video": "视频",
      "audio": "音频",
      "document": "文档"
    }
  }
}
```

## 8. 安全考虑

1. **权限校验**: 上传和下载都需要校验用户权限
2. **文件类型验证**: 通过 MIME 类型和扩展名双重验证
3. **文件大小限制**: 防止大文件攻击
4. **用户隔离**: 每个用户只能访问自己上传的文件
5. **签名 URL**: 代理接口生成短期 presigned URL，不暴露 S3 凭证

## 9. 实现优先级

1. **P0 - 核心功能**
   - 后端权限扩展
   - 上传接口改动
   - 动态代理接口
   - 前端上传按钮和预览

2. **P1 - 增强功能**
   - 系统设置配置 UI
   - 消息中的文件展示
   - 国际化支持

3. **P2 - 优化**
   - 上传进度显示
   - 大文件分片上传
   - 文件管理页面
