import { useEffect, useRef } from "react";
import sdk from "@stackblitz/sdk";

interface StackBlitzPreviewProps {
  name: string;
  template: string;
  files: Record<string, string>;
  entry?: string;
}

export default function StackBlitzPreview({
  name,
  template,
  files,
  entry,
}: StackBlitzPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // 移除文件路径开头的 /
    const normalizedFiles: Record<string, string> = {};
    for (const [path, content] of Object.entries(files)) {
      const normalizedPath = path.startsWith("/") ? path.slice(1) : path;
      normalizedFiles[normalizedPath] = content;
    }

    // 确保 package.json 存在
    if (!normalizedFiles["package.json"]) {
      normalizedFiles["package.json"] = JSON.stringify(
        {
          name: name.toLowerCase().replace(/\s+/g, "-"),
          version: "0.0.0",
          private: true,
          scripts: {
            dev: "vite",
            build: "vite build",
            preview: "vite preview",
          },
        },
        null,
        2,
      );
    }

    const normalizedEntry = entry?.startsWith("/")
      ? entry.slice(1)
      : entry || "src/main.js";

    sdk.embedProject(
      containerRef.current,
      {
        title: name,
        description: `${name} - Preview`,
        template: "node",
        files: normalizedFiles,
      },
      {
        openFile: normalizedEntry,
        view: "preview",
        height: "100%",
        hideNavigation: false,
        hideDevTools: false,
      },
    );
  }, [name, template, files, entry]);

  return <div ref={containerRef} className="w-full h-full" />;
}
