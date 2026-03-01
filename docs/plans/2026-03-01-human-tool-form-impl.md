# Human Tool 2.0 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 重构 ask_human 工具，支持多字段表单输入，替代原有的单字段模式。

**Architecture:** 将 human_tool.py 拆分为模块化结构，使用 Pydantic 模型定义表单字段，前后端通过 JSON 结构通信，前端使用 ChatGPT 风格的表单 UI。

**Tech Stack:** Python + Pydantic + LangChain (后端) / React + Tailwind CSS (前端)

---

## Task 1: 创建后端模型定义

**Files:**
- Create: `src/infra/tool/human_tool/__init__.py`
- Create: `src/infra/tool/human_tool/models.py`

**Step 1: 创建模块目录**

```bash
mkdir -p /home/yangyang/LambChat/src/infra/tool/human_tool
```

**Step 2: 创建 models.py**

```python
"""
Human Tool 数据模型

定义表单字段类型和输入参数模型。
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    """
    表单字段类型枚举

    - text: 单行文本输入
    - textarea: 多行文本输入
    - number: 数字输入
    - checkbox: 布尔开关
    - select: 单选下拉
    - multi_select: 多选（复选框组）
    """

    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    CHECKBOX = "checkbox"
    SELECT = "select"
    MULTI_SELECT = "multi_select"

    def __str__(self) -> str:
        return self.value


class FormField(BaseModel):
    """
    表单字段定义

    Attributes:
        name: 字段标识符，用于返回结果中的键名
        label: 用户界面显示的标签文本
        type: 字段类型
        placeholder: 输入框占位提示文本
        default: 字段默认值
        required: 是否为必填字段
        options: 选项列表（仅 select/multi_select 类型使用）
    """

    name: str = Field(..., description="字段标识符")
    label: str = Field(..., description="显示标签")
    type: FieldType = Field(default=FieldType.TEXT, description="字段类型")
    placeholder: Optional[str] = Field(default=None, description="占位提示")
    default: Optional[Any] = Field(default=None, description="默认值")
    required: bool = Field(default=True, description="是否必填")
    options: Optional[list[str]] = Field(
        default=None, description="选项列表（select/multi_select 使用）"
    )


class AskHumanInput(BaseModel):
    """
    ask_human 工具的输入参数

    Attributes:
        message: 表单标题/提示信息，向用户说明需要填写的内容
        fields: 表单字段列表
        timeout: 等待用户响应的超时时间（秒）
    """

    message: str = Field(..., description="表单标题/提示信息")
    fields: list[FormField] = Field(
        ...,
        min_length=1,
        description="表单字段列表，至少需要一个字段",
    )
    timeout: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="等待响应的超时时间（秒），范围 10-3600",
    )
```

**Step 3: 创建 __init__.py**

```python
"""
Human Tool 模块

提供 Agent 请求人工输入的工具。
"""

from src.infra.tool.human_tool.models import AskHumanInput, FieldType, FormField
from src.infra.tool.human_tool.tool import AskHumanTool, get_human_tool

__all__ = [
    "AskHumanInput",
    "AskHumanTool",
    "FieldType",
    "FormField",
    "get_human_tool",
]
```

**Step 4: 验证模块导入**

```bash
cd /home/yangyang/LambChat && python -c "from src.infra.tool.human_tool.models import FormField, FieldType; print('OK')"
```

Expected: 输出 `OK`

---

## Task 2: 创建工具实现

**Files:**
- Create: `src/infra/tool/human_tool/tool.py`

**Step 1: 创建 tool.py**

