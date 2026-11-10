import { useTranslation } from "react-i18next";

/** Bounded preview; the complete payload remains available in the raw result. */
export function StructuredToolResult({
  data,
  depth = 0,
}: {
  data: unknown;
  depth?: number;
}) {
  const { t } = useTranslation();
  if (data === null || data === undefined)
    return <span className="text-theme-text-tertiary">—</span>;
  if (typeof data !== "object") {
    return <span className="tool-result-value">{String(data)}</span>;
  }
  if (depth >= 4)
    return (
      <span className="text-theme-text-tertiary">
        {t("chat.message.toolResultMore")}
      </span>
    );
  if (Array.isArray(data)) {
    if (!data.length)
      return (
        <span className="text-theme-text-tertiary">
          {t("chat.message.toolResultEmpty")}
        </span>
      );
    return (
      <div className="tool-structured-list">
        {data.slice(0, 20).map((item, index) => (
          <div className="tool-structured-item" key={index}>
            <StructuredToolResult data={item} depth={depth + 1} />
          </div>
        ))}
        {data.length > 20 && (
          <span className="text-theme-text-tertiary">
            {t("chat.message.toolResultMore")}
          </span>
        )}
      </div>
    );
  }
  const entries = Object.entries(data);
  const title = entries.find(
    ([key, value]) =>
      (key === "name" || key === "title") && typeof value === "string",
  );
  const metadata = entries.filter(
    ([key]) =>
      key === "id" ||
      key === "url" ||
      key.endsWith("_id") ||
      key.endsWith("_ids"),
  );
  const fields = entries.filter(
    ([key]) =>
      key !== title?.[0] && !metadata.some(([metaKey]) => key === metaKey),
  );
  const renderFields = (values: [string, unknown][]) => (
    <dl className="tool-structured-fields">
      {values.slice(0, 24).map(([key, value]) => (
        <div className="tool-structured-field" key={key}>
          <dt>
            {t(`chat.message.toolResultFields.${key}`, {
              defaultValue: key.replaceAll("_", " "),
            })}
          </dt>
          <dd>
            <StructuredToolResult data={value} depth={depth + 1} />
          </dd>
        </div>
      ))}
      {values.length > 24 && <div>{t("chat.message.toolResultMore")}</div>}
    </dl>
  );
  return (
    <div className="tool-structured-record">
      {title && <h4 className="tool-structured-title">{String(title[1])}</h4>}
      {!entries.length && (
        <span className="text-theme-text-tertiary">
          {t("chat.message.toolResultEmpty")}
        </span>
      )}
      {renderFields(fields)}
      {metadata.length > 0 && (
        <details className="tool-result-metadata">
          <summary>{t("chat.message.toolResultDetails")}</summary>
          {renderFields(metadata)}
        </details>
      )}
    </div>
  );
}
