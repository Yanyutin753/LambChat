import { buildSkillFilesPayload } from "../SkillForm.utils.tsx";

test("buildSkillFilesPayload skips unloaded lazy files while editing", () => {
  const files = buildSkillFilesPayload({
    files: [
      { path: "SKILL.md", content: "" },
      { path: "docs/kept.md", content: "" },
      { path: "docs/edited.md", content: "edited" },
    ],
    syncedSkillMarkdown: "---\nname: demo\n---\n",
    isEditing: true,
    loadedFilePaths: new Set(["SKILL.md", "docs/edited.md"]),
  });

  expect(files).toEqual({
    "SKILL.md": "---\nname: demo\n---\n",
    "docs/edited.md": "edited",
  });
});

test("buildSkillFilesPayload keeps empty content for loaded edited files", () => {
  const files = buildSkillFilesPayload({
    files: [
      { path: "SKILL.md", content: "" },
      { path: "docs/emptied.md", content: "" },
    ],
    syncedSkillMarkdown: "---\nname: demo\n---\n",
    isEditing: true,
    loadedFilePaths: new Set(["SKILL.md", "docs/emptied.md"]),
  });

  expect(files["docs/emptied.md"]).toBe("");
});

test("buildSkillFilesPayload includes all files when creating", () => {
  const files = buildSkillFilesPayload({
    files: [
      { path: "SKILL.md", content: "" },
      { path: "docs/new.md", content: "new doc" },
    ],
    syncedSkillMarkdown: "---\nname: demo\n---\n",
    isEditing: false,
    loadedFilePaths: new Set(["SKILL.md"]),
  });

  expect(files).toEqual({
    "SKILL.md": "---\nname: demo\n---\n",
    "docs/new.md": "new doc",
  });
});