```python
"""
Human Tool 实现

让 Agent 可以请求人工输入，支持多字段表单。
"""

import json
import logging
from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from src.infra.tool.human_tool.models import AskHumanInput, FieldType, FormField

logger = logging.getLogger(__name__)


class AskHumanTool(BaseTool):
    """
    请求人工输入的表单工具

    当 Agent 需要向用户收集结构化信息时调用此工具。
    工具会阻塞直到用户响应或超时。

    使用场景：
    - 需要用户提供多个参数
    - 需要用户确认或选择选项
    - 收集结构化输入

    字段类型：
    - text: 单行文本输入
    - textarea: 多行文本输入
    - number: 数字输入
    - checkbox: 布尔开关（是/否）
    - select: 单选下拉
    - multi_select: 多选（复选框组）
    """

    name: str = "ask_human"
    description: str = """向用户收集信息的表单工具。

使用场景：
- 需要用户提供多个参数
- 需要用户确认或选择选项
- 收集结构化输入

字段类型：
- text: 单行文本输入
- textarea: 多行文本输入
- number: 数字输入
- checkbox: 布尔开关（是/否）
- select: 单选下拉
- multi_select: 多选（复选框组）

参数：
- message: 表单标题/提示信息
- fields: 表单字段列表，每个字段包含:
  - name: 字段标识符（返回结果中的键名）
  - label: 显示标签
  - type: 字段类型
  - placeholder: 占位提示（可选）
  - default: 默认值（可选）
  - required: 是否必填（默认 true）
  - options: 选项列表（select/multi_select 类型必填）

示例：
ask_human(
    message="请填写部署配置",
    fields=[
        {"name": "env", "label": "环境", "type": "select",
         "options": ["development", "staging", "production"], "default": "development"},
        {"name": "replicas", "label": "副本数", "type": "number", "default": 1},
        {"name": "enable_cache", "label": "启用缓存", "type": "checkbox", "default": false},
        {"name": "notes", "label": "备注", "type": "textarea", "default": ""},
    ]
)

返回：
用户填写后的 JSON 对象，键为字段 name，值为用户输入。
"""
    args_schema: Type[BaseModel] = AskHumanInput
    return_direct: bool = False

    # 从 context 注入（可选，优先使用 TraceContext）
    session_id: str = ""

    def _run(self, message: str, fields: list, timeout: int = 300) -> str:
        """同步执行（不支持，返回提示）"""
        return "Error: ask_human only supports async execution. Use ainvoke instead."

    async def _arun(
        self,
        message: str,
        fields: list,
        timeout: int = 300,
    ) -> str:
        """
        异步执行：创建审批请求并等待响应

        Args:
            message: 表单标题/提示信息
            fields: 表单字段列表
            timeout: 超时时间（秒），范围 10-3600

        Returns:
            用户填写的 JSON 结果，或超时/拒绝的错误消息
        """
        # 解析字段
        parsed_fields = self._parse_fields(fields)

        # 处理默认值：为每个字段设置默认值
        for field in parsed_fields:
            if field.default is None:
                field.default = self._get_type_default(field.type)

        # 获取当前请求上下文
        from src.infra.logging.context import TraceContext

        ctx = TraceContext.get_request_context()
        session_id = self.session_id or ctx.session_id
        run_id = ctx.run_id

        # 创建审批请求
        from src.api.routes.human import create_approval

        approval = await create_approval(
            message=message,
            approval_type="form",
            fields=[f.model_dump() for f in parsed_fields],
            session_id=session_id or None,
        )

        # 通过 SSE 流发送 approval_required 事件
        await self._send_approval_event(approval, session_id, run_id)

        # 等待用户响应
        from src.api.routes.human import wait_for_response

        response = await wait_for_response(approval.id, timeout=timeout)

        if response is None:
            # 超时：使用默认值构建响应
            default_response = {f.name: f.default for f in parsed_fields}
            return json.dumps(
                {
                    "status": "timeout",
                    "message": f"等待用户响应超时（{timeout}秒），已使用默认值",
                    "data": default_response,
                },
                ensure_ascii=False,
            )

        if not response.approved:
            return json.dumps(
                {
                    "status": "rejected",
                    "message": "用户取消了此表单",
                    "data": None,
                },
                ensure_ascii=False,
            )

        # 返回用户的响应数据
        try:
            # response.response 可能是 dict 或 JSON 字符串
            if isinstance(response.response, dict):
                return json.dumps(response.response, ensure_ascii=False)
            return response.response
        except Exception:
            return json.dumps(
                {"status": "error", "message": "响应解析失败", "data": None},
                ensure_ascii=False,
            )

    def _parse_fields(self, fields: list) -> list[FormField]:
        """解析字段列表为 FormField 对象"""
        result = []
        for f in fields:
            if isinstance(f, FormField):
                result.append(f)
            elif isinstance(f, dict):
                # 转换 type 字符串为枚举
                if "type" in f and isinstance(f["type"], str):
                    f["type"] = FieldType(f["type"])
                result.append(FormField(**f))
        return result

    def _get_type_default(self, field_type: FieldType) -> Any:
        """获取字段类型的默认值"""
        defaults = {
            FieldType.TEXT: "",
            FieldType.TEXTAREA: "",
            FieldType.NUMBER: 0,
            FieldType.CHECKBOX: False,
            FieldType.SELECT: None,
            FieldType.MULTI_SELECT: [],
        }
        return defaults.get(field_type, "")

    async def _send_approval_event(
        self, approval, session_id: Optional[str], run_id: Optional[str]
    ) -> None:
        """发送 approval_required 事件到 SSE 流"""
        if not session_id:
            logger.warning("[AskHuman] Cannot send approval event: no session_id")
            return

        try:
            from src.infra.session.dual_writer import get_dual_writer

            dual_writer = get_dual_writer()
            await dual_writer.write_event(
                session_id=session_id,
                event_type="approval_required",
                data={
                    "id": approval.id,
                    "message": approval.message,
                    "type": approval.type,
                    "fields": approval.fields,
                },
                run_id=run_id,
            )
            logger.info(
                f"[AskHuman] Sent approval_required event: approval_id={approval.id}"
            )
        except Exception as e:
            logger.error(f"[AskHuman] Failed to send approval event: {e}")


def get_human_tool(session_id: str = "") -> AskHumanTool:
    """
    获取 ask_human 工具实例

    Args:
        session_id: 会话 ID，用于关联审批请求（可选，优先使用 TraceContext）

    Returns:
        配置好的 AskHumanTool 实例
    """
    return AskHumanTool(session_id=session_id)
```

