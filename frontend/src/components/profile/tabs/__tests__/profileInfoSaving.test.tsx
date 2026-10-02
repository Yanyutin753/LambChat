/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ProfileInfoTab } from "../ProfileInfoTab";

const api = vi.hoisted(() => ({
  username: vi.fn(),
  upload: vi.fn(),
  remove: vi.fn(),
  compress: vi.fn(),
  refresh: vi.fn(),
  profile: vi.fn(),
  toast: vi.fn(),
  permission: true,
  user: {
    id: "first",
    username: "Original",
    email: "person@example.test",
    avatar_url: null as string | null,
    roles: ["member"],
  },
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    user: api.user,
    refreshUser: api.refresh,
    hasPermission: () => api.permission,
  }),
}));
vi.mock("../../../../hooks/useSettings", () => ({
  useSettings: () => ({ getSettingValue: () => null }),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("react-hot-toast", () => ({
  toast: { success: api.toast, error: api.toast },
}));
vi.mock("../../../../services/api", () => ({
  authApi: { updateUsername: api.username, getProfile: api.profile },
  uploadApi: { uploadAvatar: api.upload, deleteAvatar: api.remove },
  getFullUrl: (url: string) => url,
}));
vi.mock("../../../../utils/imageCompression", () => ({
  compressImageFile: api.compress,
}));
beforeEach(() => {
  api.username.mockReset().mockResolvedValue({});
  api.upload.mockReset().mockResolvedValue({ url: "/avatar.png" });
  api.remove.mockReset().mockResolvedValue({ deleted: true });
  api.compress.mockReset().mockImplementation(async (file: File) => file);
  api.refresh.mockReset().mockResolvedValue(undefined);
  api.profile.mockReset().mockResolvedValue({});
  api.toast.mockReset();
  api.permission = true;
  api.user = {
    id: "first",
    username: "Original",
    email: "person@example.test",
    avatar_url: null,
    roles: ["member"],
  };
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function deferred<T = void>() {
  let resolve!: (value: T) => void, reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function edit(value = "New name") {
  fireEvent.click(screen.getByRole("button", { name: "common.edit" }));
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value } });
  return input;
}
function chooseAvatar(file: File) {
  fireEvent.change(document.querySelector("input[type=file]")!, {
    target: { files: [file] },
  });
}

test("username save freezes the active draft and retries failure without losing it", async () => {
  const pending = deferred();
  api.username.mockReturnValueOnce(pending.promise);
  render(<ProfileInfoTab />);
  const input = edit();
  const save = screen.getByRole("button", { name: "common.save" });
  fireEvent.click(save);
  fireEvent.click(save);
  expect(input).toBeDisabled();
  expect(screen.getByRole("button", { name: "common.cancel" })).toBeDisabled();
  expect(document.activeElement?.tagName).toBe("FORM");
  await act(async () => pending.reject(new Error("Name unavailable")));
  expect(screen.getByRole("alert")).toHaveTextContent("Name unavailable");
  expect(input).toHaveValue("New name");
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  await waitFor(() => expect(screen.queryByRole("textbox")).toBeNull());
  expect(api.username.mock.calls).toEqual([["New name"], ["New name"]]);
  expect(api.refresh).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(
    screen.getByRole("button", { name: "common.edit" }),
  );
});

test("Escape cancels only username editing and restores the edit trigger", () => {
  render(<ProfileInfoTab />);
  const input = edit();
  const outer = vi.fn();
  document.addEventListener("keydown", outer);
  try {
    fireEvent.keyDown(input, { key: "Escape", isComposing: true });
    expect(screen.getByRole("textbox")).toHaveValue("New name");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "common.edit" }),
    );
    expect(outer).not.toHaveBeenCalled();
  } finally {
    document.removeEventListener("keydown", outer);
  }
});

test("closing the profile before username completion prevents stale refresh and toast", async () => {
  const pending = deferred();
  api.username.mockReturnValue(pending.promise);
  const view = render(<ProfileInfoTab />);
  edit();
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  view.unmount();
  await act(async () => pending.resolve());
  expect(api.refresh).not.toHaveBeenCalled();
  expect(api.toast).not.toHaveBeenCalled();
});

test("switching accounts discards the old username draft and its late response", async () => {
  const pending = deferred();
  api.username.mockReturnValue(pending.promise);
  const view = render(<ProfileInfoTab />);
  edit();
  fireEvent.click(screen.getByRole("button", { name: "common.save" }));
  api.user = { ...api.user, id: "second", username: "Second" };
  view.rerender(<ProfileInfoTab />);
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(screen.getByText("Second")).toBeInTheDocument();
  await act(async () => pending.resolve());
  expect(api.refresh).not.toHaveBeenCalled();
});

