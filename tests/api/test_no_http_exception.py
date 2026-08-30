"""守门：src/api/routes/ 禁止 raise HTTPException（统一错误码体系）。

新错误必须走 src/kernel/errors.py 的 ErrorCode + AppError，
否则错误响应不携带稳定 code，前端无法翻译。
"""

import re
from pathlib import Path

ROUTES_DIR = Path(__file__).resolve().parents[2] / "src" / "api" / "routes"

# 允许例外（如有充分理由在此登记并注明原因）
ALLOWLIST: dict[str, list[int]] = {}


def test_no_http_exception_raises_in_routes() -> None:
    pattern = re.compile(r"raise\s+HTTPException\s*\(")
    violations: list[str] = []
    for py in sorted(ROUTES_DIR.rglob("*.py")):
        rel = py.relative_to(ROUTES_DIR.parent.parent.parent)
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            if lineno in ALLOWLIST.get(str(rel), []):
                continue
            if pattern.search(line):
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, "路由层禁止 raise HTTPException，请改用 AppError:\n" + "\n".join(
        violations
    )
