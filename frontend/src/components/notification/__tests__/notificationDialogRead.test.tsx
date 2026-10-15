/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { NotificationDialog } from "../NotificationDialog";
import { notificationApi } from "../../../services/api/notification";
import toast from "react-hot-toast";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../services/api/notification", () => ({
  notificationApi: { getActive: vi.fn(), dismiss: vi.fn() },
}));
vi.mock("../../../services/notifications/announcementNotifications", () => ({
  surfaceAppAnnouncementNotifications: vi.fn(),
}));
vi.mock("react-hot-toast", () => ({ default: { error: vi.fn() } }));
vi.mock("../../common/SceneIllustration", () => ({ SceneIllustration: () => null }));
vi.mock("../../selectors/shared", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../selectors/shared")>(),
  SelectorModalPortal: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectorModalShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(notificationApi.getActive).mockResolvedValue(
    ["first", "second"].map((id) => ({
      id, title_i18n: { en: id }, content_i18n: { en: "body" }, type: "info",
    })) as Awaited<ReturnType<typeof notificationApi.getActive>>,
  );
  vi.mocked(notificationApi.dismiss).mockResolvedValue(undefined);
});
afterEach(cleanup);

test("one click marks every notification read and refreshes the badge", async () => {
  const refreshed = vi.fn();
  render(<NotificationDialog isOpen onClose={vi.fn()} onDismissed={refreshed} />);
  const markAllRead = await screen.findByRole("button", { name: "sidebar.markAllRead" });
  expect(markAllRead.parentElement).toContainElement(screen.getByRole("button", { name: "common.close" }));
  fireEvent.click(markAllRead);
  await waitFor(() => expect(refreshed).toHaveBeenCalledOnce());
  expect(notificationApi.dismiss).toHaveBeenCalledWith("first");
  expect(notificationApi.dismiss).toHaveBeenCalledWith("second");
  expect(screen.getByText("notification.noNotifications")).toBeVisible();
});

test("failed reads remain visible and can be retried", async () => {
  vi.mocked(notificationApi.dismiss).mockRejectedValueOnce(new Error("offline"));
  const refreshed = vi.fn();
  render(<NotificationDialog isOpen onClose={vi.fn()} onDismissed={refreshed} />);
  fireEvent.click(await screen.findByRole("button", { name: "sidebar.markAllRead" }));
  await waitFor(() => expect(refreshed).toHaveBeenCalledOnce());
  expect(screen.getByText("first")).toBeVisible();
  expect(screen.queryByText("second")).toBeNull();
  expect(toast.error).toHaveBeenCalledWith("sidebar.markAllReadFailed");
  fireEvent.click(screen.getByRole("button", { name: "sidebar.markAllRead" }));
  await waitFor(() => expect(screen.getByText("notification.noNotifications")).toBeVisible());
});