**Step 2: 验证工具导入**

```bash
cd /home/yangyang/LambChat && python -c "from src.infra.tool.human_tool import get_human_tool; print('OK')"
```

Expected: 输出 `OK`

---

## Task 3: 更新存储模型

**Files:**
- Modify: `src/infra/storage/mongodb.py` (PendingApproval, ApprovalResponse 类)

**Step 1: 修改 PendingApproval 模型**

找到 `class PendingApproval` (约121行)，替换为：

```python
class PendingApproval(BaseModel):
    """
    待处理的审批请求

    Attributes:
        id: 审批请求唯一标识
        message: 表单标题/提示信息
        type: 审批类型（固定为 "form"）
        fields: 表单字段列表
        status: 状态（pending/approved/rejected）
        session_id: 关联的会话 ID
        created_at: 创建时间
    """

    id: str
    message: str
    type: str = "form"
    fields: List[dict] = []  # 表单字段列表，每个字段是一个 dict
    status: str = "pending"
    session_id: Optional[str] = None
    created_at: Optional[datetime] = None
```

**Step 2: 修改 ApprovalResponse 模型**

找到 `class ApprovalResponse` (约133行)，替换为：

```python
class ApprovalResponse(BaseModel):
    """
    审批响应

    Attributes:
        approved: 是否批准/提交
        response: 响应数据（表单字段名到值的映射）
    """

    approved: bool
    response: dict = {}  # 改为 dict 类型
```

**Step 3: 验证模型**

```bash
cd /home/yangyang/LambChat && python -c "from src.infra.storage.mongodb import PendingApproval, ApprovalResponse; print('OK')"
```

---

## Task 4: 更新 API 路由

**Files:**
- Modify: `src/api/routes/human.py`

**Step 1: 修改 create_approval 函数签名**

找到 `async def create_approval` (约79行)，修改参数：

