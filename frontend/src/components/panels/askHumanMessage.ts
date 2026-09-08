/**
 * ask_human 消息结构化解析。
 *
 * 后端沙箱确认门（sandbox_confirm.py）的 message 是「标题行 + 编号操作行」
 * 的多行文本；普通提问则是任意散文。这里把它拆成 headline / ops / prose，
 * 供审批卡与工具 pill 按各自密度渲染——标题进头部、操作清单进明细区，
 * 避免 replace(/\s+/g, " ") 把整段压成一行的排版事故。
 */

export interface AskHumanOp {
  /** 操作动词（执行命令 / 写入文件 / …），无法可靠识别时为 null */
  verb: string | null;
  /** 动词之后的具体内容（命令、路径等），原样保留 */
  detail: string;
}

export interface AskHumanMessageShape {
  /** 标题行（去掉收尾冒号），空消息为 null */
  headline: string | null;
  /** 全部剩余行均为编号行时的结构化操作清单，否则 null */
  ops: AskHumanOp[] | null;
  /** 非编号的补充说明（保留换行），没有则为 null */
  prose: string | null;
  /** 全文压成单行的摘要（pill 标签 / 折叠摘要用） */
  summary: string;
}

const NUMBERED_LINE = /^\d{1,3}\s*[.、)．]\s*(.+)$/;
// 动词只认「短 + 纯中文」前缀，命令内部的冒号（含全角）不会被误切
const VERB_PREFIX = /^([\u4e00-\u9fff]{1,8})：(.+)$/;

function splitVerb(detail: string): AskHumanOp {
  const match = VERB_PREFIX.exec(detail);
  if (match) {
    return { verb: match[1], detail: match[2] };
  }
  return { verb: null, detail };
}

export function parseAskHumanMessage(message: string): AskHumanMessageShape {
  const summary = message.replace(/\s+/g, " ").trim();

  const lines = message
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  if (lines.length === 0) {
    return { headline: null, ops: null, prose: null, summary };
  }

  const headline = lines[0].replace(/[：:]\s*$/, "");
  const rest = lines.slice(1);

  if (rest.length > 0 && rest.every((line) => NUMBERED_LINE.test(line))) {
    return {
      headline,
      ops: rest.map((line) => splitVerb(NUMBERED_LINE.exec(line)![1].trim())),
      prose: null,
      summary,
    };
  }

  return {
    headline,
    ops: null,
    prose: rest.length > 0 ? rest.join("\n") : null,
    summary,
  };
}
