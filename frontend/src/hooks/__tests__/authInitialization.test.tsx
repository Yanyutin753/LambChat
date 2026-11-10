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
const api = vi.hoisted(() => ({
  current: vi.fn(),
  refresh: vi.fn(),
  logout: vi.fn(),
  expired: true,
}));
vi.mock("../../services/api/auth", () => ({
  authApi: {
    getCurrentUser: api.current,
    refreshToken: api.refresh,
    logout: api.logout,
  },
  buildOAuthLoginUrl: () => "",
}));
vi.mock("../../services/api/token", async (original) => ({
  ...(await original<typeof import("../../services/api/token")>()),
  getAccessToken: () => "access",
  getRefreshToken: () => "refresh",
  isTokenExpired: (token: string) => token === "access" && api.expired,
}));
vi.mock("../../i18n", () => ({
  default: { changeLanguage: vi.fn(), t: (key: string) => key },
}));
function Status() {
  const { isLoading, user } = useAuth();
  return <span>{isLoading ? "Loading" : user?.username ?? "Guest"}</span>;
}
function mount() {
  return render(
    <AuthProvider>
      <Status />
    </AuthProvider>,
  );
}
beforeEach(() => {
  api.expired = true;
  api.logout.mockReset();
  api.refresh.mockReset().mockResolvedValue({ access_token: "renewed" });
  api.current
    .mockReset()
    .mockResolvedValue({ id: "one", username: "First", permissions: [] });
});
afterEach(cleanup);
for (const error of [
  new TypeError("Failed to fetch"),
  Object.assign(new Error("Unavailable"), { status: 503 }),
]) {
  test(`initial refresh ${error.message} preserves login and can be retried`, async () => {
    api.refresh.mockRejectedValueOnce(error);
    mount();
    const retry = await screen.findByRole("button", { name: "common.retry" });
    expect(api.logout).not.toHaveBeenCalled();
    expect(screen.queryByText("Guest")).toBeNull();
    fireEvent.click(retry);
    await screen.findByText("First");
    expect(api.refresh).toHaveBeenCalledTimes(2);
  });
}
test("profile outage is recoverable without redirecting to guest", async () => {
  api.expired = false;
  api.current.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "common.retry" }));
  await screen.findByText("First");
  expect(api.logout).not.toHaveBeenCalled();
});
test("a rejected refresh still logs out", async () => {
  api.refresh.mockRejectedValue(
    Object.assign(new Error("Invalid"), { status: 401 }),
  );
  mount();
  await screen.findByText("Guest");
  expect(api.logout).toHaveBeenCalledOnce();
});
test("an unmounted initialization ignores a late profile result", async () => {
  let resolve!: (value: unknown) => void;
  api.expired = false;
  api.current.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const view = mount();
  view.unmount();
  await act(async () =>
    resolve({ id: "one", username: "First", permissions: [] }),
  );
  expect(api.logout).not.toHaveBeenCalled();
});

test("logout during initialization cannot be undone by the pending profile", async () => {
  let resolve!: (value: unknown) => void;
  api.expired = false;
  api.current.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  mount();
  act(() => window.dispatchEvent(new CustomEvent("auth:logout")));
  await act(async () =>
    resolve({ id: "one", username: "First", permissions: [] }),
  );
  expect(screen.getByText("Guest")).toBeInTheDocument();
  expect(screen.queryByText("First")).toBeNull();
});
