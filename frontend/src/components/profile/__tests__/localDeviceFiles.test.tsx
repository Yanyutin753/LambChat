/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
const native = vi.hoisted(() => ({
  listFiles: vi.fn(),
  importFile: vi.fn(),
  exportFile: vi.fn(),
}));
vi.mock("../../../services/capacitor/localDevice", () => ({
  LocalDevice: native,
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
import { LocalDeviceFiles } from "../LocalDeviceFiles";
beforeEach(() => {
  vi.clearAllMocks();
  native.listFiles.mockResolvedValue({ files: [] });
});

test("imports through the system picker and refreshes the shared file list", async () => {
  render(<LocalDeviceFiles />);
  await screen.findByText("profile.localSandbox.phoneFilesEmpty");
  native.listFiles.mockResolvedValue({
    files: [{ name: "report.txt", size: 12 }],
  });
  fireEvent.click(screen.getByText("profile.localSandbox.importPhoneFile"));
  await screen.findByText("report.txt");
  expect(native.importFile).toHaveBeenCalledOnce();
  fireEvent.click(
    screen.getByRole("button", { name: "common.download report.txt" }),
  );
  await waitFor(() =>
    expect(native.exportFile).toHaveBeenCalledWith({ name: "report.txt" }),
  );
});

test("a failed native listing exposes retry without claiming an empty directory", async () => {
  native.listFiles.mockRejectedValueOnce(new Error("unavailable"));
  render(<LocalDeviceFiles />);
  await screen.findByRole("alert");
  expect(screen.queryByText("profile.localSandbox.phoneFilesEmpty")).toBeNull();
  fireEvent.click(
    screen.getByRole("button", {
      name: "common.retry: profile.localSandbox.phoneFiles",
    }),
  );
  await screen.findByText("profile.localSandbox.phoneFilesEmpty");
});
