"""在 E2B 中创建自定义模板，预装 pip 包和系统依赖

用法:
    python scripts/create_e2b_template.py

该脚本会:
1. 基于 code-interpreter-v1 模板
2. 安装系统依赖 (apt-get)
3. 安装额外的 pip 包
4. 构建名为 "lambchat" 的自定义模板

构建完成后，在 .env 中设置 E2B_TEMPLATE=lambchat-prod 即可使用。
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from e2b import Template, default_build_logger

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ============== 配置区域 ==============
# 自定义模板名称
TEMPLATE_ALIAS = "lambchat-prod"

# ============== pip 包 ==============
EXTRA_PIP_PACKAGES = [
    # ========== 数据处理 ==========
    "pandas",
    "openpyxl",
    "xlrd",
    "xlsxwriter",
    "python-docx",
    "python-pptx",
    # ========== 文档格式 ==========
    "markdown",
    "mistune",
    "markdown2",
    "pypdf",
    "PyPDF2",
    "reportlab",
    "fpdf",
    # ========== 其他常用 ==========
    "Pillow",
    "Pygments",
    "jinja2",
    "pyyaml",
    "toml",
    "json5",
    # ========== 网络请求 ==========
    "httpx",
    "aiohttp",
    "requests",
    "urllib3",
    "python-multipart",
    # ========== 数据可视化 ==========
    "matplotlib",
    "seaborn",
    "plotly",
    # ========== 加密/安全 ==========
    "cryptography",
    "pycryptodome",
    "python-jose",
    "passlib",
    "bcrypt",
    # ========== SVG 转换 ==========
    "cairosvg",
    "svglib",
    # ========== 办公文档高级 ==========
    "docx2txt",
    "xhtml2pdf",
    "pdfminer.six",
    "pdfplumber",
    # ========== 日期时间 ==========
    "python-dateutil",
    "pytz",
    "arrow",
    # ========== 压缩/归档 ==========
    "rarfile",
    "py7zr",
    # ========== 数据验证 ==========
    "pydantic",
    "email-validator",
    # ========== Office 协作 ==========
    "python-calamine",
    # ========== 异步编程 ==========
    "aiofiles",
    "asyncpg",
    "motor",
    # ========== CLI/命令行 ==========
    "click",
    "typer",
    "rich",
    "colorama",
    # ========== 文本处理/NLP ==========
    "beautifulsoup4",
    "lxml",
    "jieba",
    "snownlp",
    # ========== 调试/日志 ==========
    "loguru",
    # ========== 浏览器自动化 ==========
    "playwright",
    "selenium",
    # ========== 实用工具 ==========
    "python-dotenv",
    "orjson",
    # ========== 视频配音 ==========
    "moviepy",
    "pydub",
]

# ============== 系统依赖 ==============
SYSTEM_PACKAGES = [
    # 常用工具
    "git",
    "curl",
    "unzip",
    "p7zip-full",
    "ripgrep",  # rg - 快速内容搜索（agent 裸 bash 调用，补 #199）
    "librsvg2-bin",  # rsvg-convert - SVG 转 PNG/PDF（补 #199）
    # 中文字体
    "fonts-noto-cjk",
    "fonts-wqy-zenhei",
    "fonts-wqy-microhei",
    # 视频处理
    "ffmpeg",
    # PDF 相关
    "poppler-utils",
    "pandoc",
    # Python 编译依赖
    "pkg-config",
    "libcairo2-dev",
    "libjpeg-dev",
    "libpng-dev",
    "libfreetype6-dev",
    "libffi-dev",
    "libssl-dev",
    # Playwright / Chromium 系统依赖
    "libnss3",
    "libnspr4",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libcups2",
    "libdrm2",
    "libxkbcommon0",
    "libxcomposite1",
    "libxdamage1",
    "libxfixes3",
    "libxrandr2",
    "libgbm1",
    "libpango-1.0-0",
    "libcairo2",
    "libasound2",
    "libatspi2.0-0",
    "libwayland-client0",
]

# ============== 资源配额 ==============
# Hobby 免费计划限制: 8 vCPU, 8GB RAM, 10GB disk (https://e2b.dev/docs/billing)
CPU_COUNT = 2
MEMORY_MB = 4096
# ======================================


def build_template(template_builder: Any | None = None) -> Any:
    """Create the E2B template definition without performing a remote build."""
    template = (template_builder or Template()).from_template("code-interpreter-v1")
    # 安装系统依赖
    if SYSTEM_PACKAGES:
        apt_cmd = (
            f"sudo apt-get update && "
            f"sudo apt-get install -y {' '.join(SYSTEM_PACKAGES)} && "
            f"sudo rm -rf /var/lib/apt/lists/*"
        )
        template = template.run_cmd(apt_cmd)

    # 安装 pip 包
    if EXTRA_PIP_PACKAGES:
        template = template.pip_install(EXTRA_PIP_PACKAGES)

    # 安装 Playwright Chromium 浏览器
    template = template.run_cmd("playwright install chromium --with-deps")

    # 安装 mcporter（用于沙箱内 MCP 服务器管理）+ opencli（网站转 CLI 工具）
    # 基础模板 code-interpreter-v1 已自带 Node.js 20 + npm，无需额外安装
    template = template.run_cmd("sudo npm install -g mcporter @jackwener/opencli")
    template = template.run_cmd("mkdir -p ~/.mcporter")
    return template


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_candidate(
    candidate_tag: str,
    api_key: str,
    *,
    manifest_dir: Path = Path("workspace/e2b-rollouts"),
    template_api: Any = Template,
    template_builder: Any | None = None,
    build_logger: Any | None = None,
) -> Path:
    """Build a uniquely tagged candidate and persist only non-secret identifiers."""
    if not candidate_tag.startswith("candidate-"):
        raise ValueError("candidate tag must start with 'candidate-'")
    if not api_key:
        raise ValueError("E2B_API_KEY is not configured")

    build_info = template_api.build(
        build_template(template_builder),
        TEMPLATE_ALIAS,
        tags=[candidate_tag],
        cpu_count=CPU_COUNT,
        memory_mb=MEMORY_MB,
        api_key=api_key,
        on_build_logs=build_logger or default_build_logger(),
    )
    build_id = str(build_info.build_id)
    manifest = {
        "rollout_id": str(uuid.uuid4()),
        "candidate_tag": candidate_tag,
        "template_name": TEMPLATE_ALIAS,
        "template_id": str(build_info.template_id),
        "build_id": build_id,
        "immutable_ref": f"{TEMPLATE_ALIAS}:{build_id}",
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = manifest_dir / f"{candidate_tag}.json"
    _write_manifest(manifest_path, manifest)
    return manifest_path


async def resolve_e2b_api_key(settings_service: Any | None = None) -> str:
    """Resolve the build credential through the database-first settings service."""
    if settings_service is None:
        from src.infra.settings.service import SettingsService

        settings_service = SettingsService.get_instance()
    value = await settings_service.get_raw("E2B_API_KEY")
    return str(value or "")


def _candidate_tag() -> str:
    return datetime.now(timezone.utc).strftime("candidate-%Y%m%d%H%M%S")


async def async_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build"], nargs="?", default="build")
    args = parser.parse_args(argv)
    if args.command != "build":
        parser.error("unsupported command")

    e2b_api_key = await resolve_e2b_api_key()
    if not e2b_api_key:
        print("Error: E2B_API_KEY is not configured.", file=sys.stderr)
        return 1

    print("\nBuilding template (this may take a few minutes)...\n")
    try:
        manifest_path = build_candidate(_candidate_tag(), e2b_api_key)
        print(f"Candidate manifest: {manifest_path}")
    except KeyboardInterrupt:
        print("\n\nBuild cancelled by user.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n\nError building template: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
