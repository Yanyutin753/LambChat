# Human Tool 2.0 设计文档

## 概述

重构 `ask_human` 工具，支持多字段表单输入，替代原有的单字段模式。

## 需求

- 支持多字段表单（一次请求收集多个输入）
- 支持 6 种字段类型：text, textarea, number, checkbox, select, multi_select
- 每个字段支持默认值
- ChatGPT 风格的 UI
- 支持主题色适配（深色/浅色模式）

## 数据模型

### 字段类型 (FieldType)

```python
class FieldType(str, Enum):
    TEXT = "text"           # 单行文本
    TEXTAREA = "textarea"   # 多行文本
    NUMBER = "number"       # 数字
    CHECKBOX = "checkbox"   # 布尔开关
    SELECT = "select"       # 单选下拉
    MULTI_SELECT = "multi_select"  # 多选
```

### 表单字段 (FormField)

```python
class FormField(BaseModel):
    name: str                    # 字段标识
    label: str                   # 显示标签
    type: FieldType              # 字段类型
    placeholder: Optional[str]   # 占位提示
    default: Optional[Any]       # 默认值
    required: bool = True        # 是否必填
    options: Optional[list[str]] # 选项（select/multi_select 用）
```

### 工具输入 (AskHumanInput)

```python
class AskHumanInput(BaseModel):
    message: str                 # 标题/提示信息
    fields: list[FormField]      # 表单字段列表
    timeout: int = 300           # 超时时间（秒）
```

### 返回格式

用户提交后，返回 JSON 字符串：

```json
{
  "env": "production",
  "replicas": 3,
  "enable_cache": true,
  "tags": ["frontend", "api"],
  "notes": "紧急部署"
}
```

## 后端实现

### 目录结构

```
src/infra/tool/human_tool/
├── __init__.py          # 导出 get_human_tool
├── models.py            # FieldType, FormField, AskHumanInput
└── tool.py              # AskHumanTool 实现
```

### 存储模型变更

`PendingApproval` 模型：

```python
class PendingApproval(BaseModel):
    id: str
    message: str
    type: str = "form"
    fields: list[FormField]  # 替代原来的 choices
    status: str = "pending"
    session_id: Optional[str]
    created_at: datetime
```

### API 变更

`POST /human/{approval_id}/respond` 请求体：

```python
class ApprovalResponse(BaseModel):
    approved: bool
    response: dict[str, Any]  # 原来是 str，改为 dict
```

## 前端实现

### TypeScript 类型

```typescript
export type FormFieldType =
  | 'text' | 'textarea' | 'number'
  | 'checkbox' | 'select' | 'multi_select';

export interface FormField {
  name: string;
  label: string;
  type: FormFieldType;
  placeholder?: string;
  default?: unknown;
  required: boolean;
  options?: string[];
}

export interface PendingApproval {
  id: string;
  message: string;
  type: 'form';
  fields: FormField[];
  status: 'pending' | 'approved' | 'rejected';
  session_id?: string;
}
```

### UI 设计（ChatGPT 风格）

```
┌─────────────────────────────────────────────────┐
│  ℹ️  请填写部署配置                              │
├─────────────────────────────────────────────────┤
│                                                 │
│  环境 *                                          │
│  ┌─────────────────────────────────────────┐   │
│  │ production                        ▼     │   │  ← select
│  └─────────────────────────────────────────┘   │
│                                                 │
│  副本数 *                                        │
│  ┌─────────────────────────────────────────┐   │
│  │ 3                                       │   │  ← number
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ☑ 启用缓存                                     │  ← checkbox
│                                                 │
│  标签                                           │
│  ☑ frontend   ☑ backend   ☐ api               │  ← multi_select
│                                                 │
│  备注                                           │
│  ┌─────────────────────────────────────────┐   │
│  │ 紧急部署...                              │   │  ← textarea
│  │                                         │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
├─────────────────────────────────────────────────┤
│              [ 取消 ]     [ 提交 ]              │
└─────────────────────────────────────────────────┘
```

### 主题适配

- 使用 Tailwind CSS 的 `dark:` 前缀
- 颜色变量复用项目现有的主题色
- 深色模式：`bg-stone-800`, `text-stone-200`, `border-stone-600`
- 浅色模式：`bg-white`, `text-gray-900`, `border-gray-200`

## 文件变更清单

### 修改文件

| 文件 | 说明 |
|------|------|
| `src/infra/tool/human_tool.py` | 删除，拆分为模块 |
| `src/api/routes/human.py` | 适配新表单格式 |
| `src/infra/storage/mongodb.py` | 更新 PendingApproval 模型 |
| `frontend/src/types/index.ts` | 更新类型定义 |
| `frontend/src/components/panels/ApprovalPanel.tsx` | 重构表单渲染 |

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/infra/tool/human_tool/__init__.py` | 模块导出 |
| `src/infra/tool/human_tool/models.py` | Pydantic 模型 |
| `src/infra/tool/human_tool/tool.py` | AskHumanTool 实现 |

## 调用示例

```python
# Agent 调用
ask_human(
    message="请填写部署配置",
    fields=[
        {
            "name": "env",
            "label": "环境",
            "type": "select",
            "options": ["development", "staging", "production"],
            "default": "development",
            "required": True
        },
        {
            "name": "replicas",
            "label": "副本数",
            "type": "number",
            "default": 1,
            "required": True
        },
        {
            "name": "enable_cache",
            "label": "启用缓存",
            "type": "checkbox",
            "default": False
        },
        {
            "name": "tags",
            "label": "标签",
            "type": "multi_select",
            "options": ["frontend", "backend", "api"],
            "default": []
        },
        {
            "name": "notes",
            "label": "备注",
            "type": "textarea",
            "default": "",
            "required": False
        }
    ]
)
```

## 迁移说明

由于不保持向后兼容，需要：

1. 删除旧的 `QuestionType` 枚举（TEXT, CONFIRM, CHOICE）
2. 更新所有调用 `get_human_tool()` 的代码
3. 前端 ApprovalPanel 完全重写
