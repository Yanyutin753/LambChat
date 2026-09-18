/**
 * Pure helpers for the batch model create / import modal.
 *
 * 逐条添加与 JSON 导入共用同一套「最新 ModelConfigCreate 结构」的构建、
 * 校验与合并逻辑，保证两个入口导入出的模型配置字段一致。
 */

import type {
  ApiFormat,
  ModelConfigCreate,
  ModelPricingOverride,
  ModelProfile,
  ProviderType,
} from "../../../../services/api/model";

const API_FORMATS: readonly ApiFormat[] = ["chat_completions", "responses"];

/** 表格行状态（组件侧另加 id 作为 React key）。 */
export interface BatchModelRow {
  value: string;
  label: string;
  description: string;
  provider: string;
  icon: string;
  apiKey: string;
  apiBase: string;
  temperature: string;
  maxTokens: string;
  maxInputTokens: string;
  supportsVision: boolean;
  imageUrlToBase64: boolean;
  priceInput: string;
  priceOutput: string;
  priceCacheRead: string;
  priceCacheWrite: string;
}

/** 共享配置：为所有行 / 导入项统一补齐的连接信息（自身有值时优先自身）。 */
export interface SharedModelConfig {
  apiKey: string;
  apiBase: string;
  apiFormat: ApiFormat | "";
  requestHeaders?: Record<string, string>;
}

export type RowBuildResult =
  | { ok: true; model: ModelConfigCreate }
  | {
      ok: false;
      error:
        | "invalidTemperature"
        | "invalidMaxTokens"
        | "invalidMaxInputTokens"
        | "pricingInvalid";
    };

/** 模型列表导出的 api_key 是掩码（`sk-1...abcd` / `****`），导入时应忽略。 */
export function isMaskedApiKey(key: unknown): boolean {
  return typeof key === "string" && (key.includes("...") || key === "****");
}

function asTrimmedString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function asFiniteNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : undefined;
}

function asInteger(value: unknown): number | undefined {
  const num = asFiniteNumber(value);
  return num !== undefined && Number.isInteger(num) ? num : undefined;
}

function asApiFormat(value: unknown): ApiFormat | undefined {
  return typeof value === "string" &&
    (API_FORMATS as readonly string[]).includes(value)
    ? (value as ApiFormat)
    : undefined;
}

function asStringRecord(value: unknown): Record<string, string> | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return undefined;
  }
  const record: Record<string, string> = {};
  for (const [key, item] of Object.entries(value)) {
    record[key] = String(item);
  }
  return record;
}

function asProfile(value: unknown): ModelProfile | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return undefined;
  }
  const source = value as Record<string, unknown>;
  const profile: ModelProfile = {};
  const maxInputTokens = asInteger(source.max_input_tokens);
  if (maxInputTokens !== undefined) {
    profile.max_input_tokens = maxInputTokens;
  }
  if (typeof source.supports_vision === "boolean") {
    profile.supports_vision = source.supports_vision;
  }
  if (typeof source.image_url_to_base64 === "boolean") {
    profile.image_url_to_base64 = source.image_url_to_base64;
  }
  return Object.keys(profile).length > 0 ? profile : undefined;
}

function asPricing(value: unknown): ModelPricingOverride | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return undefined;
  }
  const source = value as Record<string, unknown>;
  const pricing: ModelPricingOverride = {};
  const input = asFiniteNumber(source.input);
  const output = asFiniteNumber(source.output);
  const cacheRead = asFiniteNumber(source.cache_read);
  const cacheWrite = asFiniteNumber(source.cache_write);
  if (input !== undefined) pricing.input = input;
  if (output !== undefined) pricing.output = output;
  if (cacheRead !== undefined) pricing.cache_read = cacheRead;
  if (cacheWrite !== undefined) pricing.cache_write = cacheWrite;
  return Object.keys(pricing).length > 0 ? pricing : undefined;
}

export interface NormalizedImport {
  models: ModelConfigCreate[];
  /** api_key 为掩码占位而被忽略的条数。 */
  maskedKeyCount: number;
  /** 缺少 value / label 而被跳过的条数。 */
  skippedCount: number;
}

/**
 * 把粘贴 / 上传的 JSON 数组规范化为 ModelConfigCreate 列表：
 * 只保留导入支持的白名单字段（含 profile / pricing / request_headers 等最新结构），
 * 剔除 id、时间戳、掩码 api_key 与非法取值，缺少 value / label 的条目直接跳过。
 */
