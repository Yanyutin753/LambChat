/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import i18n from "../../../../i18n";
import CadPreview from "../CadPreview";

const load = vi.hoisted(() => ({
  reject: undefined as undefined | ((reason: Error) => void),
  resolve: undefined as undefined | (() => void),
}));
vi.mock("dxf-viewer", () => ({
  DxfViewer: class {
    HasRenderer() {
      return true;
    }
    Load() {
      return new Promise<void>((resolve, reject) => {
        load.resolve = resolve;
        load.reject = reject;
      });
    }
    Destroy() {}
  },
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test.each([true, false])(
  "CAD load preserves focus when the loading overlay disappears (focused=%s)",
  async (focused) => {
    const locale = i18n.cloneInstance({ lng: "zh" });
    render(
      <>
        <button>Outside preview</button>
        <CadPreview
          kind="dxf"
          url="/sample.dxf"
          fileName="sample.dxf"
          t={locale.t}
        />
      </>,
    );
    const overlay = screen.getByRole("status").parentElement!.parentElement!;
    const outside = screen.getByRole("button", { name: "Outside preview" });
    (focused ? overlay : outside).focus();
    await act(async () => load.resolve?.());
    expect(screen.queryByRole("status")).toBeNull();
    if (focused) {
      expect(document.activeElement?.closest(".cad-preview")).not.toBeNull();
    } else {
      expect(outside).toHaveFocus();
    }
  },
);

test("CAD loading announces status and a failed renderer announces recovery", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  const locale = i18n.cloneInstance({ lng: "zh" });
  render(
    <I18nextProvider i18n={locale}>
      <CadPreview
        kind="dxf"
        url="/sample.dxf"
        fileName="sample.dxf"
        t={locale.t}
      />
    </I18nextProvider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("正在准备 CAD 预览");
  await act(async () => load.reject?.(new Error("Unsupported drawing")));
  expect(screen.getByRole("alert")).toHaveTextContent("CAD 文件渲染失败");
  expect(screen.getByRole("alert")).toHaveTextContent("您仍可下载原始文件");
  expect(screen.queryByRole("status")).toBeNull();
});
