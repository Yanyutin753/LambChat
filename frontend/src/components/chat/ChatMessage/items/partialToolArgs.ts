/**
 * 渐进式部分 JSON 解析：把 tool:args:chunk 流式累积的 JSON 对象前缀
 * （如 `{"file_path":"/tmp/ma`）解析成尽量完整的 args 对象。
 *
 * 规则：
 * - 已完整闭合的顶层键值对全部解析（含嵌套对象/数组）。
 * - 正在生成中的字符串值（开了引号还没闭合）按当前累积内容输出，
 *   让专属工具卡片在流式期间就能逐字展示路径/命令。
 * - 截断的键、无效的数字前缀、截断的布尔字面量、未闭合的嵌套值
 *   一律丢弃该键，不影响更早的键值对。
 * - 任何非法形态都不抛错，返回已解析部分（最差为空对象）。
 */

interface ScannedString {
  value: string;
  /** 扫描停留位置（未闭合时为 s.length） */
  end: number;
  closed: boolean;
}

interface ScannedValue {
  value: unknown;
  end: number;
  /** false 表示取到了生成中的值（应视为最后一个键） */
  closed: boolean;
}

function skipWs(s: string, i: number): number {
  while (i < s.length && /\s/.test(s[i])) i++;
  return i;
}

/** 解码字符串字面量内累积的转义（含截断时的未闭合内容）。 */
function decodeEscapes(raw: string): string {
  let out = "";
  for (let i = 0; i < raw.length; ) {
    const c = raw[i];
    if (c !== "\\") {
      out += c;
      i++;
      continue;
    }
    const next = raw[i + 1];
    if (next === undefined) break; // 结尾孤立反斜杠：丢弃，等下一个增量
    if (next === "u" && /^[0-9a-fA-F]{4}$/.test(raw.slice(i + 2, i + 6))) {
      out += String.fromCharCode(parseInt(raw.slice(i + 2, i + 6), 16));
      i += 6;
      continue;
    }
    const map: Record<string, string> = {
      '"': '"',
      "\\": "\\",
      "/": "/",
      b: "\b",
      f: "\f",
      n: "\n",
      r: "\r",
      t: "\t",
    };
    out += next in map ? map[next] : next;
    i += 2;
  }
  return out;
}

/** 从开引号起扫描字符串字面量；未闭合时按累积内容返回。 */
function scanString(s: string, start: number): ScannedString {
  for (let j = start + 1; j < s.length; j++) {
    const c = s[j];
    if (c === "\\") {
      j++; // 跳过被转义字符（越界即结尾孤立反斜杠，交给 decodeEscapes）
      continue;
    }
    if (c === '"') {
      return {
        value: decodeEscapes(s.slice(start + 1, j)),
        end: j + 1,
        closed: true,
      };
    }
  }
  return {
    value: decodeEscapes(s.slice(start + 1)),
    end: s.length,
    closed: false,
  };
}

/** 扫描完整键名；未闭合返回 null。 */
function scanKey(s: string, start: number): ScannedString | null {
  const scanned = scanString(s, start);
  return scanned.closed ? scanned : null;
}

/** 寻找嵌套值（对象/数组）的闭合位置；未闭合返回 -1。 */
function findBracketEnd(s: string, open: number): number {
  const close = s[open] === "{" ? "}" : "]";
  let depth = 0;
  for (let j = open; j < s.length; j++) {
    const c = s[j];
    if (c === '"') {
      j = scanString(s, j).end - 1;
      continue;
    }
    if (c === "{" || c === "[") depth++;
    else if (c === "}" || c === "]") {
      depth--;
      if (depth === 0) return c === close ? j : -1; // 括号类型不匹配
    }
  }
  return -1;
}

function scanValue(s: string, start: number): ScannedValue | null {
  const c = s[start];
  if (c === '"') {
    return scanString(s, start);
  }
  if (c === "-" || (c >= "0" && c <= "9")) {
    let j = start;
    while (j < s.length && /[0-9+\-.eE]/.test(s[j])) j++;
    const num = Number(s.slice(start, j));
    if (!Number.isFinite(num)) return null; // 悬空指数等无效前缀
    return { value: num, end: j, closed: true };
  }
  for (const [lit, val] of [
    ["true", true],
    ["false", false],
    ["null", null],
  ] as const) {
    if (lit.startsWith(s.slice(start))) return null; // 字面量截断（tru/nul…）
    if (s.startsWith(lit, start)) return { value: val, end: start + lit.length, closed: true };
  }
  if (c === "{" || c === "[") {
    const end = findBracketEnd(s, start);
    if (end === -1) return null; // 嵌套值生成中：丢弃该键
    try {
      return {
        value: JSON.parse(s.slice(start, end + 1)),
        end: end + 1,
        closed: true,
      };
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * 解析流式累积的参数 JSON 前缀，返回尽量完整的键值对象。
 * 生成中的（未闭合）字符串值按当前内容输出。
 */
export function parsePartialToolArgs(partial: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const s = partial;
  let i = skipWs(s, 0);
  if (s[i] !== "{") return result;

  i = skipWs(s, i + 1);
  for (;;) {
    if (i >= s.length || s[i] === "}") return result;
    if (s[i] !== '"') return result; // 非法或截断的键

    const key = scanKey(s, i);
    if (!key) return result; // 键名生成中
    i = skipWs(s, key.end);
    if (s[i] !== ":") return result;

    i = skipWs(s, i + 1);
    const value = scanValue(s, i);
    if (!value) return result;
    result[key.value] = value.value;
    if (!value.closed) return result; // 生成中的值：已是最后一个键

    i = skipWs(s, value.end);
    if (s[i] === ",") {
      i = skipWs(s, i + 1);
      continue;
    }
    return result; // 闭括号、结尾或非法形态
  }
}
