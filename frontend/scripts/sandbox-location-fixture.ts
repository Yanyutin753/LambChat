/** Preview-only native commands: no filesystem access, migration or relaunch. */
const params = new URLSearchParams(location.search);
const attempted = new Set<string>();
async function run(operation: string) {
  await new Promise((resolve) => setTimeout(resolve, 1200));
  if (params.get("failure") === operation && !attempted.has(operation)) {
    attempted.add(operation);
    throw new Error("Preview operation unavailable");
  }
}

export async function readSandboxDataLocation() {
  await run("read");
  return {
    root: "/Users/preview/Projects/研究资料与长期交付计划/Local Sandbox/.lambchat",
    customized: params.has("custom"),
    overrideConfigured: params.has("custom"),
  };
}
export async function pickSandboxDirectory() {
  await run("pick");
  return "/Volumes/Workspace/研究资料与长期交付计划/团队共享工作区/sandbox-data";
}
export async function setSandboxDataLocation() {
  await run("save");
}
export async function clearSandboxDataLocation() {
  await run("reset");
}
export async function relaunch() {
  await run("relaunch");
}
