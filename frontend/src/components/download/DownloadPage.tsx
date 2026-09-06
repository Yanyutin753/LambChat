import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Monitor,
  Terminal,
  GraduationCap,
  ArrowLeft,
  Download as DownloadIcon,
  ExternalLink,
  Command,
  AppWindow,
  Cloud,
  Check,
  Smartphone,
} from "lucide-react";
import { versionApi } from "../../services/api/version";
import { useSEO } from "../../hooks/usePageTitle";
import { useScrollReveal } from "../landing/hooks/useScrollReveal";
import {
  detectDesktopPlatform,
  formatAssetSize,
  isAndroid,
  matchAndroidApk,
  matchDaemonAssets,
  matchDesktopAssets,
  pickRecommendedAsset,
  type DesktopPlatform,
} from "../../utils/releaseAssets";
import { GITHUB_URL } from "../../constants";
import { BrandLogo } from "../common/BrandLogo";
import { BrandWordmark } from "../common/BrandWordmark";
import type { VersionInfo } from "../../types";

const RELEASES_FALLBACK_URL = `${GITHUB_URL}/releases/latest`;

/** 平台分区的展示顺序：检测到的平台置顶并高亮。 */
const PLATFORM_ORDER: DesktopPlatform[] = ["windows", "macos", "linux"];

const PLATFORM_META: Record<
  DesktopPlatform,
  { icon: typeof Monitor; gradient: string }
> = {
  windows: { icon: AppWindow, gradient: "from-sky-400/90 to-blue-500/90" },
  macos: { icon: Command, gradient: "from-stone-500/90 to-stone-700/90" },
  linux: { icon: Terminal, gradient: "from-amber-400/90 to-orange-500/90" },
};

/** 扩展名类型徽章（技术感标签，免 i18n：MSI/DMG/DEB…）。 */
function extBadge(name: string): string {
  const m = name.match(/\.([A-Za-z0-9]+)$/);
  return m ? m[1].toUpperCase() : "BIN";
}

