import JSZip from "jszip";

export async function exportProjectZip(
  files: Record<string, string>,
  projectName: string,
): Promise<void> {
  const zip = new JSZip();
  for (const [path, content] of Object.entries(files)) {
    zip.file(path, content);
  }
  const blob = await zip.generateAsync({ type: "blob" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${projectName.replace(
    /[^a-zA-Z0-9_\u4e00-\u9fa5-]/g,
    "_",
  )}.zip`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
