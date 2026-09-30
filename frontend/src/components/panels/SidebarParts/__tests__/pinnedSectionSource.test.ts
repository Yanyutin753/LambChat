import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(__dirname, "../../../../..");

test("sidebar renders a standalone pinned section above the chats section", () => {
  const source = readFileSync(
    resolve(__dirname, "../SessionListContent.tsx"),
    "utf8",
  );

  const pinnedHeader = source.indexOf('t("sidebar.pinnedChats")');
  const chatsHeader = source.indexOf('t("sidebar.chats")');
  expect(pinnedHeader).toBeGreaterThan(-1);
  expect(chatsHeader).toBeGreaterThan(pinnedHeader);

  // 置顶分类渲染会话条目（SessionItem），且未置顶时整个分类隐藏
  expect(source).toMatch(/pinnedSessions\.length > 0 \|\| isPinnedLoading/);
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
