import { useEffect } from "react";
import { useTranslation } from "react-i18next";

/**
 * 设置页面标题的 Hook，支持 i18n
 * @param title 页面标题，可以是翻译 key 或直接字符串
 * @param suffix 标题后缀，默认 "LambChat"
 * @param options i18n 选项
 */
export function usePageTitle(
  title: string,
  suffix: string = "LambChat",
  options?: { isI18nKey?: boolean },
) {
  const { t } = useTranslation();
  const isI18nKey = options?.isI18nKey ?? true;

  useEffect(() => {
    // 如果是 i18n key，则翻译；否则直接使用
    const translatedTitle = isI18nKey && title ? t(title) : title;
    const translatedSuffix = isI18nKey ? t("appName") || suffix : suffix;

    const fullTitle = translatedTitle
      ? `${translatedTitle} - ${translatedSuffix}`
      : translatedSuffix;
    document.title = fullTitle;

    // 组件卸载时恢复默认标题
    return () => {
      document.title = isI18nKey ? t("appName") || suffix : suffix;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, suffix, isI18nKey]);
}
