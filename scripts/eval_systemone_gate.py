"""记忆提取 System One 预门真实数据评估（只读、离线跑在本机）。

对一份提取任务样本 JSON 逐条跑预门判定，输出与生产 LLM 实际结果的一致率
与各阈值下的漏检/节省矩阵。用于换用任何 /v1/systemone 兼容决策模型
（TypeSafe Jev / 自托管 von）时的上线前验证。

样本导出（在生产 Pod 内执行，只读；凭据取自应用环境变量）：

    kubectl exec -i -n lambchat <api-pod> -- /app/.venv/bin/python \
        <dump脚本> > extraction_samples.json

dump 脚本要点：memory_extraction_jobs 终态（succeeded / succeeded_no_output）
+ 对应 traces.conversation_search 转录，ID 哈希脱敏，stdout 输出 JSON。

用法（仓库根目录）：

    SYSTEMONE_API_BASE=http://<host>:<port> \
    SYSTEMONE_MODEL=<model> \
    uv run python scripts/eval_systemone_gate.py extraction_samples.json

2026-09-23 实测基线（自托管 von 1.1 / RTX 5070 Ti，260 条生产样本）：
中文转录下 extracted 与 no_output 的 p_memorable 分布无区分度（中位
0.372 vs 0.415），阈值 0.35 漏检 38.7%——von 不适用于中文流量的预门；
英文对照实验（同款提示词）分离度良好（0.756 vs 0.336），确认根因为
模型中文能力缺失而非任务设计。换模型后须重跑本评估。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infra.decision.client import judge_noul  # noqa: E402
from src.infra.memory.extraction import _INJECTED_BLOCK_RE  # noqa: E402
from src.infra.memory.extraction_gate import (  # noqa: E402
    _MEMORABLE_CRITERIA,
    _MEMORABLE_INSTRUCTIONS,
    _render_gate_state,
)

THRESHOLDS = (0.2, 0.3, 0.35, 0.4, 0.5, 0.6)


def clean_turns(turns: list[dict]) -> list[dict]:
    out = []
    for t in turns:
        user = _INJECTED_BLOCK_RE.sub("", t.get("user") or "").strip()
        assistant = _INJECTED_BLOCK_RE.sub("", t.get("assistant") or "").strip()
        if user or assistant:
            out.append({"run_id": t.get("run_id", ""), "user": user, "assistant": assistant})
    return out


async def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1]) as fh:
        samples = [d for d in json.load(fh) if d.get("turns")]
    samples = [{**d, "turns": clean_turns(d["turns"])} for d in samples]
    samples = [d for d in samples if d["turns"]]
    print(f"evaluating {len(samples)} samples ...")

    results: list[dict] = []
    for index, d in enumerate(samples):
        state = _render_gate_state(d["session_name"], d["agent_id"], d["turns"])
        p = await judge_noul(state, _MEMORABLE_INSTRUCTIONS, criteria=_MEMORABLE_CRITERIA)
        results.append({"extracted": d["status"] == "succeeded", "p": p})
        if (index + 1) % 25 == 0:
            print(f"  {index + 1}/{len(samples)}")

    ok = [r for r in results if r["p"] is not None]
    n_extracted = sum(1 for r in ok if r["extracted"])
    print(f"\nvon failures: {len(results) - len(ok)} / {len(results)}")

    def q(frac: float, extracted: bool) -> float:
        vals = sorted(r["p"] for r in ok if r["extracted"] == extracted)
        return vals[min(len(vals) - 1, int(len(vals) * frac))]

    print(f"extracted (n={n_extracted}): p10={q(0.1, True):.3f} median={q(0.5, True):.3f}")
    print(
        f"no_output (n={len(ok) - n_extracted}): p10={q(0.1, False):.3f} median={q(0.5, False):.3f}"
    )

    print("\nthreshold | skip-rate | saved-LLM | false-skip(missed memories)")
    for t in THRESHOLDS:
        skip = [(r["p"] < t) for r in ok]
        n_skip = sum(skip)
        false_skip = sum(1 for r, s in zip(ok, skip) if s and r["extracted"])
        print(
            f"   {t:.2f}    |  {n_skip / len(ok):5.1%}   |  {n_skip - false_skip:4d}    |  "
            f"{false_skip:4d} ({false_skip / max(1, n_extracted):5.1%})"
        )


if __name__ == "__main__":
    asyncio.run(main())
