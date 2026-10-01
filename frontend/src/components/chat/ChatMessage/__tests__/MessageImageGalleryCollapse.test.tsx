/** @vitest-environment jsdom */

import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MessageImageGallery } from "../MessageImageGallery";
import {
  clearUiExpansions,
  getUiExpansion,
  setUiExpansion,
} from "../uiExpansionStore";
import type { RevealFileImageInfo } from "../revealFileImageUtils";

// Mock i18next with simple {{var}} interpolation（RunStepsCollapse.test.tsx 同款）。
// 必须展开原模块：组件依赖链（chatThumbs → api/config → tokenManager →
// src/i18n）在模块加载期会用到真实的 initReactI18next，整体替换会让 i18n.init 抛错
vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();
  return {
    ...actual,
    useTranslation: () => ({
      t: (key: string, opts?: unknown) => {
        const templates: Record<string, string> = {
          "chat.message.imageGalleryCount": "{{count}} images",
          "chat.message.imageGalleryToggle": "Expand or collapse images",
        };
        let out = templates[key] ?? key;
        if (opts && typeof opts === "object") {
          for (const [k, v] of Object.entries(
            opts as Record<string, unknown>,
          )) {
            out = out.split(`{{${k}}}`).join(String(v));
          }
        }
        return out;
      },
      i18n: { language: "en" },
    }),
  };
});

const IMAGES: RevealFileImageInfo[] = [
  {
    id: "reveal-1",
    src: "https://app.example.com/api/upload/file/generated-images/img-1.png",
    fileName: "img-1.png",
  },
  {
    id: "reveal-2",
    src: "https://app.example.com/api/upload/file/generated-images/img-2.png",
    fileName: "img-2.png",
  },
];

function toggleRow() {
  return screen.getByRole("button", { name: "Expand or collapse images" });
}

describe("MessageImageGallery collapse", () => {
  test("history message mounts collapsed and expands on toggle", () => {
    clearUiExpansions();
    render(
      <MessageImageGallery
        images={IMAGES}
        defaultExpanded={false}
        stateKey="msg-1:gallery-3"
      />,
    );

    const toggle = toggleRow();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.textContent).toContain("2 images");
    // 收起时不渲染整图（缩略图 alt 为空串，不参与 alt 断言）
    expect(screen.queryByAltText("img-1.png")).toBeNull();
    expect(screen.queryByAltText("img-2.png")).toBeNull();

    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByAltText("img-1.png")).toBeTruthy();
    expect(screen.getByAltText("img-2.png")).toBeTruthy();
  });

  test("streaming message mounts expanded", () => {
    clearUiExpansions();
    render(
      <MessageImageGallery
        images={IMAGES}
        defaultExpanded
        stateKey="msg-2:gallery-0"
      />,
    );

    expect(screen.getByAltText("img-1.png")).toBeTruthy();
    expect(screen.getByAltText("img-2.png")).toBeTruthy();
    expect(toggleRow().getAttribute("aria-expanded")).toBe("true");
  });

  test("defaults to expanded when defaultExpanded is not given", () => {
    clearUiExpansions();
    render(<MessageImageGallery images={IMAGES} />);

    expect(screen.getByAltText("img-1.png")).toBeTruthy();
  });

  test("user toggle survives remount via the session uiExpansion store", () => {
    clearUiExpansions();
    const first = render(
      <MessageImageGallery
        images={IMAGES}
        defaultExpanded
        stateKey="msg-3:gallery-1"
      />,
    );
    fireEvent.click(toggleRow()); // 用户手动收起
    expect(screen.queryByAltText("img-1.png")).toBeNull();
    first.unmount();

    render(
      <MessageImageGallery
        images={IMAGES}
        defaultExpanded
        stateKey="msg-3:gallery-1"
      />,
    );
    expect(screen.queryByAltText("img-1.png")).toBeNull();
    expect(getUiExpansion("msg-3:gallery-1")).toBe(false);
  });

  test("first-generation expansion persists across remount within the session", () => {
    clearUiExpansions();
    // 初次生成：流式挂载 → 展开，挂载时把展开态钉进会话级 store
    const first = render(
      <MessageImageGallery
        images={IMAGES}
        defaultExpanded
        stateKey="msg-4:gallery-2"
      />,
    );
    first.unmount();

    // 同一会话内流式已结束（重挂载时 defaultExpanded 翻 false）：仍保持展开，
    // 不能因为虚拟列表卸载复水就收起刚生成的图
    render(
      <MessageImageGallery
        images={IMAGES}
        defaultExpanded={false}
        stateKey="msg-4:gallery-2"
      />,
    );
    expect(screen.getByAltText("img-1.png")).toBeTruthy();
  });

  test("collapsed store entry wins over a streaming default on remount", () => {
    clearUiExpansions();
    // 用户收起过（store=false），流式默认展开也不能顶掉用户选择
    setUiExpansion("msg-5:gallery-0", false);
    render(
      <MessageImageGallery
        images={IMAGES}
        defaultExpanded
        stateKey="msg-5:gallery-0"
      />,
    );
    expect(screen.queryByAltText("img-1.png")).toBeNull();
  });
});
