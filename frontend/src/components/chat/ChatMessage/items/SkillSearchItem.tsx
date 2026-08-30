import { memo, useMemo } from "react";
import { Sparkles, Search, BookOpen, Tag } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CollapsiblePill } from "../../../common";
import { extractText } from "./toolUtils";
import {
  openToolLivePanel,
  toolDetailPropsFromPanelData,
  type ToolDetailProps,
} from "./ToolLivePanelContent";
import { ToolArgsBlock } from "./ToolArgsBlock";
import { ToolInlineDetails } from "./ToolInlineDetails";
import { ToolDurationFooter } from "./ToolDurationFooter";
import { ToolHoverCopyButton } from "./ToolHoverCopyButton";

// ── Types ────────────────────────────────────────────────────────────────

interface SkillMatch {
  name: string;
  description: string;
  path: string;
  tags: string[];
}

// ── Helpers ──────────────────────────────────────────────────────────────

/**
 * search_skills 返回纯文本块（Name:/Description:/Path:/Tags:），
 * 首块是给模型的操作指引，其余每块是一个匹配的 Skill。
 */
function parseSkillMatches(result: unknown): SkillMatch[] {
  const text = extractText(result as never);
  if (!text) return [];

  const blocks = text
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter((block) => /^Name:/m.test(block));

  return blocks.map((block) => {
    const pick = (key: string): string => {
      const match = block.match(new RegExp(`^${key}:\\s*(.*)$`, "m"));
      return (match?.[1] || "").trim();
    };
    const name = pick("Name");
    return {
      name,
      description: pick("Description"),
      path: pick("Path") || `/skills/${name}/SKILL.md`,
      tags: pick("Tags")
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    };
  });
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

// ── Panel detail ─────────────────────────────────────────────────────────

/** 面板详情：实时跟随 toolCallPanelStore 数据重建（匹配结果到达即刷新） */
function SkillSearchDetail({ args, result }: ToolDetailProps) {
  const query = (args.query as string) || "";
  const matches = useMemo(() => parseSkillMatches(result), [result]);
  const hasRawFallback = !!result && matches.length === 0;

  return (
    <div className="space-y-3 max-h-full overflow-y-auto p-2 sm:p-4">
      {query && (
        <ToolArgsBlock size="detail">
          <Search
            size={14}
            className="shrink-0 text-violet-500 dark:text-violet-400"
          />
          <span className="text-violet-600 dark:text-violet-400 font-mono font-semibold min-w-0 truncate">
            {truncate(query, 80)}
          </span>
        </ToolArgsBlock>
      )}

      {matches.length > 0 && (
        <div className="space-y-2">
          {matches.map((match) => (
            <div
              key={match.name}
              className="rounded-xl bg-theme-bg border border-theme-border px-3.5 py-3 space-y-2 shadow-[0_1px_2px_rgb(0_0_0/0.04)]"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Sparkles
                  size={13}
                  className="shrink-0 text-violet-500 dark:text-violet-400"
                />
                <span className="text-sm font-semibold text-theme-text truncate">
                  {match.name}
                </span>
              </div>
              {match.description && (
                <p className="text-xs text-theme-text-secondary leading-relaxed line-clamp-3">
                  {match.description}
                </p>
              )}
              <div className="flex items-center gap-2 min-w-0 flex-wrap">
                <span className="inline-flex items-center gap-1 text-10 font-mono text-theme-text-tertiary bg-theme-bg border border-theme-border rounded-md px-1.5 py-0.5 truncate">
                  <BookOpen size={10} className="shrink-0 opacity-60" />
                  {match.path}
                </span>
                {match.tags.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-10 text-theme-text-tertiary truncate">
                    <Tag size={10} className="shrink-0 opacity-60" />
                    {match.tags.join(" · ")}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {hasRawFallback && (
        <pre className="group/result relative text-xs text-theme-text-tertiary whitespace-pre-wrap break-words p-3 rounded-lg bg-theme-bg border border-theme-border">
          {truncate(extractText(result as never), 600)}
          <ToolHoverCopyButton
            text={extractText(result as never)}
            position="result"
          />
        </pre>
      )}
    </div>
  );
}

// ── Item ─────────────────────────────────────────────────────────────────

const SkillSearchItem = memo(function SkillSearchItem({
  id,
  args,
  result,
  success,
  isPending,
  cancelled,
  startedAt,
  completedAt,
}: {
  id?: string;
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}) {
  const { t } = useTranslation();
  const durationFooter = (
    <ToolDurationFooter startedAt={startedAt} completedAt={completedAt} />
  );

  const query = (args.query as string) || "";
  const matches = useMemo(() => parseSkillMatches(result), [result]);

  // 参数生成中（无 result）也允许打开面板：实时等待匹配结果
  const canExpand = !!query || matches.length > 0 || isPending;

  const status = isPending
    ? "loading"
    : cancelled
      ? "cancelled"
      : success
        ? "success"
        : "error";

  const titleLabel = t("chat.message.toolSkillSearch");
  const pillLabel = `${titleLabel} ${query ? `"${truncate(query, 24)}"` : ""}${
    matches.length > 0 ? ` (${matches.length})` : ""
  }`.trim();

  const detailContent = canExpand && (
    <SkillSearchDetail
      args={args}
      result={result}
      success={success}
      isPending={isPending}
      cancelled={cancelled}
      startedAt={startedAt}
      completedAt={completedAt}
    />
  );

  return (
    <CollapsiblePill
      status={status}
      icon={<Sparkles size={12} className="shrink-0 opacity-50" />}
      label={pillLabel}
      variant="tool"
      formatLabel={false}
      expandable={canExpand}
      onPanelOpen={() => {
        if (!canExpand) return;
        openToolLivePanel({
          id,
          title: titleLabel,
          icon: <Sparkles size={16} />,
          status,
          subtitle: query || undefined,
          fallback: detailContent || undefined,
          buildDetail: (data) => (
            <SkillSearchDetail {...toolDetailPropsFromPanelData(data)} />
          ),
          footer: durationFooter,
        });
      }}
    >
      {canExpand && (
        <ToolInlineDetails>
          {query && (
            <ToolArgsBlock size="compact">
              <Search
                size={12}
                className="shrink-0 text-violet-500 dark:text-violet-400"
              />
              <span className="text-violet-600 dark:text-violet-400 font-mono font-medium min-w-0 truncate">
                {truncate(query, 50)}
              </span>
            </ToolArgsBlock>
          )}

          {matches.length > 0 && (
            <div className="space-y-1">
              {matches.slice(0, 4).map((match) => (
                <div
                  key={match.name}
                  className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-theme-bg border border-theme-border"
                >
                  <Sparkles
                    size={11}
                    className="shrink-0 text-violet-500 dark:text-violet-400 opacity-70"
                  />
                  <span className="text-xs text-theme-text font-medium min-w-0 truncate flex-1">
                    {match.name}
                  </span>
                  {match.tags[0] && (
                    <span className="shrink-0 text-10 text-theme-text-tertiary truncate max-w-[96px]">
                      {match.tags[0]}
                    </span>
                  )}
                </div>
              ))}
              {matches.length > 4 && (
                <div className="text-xs text-theme-text-tertiary px-2.5">
                  {t("chat.message.toolSkillMore", {
                    count: matches.length - 4,
                  })}
                </div>
              )}
            </div>
          )}
        </ToolInlineDetails>
      )}
    </CollapsiblePill>
  );
});

export { SkillSearchItem };