```python
async def create_approval(
    message: str,
    approval_type: str = "form",
    fields: Optional[List[dict]] = None,  # 替换原来的 choices
    session_id: Optional[str] = None,
) -> PendingApproval:
    """
    创建审批请求 (供 Agent 调用)

    Args:
        message: 表单标题
        approval_type: 类型 (固定为 "form")
        fields: 表单字段列表
        session_id: 关联的会话 ID

    Returns:
        PendingApproval 对象
    """
    approval_id = str(uuid.uuid4())
    approval = PendingApproval(
        id=approval_id,
        message=message,
        type=approval_type,
        fields=fields or [],  # 使用 fields
        status="pending",
        session_id=session_id,
        created_at=datetime.now(),
    )

    # 存储到 MongoDB
    await _approval_storage.create(approval)

    # 创建本地 Event（单进程优化）
    _local_events[approval_id] = asyncio.Event()

    # 通知前端有新的审批请求
    await _notify_approval_created(session_id or "")

    return approval
```

**Step 2: 修改 respond_to_approval API**

找到 `@router.post("/{approval_id}/respond")` (约204行)，修改请求体处理：

```python
@router.post("/{approval_id}/respond")
async def respond_to_approval(
    approval_id: str,
    approved: bool = Query(..., description="是否批准"),
    response: str = Query("{}", description="响应数据（JSON 字符串）"),
):
    """
    响应审批请求

    前端调用此接口提交表单数据。
    """
    import json

    approval = await _approval_storage.get(approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="审批请求不存在")

    if approval.status != "pending":
        raise HTTPException(status_code=400, detail="审批请求已处理")

    # 解析 JSON 响应
    try:
        response_data = json.loads(response) if response else {}
    except json.JSONDecodeError:
        response_data = {}

    # 记录响应并更新状态
    approval_response = ApprovalResponse(approved=approved, response=response_data)
    status = "approved" if approved else "rejected"
    await _approval_storage.update_status(approval_id, status, approval_response)

    # 通知等待的 Agent
    await notify_approval_response(approval_id, approval_response)

    # 触发本地 Event
    if approval_id in _local_events:
        _local_events[approval_id].set()

    return {"status": "success", "approval_id": approval_id, "approved": approved}
```

---

## Task 5: 删除旧文件并更新导入

**Files:**
- Delete: `src/infra/tool/human_tool.py`
- Modify: `src/agents/search_agent/context.py`

**Step 1: 删除旧文件**

```bash
rm /home/yangyang/LambChat/src/infra/tool/human_tool.py
```

**Step 2: 更新导入路径**

在 `src/agents/search_agent/context.py` 中，找到：

```python
from src.infra.tool.human_tool import get_human_tool
```

确认导入路径正确（应该已经可以工作，因为 __init__.py 导出了 get_human_tool）。

---

## Task 6: 更新前端类型定义

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: 添加表单相关类型**

找到 `PendingApproval` 接口（约126行），替换为：

```typescript
// ============================================
// Form Field Types (Human Tool)
// ============================================

export type FormFieldType =
  | 'text'
  | 'textarea'
  | 'number'
  | 'checkbox'
  | 'select'
  | 'multi_select';

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
  session_id?: string | null;
}
```

---

## Task 7: 更新 useApprovals Hook

**Files:**
- Modify: `frontend/src/hooks/useApprovals.ts`

**Step 1: 修改 respondToApproval 函数**

找到 `respondToApproval` 函数（约47行），修改为支持 JSON 响应：

```typescript
const respondToApproval = useCallback(
  async (
    approvalId: string,
    response: Record<string, unknown>,
    approved: boolean = true
  ) => {
    setIsLoading(true);
    try {
      // 将响应对象序列化为 JSON 字符串
      const responseJson = JSON.stringify(response);
      const params = new URLSearchParams({
        approved: String(approved),
        response: responseJson,
      });
      const res = await fetch(
        `${API_BASE}/human/${approvalId}/respond?${params}`,
        {
          method: "POST",
        }
      );

      if (res.ok) {
        setApprovals((prev) => prev.filter((a) => a.id !== approvalId));
        return true;
      }
      return false;
    } catch (error) {
      console.error("Failed to respond to approval:", error);
      return false;
    } finally {
      setIsLoading(false);
    }
  },
  []
);
```

**Step 2: 更新返回类型**

更新函数签名中的 `response` 参数类型从 `string` 改为 `Record<string, unknown>`。

---

