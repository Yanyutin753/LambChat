import type { Parent, Root } from "mdast";
import { getOwnUploadFileUrl } from "../../services/api/uploadFileUrl";
import type { Options } from "react-markdown";
import remarkCjkFriendly from "remark-cjk-friendly/parseOnly";
import remarkCjkFriendlyGfmStrikethrough from "remark-cjk-friendly-gfm-strikethrough/parseOnly";
import remarkGfm from "remark-gfm";
import { visit } from "unist-util-visit";

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

// 带协议/协议相对/锚点/站内绝对路径的 URL 不参与相对解析(保持原样)
const NON_RELATIVE_URL = /^(?:[a-z][a-z0-9+.-]*:|\/\/|#)/i;

/**
 * 按当前渲染的 markdown 文件自身 URL 解析文档内的相对链接/图片
 * (README 里的 ./report.pdf、docs/x.md 等),使链接进入站内文件的
 * 预览/能力签名管线,私有文件同样可见。
 */
export function remarkRelativeLinkBase(baseUrl: string): Options["remarkPlugins"][number] {
  const plugin = function remarkRelativeLinkBasePlugin() {
    return (tree: Root) => {
      const origin =
        typeof window === "undefined" ? "http://localhost" : window.location.origin;
      let base: URL;
      try {
        base = new URL(baseUrl, origin);
      } catch {
        return;
      }
      // 外链基址(如 S3 直链)没有站内相对语义,不重写
      if (base.origin !== origin) return;
      visit(tree, ["link", "image", "definition"], (node) => {
        const target = node as { url?: unknown };
        if (typeof target.url !== "string" || !target.url) return;
        if (NON_RELATIVE_URL.test(target.url) || target.url.startsWith("/")) return;
        try {
          target.url = new URL(target.url, base).toString();
        } catch {
          // 非法相对地址保持原样
        }
      });
    };
  };
  return plugin as unknown as Options["remarkPlugins"][number];
}
