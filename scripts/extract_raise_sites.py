"""提取 src/api/routes/ 下所有 raise HTTPException / kernel 异常位置，生成迁移清单。

用法：uv run python scripts/extract_raise_sites.py
输出：docs/superpowers/plans/error-migration-worksheet.json
"""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES_DIR = ROOT / "src" / "api" / "routes"
OUT = ROOT / "docs" / "superpowers" / "plans" / "error-migration-worksheet.json"

KERNEL_EXCEPTIONS = {
    "AgentError",
    "ConfigurationError",
    "ValidationError",
    "NotFoundError",
    "AuthenticationError",
    "AuthorizationError",
    "StorageError",
    "LLMError",
    "ToolError",
    "SkillError",
    "SessionError",
    "EmailNotVerifiedError",
    "AccountNotActiveError",
}


def classify_detail(expr: ast.expr) -> str:
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return "literal"
    if isinstance(expr, ast.JoinedStr):
        return "fstring"
    if isinstance(expr, ast.Call):
        return "exc_pass"
    if isinstance(expr, ast.Dict):
        return "dict"
    return "other"


def visit_file(path: Path) -> list[dict]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        call = node.exc
        func = call.func
        name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else None)
        if name is None:
            continue
        entry = {
            "file": str(path.relative_to(ROOT)),
            "line": node.lineno,
            "exception": name,
        }
        if name == "HTTPException":
            status = None
            detail_expr = None
            for kw in call.keywords:
                if kw.arg == "status_code":
                    status = ast.literal_eval(kw.value) if isinstance(kw.value, ast.Constant) else "?"
                elif kw.arg == "detail":
                    detail_expr = kw.value
            if detail_expr is None and len(call.args) >= 2:
                detail_expr = call.args[1]
                if call.args[0] and isinstance(call.args[0], ast.Constant):
                    status = call.args[0].value
            entry["kind"] = "http"
            entry["status"] = status
            entry["detail_class"] = classify_detail(detail_expr) if detail_expr is not None else "none"
            try:
                if detail_expr is not None:
                    entry["detail_preview"] = ast.get_source_segment(
                        path.read_text(encoding="utf-8"), detail_expr
                    )[:120]
            except Exception:
                pass
        elif name in KERNEL_EXCEPTIONS:
            entry["kind"] = "kernel"
            entry["args_count"] = len(call.args)
            if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
                entry["message_preview"] = call.args[0].value[:120]
        else:
            continue
        sites.append(entry)
    return sites


def main() -> None:
    all_sites = []
    for py in sorted(ROUTES_DIR.rglob("*.py")):
        all_sites.extend(visit_file(py))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(all_sites, ensure_ascii=False, indent=1), encoding="utf-8")
    http = [s for s in all_sites if s["kind"] == "http"]
    kernel = [s for s in all_sites if s["kind"] == "kernel"]
    print(f"HTTPException: {len(http)}  kernel: {len(kernel)}  total: {len(all_sites)}")
    print(f"worksheet -> {OUT}")
    from collections import Counter

    print("by file:", dict(Counter(s["file"] for s in http).most_common(15)))


if __name__ == "__main__":
    main()