test("a failed avatar upload keeps the prepared file for retry and refreshes once on success", async () => {
  const source = new File(["source"], "avatar.png", { type: "image/png" });
  const compressed = new File(["small"], "avatar.png", { type: "image/png" });
  api.compress.mockResolvedValue(compressed);
  api.upload.mockRejectedValueOnce(new Error("Offline"));
  render(<ProfileInfoTab />);
  chooseAvatar(source);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "profile.uploadFailed",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: profile.avatar" }),
  );
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(api.upload.mock.calls).toEqual([[compressed], [compressed]]);
  expect(api.compress).toHaveBeenCalledOnce();
  expect(api.refresh).toHaveBeenCalledOnce();
  expect(api.profile).not.toHaveBeenCalled();
});

test("avatar preparation errors remain recoverable with the original file", async () => {
  const file = new File(["image"], "avatar.png", { type: "image/png" });
  api.compress.mockRejectedValueOnce(new Error("Decode failed"));
  render(<ProfileInfoTab />);
  chooseAvatar(file);
  await screen.findByRole("alert");
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: profile.avatar" }),
  );
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(api.compress.mock.calls.map((call) => call[0])).toEqual([file, file]);
  expect(api.upload).toHaveBeenCalledWith(file);
});

test("closing during image preparation prevents uploading for an obsolete profile", async () => {
  const pending = deferred<File>();
  api.compress.mockReturnValue(pending.promise);
  const file = new File(["image"], "avatar.png", { type: "image/png" });
  const view = render(<ProfileInfoTab />);
  chooseAvatar(file);
  await waitFor(() => expect(api.compress).toHaveBeenCalledOnce());
  expect(
    screen.getByRole("button", { name: "profile.changeAvatar" }),
  ).toBeDisabled();
  expect(document.activeElement).toBe(
    document.querySelector(".profile-avatar"),
  );
  const signal = api.compress.mock.calls[0][1].signal as AbortSignal;
  expect(signal).toBeDefined();
  view.unmount();
  expect(signal.aborted).toBe(true);
  await act(async () => pending.resolve(file));
  expect(api.upload).not.toHaveBeenCalled();
  expect(api.refresh).not.toHaveBeenCalled();
});

test("avatar deletion exposes a persistent error and retries without an extra profile read", async () => {
  api.user.avatar_url = "/avatar.png";
  api.remove.mockRejectedValueOnce(new Error("Offline"));
  render(<ProfileInfoTab />);
  fireEvent.click(screen.getByRole("button", { name: "profile.deleteAvatar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "profile.deleteFailed",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "common.retry: profile.avatar" }),
  );
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(api.remove).toHaveBeenCalledTimes(2);
  expect(api.refresh).toHaveBeenCalledOnce();
  expect(api.profile).not.toHaveBeenCalled();
});

test("avatar actions remain absent without upload permission", () => {
  api.permission = false;
  render(<ProfileInfoTab />);
  expect(
    screen.queryByRole("button", { name: "profile.changeAvatar" }),
  ).toBeNull();
  expect(document.querySelector("input[type=file]")).toBeNull();
});

test.each(["missing", "unsupported"])(
  "large JPEG avatars use real main-thread compression when the worker is %s",
  async (support) => {
    const { compressImageFile } = await vi.importActual<
      typeof import("../../../../utils/imageCompression")
    >("../../../../utils/imageCompression");
    api.compress.mockImplementation(compressImageFile);
    class UnsupportedWorker {
      onmessage: ((event: { data: object }) => void) | null = null;
      postMessage() {
        queueMicrotask(() =>
          this.onmessage?.({
            data: { ok: false, code: "unsupported", message: "unsupported" },
          }),
        );
      }
      terminate() {}
    }
    vi.stubGlobal(
      "Worker",
      support === "missing" ? undefined : UnsupportedWorker,
    );
    vi.stubGlobal("createImageBitmap", async () => ({
      width: 2048,
      height: 1024,
      close: vi.fn(),
    }));
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
      () => ({ drawImage: vi.fn() }) as unknown as CanvasRenderingContext2D,
    );
    vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation(
      function (callback) {
        expect(this.width).toBe(512);
        expect(this.height).toBe(256);
        callback(new Blob([new Uint8Array(90 * 1024)], { type: "image/jpeg" }));
      },
    );
    api.upload.mockImplementation(async (file: File) => {
      if (file.size > 2 * 1024 * 1024) throw new Error("Avatar exceeds 2MB");
      return { url: "/avatar.jpg" };
    });
    render(<ProfileInfoTab />);
    chooseAvatar(
      new File([new Uint8Array(3 * 1024 * 1024)], "photo.jpg", {
        type: "image/jpeg",
      }),
    );
    await waitFor(() => expect(api.refresh).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).toBeNull();
    const uploaded = api.upload.mock.calls[0][0] as File;
    expect(uploaded.size).toBe(90 * 1024);
    expect(uploaded.type).toBe("image/jpeg");
  },
);
