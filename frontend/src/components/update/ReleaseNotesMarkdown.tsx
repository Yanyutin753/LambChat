import ReactMarkdown from "react-markdown";
import { useTranslation } from "react-i18next";
import remarkBreaks from "remark-breaks";
import { cjkGfmRemarkPlugins } from "../common/markdownRemarkPlugins";

interface ReleaseNotesMarkdownProps {
  content: string;
}

// 弹窗空间有限：允许 GitHub Release 常见的块级语法，
// 禁止 img/pre 等会撑爆小弹窗的元素（unwrapDisallowed 保留其文本内容）。
const ALLOWED_RELEASE_NOTES_ELEMENTS = [
  "a",
  "blockquote",
  "br",
  "code",
  "del",
  "em",
  "h1",
  "h2",
  "h3",
  "hr",
  "li",
  "ol",
  "p",
  "strong",
  "table",
  "tbody",
  "td",
  "th",
  "thead",
  "tr",
  "ul",
] as const;

// Release notes 来自 GitHub Release body，标题统一收敛为紧凑小节样式，
// 避免 ## 在小弹窗里渲染成大标题。
const RELEASE_NOTES_HEADING_CLASS =
  "text-14 font-semibold text-theme-text mt-3 first:mt-0 mb-1.5";

export function ReleaseNotesMarkdown({ content }: ReleaseNotesMarkdownProps) {
  const { t } = useTranslation();
  const notes = content
    .split("<!-- macos-gatekeeper-note -->")[0]
    .replace(
      /^(?:#{1,6}\s+)?LambChat\s+v?\d+\.\d+\.\d+(?:[-+][\w.-]+)?\s*(?:\n|$)/i,
      "",
    )
    .replace(/\n---\s*$/, "")
    .trim();
  if (!notes) {
    return (
      <p className="text-13 leading-relaxed text-theme-text-tertiary">
        {t(
          "update.notesUnavailable",
          "Detailed release notes are not provided for this version.",
        )}
      </p>
    );
  }
  return (
    <div className="min-w-0 [overflow-wrap:anywhere] text-14 leading-relaxed text-theme-text-secondary [&_code]:rounded [&_code]:bg-stone-100 dark:[&_code]:bg-stone-800 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em] [&_code]:text-stone-700 dark:[&_code]:text-stone-200 [&_del]:line-through [&_strong]:font-semibold [&_strong]:text-stone-800 dark:[&_strong]:text-stone-200">
      <ReactMarkdown
        allowedElements={[...ALLOWED_RELEASE_NOTES_ELEMENTS]}
        components={{
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[var(--theme-primary)] hover:underline"
            >
              {children}
            </a>
          ),
          h1: ({ children }) => (
            <h1 className={RELEASE_NOTES_HEADING_CLASS}>{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className={RELEASE_NOTES_HEADING_CLASS}>{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className={RELEASE_NOTES_HEADING_CLASS}>{children}</h3>
          ),
          p: ({ children }) => (
            <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="my-1.5 list-disc space-y-1 pl-4 marker:text-stone-400 dark:marker:text-stone-500">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="my-1.5 list-decimal space-y-1 pl-4 marker:text-stone-400 dark:marker:text-stone-500">
              {children}
            </ol>
          ),
          hr: () => <hr className="my-2.5 border-theme-border" />,
          blockquote: ({ children }) => (
            <blockquote className="my-1.5 border-l-2 border-stone-300 pl-3 text-theme-text-secondary dark:border-theme-border">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <table className="my-2 w-full table-fixed text-left text-12 [&_td]:border-t [&_td]:border-stone-200 [&_td]:py-1 [&_td]:pr-3 [&_th]:border-b [&_th]:border-stone-200 [&_th]:py-1 [&_th]:pr-3 dark:[&_td]:border-stone-700 dark:[&_th]:border-stone-700">
              {children}
            </table>
          ),
        }}
        remarkPlugins={[...cjkGfmRemarkPlugins, remarkBreaks]}
        unwrapDisallowed
      >
        {notes}
      </ReactMarkdown>
    </div>
  );
}
