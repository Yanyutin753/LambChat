import ReactMarkdown from "react-markdown";
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
  "text-sm font-semibold text-stone-800 dark:text-stone-200 mt-3 first:mt-0 mb-1.5";

export function ReleaseNotesMarkdown({ content }: ReleaseNotesMarkdownProps) {
  return (
    <div className="text-sm leading-relaxed text-stone-600 dark:text-stone-400 [&_code]:rounded [&_code]:bg-stone-100 dark:[&_code]:bg-stone-800 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em] [&_code]:text-stone-700 dark:[&_code]:text-stone-200 [&_del]:line-through [&_strong]:font-semibold [&_strong]:text-stone-800 dark:[&_strong]:text-stone-200">
      <ReactMarkdown
        allowedElements={[...ALLOWED_RELEASE_NOTES_ELEMENTS]}
        components={{
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 dark:text-blue-400 hover:underline"
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
          hr: () => (
            <hr className="my-2.5 border-stone-200 dark:border-stone-700" />
          ),
          blockquote: ({ children }) => (
            <blockquote className="my-1.5 border-l-2 border-stone-300 pl-3 text-stone-500 dark:border-stone-600 dark:text-stone-400">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <table className="my-2 w-full text-left text-xs [&_td]:border-t [&_td]:border-stone-200 [&_td]:py-1 [&_td]:pr-3 [&_th]:border-b [&_th]:border-stone-200 [&_th]:py-1 [&_th]:pr-3 dark:[&_td]:border-stone-700 dark:[&_th]:border-stone-700">
              {children}
            </table>
          ),
        }}
        remarkPlugins={[...cjkGfmRemarkPlugins, remarkBreaks]}
        unwrapDisallowed
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
