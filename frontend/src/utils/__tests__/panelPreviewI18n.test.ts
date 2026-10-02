import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { expect, test } from "vitest";
import {
  createPreviewLanguageBootstrap,
  localizePreviewData,
  previewLanguages,
  resolvePreviewLanguage,
  restorePreviewText,
  translatePreviewText,
} from "../../../scripts/preview-i18n";

test("preview language accepts five locales and falls back to Chinese", () => {
  for (const language of previewLanguages) {
    expect(resolvePreviewLanguage(language)).toBe(language);
  }
  expect(resolvePreviewLanguage("EN-us")).toBe("en");
  expect(resolvePreviewLanguage("de")).toBe("zh");
  expect(resolvePreviewLanguage(null)).toBe("zh");
});

test("localized sample punctuation and fixture errors match the selected language", () => {
  expect(translatePreviewText("研究。", "en")).toBe("Research. ");
  expect(translatePreviewText("研究。", "zh")).toBe("研究。");
  for (const language of ["zh", "ja", "ko", "ru"] as const) {
    expect(
      translatePreviewText("Preview fixture unavailable", language),
    ).not.toBe("Preview fixture unavailable");
  }
});

test.each(previewLanguages)(
  "%s translates fixture data without mutating it",
  (language) => {
    const fixture = {
      id: "session-1",
      title: "季度业务分析 01",
      content: "## 研究结论\n\n整理关键发现、证据与后续行动。",
      files: { "/研究资料/会议记录.txt": "确认目标用户和首要任务。" },
      title_i18n: Object.fromEntries(
        previewLanguages.map((lang) => [lang, "季度业务分析 01"]),
      ),
    };
    const localized = localizePreviewData(fixture, language);
    expect(localized.id).toBe(fixture.id);
    expect(localized.title).toBe(translatePreviewText(fixture.title, language));
    for (const lang of previewLanguages) {
      expect(localized.title_i18n[lang]).toBe(
        translatePreviewText(fixture.title, lang),
      );
    }
    if (language !== "zh") expect(localized.title).not.toBe(fixture.title);
    expect(fixture.title).toBe("季度业务分析 01");
    if (["en", "ko", "ru"].includes(language)) {
      expect(JSON.stringify(localized.files)).not.toMatch(/\p{Script=Han}/u);
    }
  },
);

test.each(previewLanguages)(
  "%s keeps localized fixture filenames readable",
  (language) => {
    const path = "/研究资料/会议记录.txt";
    expect(
      restorePreviewText(translatePreviewText(path, language), language),
    ).toBe(path);
    expect(
      translatePreviewText(
        "preview-model-1 https://example.test/report.csv",
        language,
      ),
    ).toBe("preview-model-1 https://example.test/report.csv");
  },
);

test.each(previewLanguages)(
  "%s initializes the real app language and preserves it during navigation",
  (language) => {
    const storage = new Map<string, string>();
    const location = new URL(`http://127.0.0.1:3002/skills?lang=${language}`);
    const navigations: string[] = [];
    const history = {
      pushState: (_data: unknown, _unused: string, url: string) =>
        navigations.push(url),
      replaceState: (_data: unknown, _unused: string, url: string) =>
        navigations.push(url),
    };
    const document = { documentElement: { lang: "" } };
    runInNewContext(createPreviewLanguageBootstrap(), {
      URL,
      URLSearchParams,
      location,
      history,
      document,
      localStorage: {
        setItem: (key: string, value: string) => storage.set(key, value),
      },
    });
    expect(storage.get("language")).toBe(language);
    expect(document.documentElement.lang).toBe(language);
    history.pushState(null, "", "/files?fixture=empty");
    expect(new URL(navigations[0]).searchParams.get("lang")).toBe(language);
    expect(new URL(navigations[0]).searchParams.get("fixture")).toBe("empty");
    history.replaceState(null, "", "/files?lang=ru");
    expect(new URL(navigations[1]).searchParams.get("lang")).toBe("ru");
  },
);

test("all Chinese sample text in preview entry points has English, Korean and Russian translations", () => {
  for (const file of [
    "panel-preview.ts",
    "dialog-preview.tsx",
    "sandbox-data-preview.tsx",
    "server-connection-preview.tsx",
    "local-sandbox-fixture.ts",
    "sandbox-location-fixture.ts",
  ]) {
    const text = readFileSync(
      new URL(`../../../scripts/${file}`, import.meta.url),
      "utf8",
    );
    const source = ts.createSourceFile(
      file,
      text,
      ts.ScriptTarget.Latest,
      true,
    );
    const visit = (node: ts.Node) => {
      if (
        ts.isStringLiteralLike(node) ||
        ts.isTemplateHead(node) ||
        ts.isTemplateMiddle(node) ||
        ts.isTemplateTail(node)
      ) {
        for (const language of ["en", "ko", "ru"] as const) {
          expect(
            translatePreviewText(node.text, language),
            `${file}: ${node.text}`,
          ).not.toMatch(/\p{Script=Han}/u);
        }
      }
      ts.forEachChild(node, visit);
    };
    visit(source);
  }
});

test.each(previewLanguages)(
  "%s preserves every sample file path after localization",
  (language) => {
    for (const path of [
      "研究资料/访谈笔记.md",
      "研究资料/访谈记录",
      "今天吃什么.py",
      "随手记.txt",
      "交付计划与下一阶段验证清单.md",
      "品牌图标.png",
      "音频样例.wav",
      "视频样例.mp4",
    ]) {
      expect(
        restorePreviewText(translatePreviewText(path, language), language),
      ).toBe(path);
    }
  },
);

test.each(previewLanguages)(
  "%s preserves CSV cells containing translated commas",
  (language) => {
    const localized = localizePreviewData(
      { "/sample.csv": "验证方法,完成率\n手机平板桌面逐页走查,100%" },
      language,
    )["/sample.csv"];
    const row = localized.split("\n")[1];
    const translated = translatePreviewText("手机平板桌面逐页走查", language);
    const expectedCell = /[,"\n]/.test(translated)
      ? `"${translated.replaceAll('"', '""')}"`
      : translated;
    expect(row).toBe(`${expectedCell},100%`);
  },
);
