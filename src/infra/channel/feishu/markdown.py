"""
Feishu Markdown adapter for converting standard Markdown to Feishu card elements.

飞书卡片 markdown 标签支持的语法:
- **粗体** / *斜体* / ~~删除线~~
- `行内代码`
- ```代码块```（原生支持，含语法高亮）
- [链接](url)
- 引用块 (> )
- 有序/无序列表

不支持（需要转换）:
- 标题 (#)（转换为粗体）
- 表格（转换为飞书 table 组件）
- 图片 (![alt](url))（需要用 img 元素）
"""

import re
from typing import Any

# 匹配 markdown 表格（表头 + 分隔行 + 数据行）
_TABLE_RE = re.compile(
    r"((?:^[ \t]*\|.+\|[ \t]*\n)(?:^[ \t]*\|[-:\s|]+\|[ \t]*\n)(?:^[ \t]*\|.+\|[ \t]*\n?)+)",
    re.MULTILINE,
)

_CODE_BLOCK_RE = re.compile(r"(```[\s\S]*?```)")

# 匹配 send:// 图片 URI（markdown 格式: ![alt](send://...) 和裸格式: send://...）
_SEND_IMAGE_MD_RE = re.compile(r"!\[([^\]]*)\]\((send://[^)\s]+\.(?:png|jpeg|jpg|gif|bmp|webp))\)")
_SEND_IMAGE_RAW_RE = re.compile(r"(send://[^)\s]+\.(?:png|jpeg|jpg|gif|bmp|webp))\)?")


def _parse_md_table(table_text: str) -> dict | None:
    """将 markdown 表格解析为飞书 table 组件元素"""
    lines = [line.strip() for line in table_text.strip().split("\n") if line.strip()]
    if len(lines) < 3:
        return None

    def split_row(line: str) -> list[str]:
        return [c.strip() for c in line.strip("|").split("|")]

    headers = split_row(lines[0])
    rows = [split_row(line) for line in lines[2:]]
    columns = [
        {"tag": "column", "name": f"c{i}", "display_name": h, "width": "auto"}
        for i, h in enumerate(headers)
    ]
    return {
        "tag": "table",
        "page_size": len(rows) + 1,
        "columns": columns,
        "rows": [{f"c{i}": r[i] if i < len(r) else "" for i in range(len(headers))} for r in rows],
    }


