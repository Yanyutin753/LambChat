import { projectComposerSnapshot } from "../composerProjection";
import type { ComposerSnapshot } from "../composerTypes";
import { buildSubmitChatBody } from "../../../../services/api/session";

test("sends both inline reference positions and ordered skill names to the Agent API", () => {
  const projection = projectComposerSnapshot({
    version: 1,
    editorState: {
      root: { type: "root", children: [{ type: "paragraph", children: [
        { type: "text", text: "先 " },
        { type: "skill-reference", skillName: "preview-budget-plan" },
        { type: "text", text: " 制定预算，再 " },
        { type: "skill-reference", skillName: "lambchat-coding" },
        { type: "text", text: " 实现。" },
      ] }] },
    },
  });
  expect(buildSubmitChatBody({ message: projection.message, enabledSkills: projection.enabledSkills })).toMatchObject({
    message: "先 [引用技能：preview-budget-plan] 制定预算，再 [引用技能：lambchat-coding] 实现。",
    enabled_skills: ["preview-budget-plan", "lambchat-coding"],
  });
});

test("projects text, file references, and unique skills in document order", () => {
  const snapshot = {
    version: 1,
    editorState: {
      root: {
        type: "root",
        version: 1,
        children: [
          {
            type: "paragraph",
            version: 1,
            children: [
              {
                type: "text",
                version: 1,
                text: "请总结 ",
                detail: 0,
                format: 0,
                mode: "normal",
                style: "",
              },
              {
                type: "file-reference",
                version: 1,
                referenceId: "ref-1",
                fileName: "notes.txt",
                category: "document",
                status: "ready",
              },
              {
                type: "text",
                version: 1,
                text: " 并使用 ",
                detail: 0,
                format: 0,
                mode: "normal",
                style: "",
              },
              {
                type: "skill-reference",
                version: 1,
                skillName: "writer",
                tags: ["writing"],
              },
              {
                type: "skill-reference",
                version: 1,
                skillName: "writer",
                tags: ["writing"],
              },
            ],
          },
        ],
        direction: null,
        format: "",
        indent: 0,
      },
    },
  } satisfies ComposerSnapshot;

  expect(projectComposerSnapshot(snapshot)).toEqual({
    message: "请总结 [引用文件：notes.txt] 并使用 [引用技能：writer][引用技能：writer]",
    activeReferenceIds: ["ref-1"],
    enabledSkills: ["writer"],
    runModes: [],
    isEmpty: false,
  });
});

test("projects paragraphs and line breaks without flattening normal writing", () => {
  const snapshot = {
    version: 1,
    editorState: {
      root: {
        type: "root",
        version: 1,
        children: [
          {
            type: "paragraph",
            version: 1,
            children: [
              { type: "text", version: 1, text: "first" },
              { type: "linebreak", version: 1 },
              { type: "text", version: 1, text: "second" },
            ],
          },
          {
            type: "paragraph",
            version: 1,
            children: [{ type: "text", version: 1, text: "third" }],
          },
        ],
      },
    },
  } satisfies ComposerSnapshot;

  expect(projectComposerSnapshot(snapshot).message).toBe(
    "first\nsecond\nthird",
  );
});

test("treats a document containing only a skill as non-empty", () => {
  const snapshot = {
    version: 1,
    editorState: {
      root: {
        type: "root",
        version: 1,
        children: [
          {
            type: "paragraph",
            version: 1,
            children: [
              {
                type: "skill-reference",
                version: 1,
                skillName: "writer",
                tags: [],
              },
            ],
          },
        ],
      },
    },
  } satisfies ComposerSnapshot;

  expect(projectComposerSnapshot(snapshot)).toEqual({
    message: "[引用技能：writer]",
    activeReferenceIds: [],
    enabledSkills: ["writer"],
    runModes: [],
    isEmpty: false,
  });
});

test("collects run-mode chips in canonical order without contributing text", () => {
  const snapshot = {
    version: 1,
    editorState: {
      root: {
        type: "root",
        version: 1,
        children: [
          {
            type: "paragraph",
            version: 1,
            children: [
              { type: "run-mode-reference", version: 1, modeKey: "goal" },
              { type: "text", version: 1, text: "ok" },
              { type: "run-mode-reference", version: 1, modeKey: "auto" },
              { type: "run-mode-reference", version: 1, modeKey: "goal" },
            ],
          },
        ],
      },
    },
  } satisfies ComposerSnapshot;

  expect(projectComposerSnapshot(snapshot)).toEqual({
    message: "ok",
    activeReferenceIds: [],
    enabledSkills: [],
    runModes: ["auto", "goal"],
    isEmpty: false,
  });
});
