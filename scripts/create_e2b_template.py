"""在 E2B 中创建自定义模板，预装 pip 包和系统依赖

用法:
    python scripts/create_e2b_template.py

该脚本会:
1. 基于 code-interpreter-v1 模板
2. 安装系统依赖 (apt-get)
3. 安装额外的 pip 包
4. 构建名为 "lambchat" 的自定义模板

构建完成后，在 .env 中设置 E2B_TEMPLATE=lambchat 即可使用。
"""

import os
import sys

# 导入 settings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.kernel.config import settings

# ============== 配置区域 ==============
# 自定义模板名称
TEMPLATE_ALIAS = "lambchat"

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
# Hobby 免费计划限制: 8 vCPU, 8GB RAM, 10GB disk
CPU_COUNT = 2
MEMORY_MB = 2024
# ======================================


def main():
    from e2b import Template, default_build_logger

    e2b_api_key = settings.E2B_API_KEY
    if not e2b_api_key:
        print("Error: E2B_API_KEY is not set in settings.")
        sys.exit(1)

    print(f"Creating E2B template: {TEMPLATE_ALIAS}")
    print(f"Pip packages: {len(EXTRA_PIP_PACKAGES)}")
    print(f"System packages: {len(SYSTEM_PACKAGES)}")
    print(f"Resources: {CPU_COUNT} vCPU, {MEMORY_MB}MB RAM")

    # 定义模板
    template = Template().from_template("code-interpreter-v1")

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

    # 安装 Bun + mcporter（用于沙箱内 MCP 服务器管理）
    template = template.run_cmd("curl -fsSL https://bun.sh/install | bash")
    template = template.run_cmd("~/.bun/bin/bun install -g mcporter")
    template = template.run_cmd("mkdir -p ~/.mcporter")

    # 安装 Node.js / npx（sandbox MCP 常用 npx 启动 stdio 服务器）
    template = template.run_cmd(
        "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash - && sudo apt-get install -y nodejs && sudo rm -rf /var/lib/apt/lists/*"
    )

    print("\nBuilding template (this may take a few minutes)...\n")

    try:
        Template.build(
            template,
            alias=TEMPLATE_ALIAS,
            cpu_count=CPU_COUNT,
            memory_mb=MEMORY_MB,
            api_key=e2b_api_key,
            on_build_logs=default_build_logger(),
        )
        print(f"\nTemplate '{TEMPLATE_ALIAS}' built successfully!")
        print(f"Set E2B_TEMPLATE={TEMPLATE_ALIAS} in your .env to use it.")
    except KeyboardInterrupt:
        print("\n\nBuild cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError building template: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
