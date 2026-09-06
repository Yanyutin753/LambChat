// 模型协议推断：决定「API 格式」选择器是否显示（仅 OpenAI 协议有意义）
import { resolveModelProtocol, showsApiFormat } from "../modelProtocol";

const providers = [
  { value: "anthropic", protocol: "anthropic", prefixes: ["claude"] },
  { value: "google", protocol: "google", prefixes: ["gemini", "gemma"] },
  { value: "openai", protocol: "openai", prefixes: ["gpt", "o1"] },
  { value: "deepseek", protocol: "openai", prefixes: ["deepseek"] },
];

describe("resolveModelProtocol", () => {
  test("值自带 provider 前缀时按前缀解析", () => {
    expect(
      resolveModelProtocol({ value: "anthropic/claude-sonnet-4-5", providers }),
    ).toBe("anthropic");
    expect(
      resolveModelProtocol({ value: "google/gemini-2.5-pro", providers }),
    ).toBe("google");
  });

  test("显式 provider 字段优先于裸模型名", () => {
    expect(
      resolveModelProtocol({
        value: "deepseek-chat",
        provider: "deepseek",
        providers,
      }),
    ).toBe("openai");
  });

  test("值前缀优先于 provider 提示（与后端 _parse_provider 一致）", () => {
    expect(
      resolveModelProtocol({
        value: "anthropic/claude-x",
        provider: "openai",
        providers,
      }),
    ).toBe("anthropic");
  });

  test("裸模型名按前缀推断", () => {
    expect(resolveModelProtocol({ value: "claude-opus-4", providers })).toBe(
      "anthropic",
    );
    expect(resolveModelProtocol({ value: "gemini-2.5-flash", providers })).toBe(
      "google",
    );
    expect(resolveModelProtocol({ value: "gpt-4o", providers })).toBe("openai");
  });

  test("未注册 provider 与未知模型名回退 openai 兼容", () => {
    expect(
      resolveModelProtocol({ value: "relay/custom-model", providers }),
    ).toBe("openai");
    expect(resolveModelProtocol({ value: "totally-unknown", providers })).toBe(
      "openai",
    );
    expect(resolveModelProtocol({ value: "", providers })).toBe("openai");
  });

  test("空 provider 列表安全回退", () => {
    expect(resolveModelProtocol({ value: "claude-x", providers: [] })).toBe(
      "openai",
    );
  });
});

describe("showsApiFormat", () => {
  test("仅 OpenAI 协议显示 API 格式选择器", () => {
    expect(showsApiFormat("openai")).toBe(true);
    expect(showsApiFormat("anthropic")).toBe(false);
    expect(showsApiFormat("google")).toBe(false);
  });
});
