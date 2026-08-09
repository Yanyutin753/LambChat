import ReactMarkdown from "react-markdown";
import { cjkGfmRemarkPlugins } from "../../common/markdownRemarkPlugins";

interface TaskToastMarkdownProps {
  content: string;
}

const ALLOWED_TOAST_MARKDOWN_ELEMENTS = [
  "a",
  "br",
  "code",
  "del",
  "em",
  "p",
  "strong",
] as const;

export function TaskToastMarkdown({ content }: TaskToastMarkdownProps) {
  return (
    <span className="line-clamp-1 text-xs leading-snug text-stone-500 dark:text-stone-400 [&_a]:text-blue-600 [&_a]:underline-offset-2 [&_a:hover]:underline dark:[&_a]:text-blue-400 [&_code]:rounded [&_code]:bg-stone-100 [&_code]:px-1 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.92em] [&_code]:text-stone-700 dark:[&_code]:bg-stone-800 dark:[&_code]:text-stone-200 [&_em]:italic [&_p]:inline [&_strong]:font-semibold [&_strong]:text-stone-700 dark:[&_strong]:text-stone-200">
      <ReactMarkdown
        allowedElements={[...ALLOWED_TOAST_MARKDOWN_ELEMENTS]}
        components={{
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              {children}
            </a>
          ),
          p: ({ children }) => <span>{children}</span>,
        }}
        remarkPlugins={[...cjkGfmRemarkPlugins]}
        unwrapDisallowed
      >
        {content}
      </ReactMarkdown>
    </span>
  );
}
