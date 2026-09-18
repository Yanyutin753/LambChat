import {
  buildModelCreateFromRow,
  isMaskedApiKey,
  mergeSharedIntoImported,
  normalizeImportedModels,
  type BatchModelRow,
} from "../batchModelImport";

const emptyRow = (): BatchModelRow => ({
  value: "openai/gpt-4o",
  label: "GPT-4o",
  description: "",
  provider: "",
  icon: "",
  apiKey: "",
  apiBase: "",
  temperature: "",
  maxTokens: "",
  maxInputTokens: "",
  supportsVision: false,
  imageUrlToBase64: false,
  priceInput: "",
  priceOutput: "",
  priceCacheRead: "",
  priceCacheWrite: "",
});

describe("isMaskedApiKey", () => {
  test("detects masked keys exported from the model list", () => {
    expect(isMaskedApiKey("sk-1...abcd")).toBe(true);
    expect(isMaskedApiKey("****")).toBe(true);
  });

  test("keeps real keys", () => {
    expect(isMaskedApiKey("sk-proj-real-key-value")).toBe(false);
    expect(isMaskedApiKey("")).toBe(false);
  });
});

describe("normalizeImportedModels", () => {
  test("keeps latest-structure fields and strips non-import fields", () => {
    const result = normalizeImportedModels([
      {
        id: "existing-id",
        value: " openai/gpt-4o ",
        label: " GPT-4o ",
        description: "flagship",
        provider: "openai",
        icon: "openai",
        api_key: "sk-real",
        api_base: "https://api.openai.com/v1",
        api_format: "responses",
        request_headers: { "X-Custom": "1" },
        temperature: 0.5,
        max_tokens: 4096,
        profile: {
          max_input_tokens: 128000,
          supports_vision: true,
          image_url_to_base64: true,
        },
        pricing: { input: 2.5, output: 10 },
        fallback_model: "other-id",
        enabled: false,
        order: 3,
        created_at: "2024-01-01",
        updated_at: "2024-01-02",
        unknown_field: "drop me",
      },
    ]);

    expect(result.models).toHaveLength(1);
    expect(result.models[0]).toEqual({
      value: "openai/gpt-4o",
      label: "GPT-4o",
      description: "flagship",
      provider: "openai",
      icon: "openai",
      api_key: "sk-real",
      api_base: "https://api.openai.com/v1",
      api_format: "responses",
      request_headers: { "X-Custom": "1" },
      temperature: 0.5,
      max_tokens: 4096,
      profile: {
        max_input_tokens: 128000,
        supports_vision: true,
        image_url_to_base64: true,
      },
      pricing: { input: 2.5, output: 10 },
      fallback_model: "other-id",
      enabled: false,
      order: 3,
    });
    expect(result.skippedCount).toBe(0);
    expect(result.maskedKeyCount).toBe(0);
  });

  test("strips masked api keys and counts them", () => {
    const result = normalizeImportedModels([
      { value: "a", label: "A", api_key: "sk-1...abcd" },
      { value: "b", label: "B", api_key: "****" },
      { value: "c", label: "C", api_key: "sk-real" },
    ]);

    expect(result.maskedKeyCount).toBe(2);
    expect(result.models.map((m) => m.api_key)).toEqual([
      undefined,
      undefined,
      "sk-real",
    ]);
  });

  test("skips entries missing value or label", () => {
    const result = normalizeImportedModels([
      { value: "a", label: "A" },
      { label: "NoValue" },
      { value: "NoLabel" },
      "not-an-object",
      null,
    ]);

    expect(result.skippedCount).toBe(4);
    expect(result.models.map((m) => m.value)).toEqual(["a"]);
  });

  test("drops invalid enum, header and numeric values", () => {
    const result = normalizeImportedModels([
      {
        value: "a",
        label: "A",
        api_format: "bogus",
        request_headers: ["not", "an", "object"],
        temperature: "hot",
        max_tokens: 1.5,
        profile: { supports_vision: "yes", max_input_tokens: "128k" },
        pricing: { input: "free" },
        order: "first",
      },
    ]);

    expect(result.models[0]).toEqual({
      value: "a",
      label: "A",
      enabled: true,
    });
  });

  test("coerces request header values to strings", () => {
    const result = normalizeImportedModels([
      { value: "a", label: "A", request_headers: { "X-Num": 42 } },
    ]);

    expect(result.models[0].request_headers).toEqual({ "X-Num": "42" });
  });
});

