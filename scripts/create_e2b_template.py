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

from e2b import Sandbox, Template, default_build_logger

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


def _read_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("candidate manifest must contain a JSON object")
    return manifest


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


def verify_manifest(
    manifest_path: Path,
    api_key: str,
    *,
    sandbox_api: Any = Sandbox,
) -> None:
    """Smoke-test the exact candidate build and persist evidence on success."""
    manifest = _read_manifest(manifest_path)
    build_id = str(manifest.get("build_id") or "")
    immutable_ref = str(manifest.get("immutable_ref") or "")
    expected_ref = f"{manifest.get('template_name')}:{build_id}"
    if not build_id or immutable_ref != expected_ref:
        raise ValueError("candidate manifest has inconsistent build identity")

    sandbox = sandbox_api.create(immutable_ref, timeout=300, api_key=api_key)
    try:
        sandbox.commands.run(
            "set -euo pipefail; "
            "command -v rg; "
            "command -v rsvg-convert; "
            "tmpdir=$(mktemp -d); "
            "trap 'rm -rf \"$tmpdir\"' EXIT; "
            'printf \'%s\' \'<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2"/></svg>\' > "$tmpdir/check.svg"; '
            'rsvg-convert "$tmpdir/check.svg" -o "$tmpdir/check.png"; '
            'test -s "$tmpdir/check.png"'
        )
    finally:
        sandbox.kill()

    manifest["verified_build_id"] = build_id
    manifest["verified_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, manifest)


def _env_template_line(env_file: Path) -> str | None:
    if not env_file.exists():
        return None
    matches = [
        line
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if line.startswith("E2B_TEMPLATE=")
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple E2B_TEMPLATE lines in {env_file}")
    return matches[0] if matches else None


def _write_env_template(env_file: Path, value: str | None) -> None:
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    replacement = f"E2B_TEMPLATE={value}" if value is not None else None
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith("E2B_TEMPLATE="):
            if replacement is not None and not replaced:
                output.append(replacement)
                replaced = True
            continue
        output.append(line)
    if replacement is not None and not replaced:
        output.append(replacement)
    env_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = env_file.with_suffix(f"{env_file.suffix}.tmp")
    temporary.write_text("\n".join(output) + ("\n" if output else ""), encoding="utf-8")
    temporary.replace(env_file)


def _template_document(value: str, rollout_id: str) -> dict[str, Any]:
    from src.infra.settings.storage import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS["E2B_TEMPLATE"]
    return {
        "_id": "E2B_TEMPLATE",
        "value": value,
        "type": definition["type"].value,
        "category": definition["category"].value,
        "description": definition["description"],
        "default_value": definition["default"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": f"rollout:{rollout_id}",
    }


def _document_guard(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "_id": "E2B_TEMPLATE",
        "value": document.get("value"),
        "updated_at": document.get("updated_at"),
        "updated_by": document.get("updated_by"),
    }


async def _publish_effective_value(settings_service: Any, value: str) -> None:
    from src.kernel.config import settings

    settings.E2B_TEMPLATE = value
    await settings_service._publish_change("E2B_TEMPLATE", value)


async def pin_effective_configuration(
    manifest_path: Path,
    env_file: Path,
    *,
    settings_service: Any | None = None,
) -> None:
    """CAS-pin database-first and fallback configuration to a verified build."""
    if settings_service is None:
        from src.infra.settings.service import SettingsService

        settings_service = SettingsService.get_instance()
    manifest = _read_manifest(manifest_path)
    build_id = str(manifest.get("build_id") or "")
    candidate = str(manifest.get("immutable_ref") or "")
    if manifest.get("verified_build_id") != build_id or not manifest.get("verified_at"):
        raise RuntimeError("candidate must be verified before configuration pinning")

    collection = settings_service._storage._get_collection()
    current = await collection.find_one({"_id": "E2B_TEMPLATE"})
    resolved_env_file = env_file.resolve()
    baseline = manifest.get("configuration_baseline")
    if baseline is None:
        baseline = {
            "db_existed": current is not None,
            "db_document": dict(current) if current is not None else None,
            "env_file": str(resolved_env_file),
            "env_previous_line": _env_template_line(resolved_env_file),
        }
        manifest["configuration_baseline"] = baseline
        _write_manifest(manifest_path, manifest)
    elif baseline.get("env_file") != str(resolved_env_file):
        raise RuntimeError("rollout manifest is already bound to a different environment file")

    rollout_marker = f"rollout:{manifest['rollout_id']}"
    env_candidate_line = f"E2B_TEMPLATE={candidate}"
    if (
        current is not None
        and current.get("value") == candidate
        and current.get("updated_by") == rollout_marker
    ):
        if _env_template_line(resolved_env_file) != env_candidate_line:
            _write_env_template(resolved_env_file, candidate)
        manifest["pinned_ref"] = candidate
        manifest["pinned_build_id"] = build_id
        _write_manifest(manifest_path, manifest)
        await _publish_effective_value(settings_service, candidate)
        return

    previous_document = baseline.get("db_document")
    if previous_document is None:
        if current is not None:
            raise RuntimeError("concurrent E2B_TEMPLATE edit detected during pin")
    elif not _document_guard(previous_document) == _document_guard(current or {}):
        raise RuntimeError("concurrent E2B_TEMPLATE edit detected during pin")

    _write_env_template(resolved_env_file, candidate)
    replacement = dict(previous_document or _template_document(candidate, manifest["rollout_id"]))
    replacement.update(
        {
            "_id": "E2B_TEMPLATE",
            "value": candidate,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": rollout_marker,
        }
    )
    try:
        if previous_document is None:
            await collection.insert_one(replacement)
        else:
            result = await collection.replace_one(_document_guard(previous_document), replacement)
            if result.matched_count != 1:
                raise RuntimeError("concurrent E2B_TEMPLATE edit detected during pin")
    except Exception:
        previous_line = baseline.get("env_previous_line")
        previous_value = previous_line.partition("=")[2] if previous_line is not None else None
        if _env_template_line(resolved_env_file) == env_candidate_line:
            _write_env_template(resolved_env_file, previous_value)
        raise

    manifest["pinned_ref"] = candidate
    manifest["pinned_build_id"] = build_id
    _write_manifest(manifest_path, manifest)
    await _publish_effective_value(settings_service, candidate)


async def restore_effective_configuration(
    manifest_path: Path,
    *,
    settings_service: Any | None = None,
) -> None:
    """Restore the first baseline without overwriting a later administrator edit."""
    if settings_service is None:
        from src.infra.settings.service import SettingsService

        settings_service = SettingsService.get_instance()
    manifest = _read_manifest(manifest_path)
    baseline = manifest.get("configuration_baseline")
    if not isinstance(baseline, dict):
        raise RuntimeError("rollout manifest has no configuration baseline")
    collection = settings_service._storage._get_collection()
    current = await collection.find_one({"_id": "E2B_TEMPLATE"})
    candidate = str(manifest.get("immutable_ref") or "")
    rollout_marker = f"rollout:{manifest['rollout_id']}"
    previous_document = baseline.get("db_document")

    already_restored = (
        current is None
        if previous_document is None
        else _document_guard(current or {}) == _document_guard(previous_document)
    )
    if not already_restored:
        candidate_guard = {
            "_id": "E2B_TEMPLATE",
            "value": candidate,
            "updated_at": current.get("updated_at") if current else None,
            "updated_by": rollout_marker,
        }
        if (
            current is None
            or current.get("value") != candidate
            or current.get("updated_by") != rollout_marker
        ):
            raise RuntimeError("concurrent E2B_TEMPLATE edit detected during restore")
        if previous_document is None:
            result = await collection.delete_one(candidate_guard)
            if result.deleted_count != 1:
                raise RuntimeError("concurrent E2B_TEMPLATE edit detected during restore")
        else:
            result = await collection.replace_one(candidate_guard, previous_document)
            if result.matched_count != 1:
                raise RuntimeError("concurrent E2B_TEMPLATE edit detected during restore")

    env_file = Path(str(baseline["env_file"]))
    previous_line = baseline.get("env_previous_line")
    previous_value = previous_line.partition("=")[2] if previous_line is not None else None
    current_env_line = _env_template_line(env_file)
    if current_env_line not in {f"E2B_TEMPLATE={candidate}", previous_line}:
        raise RuntimeError("concurrent E2B_TEMPLATE edit detected in environment file")
    _write_env_template(env_file, previous_value)

    for field in (
        "pinned_ref",
        "pinned_build_id",
        "effective_ref_verified_at",
        "effective_ref_build_id",
        "health_checked_at",
        "health_build_id",
        "health_ref",
    ):
        manifest.pop(field, None)
    _write_manifest(manifest_path, manifest)
    effective_value = str(await settings_service.get_raw("E2B_TEMPLATE") or "")
    await _publish_effective_value(settings_service, effective_value)


def _require_bound_candidate(manifest: dict[str, Any], *, require_health: bool) -> None:
    build_id = str(manifest.get("build_id") or "")
    reference = str(manifest.get("immutable_ref") or "")
    required = {
        "verified_build_id": build_id,
        "pinned_build_id": build_id,
        "pinned_ref": reference,
        "effective_ref_build_id": build_id,
    }
    if require_health:
        required.update(
            {
                "health_build_id": build_id,
                "health_ref": reference,
            }
        )
    if any(manifest.get(field) != expected for field, expected in required.items()):
        raise RuntimeError("rollout evidence does not match the candidate build")
    timestamp_fields = ["verified_at", "effective_ref_verified_at"]
    if require_health:
        timestamp_fields.append("health_checked_at")
    if any(not manifest.get(field) for field in timestamp_fields):
        raise RuntimeError("rollout evidence is incomplete")


async def verify_effective_configuration(
    manifest_path: Path,
    *,
    settings_service: Any | None = None,
) -> None:
    """Bind database-first effective configuration evidence to the candidate."""
    if settings_service is None:
        from src.infra.settings.service import SettingsService

        settings_service = SettingsService.get_instance()
    manifest = _read_manifest(manifest_path)
    build_id = str(manifest.get("build_id") or "")
    reference = str(manifest.get("immutable_ref") or "")
    if manifest.get("pinned_ref") != reference or manifest.get("pinned_build_id") != build_id:
        raise RuntimeError("candidate configuration has not been pinned")
    effective = str(await settings_service.get_raw("E2B_TEMPLATE") or "")
    if effective != reference:
        raise RuntimeError("effective E2B_TEMPLATE does not match candidate")
    manifest["effective_ref_build_id"] = build_id
    manifest["effective_ref_verified_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, manifest)


async def record_health(
    manifest_path: Path,
    health_url: str,
    *,
    http_client: Any | None = None,
) -> None:
    """Record a successful health response only for the fully bound candidate."""
    manifest = _read_manifest(manifest_path)
    _require_bound_candidate(manifest, require_health=False)
    if http_client is None:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(health_url)
    else:
        response = await http_client.get(health_url)
    if not 200 <= int(response.status_code) < 300:
        raise RuntimeError(f"health check failed with HTTP {response.status_code}")
    manifest["health_checked_at"] = datetime.now(timezone.utc).isoformat()
    manifest["health_build_id"] = manifest["build_id"]
    manifest["health_ref"] = manifest["immutable_ref"]
    _write_manifest(manifest_path, manifest)


async def promote_manifest(
    manifest_path: Path,
    api_key: str,
    *,
    settings_service: Any | None = None,
    template_api: Any = Template,
) -> None:
    """Promote only when stored and live evidence identify the same build."""
    if settings_service is None:
        from src.infra.settings.service import SettingsService

        settings_service = SettingsService.get_instance()
    manifest = _read_manifest(manifest_path)
    _require_bound_candidate(manifest, require_health=True)
    effective = str(await settings_service.get_raw("E2B_TEMPLATE") or "")
    if effective != manifest["immutable_ref"]:
        raise RuntimeError("effective E2B_TEMPLATE changed after health verification")
    result = template_api.assign_tags(
        manifest["immutable_ref"],
        "production",
        api_key=api_key,
    )
    if str(result.build_id) != str(manifest["build_id"]):
        raise RuntimeError("production tag resolved to an unexpected build")
    manifest["promoted_build_id"] = manifest["build_id"]
    manifest["promoted_at"] = datetime.now(timezone.utc).isoformat()
    _write_manifest(manifest_path, manifest)


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
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("build")
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    pin_parser = subparsers.add_parser("pin-config")
    pin_parser.add_argument("--manifest", type=Path, required=True)
    pin_parser.add_argument("--env-file", type=Path, required=True)
    restore_parser = subparsers.add_parser("restore-config")
    restore_parser.add_argument("--manifest", type=Path, required=True)
    effective_parser = subparsers.add_parser("verify-effective")
    effective_parser.add_argument("--manifest", type=Path, required=True)
    health_parser = subparsers.add_parser("record-health")
    health_parser.add_argument("--manifest", type=Path, required=True)
    health_parser.add_argument("--url", required=True)
    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    command = args.command or "build"
    api_key = ""
    try:
        if command in {"build", "verify", "promote"}:
            api_key = await resolve_e2b_api_key()
            if not api_key:
                print("Error: E2B_API_KEY is not configured.", file=sys.stderr)
                return 1
        if command == "build":
            print("\nBuilding template (this may take a few minutes)...\n")
            manifest_path = build_candidate(_candidate_tag(), api_key)
            print(f"Candidate manifest: {manifest_path}")
        elif command == "verify":
            verify_manifest(args.manifest, api_key)
            print(f"Verified candidate manifest: {args.manifest}")
        elif command == "pin-config":
            await pin_effective_configuration(args.manifest, args.env_file)
            print(f"Pinned candidate configuration: {args.manifest}")
        elif command == "restore-config":
            await restore_effective_configuration(args.manifest)
            print(f"Restored candidate configuration: {args.manifest}")
        elif command == "verify-effective":
            await verify_effective_configuration(args.manifest)
            print(f"Verified effective configuration: {args.manifest}")
        elif command == "record-health":
            await record_health(args.manifest, args.url)
            print(f"Recorded candidate health: {args.manifest}")
        elif command == "promote":
            await promote_manifest(args.manifest, api_key)
            print(f"Promoted candidate manifest: {args.manifest}")
        else:
            parser.error("unsupported command")
    except KeyboardInterrupt:
        print("\n\nBuild cancelled by user.", file=sys.stderr)
        return 1
    except Exception as e:
        message = str(e).replace(api_key, "[REDACTED]") if api_key else str(e)
        print(f"Error: {type(e).__name__}: {message}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
