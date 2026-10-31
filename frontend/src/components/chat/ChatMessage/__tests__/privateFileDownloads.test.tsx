/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { FileTreeView } from "../items/FileTreeView";
import { RevealArtifactsSummary } from "../RevealArtifactsSummary";
import { useDocumentPreviewState } from "../../../documents/useDocumentPreviewState";
import { authenticatedRequest } from "../../../../services/api/authenticatedRequest";
import { invoke } from "@tauri-apps/api/core";
import toast from "react-hot-toast";
import type { MessagePart } from "../../../../types";

vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));
vi.mock("../../../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn(),
}));
vi.mock("react-i18next", async (original) => ({
  ...(await original<typeof import("react-i18next")>()),
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("react-hot-toast", () => ({ default: { error: vi.fn() } }));

const name = "mace ab recon 38664 qc.sas";
const key = `revealed_files/${name}`;
const url = `/api/upload/file/${key
  .split("/")
  .map(encodeURIComponent)
  .join("/")}`;
const fetchFile = vi.fn();
let saved: { href: string; name: string; connected: boolean }[];
let blobs: Blob[];

function Preview({ keyOnly = false }: { keyOnly?: boolean }) {
  const state = useDocumentPreviewState({
    path: name,
    content: "truncated preview",
    s3Key: key,
    signedUrl: keyOnly ? undefined : url,
    onClose: vi.fn(),
  });
  return <button onClick={state.handleDownload}>Download preview</button>;
}

beforeEach(() => {
  saved = [];
  blobs = [];
  localStorage.setItem("access_token", `account-${Math.random()}`);
  vi.mocked(authenticatedRequest)
    .mockReset()
    .mockResolvedValue(
      new Response(JSON.stringify({ url: `${url}?file_token=capability` })),
    );
  fetchFile
    .mockReset()
    .mockResolvedValue(new Response("complete original file"));
  vi.stubGlobal("fetch", fetchFile);
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL(blob: Blob) {
        blobs.push(blob);
        return "blob:download";
      }
      static revokeObjectURL = vi.fn();
    },
  );
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    saved.push({
      href: this.href,
      name: this.download,
      connected: this.isConnected,
    });
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test.each(["summary", "project", "preview", "key-only preview"])(
  "%s downloads the complete private file with a capability without navigating the chat",
  async (kind) => {
    if (kind === "project") {
      render(
        <FileTreeView
          files={{}}
          binaryFiles={{ [name]: url }}
          showHeader={false}
        />,
      );
    } else if (kind === "summary") {
      const part: MessagePart = {
        type: "artifact",
        success: true,
        artifact: {
          kind: "file",
          id: "file",
          name,
          path: name,
          preview: {
            kind: "file",
            previewKey: "file",
            filePath: name,
            signedUrl: url,
          },
        },
      };
      render(<RevealArtifactsSummary parts={[part]} />);
    } else {
      render(<Preview keyOnly={kind === "key-only preview"} />);
    }
    fireEvent.click(
      screen.getByRole("button", {
        name: kind.includes("preview")
          ? "Download preview"
          : `documents.downloadFile: ${name}`,
      }),
    );
    if (kind.includes("preview")) {
      // Preview panes still materialize the bytes themselves.
      await waitFor(() =>
        expect(saved).toEqual([
          { href: "blob:download", name, connected: true },
        ]),
      );
      const fetched = new URL(
        String(fetchFile.mock.calls[0][0]),
        window.location.origin,
      );
      expect(fetched.searchParams.get("file_token")).toBe("capability");
      expect(fetched.searchParams.get("proxy")).toBe("true");
      expect(blobs[0].size).toBe(new Blob(["complete original file"]).size);
      expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    } else {
      // Chat cards hand the authenticated same-origin URL straight to the
      // browser's native download; the browser streams the bytes itself.
      await waitFor(() => expect(saved).toHaveLength(1));
      const target = new URL(saved[0].href, window.location.origin);
      expect(target.pathname).toBe(url);
      expect(target.searchParams.get("file_token")).toBe("capability");
      expect(target.searchParams.get("proxy")).toBe("true");
      expect(saved[0]).toEqual({
        href: saved[0].href,
        name,
        connected: true,
      });
      expect(fetchFile).not.toHaveBeenCalled();
      expect(blobs).toEqual([]);
    }
    expect(authenticatedRequest).toHaveBeenCalledOnce();
  },
);

test("a denied private download never navigates to the unsigned URL", async () => {
  vi.mocked(authenticatedRequest).mockResolvedValue(
    new Response("denied", { status: 404 }),
  );
  render(
    <FileTreeView
      files={{}}
      binaryFiles={{ [name]: url }}
      showHeader={false}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: `documents.downloadFile: ${name}` }),
  );
  await waitFor(() => expect(authenticatedRequest).toHaveBeenCalledOnce());
  expect(saved).toEqual([]);
  expect(fetchFile).not.toHaveBeenCalled();
});

test("desktop preview sends the complete authenticated file to the native save dialog", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  vi.mocked(invoke).mockResolvedValue(true);
  render(<Preview />);
  fireEvent.click(screen.getByRole("button", { name: "Download preview" }));
  await waitFor(() => expect(invoke).toHaveBeenCalledOnce());
  const [command, bytes, options] = vi.mocked(invoke).mock.calls[0];
  expect(command).toBe("desktop_save_file");
  expect(new TextDecoder().decode(bytes as ArrayBuffer)).toBe(
    "complete original file",
  );
  expect(
    JSON.parse((options?.headers as Record<string, string>)["x-file-name"]),
  ).toBe(name);
  expect(authenticatedRequest).toHaveBeenCalledOnce();
  const fetched = new URL(
    String(fetchFile.mock.calls[0][0]),
    window.location.origin,
  );
  expect(fetched.searchParams.get("file_token")).toBe("capability");
  expect(fetched.searchParams.get("proxy")).toBe("true");
  expect(saved).toEqual([]);
});

test("desktop preview reports fetch failure without opening an unsigned external page", async () => {
  vi.stubGlobal("__TAURI_INTERNALS__", {});
  vi.mocked(authenticatedRequest).mockResolvedValue(
    new Response("denied", { status: 404 }),
  );
  vi.mocked(toast.error).mockClear();
  vi.mocked(invoke).mockClear();
  const open = vi.spyOn(window, "open").mockImplementation(() => null);
  render(<Preview />);
  fireEvent.click(screen.getByRole("button", { name: "Download preview" }));
  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith("chat.message.downloadFailed"),
  );
  expect(invoke).not.toHaveBeenCalled();
  expect(open).not.toHaveBeenCalled();
  expect(saved).toEqual([]);
});
