/**
 * 解析 langchain_quickjs eval 工具的 wire 格式结果。
 *
 * 工具返回给模型的是结构化标签（`<stdout>` / `<result kind="…">` /
 * `<error type="…">`，XML 转义），模型侧依赖该格式；前端展示前先剥掉
 * 标签噪声，只保留用户关心的值。
 */

export interface EvalWireError {
  type?: string;
  message: string;
}

export interface EvalWireResult {
  stdout?: string;
  kind?: string;
  value?: string;
  error?: EvalWireError;
}

function unescapeXml(text: string): string {
  return text
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

export function parseEvalWireResult(raw: string): EvalWireResult | null {
  if (typeof raw !== "string" || raw.length === 0) return null;

  const stdoutMatch = raw.match(/<stdout>\n?([\s\S]*?)\n?<\/stdout>/);
  const resultMatch = raw.match(
    /<result(?:\s+kind="([^"]*)")?>([\s\S]*?)<\/result>/,
  );
  const errorMatch = raw.match(
    /<error(?:\s+type="([^"]*)")?>([\s\S]*?)<\/error>/,
  );
  if (!stdoutMatch && !resultMatch && !errorMatch) return null;

  const parsed: EvalWireResult = {};
  if (stdoutMatch) parsed.stdout = stdoutMatch[1];
  if (resultMatch) {
    parsed.kind = resultMatch[1] || undefined;
    parsed.value = unescapeXml(resultMatch[2]);
  }
  if (errorMatch) {
    parsed.error = {
      type: errorMatch[1] || undefined,
      message: unescapeXml(errorMatch[2]),
    };
  }
  return parsed;
}

/** 数字/短值走醒目展示，长文本与多行值走代码块展示 */
export function isProminentEvalValue(value: string | undefined): boolean {
  if (!value || value === "undefined") return false;
  return value.length <= 32 && !value.includes("\n");
}