class FeishuMarkdownAdapter:
    """将标准 Markdown 转换为飞书卡片 elements 列表

    - 普通文本/代码块 → {"tag": "markdown", "content": ...}
    - 表格 → {"tag": "table", ...}（飞书 markdown 不支持表格语法）
    - 标题 → 转为粗体（飞书 markdown 不支持 # 标题语法）
    """

    @classmethod
    def build_elements(cls, text: str) -> list[dict]:
        """将 markdown 文本转换为飞书卡片 elements 列表

        返回多个元素：markdown 文本块 + table 组件，按原文顺序排列。
        """
        if not text:
            return []

        # 1. 保护代码块，避免内部内容被表格正则误匹配
        protected, code_blocks = cls._protect_code_blocks(text)

        # 2. 按表格拆分内容，生成 elements
        elements = []
        last_end = 0
        table_count = 0
        max_tables = 5  # 飞书卡片表格数量限制

        for m in _TABLE_RE.finditer(protected):
            # 表格前的文本
            before = protected[last_end : m.start()]
            if before.strip():
                before = cls._restore_code_blocks(before, code_blocks)
                elements.extend(cls._text_to_elements(before))

            # 表格本身
            table_text = cls._restore_code_blocks(m.group(1), code_blocks)
            if table_count < max_tables:
                table_el = _parse_md_table(table_text)
                if table_el:
                    elements.append(table_el)
                else:
                    elements.append({"tag": "markdown", "content": cls._adapt_text(table_text)})
                table_count += 1
            else:
                # 超出表格限制，降级为 markdown 文本
                elements.append({"tag": "markdown", "content": cls._adapt_text(table_text)})

            last_end = m.end()

        # 剩余文本
        remaining = protected[last_end:]
        if remaining.strip():
            remaining = cls._restore_code_blocks(remaining, code_blocks)
            elements.extend(cls._text_to_elements(remaining))

        return elements or [{"tag": "markdown", "content": text.strip()}]

    @classmethod
    def adapt(cls, text: str) -> str:
        """简单适配：仅处理标题和段落间距（向后兼容）"""
        if not text:
            return text
        return cls._adapt_text(text)

    @classmethod
    async def build_elements_with_images(cls, text: str, image_uploader: Any) -> list[dict]:
        """将 markdown 文本转换为飞书卡片 elements，支持 send:// 图片上传嵌入。

        Args:
            text: markdown 文本，可能包含 send://... 图片 URI
            image_uploader: 异步回调 async (uri: str) -> str|None，
                            接收图片 URI 字符串返回飞书 image_key

        Returns:
            飞书卡片 elements 列表（含 img 元素）
        """
        if not text:
            return []

        # 1. 提取所有 send:// 图片 URI
        image_uris: list[str] = []
        for m in _SEND_IMAGE_MD_RE.finditer(text):
            image_uris.append(m.group(2))
        for m in _SEND_IMAGE_RAW_RE.finditer(text):
            uri = m.group(1)
            if uri not in image_uris:
                image_uris.append(uri)

        # 2. 从文本中移除 send:// 图片引用
        cleaned = _SEND_IMAGE_MD_RE.sub("", text)
        cleaned = _SEND_IMAGE_RAW_RE.sub("", cleaned)

        # 3. 上传图片到飞书
        image_elements: list[dict] = []
        for uri in image_uris:
            try:
                image_key = await image_uploader(uri)
                if image_key:
                    image_elements.append({"tag": "img", "img_key": image_key})
            except Exception:
                pass  # Skip failed uploads

        # 4. 对剩余文本构建普通 elements
        text_elements = cls.build_elements(cleaned.strip())

        # 5. 合并：文本 elements + 图片 elements
        return text_elements + image_elements

    @classmethod
    def _adapt_text(cls, text: str) -> str:
        """对文本做飞书兼容适配：标题转粗体 + 清理空行"""
        text, code_blocks = cls._protect_code_blocks(text)
        text = cls._convert_headers(text)
        text = cls._fix_paragraphs(text)
        text = cls._restore_code_blocks(text, code_blocks)
        return text.strip()

    @classmethod
    def _text_to_elements(cls, text: str) -> list[dict]:
        """将文本段转为 markdown elements（处理标题转粗体）"""
        adapted = cls._adapt_text(text)
        if adapted:
            return [{"tag": "markdown", "content": adapted}]
        return []

    @classmethod
    def _protect_code_blocks(cls, text: str) -> tuple[str, list[str]]:
        """提取代码块用占位符保护"""
        code_blocks: list[str] = []

        def replace_block(match: re.Match) -> str:
            code_blocks.append(match.group(0))
            return f"\x00CODEBLOCK_{len(code_blocks) - 1}\x00"

        text = _CODE_BLOCK_RE.sub(replace_block, text)
        return text, code_blocks

    @classmethod
    def _convert_headers(cls, text: str) -> str:
        """将 markdown 标题转换为粗体"""
        lines = text.split("\n")
        result = []
        for line in lines:
            header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if header_match:
                content = header_match.group(2)
                result.append(f"**{content}**")
                result.append("")
            else:
                result.append(line)
        return "\n".join(result)

    @classmethod
    def _fix_paragraphs(cls, text: str) -> str:
        """移除多余空行"""
        return re.sub(r"\n{3,}", "\n\n", text)

    @classmethod
    def _restore_code_blocks(cls, text: str, code_blocks: list[str]) -> str:
        """恢复代码块"""
        for idx, block in enumerate(code_blocks):
            text = text.replace(f"\x00CODEBLOCK_{idx}\x00", block)
        return text
