"""在 Daytona 中为 daytona-medium 快照添加自定义 pip 包

用法:
    python scripts/create_custom_snapshot.py

该脚本会:
1. 使用 daytona-medium 作为基础镜像
2. 安装额外的 pip 包
3. 创建名为 "lambchat-medium" 的自定义快照
"""

import os
import sys

import daytona
from daytona import CreateSnapshotParams, DaytonaConfig, Image, Resources

# 导入 settings
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.kernel.config import settings

# ============== 配置区域 ==============
# 自定义快照名称
SNAPSHOT_NAME = "lambchat-medium-plus"

# 基础镜像 (daytona-medium 使用 debian_slim)
BASE_IMAGE = "debian_slim"

# Python 版本
PYTHON_VERSION = "3.12"

# 要添加的额外 pip 包
EXTRA_PIP_PACKAGES = [
    # ========== 数据处理 ==========
    "pandas",  # 数据分析
    "openpyxl",  # Excel 读写
    "xlrd",  # Excel 读取 (旧格式)
    "xlsxwriter",  # Excel 写入
    "python-docx",  # Word 文档
    "python-pptx",  # PPT 演示文稿
    # ========== 文档格式 ==========
    "markdown",  # Markdown 处理
    "mistune",  # Markdown 解析 (更快)
    "markdown2",  # Markdown 扩展
    "pypdf",  # PDF 读取
    "PyPDF2",  # PDF 操作 (旧版)
    "reportlab",  # PDF 生成
    "fpdf",  # PDF 生成 (简单)
    "pdfkit",  # HTML 转 PDF (需要系统安装 wkhtmltopdf)
    # ========== 其他常用 ==========
    "Pillow",  # 图片处理
    "Pygments",  # 代码高亮
    "jinja2",  # 模板引擎
    "pyyaml",  # YAML 处理
    "toml",  # TOML 处理
    "json5",  # JSON5 支持
    # ========== 网络请求 ==========
    "httpx",  # 异步 HTTP 客户端
    "aiohttp",  # 异步 HTTP (旧版)
    "requests",  # 同步 HTTP 客户端
    "urllib3",  # HTTP 库 (requests 依赖)
    "python-multipart",  # 文件上传
    # ========== 数据可视化 ==========
    "matplotlib",  # 基础绘图
    "seaborn",  # 统计绘图
    "plotly",  # 交互式图表
    # ========== 加密/安全 ==========
    "cryptography",  # 加密库
    "pycryptodome",  # 加密算法
    "python-jose",  # JWT 令牌
    "passlib",  # 密码哈希
    "bcrypt",  # bcrypt 哈希
    # ========== SVG 转换 ==========
    "cairosvg",  # SVG 转 PNG/PDF (依赖 libcairo2)
    "svglib",  # SVG 解析 + reportlab 渲染
    # ========== 办公文档高级 ==========
    "pypandoc",  # Pandoc 包装 (需要系统安装 pandoc)
    "docx2txt",  # Word 文本提取
    "xhtml2pdf",  # HTML/CSS 转 PDF
    "pdfminer.six",  # PDF 文本提取 (维护版)
    "pdfplumber",  # PDF 表格提取
    # ========== 日期时间 ==========
    "python-dateutil",  # 日期时间扩展
    "pytz",  # 时区处理
    "arrow",  # 更好的日期时间
    # ========== 压缩/归档 ==========
    "rarfile",  # RAR 文件
    "py7zr",  # 7z 文件
    # ========== 数据验证 ==========
    "pydantic",  # 数据验证
    "email-validator",  # 邮箱验证
    # ========== Office 协作 ==========
    "python-calamine",  # Excel/PDF 读取 (Rust 实现，更快)
    # ========== 异步编程 ==========
    "aiofiles",  # 异步文件
    "asyncpg",  # 异步 PostgreSQL
    "motor",  # 异步 MongoDB
    # ========== CLI/命令行 ==========
    "click",  # CLI 框架
    "typer",  # CLI (类型友好)
    "rich",  # 富文本输出
    "colorama",  # 彩色终端
    # ========== 文本处理/NLP ==========
    "beautifulsoup4",  # HTML 解析
    "lxml",  # XML/HTML (C 实现)
    "jieba",  # 中文分词
    "snownlp",  # 中文情感分析
    # ========== 调试/日志 ==========
    "loguru",  # 简单日志
    "sentry-sdk",  # 错误追踪
    # ========== 爬虫 ==========
    "playwright",  # 浏览器自动化
    "selenium",  # 浏览器自动化
    # ========== 实用工具 ==========
    "python-dotenv",  # .env 加载
    "orjson",  # 快速 JSON
    # ========== 视频配音 ==========
    "moviepy",  # 视频编辑
    "pydub",  # 音频处理
]

# ============== 资源配额 ==============
# daytona-medium: 2 vCPU, 4GiB memory, 8GiB storage
SNAPSHOT_RESOURCES = Resources(
    cpu=2,
    memory=4,
    disk=6,
)
# ======================================

