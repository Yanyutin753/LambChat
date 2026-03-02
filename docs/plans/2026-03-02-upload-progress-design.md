# 上传进度与文件类型选择设计

## 概述

为文件上传功能添加：
1. 上传弹窗 - 选择文件类型后再选择文件
2. 拖放支持 - 自动判断文件类型
3. 上传进度 - 在卡片内显示进度条

## 需求确认

- **文件类型选择**：按媒体类型分类（图片、视频、音频、文档）
- **进度显示**：在卡片内显示进度条和百分比
- **弹窗样式**：下拉菜单 + 选择文件按钮
- **多文件上传**：始终允许多选
- **拖放支持**：支持拖放自动判断类型

## 组件架构

### 文件变更

```
frontend/src/components/chat/
├── FileUploadButton.tsx    # 修改：点击打开弹窗
├── UploadModal.tsx         # 新增：上传弹窗组件
└── ...

frontend/src/components/common/
├── AttachmentCard.tsx      # 修改：支持显示上传进度
└── ...

frontend/src/services/api/
└── upload.ts               # 修改：支持进度回调
```

## 详细设计

### 1. UploadModal 组件

```tsx
interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
  onUpload: (attachments: MessageAttachment[]) => void;
}
```

**UI 布局**：
- 顶部：拖放区域（虚线边框，支持拖放检测）
- 中部：文件类型下拉菜单（图片/视频/音频/文档）
- 底部：选择文件按钮

**交互流程**：
1. 用户点击上传按钮 → 打开弹窗
2. 用户可选择：
   - 直接拖放文件到拖放区域（自动判断类型）
   - 或选择类型后点击"选择文件"按钮
3. 选择文件后开始上传，显示进度
4. 上传完成后关闭弹窗，更新附件列表

### 2. AttachmentCard 进度显示

扩展 `AttachmentCardProps`：

```tsx
interface AttachmentCardProps {
  // ... 现有属性
  uploadProgress?: number;      // 0-100 的进度值
  isUploading?: boolean;        // 是否正在上传
}
```

**进度条样式**：
- 显示在文件信息下方
- 紫色进度条 + 灰色背景
- 显示百分比和已上传/总大小

### 3. 上传 API 改造

修改 `uploadApi.uploadFile` 支持 XMLHttpRequest 进度回调：

```typescript
uploadFile(
  file: File,
  options?: {
    folder?: string;
    onProgress?: (progress: number, loaded: number, total: number) => void;
  }
): Promise<UploadResult>
```

使用 XMLHttpRequest 替代 fetch 以支持上传进度监听。

### 4. 类型定义

```typescript
// 上传状态
interface UploadState {
  file: File;
  progress: number;
  loaded: number;
  status: 'pending' | 'uploading' | 'completed' | 'error';
  attachment?: MessageAttachment;
  error?: string;
}
```

## 实现步骤

1. **修改 upload.ts** - 添加进度回调支持
2. **创建 UploadModal.tsx** - 上传弹窗组件
3. **修改 FileUploadButton.tsx** - 点击打开弹窗
4. **修改 AttachmentCard.tsx** - 支持进度显示
5. **修改 ChatInput.tsx** - 集成上传状态管理
6. **添加国际化文本** - 中英文支持

## 国际化

需要添加的翻译 key：

```json
{
  "upload": {
    "title": "上传文件",
    "dragDrop": "拖放文件到此处",
    "dragDropOr": "或点击下方按钮选择",
    "selectType": "文件类型",
    "selectFile": "选择文件",
    "uploading": "上传中...",
    "uploadComplete": "上传完成",
    "uploadError": "上传失败",
    "types": {
      "image": "图片",
      "video": "视频",
      "audio": "音频",
      "document": "文档"
    }
  }
}
```
