import type { TFunction } from "i18next";
import {
  parseErrorDetail,
  translateApiError,
  translateBackendError,
} from "../backendErrors.ts";

const t = ((key: string, options?: { permission?: string }) =>
  options?.permission
    ? `translated:${key}:${options.permission}`
    : `translated:${key}`) as TFunction;

test("translates shared backend error codes", () => {
  expect(translateBackendError("model_not_found", t)).toBe(
    "translated:errors.modelNotFound",
  );
  expect(translateBackendError("persona_preset_no_delete_permission", t)).toBe(
    "translated:personaPresets.noDeletePermission",
  );
  expect(translateBackendError("File not found", t)).toBe(
    "translated:backendErrors.fileNotFound",
  );
  expect(translateBackendError("invalid_attachments", t)).toBe(
    "translated:backendErrors.invalidAttachments",
  );
});

test("translates backend error patterns", () => {
  expect(translateBackendError("缺少权限: model:admin", t)).toBe(
    "translated:backendErrors.permissionMissing:model:admin",
  );
});

test("returns unknown backend messages unchanged", () => {
  expect(translateBackendError("unexpected_backend_error", t)).toBe(
    "unexpected_backend_error",
  );
});

// ---------- translateApiError：错误码优先翻译 ----------

function makeT(overrides: Record<string, string> = {}): TFunction {
  const interpolate = (template: string, opts?: Record<string, unknown>) =>
    template.replace(/\{\{(\w+)\}\}/g, (_, k: string) =>
      opts && k in opts ? String(opts[k]) : `{{${k}}}`,
    );
  return ((key: string, opts?: Record<string, unknown>) => {
    if (key in overrides) return interpolate(overrides[key], opts);
    if (opts && typeof opts === "object" && "defaultValue" in opts) {
      return typeof opts.defaultValue === "string"
        ? interpolate(opts.defaultValue, opts)
        : key;
    }
    return key;
  }) as unknown as TFunction;
}

test("码命中时返回译文", () => {
  const tt = makeT({ "backendErrors.sessionNotFound": "会话不存在" });
  expect(
    translateApiError("session_not_found", "Session not found", undefined, tt),
  ).toBe("会话不存在");
});

test("码未命中时回退原文", () => {
  const tt = makeT();
  expect(
    translateApiError("some_unknown_code", "raw detail", undefined, tt),
  ).toBe("raw detail");
});

test("args 插值透传给 t", () => {
  const tt = makeT({ "backendErrors.fileTooLarge": "文件超过 {{max}}MB" });
  expect(
    translateApiError("file_too_large", "File size exceeds", { max: 10 }, tt),
  ).toBe("文件超过 10MB");
});

test("无码时走原文映射兜底", () => {
  const tt = makeT();
  // makeT 无 override 时返回 key 本身，可验证命中了映射而非原文直出
  expect(translateApiError(undefined, "用户名或密码错误", undefined, tt)).toBe(
    "backendErrors.invalidCredentials",
  );
});

test("internal_error 码不翻译直接用原文", () => {
  const tt = makeT({ "backendErrors.internalError": "服务器内部错误" });
  expect(
    translateApiError("internal_error", "dynamic boom message", undefined, tt),
  ).toBe("dynamic boom message");
});

test("camelCase 转换 snake_case 码", () => {
  const seen: string[] = [];
  const tt = ((key: string) => {
    seen.push(key);
    return "";
  }) as unknown as TFunction;
  translateApiError("mcp_server_not_found", "x", undefined, tt);
  expect(seen).toContain("backendErrors.mcpServerNotFound");
});

// ---------- parseErrorDetail：detail 三形状兼容 ----------

test("parseErrorDetail 提取三字段并兼容旧字符串形状", () => {
  expect(
    parseErrorDetail({ detail: { code: "a_b", message: "m", args: { x: 1 } } }),
  ).toEqual({ code: "a_b", message: "m", args: { x: 1 } });
  expect(parseErrorDetail({ detail: "legacy" })).toEqual({
    code: undefined,
    message: "legacy",
    args: undefined,
  });
  expect(parseErrorDetail({})).toEqual({
    code: undefined,
    message: "",
    args: undefined,
  });
  expect(
    parseErrorDetail({ detail: { error: "model_not_found", message: "nope" } }),
  ).toEqual({ code: "model_not_found", message: "nope", args: undefined });
});

test("quota errors distinguish exhausted, reserved and unknown costs and format their reset time", () => {
  const tt = makeT({
    "usage.quotaFiveHour": "5 小时",
    "usage.quotaWeekly": "每周",
    "usage.quotaErrorExhausted": "{{windows}}额度已用尽。",
    "usage.quotaErrorReserved": "{{windows}}额度已被进行中的调用预留。",
    "usage.quotaErrorUnknown": "{{windows}}存在未知费用，暂时无法使用。",
    "usage.quotaErrorResets": "重置于 {{time}}。",
  });
  const result = translateApiError(
    "usage_quota_exceeded",
    "raw",
    {
      windows: ["weekly"],
      reason: "exhausted",
      reset_at: "2026-10-19T00:00:00+08:00",
    },
    tt,
  );
  expect(result).toContain("每周额度已用尽");
  expect(result).toContain("重置于");
  expect(result).not.toContain("2026-10-19T00:00:00+08:00");
  expect(
    translateApiError(
      "usage_quota_exceeded",
      "raw",
      { windows: ["five_hour"], reason: "reserved" },
      tt,
    ),
  ).toBe("5 小时额度已被进行中的调用预留。");
  expect(
    translateApiError(
      "usage_quota_exceeded",
      "raw",
      { windows: ["five_hour"], reason: "unknown" },
      tt,
    ),
  ).toBe("5 小时存在未知费用，暂时无法使用。");
});
