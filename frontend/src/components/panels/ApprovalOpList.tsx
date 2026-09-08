import { TerminalSquare } from "lucide-react";
import type { AskHumanOp } from "./askHumanMessage";

/**
 * 沙箱确认门的操作清单——「单据式」只读列表：
 * 编号 + 动词标签 + 等宽命令文本，发丝线分行。
 * 同时用于审批卡（ApprovalPanel）与历史回放的 ask_human 详情面板。
 */
export function ApprovalOpList({ ops }: { ops: AskHumanOp[] }) {
  return (
    <div className="approval-op-list" role="list">
      {ops.map((op, index) => (
        <div className="approval-op-row" role="listitem" key={index}>
          <span className="approval-op-index" aria-hidden="true">
            {index + 1}
          </span>
          {op.verb ? (
            <span className="approval-op-verb">
              <TerminalSquare size={10} strokeWidth={2} aria-hidden="true" />
              {op.verb}
            </span>
          ) : null}
          <span className="approval-op-detail">{op.detail}</span>
        </div>
      ))}
    </div>
  );
}
