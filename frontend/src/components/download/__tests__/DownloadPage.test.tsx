/** @vitest-environment jsdom */
// 站内下载页：动态跟随 /api/version 返回的最新 release 资产
// （桌面端安装包 + 独立 daemon 二进制 + 配对教程），失败兜底 GitHub Releases。
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../i18n";

// jsdom 无 IntersectionObserver：给落地页同款 reveal 动画 hook 打桩
class MockIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock("../../../services/api/version", async (importOriginal) => ({
  // buildReleaseAssetDownloadUrl 用真实实现（同源反代 URL 契约本身要被测）
  ...(await importOriginal<Record<string, unknown>>()),
  versionApi: { get: mocks.get },
}));

vi.mock("react-router-dom", () => ({
  Link: ({
    to,
    children,
    ...rest
  }: {
    to: string;
    children: React.ReactNode;
  }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
  useNavigate: () => vi.fn(),
}));

import { DownloadPage } from "../DownloadPage";

const ASSETS = [
  {
    name: "lambchat-daemon-x86_64-pc-windows-msvc.exe",
    url: "https://gh/lambchat-daemon-x86_64-pc-windows-msvc.exe",
    size: 1000,
    content_type: "x",
  },
  {
    name: "lambchat-daemon-x86_64-unknown-linux-gnu",
    url: "https://gh/lambchat-daemon-x86_64-unknown-linux-gnu",
    size: 1000,
    content_type: "x",
  },
  {
    name: "LambChat-android-v2.8.1-signed.apk",
    url: "https://gh/LambChat-android-v2.8.1-signed.apk",
    size: 5000,
    content_type: "x",
  },
  {
    name: "LambChat-v2.8.1-Linux-x86_64.AppImage",
    url: "https://gh/LambChat-v2.8.1-Linux-x86_64.AppImage",
    size: 2000,
    content_type: "x",
  },
  {
    name: "LambChat-v2.8.1-macOS.dmg",
    url: "https://gh/LambChat-v2.8.1-macOS.dmg",
    size: 3000,
    content_type: "x",
  },
  {
    name: "LambChat-v2.8.1-Windows.msi",
    url: "https://gh/LambChat-v2.8.1-Windows.msi",
    size: 4000,
    content_type: "x",
  },
];

beforeEach(async () => {
  await i18n.changeLanguage("en");
  vi.clearAllMocks();
});

test("renders desktop and daemon downloads from the latest release assets", async () => {
  mocks.get.mockResolvedValue({
    app_version: "2.8.1",
    latest_version: "2.8.1",
    release_url: "https://github.com/Yanyutin753/LambChat/releases/latest",
    release_assets: ASSETS,
  });

  render(<DownloadPage />);

  // 等待锚点必须是数据驱动内容（资产文件名）：平台卡标签（Windows/macOS）
  // 不等 versionApi 就渲染，锚在静态标签上会在数据晚到时撞进空窗
  expect(
    await screen.findByText("LambChat-v2.8.1-Windows.msi"),
  ).toBeInTheDocument();
  expect(screen.getByText("Windows")).toBeInTheDocument();
  expect(screen.getByText("macOS")).toBeInTheDocument();
  expect(screen.getByText("Linux")).toBeInTheDocument();

  // 下载直链锚点：走自托管反代（国内直连 GitHub 下载不稳），跟随最新 release
  const msi = screen.getByText("LambChat-v2.8.1-Windows.msi").closest("a");
  expect(msi).toHaveAttribute(
    "href",
    "/api/version/assets/LambChat-v2.8.1-Windows.msi/download",
  );
  const dmg = screen.getByText("LambChat-v2.8.1-macOS.dmg").closest("a");
  expect(dmg).toHaveAttribute(
    "href",
    "/api/version/assets/LambChat-v2.8.1-macOS.dmg/download",
  );

  // daemon 二进制区
  const daemon = screen
    .getByText("lambchat-daemon-x86_64-pc-windows-msvc.exe")
    .closest("a");
  expect(daemon).toHaveAttribute(
    "href",
    "/api/version/assets/lambchat-daemon-x86_64-pc-windows-msvc.exe/download",
  );

  // 教程步骤
  expect(screen.getByText("Pairing tutorial")).toBeInTheDocument();
});

test("macOS card shows the Gatekeeper first-launch note with the xattr command", async () => {
  // 未公证 ad-hoc 包被浏览器下载后 macOS 提示「已损坏」，下载页必须在
  // macOS 分区给出 xattr 解法（与 release notes 引导同一命令）
  mocks.get.mockResolvedValue({
    app_version: "2.8.1",
    release_assets: ASSETS,
  });

  render(<DownloadPage />);

  // 等数据驱动的命令本身（Gatekeeper 说明块要 links 到齐才挂载），
  // 不锚在静态平台名上（见 test 1 注释）
  expect(
    await screen.findByText(/xattr -cr \/Applications\/LambChat\.app/),
  ).toBeInTheDocument();
  // 「已损坏」说明同时出现在一键安装与 xattr 兜底两段文案里
  expect(screen.getAllByText(/damaged/i).length).toBeGreaterThanOrEqual(1);
});

test("macOS card promotes the one-line install script command", async () => {
  // curl 下载不带隔离标记，装完直接可开——无需 xattr 的推荐安装路径
  mocks.get.mockResolvedValue({
    app_version: "2.8.1",
    release_assets: ASSETS,
  });

  render(<DownloadPage />);

  // 同上：等待命令本身出现（macOS 卡的安装块随资产数据异步挂载）
  expect(
    await screen.findByText(
      /curl -fsSL https:\/\/lambchat\.com\/install\.sh \| sh/,
    ),
  ).toBeInTheDocument();
});

test("daemon section shows the login and run commands", async () => {
  mocks.get.mockResolvedValue({
    app_version: "2.8.1",
    release_assets: ASSETS,
  });

  render(<DownloadPage />);

  await screen.findByText("lambchat-daemon-x86_64-pc-windows-msvc.exe");
  expect(screen.getByText(/login --server/)).toBeInTheDocument();
  expect(
    screen.getByText(/daemon run|lambchat-daemon run/),
  ).toBeInTheDocument();
});

test("falls back to the GitHub releases page when the version API fails", async () => {
  mocks.get.mockRejectedValue(new Error("offline"));

  render(<DownloadPage />);

  const fallback = await screen.findByText(/view all releases on github/i);
  expect(fallback.closest("a")).toHaveAttribute(
    "href",
    "https://github.com/Yanyutin753/LambChat/releases/latest",
  );
});

test("hero CTA directly downloads the detected platform's installer", async () => {
  // 主流软件下载页行为：按 UA 自动选包，主按钮即直链下载
  const originalUa = window.navigator.userAgent;
  Object.defineProperty(window.navigator, "userAgent", {
    value: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    configurable: true,
  });

  mocks.get.mockResolvedValue({
    app_version: "2.8.1",
    release_assets: ASSETS,
  });

  try {
    render(<DownloadPage />);

    const direct = await screen.findByText(/Download for Windows/i);
    expect(direct.closest("a")).toHaveAttribute(
      "href",
      "/api/version/assets/LambChat-v2.8.1-Windows.msi/download",
    );
  } finally {
    Object.defineProperty(window.navigator, "userAgent", {
      value: originalUa,
      configurable: true,
    });
  }
});

test("android visitors get a direct apk download in the hero and a mobile section", async () => {
  const originalUa = window.navigator.userAgent;
  Object.defineProperty(window.navigator, "userAgent", {
    value: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36",
    configurable: true,
  });

  mocks.get.mockResolvedValue({
    app_version: "2.8.1",
    release_assets: ASSETS,
  });

  try {
    render(<DownloadPage />);

    const direct = await screen.findByText(/Download for Android/i);
    expect(direct.closest("a")).toHaveAttribute(
      "href",
      "/api/version/assets/LambChat-android-v2.8.1-signed.apk/download",
    );

    // 手机端分区：APK 行可下载
    const apkRow = await screen.findByText(
      "LambChat-android-v2.8.1-signed.apk",
    );
    expect(apkRow.closest("a")).toHaveAttribute(
      "href",
      "/api/version/assets/LambChat-android-v2.8.1-signed.apk/download",
    );
  } finally {
    Object.defineProperty(window.navigator, "userAgent", {
      value: originalUa,
      configurable: true,
    });
  }
});
