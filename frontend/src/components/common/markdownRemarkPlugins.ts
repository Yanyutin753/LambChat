import type { Options } from "react-markdown";
import remarkCjkFriendly from "remark-cjk-friendly/parseOnly";
import remarkCjkFriendlyGfmStrikethrough from "remark-cjk-friendly-gfm-strikethrough/parseOnly";
import remarkGfm from "remark-gfm";

export const cjkGfmRemarkPlugins = [
  // Single tildes mark numeric ranges; reserve strikethrough for ~~text~~.
  [remarkGfm, { singleTilde: false }],
  remarkCjkFriendly,
  [remarkCjkFriendlyGfmStrikethrough, { singleTilde: false }],
] satisfies NonNullable<Options["remarkPlugins"]>;