## Task 8: 重构 ApprovalPanel 组件

**Files:**
- Modify: `frontend/src/components/panels/ApprovalPanel.tsx`

**Step 1: 完全重写组件**

```tsx
import { useState, useEffect } from "react";
import {
  AlertCircle,
  Send,
  CornerDownLeft,
  ChevronLeft,
  ChevronRight,
  ListOrdered,
  Check,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import type { PendingApproval, FormField } from "../../types";

interface FormValues {
  [key: string]: unknown;
}

interface ApprovalPanelProps {
  approvals: PendingApproval[];
  onRespond: (id: string, response: Record<string, unknown>, approved: boolean) => void;
  isLoading: boolean;
}

/**
 * 表单字段渲染组件
 */
function FormFieldRenderer({
  field,
  value,
  onChange,
  disabled,
}: {
  field: FormField;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
  disabled: boolean;
}) {
  const { t } = useTranslation();

  const handleChange = (newValue: unknown) => {
    onChange(field.name, newValue);
  };

  switch (field.type) {
    case "text":
      return (
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
            {field.label}
            {field.required && <span className="text-red-500 ml-0.5">*</span>}
          </label>
          <input
            type="text"
            value={(value as string) ?? ""}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={field.placeholder}
            disabled={disabled}
            className="w-full rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-blue-400"
          />
        </div>
      );

    case "textarea":
      return (
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
            {field.label}
            {field.required && <span className="text-red-500 ml-0.5">*</span>}
          </label>
          <textarea
            value={(value as string) ?? ""}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={field.placeholder}
            disabled={disabled}
            rows={3}
            className="w-full resize-none rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-blue-400"
          />
        </div>
      );

    case "number":
      return (
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
            {field.label}
            {field.required && <span className="text-red-500 ml-0.5">*</span>}
          </label>
          <input
            type="number"
            value={(value as number) ?? 0}
            onChange={(e) => handleChange(Number(e.target.value))}
            placeholder={field.placeholder}
            disabled={disabled}
            className="w-full rounded-xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-900 placeholder-gray-400 transition-all focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:placeholder-stone-500 dark:focus:border-blue-400"
          />
        </div>
      );

    case "checkbox":
      return (
        <label className="flex items-center gap-3 cursor-pointer">
          <div className="relative">
            <input
              type="checkbox"
              checked={(value as boolean) ?? false}
              onChange={(e) => handleChange(e.target.checked)}
              disabled={disabled}
              className="peer sr-only"
            />
            <div className="h-5 w-5 rounded border-2 border-gray-300 bg-white transition-all peer-checked:border-blue-500 peer-checked:bg-blue-500 peer-focus:ring-2 peer-focus:ring-blue-500/20 dark:border-stone-600 dark:bg-stone-700 dark:peer-checked:border-blue-400 dark:peer-checked:bg-blue-400">
              <Check
                size={14}
                className="absolute left-0.5 top-0.5 text-white opacity-0 transition-opacity peer-checked:opacity-100"
              />
            </div>
          </div>
          <span className="text-sm text-gray-700 dark:text-stone-300">
            {field.label}
          </span>
        </label>
      );

    case "select":
      return (
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
            {field.label}
            {field.required && <span className="text-red-500 ml-0.5">*</span>}
          </label>
          <div className="relative">
            <select
              value={(value as string) ?? ""}
              onChange={(e) => handleChange(e.target.value)}
              disabled={disabled}
              className="w-full appearance-none rounded-xl border border-gray-200 bg-white px-4 py-2.5 pr-10 text-sm text-gray-900 transition-all focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-100 dark:focus:border-blue-400"
            >
              {field.options?.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
              <ChevronDown size={16} className="text-gray-400" />
            </div>
          </div>
        </div>
      );

    case "multi_select":
      return (
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-gray-700 dark:text-stone-300">
            {field.label}
            {field.required && <span className="text-red-500 ml-0.5">*</span>}
          </label>
          <div className="flex flex-wrap gap-2">
            {field.options?.map((option) => {
              const selected = ((value as string[]) ?? []).includes(option);
              return (
                <button
                  key={option}
                  type="button"
                  onClick={() => {
                    const current = (value as string[]) ?? [];
                    const newValue = selected
                      ? current.filter((v) => v !== option)
                      : [...current, option];
                    handleChange(newValue);
                  }}
                  disabled={disabled}
                  className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-all ${
                    selected
                      ? "border-blue-500 bg-blue-500 text-white dark:border-blue-400 dark:bg-blue-400"
                      : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
                  } disabled:opacity-50`}
                >
                  {option}
                </button>
              );
            })}
          </div>
        </div>
      );

    default:
      return null;
  }
}