describe("buildModelCreateFromRow", () => {
  test("row-level api credentials win over shared config", () => {
    const result = buildModelCreateFromRow(
      { ...emptyRow(), apiKey: "sk-row", apiBase: "https://row/v1" },
      {
        apiKey: "sk-shared",
        apiBase: "https://shared/v1",
        apiFormat: "responses",
      },
    );

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.model.api_key).toBe("sk-row");
      expect(result.model.api_base).toBe("https://row/v1");
      expect(result.model.api_format).toBe("responses");
    }
  });

  test("shared config fills empty row credentials", () => {
    const result = buildModelCreateFromRow(emptyRow(), {
      apiKey: "sk-shared",
      apiBase: "https://shared/v1",
      apiFormat: "",
      requestHeaders: { "X-Shared": "1" },
    });

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.model.api_key).toBe("sk-shared");
      expect(result.model.api_base).toBe("https://shared/v1");
      expect(result.model.api_format).toBeUndefined();
      expect(result.model.request_headers).toEqual({ "X-Shared": "1" });
    }
  });

  test("builds profile flags and token overrides", () => {
    const result = buildModelCreateFromRow(
      {
        ...emptyRow(),
        supportsVision: true,
        imageUrlToBase64: true,
        maxInputTokens: "200000",
        maxTokens: "8192",
        temperature: "0.3",
      },
      { apiKey: "", apiBase: "", apiFormat: "" },
    );

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.model.profile).toEqual({
        max_input_tokens: 200000,
        supports_vision: true,
        image_url_to_base64: true,
      });
      expect(result.model.max_tokens).toBe(8192);
      expect(result.model.temperature).toBe(0.3);
    }
  });

  test("includes pricing override only when a price is filled", () => {
    const withPrice = buildModelCreateFromRow(
      { ...emptyRow(), priceInput: "2.5", priceCacheRead: "0.5" },
      { apiKey: "", apiBase: "", apiFormat: "" },
    );
    const withoutPrice = buildModelCreateFromRow(
      emptyRow(),
      { apiKey: "", apiBase: "", apiFormat: "" },
    );

    expect(withPrice.ok && withPrice.model.pricing).toEqual({
      input: 2.5,
      cache_read: 0.5,
    });
    expect(withoutPrice.ok && withoutPrice.model.pricing).toBeUndefined();
  });

  test("rejects invalid numeric input with field-specific errors", () => {
    expect(
      buildModelCreateFromRow(
        { ...emptyRow(), temperature: "3" },
        { apiKey: "", apiBase: "", apiFormat: "" },
      ),
    ).toEqual({ ok: false, error: "invalidTemperature" });

    expect(
      buildModelCreateFromRow(
        { ...emptyRow(), maxTokens: "abc" },
        { apiKey: "", apiBase: "", apiFormat: "" },
      ),
    ).toEqual({ ok: false, error: "invalidMaxTokens" });

    expect(
      buildModelCreateFromRow(
        { ...emptyRow(), maxInputTokens: "abc" },
        { apiKey: "", apiBase: "", apiFormat: "" },
      ),
    ).toEqual({ ok: false, error: "invalidMaxInputTokens" });

    expect(
      buildModelCreateFromRow(
        { ...emptyRow(), priceOutput: "-1" },
        { apiKey: "", apiBase: "", apiFormat: "" },
      ),
    ).toEqual({ ok: false, error: "pricingInvalid" });
  });
});

describe("mergeSharedIntoImported", () => {
  test("fills only missing fields from shared config", () => {
    const merged = mergeSharedIntoImported(
      {
        value: "a",
        label: "A",
        api_key: "sk-own",
        request_headers: { "X-Own": "1" },
      },
      {
        apiKey: "sk-shared",
        apiBase: "https://shared/v1",
        apiFormat: "responses",
        requestHeaders: { "X-Shared": "1" },
      },
    );

    expect(merged.api_key).toBe("sk-own");
    expect(merged.api_base).toBe("https://shared/v1");
    expect(merged.api_format).toBe("responses");
    expect(merged.request_headers).toEqual({ "X-Own": "1" });
  });
});
