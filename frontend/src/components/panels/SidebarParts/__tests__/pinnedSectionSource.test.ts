import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "../../../../..");

test("session titles omit the pin icon while preserving the pin menu state", () => {
  const source = readFileSync(
    resolve(frontendRoot, "src/components/sidebar/SessionItem.tsx"),
    "utf8",
  );
  expect(source).not.toMatch(/<Pin\s/);
  expect(source).toMatch(/isPinned=\{isPinned\}/);
});

test("sidebar renders a standalone pinned section before projects and recent chats", () => {
  const source = readFileSync(
    resolve(__dirname, "../SessionListContent.tsx"),
    "utf8",
  );

  const pinnedHeader = source.indexOf('t("sidebar.pinnedChats")');
  const projectsHeader = source.indexOf('t("sidebar.projects")');
  const chatsHeader = source.indexOf('t("sidebar.recentChats")');
  expect(pinnedHeader).toBeGreaterThan(-1);
  expect(projectsHeader).toBeGreaterThan(pinnedHeader);
  expect(chatsHeader).toBeGreaterThan(projectsHeader);

  // 没有置顶对话时仍保留拖放入口
  expect(source).toMatch(/data-pinned-drop/);
  expect(source).not.toMatch(
    /pinnedSessions\.length > 0 \|\| isPinnedLoading \?/,
  );
  expect(source).toMatch(/sessionActions\.onPinSession\(sessionId\)/);
});

test("session api and list hook forward pinned_only to the backend", () => {
  const apiSource = readFileSync(
    resolve(frontendRoot, "src/services/api/session.ts"),
    "utf8",
  );
  expect(apiSource).toMatch(/pinned_only/);

  const hookSource = readFileSync(
    resolve(frontendRoot, "src/hooks/useSession.ts"),
    "utf8",
  );
  expect(hookSource).toMatch(/usePinnedSessionList/);
  expect(hookSource).toMatch(/pinnedOnly\??: boolean/);
  expect(hookSource).toMatch(/pinned_only: filter\.pinnedOnly/);
});

test("toggling pin refreshes the standalone pinned list", () => {
  const actionsSource = readFileSync(
    resolve(frontendRoot, "src/hooks/useSessionSidebarActions.ts"),
    "utf8",
  );
  expect(actionsSource).toMatch(/pinnedList\?\.softRefresh\(\)/);
});

test("collapsed sidebar sections do not retain standalone spacer rows", () => {
  const source = readFileSync(
    resolve(__dirname, "../SessionListContent.tsx"),
    "utf8",
  );
  expect(source).not.toMatch(/<div className="mt-4" \/>/);
});

test("projects and pins default to collapsed while recent chats default to expanded", () => {
  const source = readFileSync(
    resolve(__dirname, "../../SessionSidebar.tsx"),
    "utf8",
  );
  expect(source).toMatch(
    /PROJECTS_COLLAPSED_STORAGE_KEY\);\s*return saved !== "false"/,
  );
  expect(source).toMatch(
    /PINNED_COLLAPSED_STORAGE_KEY\);\s*return saved !== "false"/,
  );
  expect(source).toMatch(
    /CHATS_COLLAPSED_STORAGE_KEY\);\s*return saved === "true"/,
  );
});

test("touch drag supports pinned targets and cancels without dropping", () => {
  const source = readFileSync(
    resolve(frontendRoot, "src/hooks/useTouchDrag.ts"),
    "utf8",
  );
  expect(source).toMatch(/data-pinned-drop/);
  expect(source).toMatch(/touchcancel/);
});
test("pin drops request pinning without toggling existing pins", () => {
  const source = readFileSync(
    resolve(frontendRoot, "src/hooks/useSessionSidebarActions.ts"),
    "utf8",
  );
  expect(source).toMatch(/pinOnly/);
  expect(source).toMatch(/isSessionPinned/);
});