# ============== 系统包安装 ==============
# 安装系统依赖 (apt-get)
SYSTEM_PACKAGES = [
    # 常用工具
    "git",  # Git 版本控制
    "curl",  # 下载/HTTP 请求
    "unzip",  # ZIP 解压
    "p7zip-full",  # 7z/RAR 解压 (rarfile 可用 unar 作为替代)
    # 中文字体
    "fonts-noto-cjk",  # 思源黑体 (推荐)
    "fonts-wqy-zenhei",  # 义启黑体
    "fonts-wqy-microhei",  # 思源黑体精简版
    # 视频处理
    "ffmpeg",  # 音视频处理
    # PDF 相关
    "wkhtmltopdf",  # HTML 转 PDF
    "poppler-utils",  # PDF 工具
    "pandoc",  # 文档转换
    # Python 编译依赖 (用于 matplotlib 等)
    "pkg-config",  # 包管理工具
    "libcairo2-dev",  # cairo 开发库
    "libjpeg-dev",  # JPEG 支持
    "libpng-dev",  # PNG 支持
    "libfreetype6-dev",  # FreeType 字体
    "libffi-dev",  # cffi 依赖
    "libssl-dev",  # openssl 开发库
    # Playwright / Chromium 系统依赖
    "libnss3",  # NSS 库 (Chromium 必需)
    "libnspr4",  # NSPR 库 (Chromium 必需)
    "libatk1.0-0",  # ATK 无障碍工具包
    "libatk-bridge2.0-0",  # ATK 桥接
    "libcups2",  # 打印支持
    "libdrm2",  # DRM 库
    "libxkbcommon0",  # 键盘处理
    "libxcomposite1",  # X 合成扩展
    "libxdamage1",  # X 损坏扩展
    "libxfixes3",  # X 修复扩展
    "libxrandr2",  # X 随机分辨率
    "libgbm1",  # 图形缓冲管理
    "libpango-1.0-0",  # Pango 文本渲染
    "libcairo2",  # Cairo 2D 图形
    "libasound2",  # ALSA 音频
    "libatspi2.0-0",  # 辅助技术服务
    "libwayland-client0",  # Wayland 客户端
]
# ======================================


def main():
    """创建自定义快照"""
    print(f"Creating custom snapshot: {SNAPSHOT_NAME}")
    print(f"Base image: {BASE_IMAGE} {PYTHON_VERSION}")
    if EXTRA_PIP_PACKAGES:
        print(f"Extra pip packages: {', '.join(EXTRA_PIP_PACKAGES)}")
    if SYSTEM_PACKAGES:
        print(f"System packages: {', '.join(SYSTEM_PACKAGES)}")

    # 初始化 Daytona 客户端
    daytona_api_key = settings.DAYTONA_API_KEY
    daytona_server_url = settings.DAYTONA_SERVER_URL

    if not daytona_api_key:
        print("Error: DAYTONA_API_KEY is not set in settings.")
        sys.exit(1)

    # 根据 settings 配置 Daytona 客户端
    if daytona_server_url:
        config = DaytonaConfig(
            api_key=daytona_api_key,
            server_url=daytona_server_url,
        )
        daytona_client = daytona.Daytona(config=config)
    else:
        config = DaytonaConfig(
            api_key=daytona_api_key,
        )
        daytona_client = daytona.Daytona(config=config)

    print(f"Daytona client initialized (server_url: {daytona_server_url or 'default'})")

    # 构建镜像配置
    image = getattr(Image, BASE_IMAGE)(PYTHON_VERSION)

    # 安装系统包 (中文字体等)
    if SYSTEM_PACKAGES:
        apt_install_cmd = f"apt-get update && apt-get install -y {' '.join(SYSTEM_PACKAGES)} && rm -rf /var/lib/apt/lists/*"
        image = image.run_commands(apt_install_cmd)

    # 添加额外的 pip 包
    if EXTRA_PIP_PACKAGES:
        image = image.pip_install(EXTRA_PIP_PACKAGES)

    # 安装 Playwright 浏览器二进制 (Chromium)
    image = image.run_commands("playwright install chromium --with-deps")

    # 安装 mcporter (通过 bun)
    image = image.run_commands("curl -fsSL https://bun.sh/install | bash")
    image = image.run_commands("~/.bun/bin/bun install -g mcporter")
    image = image.run_commands("mkdir -p ~/.mcporter")

    # 安装 Node.js / npx（sandbox MCP 常用 npx 启动 stdio 服务器）
    image = image.run_commands(
        "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*"
    )

    # 创建快照参数
    params = CreateSnapshotParams(
        name=SNAPSHOT_NAME,
        image=image,
        resources=SNAPSHOT_RESOURCES,
    )

    print("\nCreating snapshot (this may take a few minutes)...")
    print("Use Ctrl+C to cancel if needed.\n")

    try:
        # 创建快照并监听日志
        snapshot = daytona_client.snapshot.create(
            params,
            on_logs=lambda chunk: print(chunk, end=""),
        )
        print("\n\nSnapshot created successfully!")
        print(f"  Name: {snapshot.name}")
        print(f"  State: {snapshot.state}")
        print(f"  Image: {snapshot.image_name}")
    except KeyboardInterrupt:
        print("\n\nSnapshot creation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError creating snapshot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