// ChevronDown icon for select
function ChevronDown({ size, className }: { size: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

/**
 * 审批面板组件
 *
 * ChatGPT 风格的表单 UI，支持：
 * - 多字段表单渲染
 * - 深色/浅色主题适配
 * - 多个表单时的导航切换
 */
export function ApprovalPanel({
  approvals,
  onRespond,
  isLoading,
}: ApprovalPanelProps) {
  const { t } = useTranslation();
  const [formValues, setFormValues] = useState<Record<string, FormValues>>({});
  const [currentIndex, setCurrentIndex] = useState(0);

  // 当 approvals 数量变化时，调整 currentIndex
  useEffect(() => {
    if (currentIndex >= approvals.length) {
      setCurrentIndex(Math.max(0, approvals.length - 1));
    }
  }, [approvals.length, currentIndex]);

  // 初始化表单值
  useEffect(() => {
    approvals.forEach((approval) => {
      if (!formValues[approval.id]) {
        const initialValues: FormValues = {};
        approval.fields.forEach((field) => {
          initialValues[field.name] = field.default;
        });
        setFormValues((prev) => ({
          ...prev,
          [approval.id]: initialValues,
        }));
      }
    });
  }, [approvals]);

  if (approvals.length === 0) return null;

  const safeIndex = Math.min(currentIndex, approvals.length - 1);
  const currentApproval = approvals[safeIndex];

  if (!currentApproval || !currentApproval.message) {
    return null;
  }

  const handleFieldChange = (name: string, value: unknown) => {
    setFormValues((prev) => ({
      ...prev,
      [currentApproval.id]: {
        ...(prev[currentApproval.id] ?? {}),
        [name]: value,
      },
    }));
  };

  const handleSubmit = () => {
    const values = formValues[currentApproval.id] ?? {};
    onRespond(currentApproval.id, values, true);
  };

  const handleCancel = () => {
    onRespond(currentApproval.id, {}, false);
  };

  const goToPrev = () => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  };

  const goToNext = () => {
    setCurrentIndex((prev) => Math.min(approvals.length - 1, prev + 1));
  };

  const currentValues = formValues[currentApproval.id] ?? {};

  return (
    <div className="w-full px-3 py-2 sm:px-4 sm:py-3 bg-white dark:bg-stone-900">
      <div className="mx-auto max-w-3xl xl:max-w-5xl">
        {/* 导航控制栏 */}
        {approvals.length > 1 && (
          <div className="mb-2 flex items-center justify-between px-1">
            <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-stone-400">
              <ListOrdered size={14} />
              <span>
                {currentIndex + 1} / {approvals.length}
              </span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={goToPrev}
                disabled={currentIndex === 0}
                className="p-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
              >
                <ChevronLeft size={16} />
              </button>
              <button
                onClick={goToNext}
                disabled={currentIndex === approvals.length - 1}
                className="p-1.5 rounded-lg border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}

        <div
          className="overflow-hidden rounded-2xl border border-gray-200 bg-white shadow-sm transition-all duration-200 dark:border-stone-700 dark:bg-stone-800"
          key={currentApproval.id}
        >
          {/* Header */}
          <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100 dark:border-stone-700">
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/30">
              <AlertCircle
                size={12}
                className="text-blue-600 dark:text-blue-400"
              />
            </div>
            <span className="text-sm font-medium text-gray-500 dark:text-stone-400">
              {t("approvals.needsConfirmation")}
            </span>
          </div>

          {/* Message content */}
          <div className="px-4 py-3 sm:px-5 border-b border-gray-100 dark:border-stone-700">
            <div className="prose prose-stone dark:prose-invert max-w-none text-sm leading-relaxed text-gray-800 dark:text-stone-200 prose-p:my-1 prose-headings:my-2">
              <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                {currentApproval.message}
              </ReactMarkdown>
            </div>
          </div>

          {/* Form fields */}
          <div className="px-4 py-4 sm:px-5 space-y-4">
            {currentApproval.fields.map((field) => (
              <FormFieldRenderer
                key={field.name}
                field={field}
                value={currentValues[field.name]}
                onChange={handleFieldChange}
                disabled={isLoading}
              />
            ))}
          </div>

          {/* Actions */}
          <div className="px-4 py-3 sm:px-5 bg-gray-50 dark:bg-stone-800/50 flex flex-col gap-2 sm:flex-row sm:justify-end">
            <button
              onClick={handleCancel}
              disabled={isLoading}
              className="flex items-center justify-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 shadow-sm transition-all hover:bg-gray-50 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:border-stone-600 dark:bg-transparent dark:text-stone-200 dark:hover:bg-stone-700"
            >
              <X size={18} />
              <span>{t("approvals.cancel") || "取消"}</span>
            </button>
            <button
              onClick={handleSubmit}
              disabled={isLoading}
              className="flex items-center justify-center gap-2 rounded-xl bg-blue-500 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-blue-600 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed dark:bg-blue-500 dark:hover:bg-blue-400"
            >
              <Send size={18} />
              <span>{t("approvals.submit") || "提交"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

---

## Task 9: 添加国际化文本

**Files:**
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/en.json`

**Step 1: 添加中文翻译**

在 `approvals` 部分添加：

```json
{
  "approvals": {
    "needsConfirmation": "需要确认",
    "cancel": "取消",
    "submit": "提交"
  }
}
```

**Step 2: 添加英文翻译**

在 `approvals` 部分添加：

```json
{
  "approvals": {
    "needsConfirmation": "Needs Confirmation",
    "cancel": "Cancel",
    "submit": "Submit"
  }
}
```

---

## Task 10: 验证集成

**Step 1: 验证后端启动**

```bash
cd /home/yangyang/LambChat && python -c "
from src.infra.tool.human_tool import get_human_tool, FormField, FieldType
tool = get_human_tool('test-session')
print(f'Tool name: {tool.name}')
print(f'Fields: {FieldType.TEXT}, {FieldType.SELECT}')
print('Backend OK')
"
```

Expected: 输出工具名称和字段类型

**Step 2: 验证前端编译**

```bash
cd /home/yangyang/LambChat/frontend && npm run build
```

Expected: 编译成功，无错误

**Step 3: 提交变更**

```bash
git add src/infra/tool/human_tool/ src/infra/storage/mongodb.py src/api/routes/human.py src/agents/search_agent/context.py frontend/src/types/index.ts frontend/src/hooks/useApprovals.ts frontend/src/components/panels/ApprovalPanel.tsx frontend/src/i18n/locales/*.json
git commit -m "feat(human-tool): redesign with multi-field form support

- Add form field types: text, textarea, number, checkbox, select, multi_select
- Refactor human_tool.py into modular package
- Update ApprovalPanel with ChatGPT-style form UI
- Support dark/light theme adaptation
- Breaking change: old text/confirm/choice types removed"
```

---

## 文件变更摘要

| 操作 | 文件 |
|------|------|
| 创建 | `src/infra/tool/human_tool/__init__.py` |
| 创建 | `src/infra/tool/human_tool/models.py` |
| 创建 | `src/infra/tool/human_tool/tool.py` |
| 删除 | `src/infra/tool/human_tool.py` |
| 修改 | `src/infra/storage/mongodb.py` |
| 修改 | `src/api/routes/human.py` |
| 修改 | `frontend/src/types/index.ts` |
| 修改 | `frontend/src/hooks/useApprovals.ts` |
| 修改 | `frontend/src/components/panels/ApprovalPanel.tsx` |
| 修改 | `frontend/src/i18n/locales/zh.json` |
| 修改 | `frontend/src/i18n/locales/en.json` |