export function normalizeImportedModels(parsed: unknown): NormalizedImport {
  const result: NormalizedImport = {
    models: [],
    maskedKeyCount: 0,
    skippedCount: 0,
  };
  if (!Array.isArray(parsed)) return result;

  for (const item of parsed) {
    if (typeof item !== "object" || item === null) {
      result.skippedCount += 1;
      continue;
    }
    const source = item as Record<string, unknown>;
    const value = asTrimmedString(source.value);
    const label = asTrimmedString(source.label);
    if (!value || !label) {
      result.skippedCount += 1;
      continue;
    }

    const model: ModelConfigCreate = {
      value,
      label,
      enabled: true,
    };

    const description = asTrimmedString(source.description);
    if (description) model.description = description;
    const provider = asTrimmedString(source.provider);
    if (provider) model.provider = provider as ProviderType;
    const icon = asTrimmedString(source.icon);
    if (icon) model.icon = icon;
    const fallbackModel = asTrimmedString(source.fallback_model);
    if (fallbackModel) model.fallback_model = fallbackModel;

    if (!isMaskedApiKey(source.api_key)) {
      const apiKey = asTrimmedString(source.api_key);
      if (apiKey) model.api_key = apiKey;
    } else {
      result.maskedKeyCount += 1;
    }
    const apiBase = asTrimmedString(source.api_base);
    if (apiBase) model.api_base = apiBase;
    const apiFormat = asApiFormat(source.api_format);
    if (apiFormat) model.api_format = apiFormat;
    const requestHeaders = asStringRecord(source.request_headers);
    if (requestHeaders) model.request_headers = requestHeaders;

    const temperature = asFiniteNumber(source.temperature);
    if (temperature !== undefined) model.temperature = temperature;
    const maxTokens = asInteger(source.max_tokens);
    if (maxTokens !== undefined) model.max_tokens = maxTokens;
    const profile = asProfile(source.profile);
    if (profile) model.profile = profile;
    const pricing = asPricing(source.pricing);
    if (pricing) model.pricing = pricing;
    const order = asInteger(source.order);
    if (order !== undefined) model.order = order;
    if (typeof source.enabled === "boolean") model.enabled = source.enabled;

    result.models.push(model);
  }
  return result;
}

/** 空串返回 undefined；非法数值同样返回 undefined（由调用方按字段报错）。 */
function parseOptionalFloat(raw: string): number | undefined {
  if (raw.trim() === "") return undefined;
  const parsed = parseFloat(raw.trim());
  return Number.isNaN(parsed) ? undefined : parsed;
}

function parseOptionalInt(raw: string): number | undefined {
  if (raw.trim() === "") return undefined;
  const parsed = parseInt(raw.trim(), 10);
  return Number.isNaN(parsed) ? undefined : parsed;
}

/** 把一行批量输入 + 共享配置构建为 ModelConfigCreate；数值非法时给出字段级错误。 */
export function buildModelCreateFromRow(
  row: BatchModelRow,
  shared: SharedModelConfig,
): RowBuildResult {
  const temperature = parseOptionalFloat(row.temperature);
  if (
    (row.temperature.trim() !== "" && temperature === undefined) ||
    (temperature !== undefined && (temperature < 0 || temperature > 2))
  ) {
    return { ok: false, error: "invalidTemperature" };
  }
  const maxTokens = parseOptionalInt(row.maxTokens);
  if (row.maxTokens.trim() !== "" && maxTokens === undefined) {
    return { ok: false, error: "invalidMaxTokens" };
  }
  const maxInputTokens = parseOptionalInt(row.maxInputTokens);
  if (row.maxInputTokens.trim() !== "" && maxInputTokens === undefined) {
    return { ok: false, error: "invalidMaxInputTokens" };
  }

  const priceInput = parseOptionalFloat(row.priceInput);
  const priceOutput = parseOptionalFloat(row.priceOutput);
  const priceCacheRead = parseOptionalFloat(row.priceCacheRead);
  const priceCacheWrite = parseOptionalFloat(row.priceCacheWrite);
  const prices = [priceInput, priceOutput, priceCacheRead, priceCacheWrite];
  if (
    prices.some(
      (price) => price !== undefined && (Number.isNaN(price) || price < 0),
    )
  ) {
    return { ok: false, error: "pricingInvalid" };
  }
  const hasAnyPrice = prices.some((price) => price !== undefined);
  const pricing: ModelPricingOverride | undefined = hasAnyPrice
    ? {
        ...(priceInput !== undefined ? { input: priceInput } : {}),
        ...(priceOutput !== undefined ? { output: priceOutput } : {}),
        ...(priceCacheRead !== undefined ? { cache_read: priceCacheRead } : {}),
        ...(priceCacheWrite !== undefined
          ? { cache_write: priceCacheWrite }
          : {}),
      }
    : undefined;

  const profile: ModelProfile = {
    ...(maxInputTokens !== undefined
      ? { max_input_tokens: maxInputTokens }
      : {}),
    supports_vision: row.supportsVision,
    image_url_to_base64: row.imageUrlToBase64,
  };

  const model: ModelConfigCreate = {
    value: row.value.trim(),
    label: row.label.trim(),
    description: row.description.trim() || undefined,
    provider: (row.provider.trim() || undefined) as ProviderType | undefined,
    icon: row.icon.trim() || undefined,
    api_key: row.apiKey.trim() || shared.apiKey.trim() || undefined,
    api_base: row.apiBase.trim() || shared.apiBase.trim() || undefined,
    api_format: shared.apiFormat || undefined,
    request_headers: shared.requestHeaders,
    temperature,
    max_tokens: maxTokens,
    profile,
    ...(pricing ? { pricing } : {}),
    enabled: true,
  };
  return { ok: true, model };
}

/** 导入项缺少连接信息时用共享配置补齐；导入项自身有值时优先自身。 */
export function mergeSharedIntoImported(
  model: ModelConfigCreate,
  shared: SharedModelConfig,
): ModelConfigCreate {
  return {
    ...model,
    api_key: model.api_key?.trim() || shared.apiKey.trim() || undefined,
    api_base: model.api_base?.trim() || shared.apiBase.trim() || undefined,
    api_format: model.api_format || shared.apiFormat || undefined,
    request_headers: model.request_headers ?? shared.requestHeaders,
  };
}
