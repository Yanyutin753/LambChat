import catalog from "./preview-locales.json";

export const previewLanguages = ["zh", "en", "ja", "ko", "ru"] as const;
export type PreviewLanguage = (typeof previewLanguages)[number];

export function resolvePreviewLanguage(value: string | null): PreviewLanguage {
  const language = value?.toLowerCase().split(/[-_]/)[0];
  return previewLanguages.find((item) => item === language) ?? "zh";
}

const translations: Record<
  string,
  Partial<Record<PreviewLanguage, string>>
> = catalog;
const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const pattern = (phrases: string[]) =>
  new RegExp(
    phrases
      .sort((a, b) => b.length - a.length)
      .map(escape)
      .join("|"),
    "g",
  );
const sourcePattern = pattern(Object.keys(translations));

export function translatePreviewText(
  text: string,
  language: PreviewLanguage,
): string {
  const translated = text.replace(
    sourcePattern,
    (phrase) => translations[phrase][language] ?? phrase,
  );
  if (language === "zh") return translated;
  const punctuation: Record<string, string> = {
    "，": language === "ja" ? "、" : ", ",
    "。": language === "ja" ? "。" : ". ",
    "：": ": ",
    "；": "; ",
    "！": "!",
    "？": "?",
    "（": "(",
    "）": ")",
  };
  return translated.replace(/[，。：；！？（）]/g, (mark) => punctuation[mark]);
}

export function restorePreviewText(
  text: string,
  language: PreviewLanguage,
): string {
  if (language === "zh") return text;
  const originals = Object.fromEntries(
    Object.entries(translations).map(([source, values]) => [
      values[language] ?? source,
      source,
    ]),
  );
  return text.replace(
    pattern(Object.keys(originals)),
    (phrase) => originals[phrase],
  );
}

// ponytail: controlled fixture CSV has unquoted source cells; use a CSV parser for imported data.
export function translatePreviewCsv(
  text: string,
  language: PreviewLanguage,
): string {
  return text
    .split("\n")
    .map((row) =>
      row
        .split(",")
        .map((cell) => {
          const translated = translatePreviewText(cell, language);
          return /[,"\n]/.test(translated)
            ? `"${translated.replaceAll('"', '""')}"`
            : translated;
        })
        .join(","),
    )
    .join("\n");
}

// ponytail: preview-only phrase matching; use fixture factories if grammatical variants are needed.
export function localizePreviewData<T>(value: T, language: PreviewLanguage): T {
  if (typeof value === "string")
    return translatePreviewText(value, language) as T;
  if (Array.isArray(value))
    return value.map((item) => localizePreviewData(item, language)) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        translatePreviewText(key, language),
        typeof item === "string" && key.endsWith(".csv")
          ? translatePreviewCsv(item, language)
          : localizePreviewData(
              item,
              previewLanguages.includes(key as PreviewLanguage)
                ? (key as PreviewLanguage)
                : language,
            ),
      ]),
    ) as T;
  }
  return value;
}

export function createPreviewLanguageBootstrap(): string {
  return `const previewLanguages=${JSON.stringify(previewLanguages)};
const requested=new URLSearchParams(location.search).get("lang")?.toLowerCase().split(/[-_]/)[0];
const previewLanguage=previewLanguages.includes(requested)?requested:"zh";
localStorage.setItem("language",previewLanguage);
document.documentElement.lang=previewLanguage;
for(const method of ["pushState","replaceState"]){
  const navigate=history[method].bind(history);
  history[method]=(data,unused,url)=>{
    if(url){const next=new URL(url,location.href);if(next.origin===location.origin&&!next.searchParams.has("lang")){next.searchParams.set("lang",previewLanguage);}url=next.href;}
    return navigate(data,unused,url);
  };
}`;
}
