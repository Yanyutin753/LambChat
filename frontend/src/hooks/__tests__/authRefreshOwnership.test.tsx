/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AuthProvider, useAuth } from "../useAuth";
import { Permission } from "../../types";
const api = vi.hoisted(() => ({
  current: vi.fn(),
  token: "",
  language: vi.fn(),
  login: vi.fn(),
}));
vi.mock("../../services/api", async () => {
  const { decodeToken } = await import("../../services/api/token");
  return {
    authApi: {
      getCurrentUser: api.current,
      login: api.login,
      logout: () => {
        api.token = "";
      },
    },
    getAccessToken: () => api.token || null,
    getRefreshToken: () => null,
    isAuthenticated: () => !!api.token,
    isTokenExpired: () => false,
    getRedirectPath: () => null,
    clearRedirectPath: () => {},
    buildOAuthLoginUrl: () => "",
    decodeToken,
  };
});
vi.mock("../../i18n", () => ({ default: { changeLanguage: api.language } }));
function token(subject: string, revision = 1) {
  return `header.${btoa(JSON.stringify({ sub: subject, exp: 4102444800, revision }))}.signature`;
}
const first = {
  id: "first",
  username: "First",
  email: "first@example.test",
  roles: ["member"],
  permissions: [Permission.AVATAR_UPLOAD],
  is_active: true,
  metadata: { theme: "light", language: "en" },
};
function deferred() {
  let resolve!: (value: typeof first) => void;
  const promise = new Promise<typeof first>((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
}
function Harness() {
  const { user, refreshUser, logout, login, hasPermission } = useAuth();
  return (
    <>
      <span>{user?.username ?? "Guest"}</span>
      <span>
        {hasPermission(Permission.AVATAR_UPLOAD)
          ? "avatar allowed"
          : "avatar denied"}
      </span>
      <button onClick={() => void refreshUser()}>Refresh</button>
      <button onClick={logout}>Logout</button>
      <button
        onClick={() =>
          void login({ username: "Second", password: "test-only" })
        }
      >
        Login second
      </button>
    </>
  );
}
async function profile() {
  const view = render(
    <AuthProvider>
      <Harness />
    </AuthProvider>,
  );
  await screen.findByText("First");
  api.language.mockClear();
  return view;
}
beforeEach(() => {
  api.token = token("first");
  api.current.mockReset().mockResolvedValue(first);
  api.language.mockReset();
  api.login.mockReset().mockImplementation(async () => {
    api.token = token("second");
  });
  localStorage.clear();
});
afterEach(cleanup);

test("a same-account profile refresh updates identity without overwriting locally applied preferences", async () => {
  await profile();
  localStorage.setItem("lambchat-theme", "sepia");
  localStorage.setItem("language", "ru");
  api.current.mockResolvedValue({ ...first, username: "Updated" });
  fireEvent.click(screen.getByText("Refresh"));
  await screen.findByText("Updated");
  expect(localStorage.getItem("lambchat-theme")).toBe("sepia");
  expect(localStorage.getItem("language")).toBe("ru");
  expect(api.language).not.toHaveBeenCalled();
});
test("a late profile refresh cannot restore the user or metadata after logout", async () => {
  await profile();
  const pending = deferred();
  api.current.mockReturnValue(pending.promise);
  fireEvent.click(screen.getByText("Refresh"));
  fireEvent.click(screen.getByText("Logout"));
  localStorage.setItem("lambchat-theme", "sepia");
  await act(async () => pending.resolve(first));
  expect(screen.getByText("Guest")).toBeInTheDocument();
  expect(screen.getByText("avatar denied")).toBeInTheDocument();
  expect(localStorage.getItem("lambchat-theme")).toBe("sepia");
});
test("a late refresh cannot overwrite a newly logged-in account", async () => {
  await profile();
  const pending = deferred();
  api.current
    .mockReturnValueOnce(pending.promise)
    .mockResolvedValue({
      ...first,
      id: "second",
      username: "Second",
      permissions: [],
    });
  fireEvent.click(screen.getByText("Refresh"));
  fireEvent.click(screen.getByText("Login second"));
  await screen.findByText("Second");
  await act(async () => pending.resolve(first));
  expect(screen.getByText("Second")).toBeInTheDocument();
  expect(screen.getByText("avatar denied")).toBeInTheDocument();
});
test("only the newest profile refresh can update identity and dynamic permissions", async () => {
  await profile();
  const older = deferred(),
    newer = deferred();
  api.current
    .mockReturnValueOnce(older.promise)
    .mockReturnValueOnce(newer.promise);
  fireEvent.click(screen.getByText("Refresh"));
  fireEvent.click(screen.getByText("Refresh"));
  await act(async () =>
    newer.resolve({ ...first, username: "Newest", permissions: [] }),
  );
  await act(async () => older.resolve(first));
  expect(screen.getByText("Newest")).toBeInTheDocument();
  expect(screen.getByText("avatar denied")).toBeInTheDocument();
});
test("same-account token renewal still allows a profile refresh to finish", async () => {
  await profile();
  const pending = deferred();
  api.current.mockReturnValue(pending.promise);
  fireEvent.click(screen.getByText("Refresh"));
  api.token = token("first", 2);
  await act(async () => pending.resolve({ ...first, username: "Renewed" }));
  expect(screen.getByText("Renewed")).toBeInTheDocument();
});
test("an externally replaced account token invalidates an in-flight profile refresh", async () => {
  await profile();
  const pending = deferred();
  api.current.mockReturnValue(pending.promise);
  fireEvent.click(screen.getByText("Refresh"));
  api.token = token("second");
  await act(async () => pending.resolve({ ...first, username: "Obsolete" }));
  expect(screen.queryByText("Obsolete")).toBeNull();
});

test("a first-account refresh restores cloud preferences for an OAuth login", async () => {
  api.token = "";
  render(
    <AuthProvider>
      <Harness />
    </AuthProvider>,
  );
  await screen.findByText("Guest");
  api.token = token("first");
  fireEvent.click(screen.getByText("Refresh"));
  await screen.findByText("First");
  expect(localStorage.getItem("lambchat-theme")).toBe("light");
  expect(api.language).toHaveBeenCalledWith("en");
});
test("an unmounted provider ignores late refresh metadata", async () => {
  const view = await profile();
  const pending = deferred();
  api.current.mockReturnValue(pending.promise);
  fireEvent.click(screen.getByText("Refresh"));
  view.unmount();
  localStorage.setItem("lambchat-theme", "sepia");
  await act(async () => pending.resolve(first));
  expect(localStorage.getItem("lambchat-theme")).toBe("sepia");
  expect(api.language).not.toHaveBeenCalled();
});
