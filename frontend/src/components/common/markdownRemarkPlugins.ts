import type { Parent, Root } from "mdast";
import { getOwnUploadFileUrl } from "../../services/api/uploadFileUrl";
import type { Options } from "react-markdown";
import remarkCjkFriendly from "remark-cjk-friendly/parseOnly";
import remarkCjkFriendlyGfmStrikethrough from "remark-cjk-friendly-gfm-strikethrough/parseOnly";
import remarkGfm from "remark-gfm";

// GFM includes full-width punctuation in bare URLs; keep following prose outside file links.
function remarkUploadFileAutolinks() {
  return (tree: Root, file: { value: unknown }) => {
    const source = String(file.value);
    function visit(parent: Parent) {
      for (let i = 0; i < parent.children.length; i++) {
        const child = parent.children[i];
        if (child.type === "link") {
          const start = child.position?.start.offset;
          const end = child.position?.end.offset;
          if (
            start === undefined ||
            end === undefined ||
            source.slice(start, end) !== child.url ||
            !getOwnUploadFileUrl(child.url)
          )
            continue;
          const boundary = /\.[a-z0-9]{1,12}(?=[（），。；！？：])/i.exec(
            child.url.split(/[?#]/, 1)[0],
          );
          if (!boundary) continue;
          const offset = boundary.index + boundary[0].length;
          const suffix = child.url.slice(offset);
          child.url = child.url.slice(0, offset);
          child.children = [{ type: "text", value: child.url }];
          parent.children.splice(++i, 0, { type: "text", value: suffix });
        } else if ("children" in child) {
          visit(child);
        }
      }
    }
    visit(tree);
  };
}

export const cjkGfmRemarkPlugins = [
  // Single tildes mark numeric ranges; reserve strikethrough for ~~text~~.
  [remarkGfm, { singleTilde: false }],
  remarkCjkFriendly,
  remarkUploadFileAutolinks,
  [remarkCjkFriendlyGfmStrikethrough, { singleTilde: false }],
] satisfies NonNullable<Options["remarkPlugins"]>;
