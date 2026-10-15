/** @vitest-environment jsdom */
import { $createParagraphNode, $createTextNode, $getRoot, createEditor } from "lexical";
import { $getClipboardDataFromSelection } from "@lexical/clipboard";
import { expect, test } from "vitest";
import { $createSkillReferenceNode, SkillReferenceNode } from "../nodes/SkillReferenceNode";
import { $createFileReferenceNode, FileReferenceNode } from "../nodes/FileReferenceNode";

test("plain text and HTML clipboard exports retain reference names in selection order", () => {
  const editor = createEditor({ nodes: [SkillReferenceNode, FileReferenceNode], onError: error => { throw error; } });
  editor.update(() => {
    $getRoot().append($createParagraphNode().append(
      $createTextNode("开头 "),
      $createSkillReferenceNode({ skillName: "writer", tags: [] }),
      $createTextNode(" 中间 "),
      $createFileReferenceNode({ referenceId: "f", fileName: "notes.txt", category: "document", status: "ready" }),
      $createTextNode(" 结尾"),
    ));
    $getRoot().select(0, $getRoot().getChildrenSize());
    const clipboard = $getClipboardDataFromSelection();
    const expected = "开头 [引用技能：writer] 中间 [引用文件：notes.txt] 结尾";
    expect(clipboard["text/plain"]).toBe(expected);
    const html = document.createElement("div");
    html.innerHTML = clipboard["text/html"] ?? "";
    expect(html.textContent).toBe(expected);
  }, { discrete: true });
});
