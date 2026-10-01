/** @vitest-environment jsdom */
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { ProfileEnvVarsTab } from "../ProfileEnvVarsTab";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({ hasAnyPermission: () => true }),
}));
vi.mock("../../../../services/api/envvar", () => ({
  envvarApi: { list: vi.fn().mockRejectedValue(new Error("offline")) },
}));
vi.mock("../../../skeletons", () => ({ SkeletonList: () => null }));
vi.mock("../../../common/ConfirmDialog", () => ({ ConfirmDialog: () => null }));
vi.mock("react-hot-toast", () => ({ toast: { error: vi.fn() } }));
test("a failed environment variable request shows a retry instead of a misleading empty list", async () => {
  const { unmount } = render(<ProfileEnvVarsTab />);
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByRole("button", { name: "common.refresh" })).toBeTruthy();
  expect(screen.queryByText("envVars.empty")).toBeNull();
  unmount();
});
