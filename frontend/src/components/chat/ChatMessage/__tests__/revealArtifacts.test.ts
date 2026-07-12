import {
  buildRevealArtifactTree,
  collectRevealArtifacts,
  getRevealArtifactStats,
  type RevealArtifact,
} from "../revealArtifacts.ts";

test("collects successful file and project reveal artifacts from current message parts", () => {
  const artifacts = collectRevealArtifacts([
    {
      type: "tool",
      name: "reveal_file",
      args: {},
      success: true,
      result: {
        key: "revealed/report.pdf",
        url: "/api/upload/file/revealed/report.pdf",
        name: "report.pdf",
        type: "document",
        mime_type: "application/pdf",
        size: 2048,
        _meta: {
          path: "/workspace/report.pdf",
          description: "Final report",
        },
      },
    },
    {
      type: "tool",
      name: "reveal_file",
      args: { path: "/workspace/draft.md" },
      success: false,
      result: {
        key: "revealed/draft.md",
        url: "/api/upload/file/revealed/draft.md",
        name: "draft.md",
        type: "document",
        size: 10,
      },
    },
    {
      type: "subagent",
      agent_id: "agent-1",
      agent_name: "worker",
      input: "build project",
      depth: 1,
      parts: [
        {
          type: "tool",
          name: "reveal_project",
          args: { project_path: "/workspace/site", name: "site" },
          success: true,
          result: {
            type: "project_reveal",
            version: 2,
            name: "site",
            mode: "project",
            template: "react",
            path: "/workspace/site",
            files: {
              "/src/main.tsx": {
                url: "/api/upload/file/revealed/main",
                is_binary: false,
                size: 100,
              },
            },
          },
        },
      ],
    },
  ]);

  expect(artifacts.length).toBe(2);
  expect(
    artifacts.map((artifact) => ({
      kind: artifact.kind,
      name: artifact.name,
      previewKey: artifact.preview.previewKey,
    })),
  ).toEqual([
    {
      kind: "file",
      name: "report.pdf",
      previewKey: "revealed/report.pdf",
    },
    {
      kind: "project",
      name: "site",
      previewKey: "/workspace/site",
    },
  ]);
});

test("deduplicates repeated file reveal artifacts by source path and keeps the latest preview", () => {
  const artifacts = collectRevealArtifacts([
    {
      type: "tool",
      name: "reveal_file",
      args: {},
      success: true,
      result: {
        key: "revealed_files/first_durian_01_main.png",
        url: "/api/upload/file/revealed_files/first_durian_01_main.png",
        name: "durian_01_main.png",
        type: "image",
        size: 1024,
        _meta: {
          path: "/home/user/durian_images/durian_01_main.png",
        },
      },
    },
    {
      type: "tool",
      name: "reveal_file",
      args: {},
      success: true,
      result: {
        key: "revealed_files/latest_durian_01_main.png",
        url: "/api/upload/file/revealed_files/latest_durian_01_main.png",
        name: "durian_01_main.png",
        type: "image",
        size: 2048,
        _meta: {
          path: "/home/user/durian_images/durian_01_main.png",
        },
      },
    },
  ]);

  expect(artifacts.length).toBe(1);
  expect(artifacts[0].kind).toBe("file");
  if (artifacts[0].kind !== "file") return;

  expect(artifacts[0].preview.previewKey).toBe(
    "revealed_files/latest_durian_01_main.png",
  );
  expect(artifacts[0].fileSize).toBe(2048);
});

test("collects artifact parts without requiring reveal tool parts", () => {
  const artifacts = collectRevealArtifacts([
    {
      type: "artifact",
      success: true,
      artifact: {
        kind: "file",
        id: "file:revealed/puppy.svg",
        name: "puppy.svg",
        path: "/workspace/puppy.svg",
        fileSize: 4096,
        preview: {
          kind: "file",
          previewKey: "revealed/puppy.svg",
          filePath: "/workspace/puppy.svg",
          signedUrl: "/api/upload/file/revealed/puppy.svg",
          fileSize: 4096,
        },
      },
    },
    {
      type: "artifact",
      success: false,
      artifact: {
        kind: "file",
        id: "file:revealed/secret.env",
        name: "secret.env",
        path: "/workspace/secret.env",
        preview: {
          kind: "file",
          previewKey: "revealed/secret.env",
          filePath: "/workspace/secret.env",
        },
      },
    },
  ]);

  expect(artifacts.length).toBe(1);
  expect(artifacts[0].kind).toBe("file");
  expect(artifacts[0].name).toBe("puppy.svg");
});

test("builds stable nested artifact tree metadata", () => {
  const artifacts: RevealArtifact[] = [
    {
      kind: "file",
      id: "file:src/app/page.tsx",
      name: "page.tsx",
      path: "/workspace/site/src/app/page.tsx",
      preview: {
        kind: "file",
        previewKey: "src/app/page.tsx",
        filePath: "/workspace/site/src/app/page.tsx",
      },
    },
    {
      kind: "file",
      id: "file:src/app/styles.css",
      name: "styles.css",
      path: "/workspace/site/src/app/styles.css",
      preview: {
        kind: "file",
        previewKey: "src/app/styles.css",
        filePath: "/workspace/site/src/app/styles.css",
      },
    },
  ];

  const tree = buildRevealArtifactTree(
    artifacts.filter(
      (a): a is RevealArtifact & { kind: "file" } => a.kind === "file",
    ),
  );
  const workspace = tree.children[0];
  expect(workspace.kind).toBe("dir");
  if (workspace.kind !== "dir") return;

  expect(workspace.path).toBe("workspace");
  expect(workspace.fileCount).toBe(2);
  expect(workspace.dirCount).toBe(3);

  const stats = getRevealArtifactStats(artifacts);
  expect(stats).toEqual({
    fileCount: 2,
    projectCount: 0,
    totalCount: 2,
  });
});
