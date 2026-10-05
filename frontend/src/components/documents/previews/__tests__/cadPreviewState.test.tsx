/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, expect, test, vi } from "vitest";
import { I18nextProvider } from "react-i18next";
import i18n, { i18nReady } from "../../../../i18n";
import CadPreview from "../CadPreview";

beforeAll(async () => {
  await i18nReady;
  await i18n.loadLanguages(["zh"]);
});

const load = vi.hoisted(() => ({
  reject: undefined as undefined | ((reason: Error) => void),
  resolve: undefined as undefined | (() => void),
  colors: [] as Array<number | undefined>,
}));
vi.mock("dxf-viewer", () => ({
  DxfViewer: class {
    canvas = document.createElement("canvas");
    constructor(
      _container: HTMLElement,
      options: { clearColor?: { getHex(): number } },
    ) {
      load.colors.push(options.clearColor?.getHex());
      _container.appendChild(this.canvas);
    }
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
    GetCanvas() {
      return this.canvas;
    }
  },
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  document.documentElement.className = "";
  document.documentElement.style.removeProperty("--theme-bg-card");
  load.colors = [];
});

test("CAD uses the visible theme surface for drawing contrast and follows theme changes", async () => {
  const locale = i18n.cloneInstance({ lng: "zh" });
  document.documentElement.style.setProperty("--theme-bg-card", "#ffffff");
  const { container } = render(
    <CadPreview
      kind="dxf"
      url="/sample.dxf"
      fileName="sample.dxf"
      t={locale.t}
    />,
  );
  expect(load.colors.at(-1)).toBe(0xffffff);
  await act(async () => {
    document.documentElement.style.setProperty("--theme-bg-card", "#1f1e1b");
    document.documentElement.classList.add("dark");
  });
  expect(load.colors.at(-1)).toBe(0x1f1e1b);
  await act(async () => {
    document.documentElement.style.setProperty("--theme-bg-card", "#fff8ea");
    document.documentElement.className = "sepia";
  });
  expect(load.colors.at(-1)).toBe(0xfff8ea);
  expect(container.querySelectorAll("canvas")).toHaveLength(1);
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
