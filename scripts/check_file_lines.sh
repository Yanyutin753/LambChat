#!/bin/bash
# 检查代码文件是否超过1000行
# 用法: ./scripts/check_file_lines.sh [最大行数]

MAX_LINES=${1:-1000}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "检查代码文件行数 (最大允许: $MAX_LINES 行)"
echo "============================================"

# 查找超过限制的文件
VIOLATIONS=$(find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" \) \
    -not -path "./.venv/*" \
    -not -path "./node_modules/*" \
    -not -path "./frontend/node_modules/*" \
    -not -path "./frontend/.next/*" \
    -not -path "./frontend/dist/*" \
    -not -path "./.ruff_cache/*" \
    -not -path "./.pytest_cache/*" \
    -exec wc -l {} \; 2>/dev/null | awk -v max="$MAX_LINES" '$1 > max {print $1, $2}' | sort -rn)

if [ -z "$VIOLATIONS" ]; then
    echo "✅ 所有代码文件都在 $MAX_LINES 行以内"
    exit 0
else
    echo "❌ 以下文件超过 $MAX_LINES 行:"
    echo ""
    echo "$VIOLATIONS"
    echo ""
    echo "请重构这些文件，确保每个文件不超过 $MAX_LINES 行"
    exit 1
fi