/** 资产下载行：类型徽章 + 文件名 + 大小 + 下载动作，两档层级（首包实心）。 */
function AssetRow({
  name,
  url,
  size,
  variant = "ghost",
}: {
  name: string;
  url: string;
  size?: number;
  variant?: "primary" | "ghost";
}) {
  const badge = (
    <span
      className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 font-mono text-9 font-bold tracking-wider ${
        variant === "primary"
          ? "bg-white/15 text-white/80 dark:bg-black/10 dark:text-stone-600"
          : "bg-stone-100/90 text-stone-500 dark:bg-stone-800/80 dark:text-stone-400"
      }`}
    >
      {extBadge(name)}
    </span>
  );
  if (variant === "primary") {
    return (
      <a
        href={url}
        download
        className="group inline-flex w-full items-center gap-3 rounded-2xl bg-stone-900 px-5 py-3.5 text-sm font-semibold text-white transition-all duration-300 hover:-translate-y-0.5 hover:bg-stone-800 hover:shadow-xl hover:shadow-stone-900/15 dark:bg-stone-50 dark:text-stone-900 dark:hover:bg-white dark:hover:shadow-stone-50/10 sm:text-15"
      >
        {badge}
        <span className="min-w-0 flex-1 truncate font-mono">{name}</span>
        {size != null && (
          <span className="ml-auto shrink-0 tabular-nums text-11 opacity-60">
            {formatAssetSize(size)}
          </span>
        )}
        <DownloadIcon
          size={14}
          className="shrink-0 transition-transform duration-300 group-hover:translate-y-0.5"
        />
      </a>
    );
  }
  return (
    <a
      href={url}
      download
      className="group inline-flex w-full items-center gap-3 rounded-2xl border border-stone-200/80 bg-white/55 px-4 py-3 text-sm font-medium text-stone-600 transition-all duration-300 hover:-translate-y-0.5 hover:border-stone-300 hover:shadow-lg hover:shadow-stone-200/30 dark:border-stone-700/50 dark:bg-stone-800/35 dark:text-stone-300 dark:hover:border-stone-600 dark:hover:shadow-stone-900/30 sm:text-15"
    >
      {badge}
      <span className="min-w-0 flex-1 truncate font-mono text-stone-700 dark:text-stone-200">
        {name}
      </span>
      {size != null && (
        <span className="ml-auto shrink-0 tabular-nums text-11 text-stone-400 dark:text-stone-500">
          {formatAssetSize(size)}
        </span>
      )}
      <DownloadIcon
        size={14}
        className="shrink-0 text-stone-400 transition-transform duration-300 group-hover:translate-y-0.5 dark:text-stone-500"
      />
    </a>
  );
}

function SectionDivider() {
  return (
    <div className="blog-section-divider py-2" aria-hidden="true">
      <div className="blog-ornament-diamond" />
    </div>
  );
}

/** 下载页专属大号分区标题（结构同落地页 SectionHeading，字号上调一档）。 */
function SectionHeadingXL({
  label,
  title,
  description,
}: {
  label: string;
  title: string;
  description: string;
}) {
  return (
    <div data-reveal className="mb-14 px-2 text-center sm:mb-18 lg:mb-20">
      <div className="mb-6 flex items-center justify-center gap-3 sm:mb-7">
        <span className="block h-px w-8 bg-gradient-to-r from-transparent to-stone-300/40 dark:to-stone-600/25" />
        <span className="text-11 font-bold uppercase tracking-[0.16em] text-stone-400 dark:text-stone-500 sm:text-13">
          {label}
        </span>
        <span className="block h-px w-8 bg-gradient-to-l from-transparent to-stone-300/40 dark:to-stone-600/25" />
      </div>
      <h2 className="mb-5 bg-gradient-to-b from-stone-900 via-stone-800 to-stone-600 bg-clip-text text-[1.9rem] font-extrabold font-serif leading-[1.15] tracking-[-0.025em] text-transparent dark:from-stone-50 dark:via-stone-200 dark:to-stone-400 sm:text-4xl lg:text-[2.6rem]">
        {title}
      </h2>
      <p className="blog-prose mx-auto max-w-md text-15 leading-[1.8] text-stone-400 dark:text-stone-500 sm:max-w-lg sm:text-base lg:text-17">
        {description}
      </p>
    </div>
  );
}

/**
 * 站内下载页（公开路由）：本地沙箱的安装包下载 + 配对教程。
 * 视觉完全复刻落地页（blog-* 类 + SectionHeading + Hero/CTA 结构）。
 *
 * 下载地址来自 `/api/version` 返回的最新 GitHub release 资产——发新版后
 * 链接自动跟随，无需在前端维护版本号；拉取失败兜底 GitHub Releases 页。
 */
export function DownloadPage() {
  const { t } = useTranslation();
  const [scrolled, setScrolled] = useState(false);
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const [failed, setFailed] = useState(false);
  // 重扫依赖：资产数据到达后条件渲染的分区（daemon 终端/二进制、失败兜底卡）
  // 才会挂载，必须重跑 observer 否则永远停在 reveal 隐藏态
  const containerRef = useScrollReveal([info, failed]);

  useSEO({
    title: "seo.download.title",
    // 描述复用 download.description（不另立 seo 拷贝，省五语重复字节）
    description: "download.description",
    path: "/download",
    noindex: true,
  });

  // 落地页同款：放开全局滚动锁（聊天界面默认禁滚）
  useEffect(() => {
    document.documentElement.classList.add("allow-scroll");
    return () => document.documentElement.classList.remove("allow-scroll");
  }, []);

  useEffect(() => {
    const h = () => setScrolled(window.scrollY > 10);
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, []);

  useEffect(() => {
    versionApi
      .get()
      .then((res) => setInfo(res))
      .catch(() => setFailed(true));
  }, []);

  const assets = useMemo(() => info?.release_assets ?? [], [info]);
  const desktop = useMemo(() => matchDesktopAssets(assets), [assets]);
  const daemons = useMemo(() => matchDaemonAssets(assets), [assets]);
  const detected =
    typeof navigator !== "undefined"
      ? detectDesktopPlatform(navigator.userAgent)
      : null;
  // 检测到的平台置顶（其余保持稳定顺序）
  const platformOrder = detected
    ? [detected, ...PLATFORM_ORDER.filter((p) => p !== detected)]
    : PLATFORM_ORDER;

  const platformLabel = (p: DesktopPlatform) =>
    t(`profile.localSandbox.platform.${p}`);

  const hasDesktopAssets =
    desktop.windows.length + desktop.macos.length + desktop.linux.length > 0;

  // 主推直链：Android 手机直下 APK；桌面按检测平台选首选安装包
  const apk = useMemo(() => matchAndroidApk(assets), [assets]);
  const android =
    typeof navigator !== "undefined" && isAndroid(navigator.userAgent);
  const recommended = detected ? pickRecommendedAsset(desktop, detected) : null;

  const daemonCommands = [
    "chmod +x lambchat-daemon-*",
    "./lambchat-daemon login --server https://your-lambchat-server",
    "./lambchat-daemon run",
  ];

  return (
    <div
      ref={containerRef}
      className="blog-landing-container font-serif relative bg-white dark:bg-stone-950 antialiased"
    >
      {/* 导航栏：同落地页（fixed h-14 + 滚动投影） */}
      <nav
        className={`safe-area-top fixed inset-x-0 top-0 z-50 border-b border-stone-100/60 bg-white/85 transition-shadow duration-300 dark:border-stone-800/40 dark:bg-stone-950/85 ${
          scrolled ? "blog-nav-scrolled" : ""
        }`}
      >
        <div className="mx-auto flex h-14 max-w-full items-center justify-between px-4 sm:px-8">
          <Link
            to="/"
            className="group flex cursor-pointer items-center gap-1.5"
            aria-label="LambChat"
          >
            <BrandLogo className="size-8 transition-transform duration-300 group-hover:scale-105" />
            <BrandWordmark
              decorative
              className="h-8 w-auto text-stone-900 dark:text-stone-100"
            />
          </Link>
          <Link
            to="/chat"
            className="inline-flex items-center gap-1.5 rounded-full border border-stone-200/80 bg-white/55 px-4 py-2 text-sm font-medium text-stone-600 transition-all duration-300 hover:-translate-y-0.5 hover:border-stone-300 hover:shadow-md hover:shadow-stone-200/30 dark:border-stone-700/50 dark:bg-stone-800/35 dark:text-stone-300 dark:hover:border-stone-600 dark:hover:shadow-stone-900/30"
          >
            <ArrowLeft size={13} />
            {t("download.back")}
          </Link>
        </div>
      </nav>

      {/* Hero */}
      <section className="blog-hero relative flex min-h-[100svh] min-h-[100dvh] flex-col items-center justify-center overflow-hidden px-4 pb-20 pt-[calc(5rem+var(--app-safe-area-top,0px))] text-center sm:px-6 sm:pt-28">
        {/* Atmospheric background */}
        <div
          className="pointer-events-none absolute inset-0 -z-10"
          aria-hidden="true"
        >
          <div className="blog-crosshatch absolute inset-0" />
          <div className="absolute left-1/2 top-0 h-[600px] w-[900px] -translate-x-1/2 bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.08)_0%,rgba(251,146,60,0.04)_40%,transparent_70%)] dark:bg-[radial-gradient(ellipse_at_center,rgba(251,191,36,0.06)_0%,rgba(251,146,60,0.03)_40%,transparent_70%)]" />
          <div className="absolute left-[10%] top-[40%] h-[400px] w-[400px] bg-[radial-gradient(circle,rgba(56,189,248,0.06)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(56,189,248,0.04)_0%,transparent_60%)]" />
          <div className="absolute bottom-[10%] right-[15%] h-[300px] w-[300px] bg-[radial-gradient(circle,rgba(168,85,247,0.04)_0%,transparent_60%)] dark:bg-[radial-gradient(circle,rgba(168,85,247,0.03)_0%,transparent_60%)]" />
        </div>

        <div className="relative mx-auto w-full max-w-[22rem] sm:max-w-4xl lg:max-w-5xl">
          {/* Editorial tag */}
          <div
            data-reveal
            className="mb-8 flex items-center justify-center gap-2.5 sm:mb-12 sm:gap-3"
          >
            <span className="block h-px w-6 bg-gradient-to-r from-transparent to-stone-300 dark:to-stone-600 sm:w-8" />
            <span className="relative text-11 font-semibold uppercase tracking-[0.16em] text-stone-400 dark:text-stone-500 sm:text-13 sm:tracking-[0.18em]">
              {t("download.tag")}
              <span className="absolute -top-1.5 -right-2.5 h-1.5 w-1.5 rounded-full bg-emerald-400" />
            </span>
            <span className="block h-px w-6 bg-gradient-to-l from-transparent to-stone-300 dark:to-stone-600 sm:w-8" />
          </div>

          {/* Title */}
          <h1
            data-reveal
            data-reveal-delay="1"
            className="mb-7 bg-gradient-to-b from-stone-900 via-stone-800 to-stone-600 bg-clip-text text-[2.35rem] font-extrabold leading-[1.15] tracking-[-0.025em] text-transparent dark:from-stone-50 dark:via-stone-200 dark:to-stone-400 sm:mb-10 sm:text-[3.1rem] lg:text-[3.4rem]"
          >
            {t("download.title")}
          </h1>

          {/* Description */}
          <p
            data-reveal
            data-reveal-delay="2"
            className="blog-prose mx-auto mb-11 max-w-[20rem] text-base leading-[1.8] text-stone-500 dark:text-stone-400 sm:mb-16 sm:max-w-xl sm:text-xl lg:text-[1.4rem] sm:leading-[1.85]"
          >
            {t("download.description")}
          </p>

          {/* CTAs */}
          {failed && !hasDesktopAssets ? (
            <div
              data-reveal
              data-reveal-delay="3"
              className="blog-feature-card blog-glass-inner-glow mx-auto max-w-md rounded-2xl border border-stone-100/80 bg-white/80 p-6 dark:border-stone-800/40 dark:bg-stone-900/40"
            >
              <p className="mb-3 text-sm leading-relaxed text-stone-500 dark:text-stone-400">
                {t("download.loadFailed")}
              </p>
              <a
                href={RELEASES_FALLBACK_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-15 font-semibold text-amber-600 transition-colors hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300"
                data-download-fallback
              >
                {t("download.viewAllReleases")}
                <ExternalLink size={13} />
              </a>
            </div>
          ) : (
            <div
              data-reveal
              data-reveal-delay="3"
              className="mx-auto flex max-w-[19rem] flex-col items-center justify-center gap-3.5 sm:max-w-none sm:flex-row sm:gap-4"
            >
              {android && apk ? (
                <a
                  href={apk.url}
                  download
                  data-hero-direct-download
                  className="blog-btn-primary group inline-flex min-h-12 w-full items-center justify-center gap-2.5 rounded-full bg-stone-900 px-8 py-4 text-sm font-semibold text-white transition-all duration-300 hover:-translate-y-0.5 hover:bg-stone-800 hover:shadow-xl hover:shadow-stone-900/15 active:translate-y-0 dark:bg-stone-50 dark:text-stone-900 dark:hover:bg-white dark:hover:shadow-stone-50/10 sm:w-auto sm:px-9"
                >
                  <DownloadIcon
                    size={15}
                    className="transition-transform duration-300 group-hover:translate-y-0.5"
                  />
                  {t("download.downloadFor", { platform: "Android" })}
                </a>
              ) : recommended && detected ? (
                <a
                  href={recommended.url}
                  download
                  data-hero-direct-download
                  className="blog-btn-primary group inline-flex min-h-12 w-full items-center justify-center gap-2.5 rounded-full bg-stone-900 px-8 py-4 text-sm font-semibold text-white transition-all duration-300 hover:-translate-y-0.5 hover:bg-stone-800 hover:shadow-xl hover:shadow-stone-900/15 active:translate-y-0 dark:bg-stone-50 dark:text-stone-900 dark:hover:bg-white dark:hover:shadow-stone-50/10 sm:w-auto sm:px-9"
                >
                  <DownloadIcon
                    size={15}
                    className="transition-transform duration-300 group-hover:translate-y-0.5"
                  />
                  {t("download.downloadFor", {
                    platform: platformLabel(detected),
                  })}
                </a>
              ) : (
                <a
                  href="#desktop"
                  className="blog-btn-primary group inline-flex min-h-12 w-full items-center justify-center gap-2.5 rounded-full bg-stone-900 px-8 py-4 text-sm font-semibold text-white transition-all duration-300 hover:-translate-y-0.5 hover:bg-stone-800 hover:shadow-xl hover:shadow-stone-900/12 active:translate-y-0 dark:bg-stone-50 dark:text-stone-900 dark:hover:bg-white dark:hover:shadow-stone-50/10 sm:w-auto sm:px-9"
                >
                  <DownloadIcon size={15} />
                  {t("download.heroCta")}
                </a>
              )}
              <a
                href="#tutorial"
                className="blog-btn-ghost group inline-flex min-h-12 w-full items-center justify-center gap-2.5 rounded-full border border-stone-200/80 bg-white/55 px-8 py-4 text-sm font-medium text-stone-600 transition-all duration-300 hover:-translate-y-0.5 hover:border-stone-300 hover:shadow-lg hover:shadow-stone-200/30 active:translate-y-0 dark:border-stone-700/50 dark:bg-stone-800/35 dark:text-stone-300 dark:hover:border-stone-600 dark:hover:shadow-stone-900/30 sm:w-auto sm:px-9"
              >
                <GraduationCap size={15} />
                {t("download.heroCtaTutorial")}
              </a>
            </div>
          )}

          {/* 版本信息行（同落地页 Hero 底部 tech-stack 行） */}
          {!failed && (
            <div
              data-reveal
              data-reveal-delay="4"
              className="mt-12 border-t border-stone-200/40 pt-6 dark:border-stone-800/30 sm:mt-20 sm:pt-8"
            >
              <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2.5">
                {info?.latest_version && (
                  <span className="blog-tech-pill inline-flex items-center gap-2 rounded-full border border-stone-100/60 bg-white/70 px-3.5 py-1.5 text-xs font-medium text-stone-500 dark:border-stone-700/20 dark:bg-stone-900/50 dark:text-stone-400 sm:text-13">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    {t("download.latestVersion", {
                      version: info.latest_version,
                    })}
                  </span>
                )}
                <a
                  href={RELEASES_FALLBACK_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-11 font-semibold uppercase tracking-[0.14em] text-stone-400 transition-colors hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 sm:text-13"
                >
                  <ExternalLink size={11} />
                  {t("download.viewAllReleases")}
                </a>
              </div>
            </div>
          )}
        </div>
      </section>

      <SectionDivider />

      {/* 桌面端：Bento——检测平台大卡 + 其余平台紧凑卡 */}
      <section
        id="desktop"
        className="blog-mesh-features relative scroll-mt-14 py-20 sm:py-28 lg:py-36"
      >
        <div className="mx-auto max-w-5xl px-5 sm:px-6 lg:max-w-6xl xl:max-w-7xl">
          <SectionHeadingXL
            label={t("download.tag")}
            title={t("download.desktop.title")}
            description={t("download.desktop.desc")}
          />
          <div className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-3">
            {platformOrder.map((platform, idx) => {
              const links = desktop[platform];
              const meta = PLATFORM_META[platform];
              const Icon = meta.icon;
              const isDetected = platform === detected;
              const featured = idx === 0;
              if (featured) {
                // 大卡：主推直下（实心）+ 全部变体（双列）
                return (
                  <div
                    key={platform}
                    data-reveal
                    className={`blog-feature-card blog-glass-inner-glow group relative rounded-3xl border p-7 transition-all duration-500 hover:-translate-y-1.5 sm:p-8 lg:col-span-2 lg:row-span-2 ${
                      isDetected
                        ? "border-amber-200/90 bg-amber-50/60 dark:border-amber-500/25 dark:bg-amber-500/[0.06]"
                        : "border-stone-100/80 bg-white/80 dark:border-stone-800/40 dark:bg-stone-900/40"
                    }`}
                  >
                    <div
                      className={`absolute left-7 top-0 h-[2px] w-10 rounded-full bg-gradient-to-r opacity-60 transition-all duration-500 group-hover:w-16 sm:left-8 ${
                        isDetected
                          ? "from-amber-300 to-orange-400"
                          : meta.gradient
                      }`}
                    />
                    <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3.5">
                        <span
                          className={`flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br text-xl text-white shadow-md transition-all duration-500 group-hover:rotate-3 group-hover:scale-110 ${meta.gradient}`}
                        >
                          <Icon size={20} />
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xl font-bold text-stone-900 dark:text-stone-100">
                              {platformLabel(platform)}
                            </span>
                            {isDetected && (
                              <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100/90 px-2.5 py-1 text-10 font-semibold text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                                <span className="h-1 w-1 rounded-full bg-amber-500" />
                                {t("download.detectedPlatform")}
                              </span>
                            )}
                          </div>
                          {links[0] && (
                            <p className="mt-0.5 truncate font-mono text-11 tabular-nums text-stone-400 dark:text-stone-500">
                              {links[0].name}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="space-y-2.5">
                      {links.length > 0 ? (
                        <>
                          <AssetRow {...links[0]} variant="primary" />
                          {links.length > 1 && (
                            <div className="grid grid-cols-1 gap-2.5 pt-1 sm:grid-cols-2">
                              {links.slice(1).map((link) => (
                                <AssetRow key={link.url} {...link} />
                              ))}
                            </div>
                          )}
                        </>
                      ) : (
                        <p className="text-sm text-stone-400 dark:text-stone-500">
                          {t("download.noAssets")}
                        </p>
                      )}
                    </div>
                  </div>
                );
              }
              // 紧凑卡：图标 + 平台名 + 首包实心行 + 其余小行
              return (
                <div
                  key={platform}
                  data-reveal
                  data-reveal-delay={String(idx)}
                  className="blog-feature-card blog-glass-inner-glow group relative rounded-3xl border border-stone-100/80 bg-white/80 p-6 transition-all duration-500 hover:-translate-y-1.5 dark:border-stone-800/40 dark:bg-stone-900/40 sm:p-7"
                >
                  <div
                    className={`absolute left-6 top-0 h-[2px] w-8 rounded-full bg-gradient-to-r opacity-50 transition-all duration-500 group-hover:w-12 group-hover:opacity-90 sm:left-7 ${meta.gradient}`}
                  />
                  <div className="mb-4 flex items-center gap-3">
                    <span
                      className={`flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br text-base text-white shadow-sm transition-all duration-500 group-hover:rotate-3 group-hover:scale-110 ${meta.gradient}`}
                    >
                      <Icon size={16} />
                    </span>
                    <span className="text-base font-bold text-stone-900 dark:text-stone-100 sm:text-17">
                      {platformLabel(platform)}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {links.length > 0 ? (
                      links.map((link, i) => (
                        <AssetRow
                          key={link.url}
                          {...link}
                          variant={i === 0 ? "primary" : "ghost"}
                        />
                      ))
                    ) : (
                      <p className="text-xs text-stone-400 dark:text-stone-500">
                        {t("download.noAssets")}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* 手机端：Android 原生应用（APK 直装） */}
      {apk && (
        <section
          id="mobile"
          className="blog-mesh-interface relative scroll-mt-14 bg-stone-50/50 py-20 dark:bg-stone-900/15 sm:py-28"
        >
          <div className="mx-auto max-w-5xl px-5 sm:px-6 lg:max-w-6xl xl:max-w-7xl">
            <SectionHeadingXL
              label={t("download.tag")}
              title={t("download.mobile.title")}
              description={t("download.mobile.desc")}
            />
            <div
              data-reveal
              className="blog-feature-card blog-glass-inner-glow group relative mx-auto max-w-xl rounded-3xl border border-stone-100/80 bg-white/80 p-6 transition-all duration-500 hover:-translate-y-1.5 dark:border-stone-800/40 dark:bg-stone-900/40 sm:p-7"
            >
              <div className="absolute left-6 top-0 h-[2px] w-10 rounded-full bg-gradient-to-r from-emerald-400/80 to-teal-500/80 opacity-60 transition-all duration-500 group-hover:w-16 sm:left-7" />
              <div className="mb-5 flex items-center gap-3.5">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400/90 to-teal-500/90 text-xl text-white shadow-md transition-all duration-500 group-hover:rotate-3 group-hover:scale-110">
                  <Smartphone size={20} />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-bold text-stone-900 dark:text-stone-100 sm:text-xl">
                      Android
                    </span>
                    <span className="rounded-full bg-emerald-100/90 px-2.5 py-1 text-10 font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 sm:text-11">
                      APK
                    </span>
                  </div>
                  {info?.latest_version && (
                    <p className="mt-0.5 truncate font-mono text-11 tabular-nums text-stone-400 dark:text-stone-500">
                      v{info.latest_version}
                    </p>
                  )}
                </div>
              </div>
              <AssetRow {...apk} variant="primary" />
            </div>
          </div>
        </section>
      )}

      <SectionDivider />

      {/* 独立 daemon：全宽终端 + 四列二进制 */}
      <section
        id="daemon"
        className="blog-mesh-architecture relative scroll-mt-14 py-20 sm:py-28 lg:py-36"
      >
        <div className="mx-auto max-w-5xl px-5 sm:px-6 lg:max-w-6xl xl:max-w-7xl">
          <SectionHeadingXL
            label={t("download.tag")}
            title={t("download.daemon.title")}
            description={t("download.daemon.desc")}
          />
          {daemons.length > 0 ? (
            <div className="space-y-5 sm:space-y-6">
              {/* 终端三步（全宽）：命令 + 模拟成功输出 */}
              <div
                data-reveal
                className="blog-feature-card group relative overflow-hidden rounded-2xl border border-stone-200/70 bg-stone-900 shadow-lg shadow-stone-900/10 transition-all duration-500 hover:-translate-y-1.5 dark:border-stone-800/60 dark:bg-black/50"
              >
                <div className="flex items-center gap-2 border-b border-white/10 px-6 py-4">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
                  <span className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
                  <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
                  <span className="ml-3 font-mono text-13 text-stone-400">
                    lambchat-daemon
                  </span>
                </div>
                <div className="space-y-4 px-6 py-6 sm:px-8 sm:py-7">
                  {daemonCommands.map((cmd) => (
                    <p
                      key={cmd}
                      className="overflow-x-auto font-mono text-sm leading-relaxed whitespace-nowrap text-stone-200 sm:text-15"
                    >
                      <span className="select-none text-emerald-400/80">
                        ${" "}
                      </span>
                      {cmd}
                    </p>
                  ))}
                  <p className="flex items-center gap-2 border-t border-white/10 pt-4 font-mono text-xs text-emerald-400/90 sm:text-13">
                    <Check size={13} />
                    paired · daemon online
                  </p>
                </div>
              </div>

              {/* 二进制下载：四列紧凑行 */}
              {/* 二进制下载：说明 + 四列紧凑行 */}
              <div data-reveal data-reveal-delay="2" className="space-y-3">
                <p className="text-center text-13 leading-relaxed text-stone-400 dark:text-stone-500 sm:text-sm">
                  {t("download.daemon.usage")}
                </p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {daemons.map((link) => (
                    <AssetRow key={link.url} {...link} />
                  ))}
                </div>
              </div>
            </div>
          ) : (
            !failed && (
              <p className="text-center text-sm text-stone-400 dark:text-stone-500">
                {t("download.noAssets")}
              </p>
            )
          )}
        </div>
      </section>

      <SectionDivider />

      {/* 配对教程：左竖向时间线 + 右产品截图（同落地页截图卡语言） */}
      <section
        id="tutorial"
        className="blog-mesh-dashboard relative scroll-mt-14 py-20 sm:py-28 lg:py-36"
      >
        <div className="mx-auto max-w-5xl px-5 sm:px-6 lg:max-w-6xl xl:max-w-7xl">
          <SectionHeadingXL
            label={t("download.tag")}
            title={t("download.tutorial.title")}
            description={t("download.description")}
          />
          <div className="grid grid-cols-1 items-center gap-8 lg:grid-cols-2 lg:gap-12">
            {/* 竖向步骤时间线 */}
            <ol className="relative space-y-5">
              <div
                className="absolute bottom-6 left-[1.4rem] top-6 w-px bg-gradient-to-b from-amber-300/50 via-stone-200 to-transparent dark:via-stone-700/60 sm:left-[1.55rem]"
                aria-hidden="true"
              />
              {(["step1", "step2", "step3"] as const).map((key, idx) => (
                <li
                  key={key}
                  data-reveal
                  data-reveal-delay={String(idx + 1)}
                  className="blog-feature-card group relative flex gap-4 rounded-2xl border border-stone-100/80 bg-white/80 p-5 transition-all duration-500 hover:-translate-y-1 hover:bg-white dark:border-stone-800/40 dark:bg-stone-900/40 dark:hover:bg-stone-900/60 sm:p-6"
                >
                  <span className="z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-400/90 to-orange-500/90 text-base text-white shadow-md transition-all duration-500 group-hover:rotate-3 group-hover:scale-110 sm:h-12 sm:w-12">
                    {idx === 0 ? (
                      <DownloadIcon size={18} />
                    ) : idx === 1 ? (
                      <Monitor size={18} />
                    ) : (
                      <GraduationCap size={18} />
                    )}
                  </span>
                  <div className="min-w-0 pt-1">
                    <span className="mb-1 block text-10 font-bold uppercase tracking-[0.14em] text-amber-600/80 dark:text-amber-400/70">
                      {String(idx + 1).padStart(2, "0")}
                    </span>
                    <p className="text-sm leading-[1.75] text-stone-600 dark:text-stone-300 sm:text-15">
                      {t(`download.tutorial.${key}`)}
                    </p>
                  </div>
                </li>
              ))}
            </ol>

            {/* div 渲染的设置页 UI 模拟窗（对应步骤 02 的「确认在线」） */}
            <div
              data-reveal
              data-reveal-delay="2"
              className="blog-screenshot-card group relative overflow-hidden rounded-2xl bg-white/80 shadow-xl shadow-stone-200/40 transition-all duration-500 hover:-translate-y-1.5 dark:bg-stone-900/40 dark:shadow-black/20"
            >
              {/* 窗口栏 */}
              <div className="flex items-center gap-2 border-b border-stone-100/70 bg-stone-50/80 px-4 py-3 dark:border-stone-800/40 dark:bg-stone-900/60">
                <span className="h-2.5 w-2.5 rounded-full bg-red-400/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-amber-400/80" />
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-400/80" />
                <span className="mx-auto rounded-full bg-stone-200/60 px-3 py-0.5 text-10 font-medium text-stone-400 dark:bg-stone-800 dark:text-stone-500 sm:text-11">
                  {t("profile.preferences")} · {t("profile.sandbox")}
                </span>
              </div>

              <div className="space-y-3 p-4 sm:p-5">
                {/* 云端沙箱行 */}
                <div className="flex items-center gap-3 rounded-xl border border-stone-100/80 bg-stone-50/60 px-4 py-3 dark:border-stone-800/50 dark:bg-stone-800/30">
                  <Cloud size={15} className="shrink-0 text-stone-400" />
                  <span className="min-w-0 truncate text-13 font-medium text-stone-700 dark:text-stone-200 sm:text-sm">
                    {t("profile.cloudSandbox")}
                  </span>
                  <span className="ml-auto shrink-0 whitespace-nowrap rounded-full border border-stone-200/80 px-2.5 py-1 text-10 text-stone-400 dark:border-stone-700/60 dark:text-stone-500 sm:px-3 sm:text-11">
                    {t("profile.localSandbox.policyOptions.none")}
                  </span>
                </div>

                {/* 本地沙箱行（在线高亮） */}
                <div className="relative flex items-center gap-3 overflow-hidden rounded-xl border border-amber-200/90 bg-amber-50/70 px-4 py-3 dark:border-amber-500/25 dark:bg-amber-500/[0.07]">
                  <div className="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-amber-300 to-orange-400" />
                  <Monitor
                    size={15}
                    className="shrink-0 text-amber-600/90 dark:text-amber-400/90"
                  />
                  <span className="shrink-0 text-13 font-semibold text-stone-800 dark:text-stone-100 sm:text-sm">
                    {t("profile.localSandbox.title")}
                  </span>
                  <span className="flex min-w-0 shrink items-center gap-1.5 text-11 text-stone-500 dark:text-stone-400 sm:text-xs">
                    <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                    {t("profile.localSandbox.statusOnline")}
                    <span className="truncate font-mono text-10 opacity-70 sm:text-11">
                      {t("profile.localSandbox.version", { version: "0.3.0" })}
                    </span>
                  </span>
                  <span className="ml-auto hidden text-10 text-stone-400 dark:text-stone-500 sm:block sm:text-11">
                    {t("profile.localSandbox.webManaged")}
                  </span>
                </div>

                {/* 会话沙箱档位切换条 */}
                <div className="flex items-center gap-2 rounded-xl border border-stone-100/80 bg-stone-50/60 px-4 py-3 dark:border-stone-800/50 dark:bg-stone-800/30">
                  <span className="shrink-0 text-10 font-semibold uppercase tracking-[0.12em] text-stone-400 dark:text-stone-500 sm:text-11">
                    {t("agentOptions.sandbox.label")}
                  </span>
                  <span className="ml-auto flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-stone-200/80 px-2.5 py-1 text-11 text-stone-500 dark:border-stone-700/60 dark:text-stone-400 sm:px-3 sm:text-xs">
                    {t("agentOptions.sandbox.options.cloud")}
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-stone-900 px-3 py-1 text-11 font-semibold text-white dark:bg-stone-50 dark:text-stone-900 sm:px-3.5 sm:text-xs">
                    <Check size={11} />
                    {t("agentOptions.sandbox.options.local")}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 结尾 CTA：同落地页 CTASection 语言 */}
      {!failed && (
        <section className="blog-mesh-cta relative overflow-hidden py-20 sm:py-28">
          <div
            className="pointer-events-none absolute inset-0"
            aria-hidden="true"
          >
            <div className="absolute left-1/2 top-1/2 h-[400px] w-[700px] -translate-x-1/2 -translate-y-1/2 bg-[radial-gradient(ellipse,rgba(251,191,36,0.08)_0%,rgba(232,121,249,0.04)_30%,transparent_65%)] dark:bg-[radial-gradient(ellipse,rgba(251,191,36,0.06)_0%,rgba(232,121,249,0.03)_30%,transparent_65%)]" />
          </div>
          <div className="relative mx-auto max-w-2xl px-5 text-center sm:px-6 lg:max-w-3xl">
            <div
              data-reveal
              className="mb-10 flex items-center justify-center gap-3 sm:mb-12"
            >
              <div className="h-px w-20 bg-gradient-to-r from-transparent via-amber-400/20 to-stone-300/50 dark:via-amber-500/15 dark:to-stone-600/30 sm:w-28" />
              <div className="blog-ornament-diamond" />
              <div className="h-px w-20 bg-gradient-to-l from-transparent via-sky-400/15 to-stone-300/50 dark:via-sky-500/10 dark:to-stone-600/30 sm:w-28" />
            </div>
            <a
              data-reveal
              data-reveal-delay="1"
              href={RELEASES_FALLBACK_URL}
              target="_blank"
              rel="noreferrer"
              className="blog-btn-ghost group inline-flex min-h-12 items-center justify-center gap-2.5 rounded-full border border-stone-200/80 bg-white/50 px-8 py-4 text-sm font-medium text-stone-600 transition-all duration-300 hover:-translate-y-0.5 hover:border-stone-300 hover:shadow-lg hover:shadow-stone-200/30 active:translate-y-0 dark:border-stone-700/50 dark:bg-stone-800/30 dark:text-stone-300 dark:hover:border-stone-600 dark:hover:shadow-stone-900/30 sm:px-9"
            >
              <ExternalLink size={14} />
              {t("download.viewAllReleases")}
            </a>
          </div>
        </section>
      )}
    </div>
  );
}

export default DownloadPage;
