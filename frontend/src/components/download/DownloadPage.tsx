import "./download.css";
import { UpdateChannelSelect } from "../update/UpdateChannelSelect";
import { useUpdateChannel } from "../../utils/updateChannel";
import { InteractiveIcon } from "../common/InteractiveIcon";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useTheme } from "../../contexts/ThemeContext";
import {
  Monitor,
  Terminal,
  GraduationCap,
  ArrowLeft,
  Download as DownloadIcon,
  ExternalLink,
  Command,
  AppWindow,
  ShieldAlert,
  Cloud,
  Check,
  Smartphone,
} from "lucide-react";
import {
  buildReleaseAssetDownloadUrl,
  versionApi,
} from "../../services/api/version";
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
import { ThemeToggle } from "../common/ThemeToggle";
import { LanguageToggle } from "../common/LanguageToggle";
import { BrandLogo } from "../common/BrandLogo";
import { BrandWordmark } from "../common/BrandWordmark";
import type { VersionInfo } from "../../types";

/** 平台分区的展示顺序：检测到的平台置顶并高亮。 */
const PLATFORM_ORDER: DesktopPlatform[] = ["windows", "macos", "linux"];

const PLATFORM_ICONS: Record<DesktopPlatform, typeof Monitor> = {
  windows: AppWindow,
  macos: Command,
  linux: Terminal,
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
  return (
    <a
      href={url}
      download
      className={`download-asset download-asset--${variant}`}
    >
      <span className="download-asset-type">{extBadge(name)}</span>
      <span className="download-asset-name">{name}</span>
      {size != null && (
        <span className="download-asset-size">{formatAssetSize(size)}</span>
      )}
      <InteractiveIcon>
        <DownloadIcon size={14} className="shrink-0" />
      </InteractiveIcon>
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

/**
 * macOS 首启引导：一键安装为推荐路径——curl 下载不带隔离标记，装完直接
 * 可用；浏览器下载的未公证 ad-hoc 包带隔离标记，Gatekeeper 会提示
 * 「已损坏」，xattr 清除隔离是开源分发标准兜底解法（与 Release Notes 同命令）。
 */
function MacGatekeeperNote() {
  const { t } = useTranslation();
  return (
    <div className="download-install-notes">
      <div className="download-install-note">
        <h3>
          <Terminal size={14} />
          {t("download.macInstall.title")}
        </h3>
        <p>{t("download.macInstall.body")}</p>
        <pre>
          <code>curl -fsSL https://lambchat.com/install.sh | sh</code>
        </pre>
      </div>
      <div className="download-install-note">
        <h3>
          <ShieldAlert size={14} />
          {t("download.macGatekeeper.title")}
        </h3>
        <p>{t("download.macGatekeeper.body")}</p>
        <pre>
          <code>xattr -cr /Applications/LambChat.app</code>
        </pre>
      </div>
    </div>
  );
}

/** 下载页分区标题沿用公开页面的排版。 */
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
    <div data-reveal className="public-section-heading">
      <div>
        <p className="public-eyebrow">{label}</p>
        <h2 className="font-serif">{title}</h2>
      </div>
      <p className="blog-prose">{description}</p>
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
  const { theme } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [info, setInfo] = useState<VersionInfo | null>(null);
  const { channel } = useUpdateChannel();
  const releasesFallbackUrl = `${GITHUB_URL}/releases${
    channel === "dev" ? "" : "/latest"
  }`;
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
    let active = true;
    setInfo(null);
    setFailed(false);
    versionApi
      .get(undefined, channel)
      .then((res) => {
        if (active) setInfo(res);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [channel]);

  // 下载链接一律走自托管反代：/api/version 返回的 browser_download_url 是
  // GitHub 直链，国内用户直连下载不稳；反代按资产名在最新 release 中查找
  // （页面资产本就来自最新 release），移动端更新下载同一契约
  const assets = useMemo(
    () =>
      (info?.release_assets ?? []).map((a) => ({
        ...a,
        url: buildReleaseAssetDownloadUrl(
          a.name,
          undefined,
          info?.latest_version ?? undefined,
        ),
      })),
    [info],
  );
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
      className="blog-landing-container public-download font-serif relative bg-white dark:bg-stone-950 antialiased"
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
          <div className="public-nav-actions flex items-center gap-2">
            <LanguageToggle />
            <ThemeToggle />
            <Link
              to="/chat"
              aria-label={t("download.back")}
              className="download-back-link"
            >
              <InteractiveIcon>
                <ArrowLeft size={13} />
              </InteractiveIcon>
              <span className="hidden sm:inline">{t("download.back")}</span>
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="public-brand-hero download-hero">
        <div className="download-hero-copy">
          <p data-reveal className="public-eyebrow download-eyebrow">
            {t("download.tag")}
          </p>

          {/* Title */}
          <h1 data-reveal data-reveal-delay="1" className="download-title">
            {t("download.title")}
          </h1>

          {/* Description */}
          <p
            data-reveal
            data-reveal-delay="2"
            className="blog-prose download-description"
          >
            {t("download.description")}
          </p>

          <div className="download-channel-row">
            <UpdateChannelSelect />
          </div>

          {/* CTAs */}
          {failed && !hasDesktopAssets ? (
            <div
              data-reveal
              data-reveal-delay="3"
              className="blog-feature-card blog-glass-inner-glow mx-auto max-w-md rounded-2xl border border-stone-100/80 bg-white/80 p-6 dark:border-stone-800/40 dark:bg-stone-900/40"
            >
              <p className="mb-3 text-14 leading-relaxed text-theme-text-secondary dark:text-theme-text-secondary">
                {t("download.loadFailed")}
              </p>
              <a
                href={releasesFallbackUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-15 font-semibold text-amber-600 transition-colors hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300"
                data-download-fallback
              >
                {t("download.viewAllReleases")}
                <InteractiveIcon>
                  <ExternalLink size={13} />
                </InteractiveIcon>
              </a>
            </div>
          ) : (
            <div
              data-reveal
              data-reveal-delay="3"
              className="download-hero-actions"
            >
              {android && apk ? (
                <a
                  href={apk.url}
                  download
                  data-hero-direct-download
                  className="download-action download-action-primary"
                >
                  <InteractiveIcon>
                    <DownloadIcon size={15} />
                  </InteractiveIcon>
                  {t("download.downloadFor", { platform: "Android" })}
                </a>
              ) : recommended && detected ? (
                <a
                  href={recommended.url}
                  download
                  data-hero-direct-download
                  className="download-action download-action-primary"
                >
                  <InteractiveIcon>
                    <DownloadIcon size={15} />
                  </InteractiveIcon>
                  {t("download.downloadFor", {
                    platform: platformLabel(detected),
                  })}
                </a>
              ) : (
                <a
                  href="#desktop"
                  className="download-action download-action-primary"
                >
                  <InteractiveIcon>
                    <DownloadIcon size={15} />
                  </InteractiveIcon>
                  {t("download.heroCta")}
                </a>
              )}
              <a
                href="#tutorial"
                className="download-action download-action-secondary"
              >
                <InteractiveIcon>
                  <GraduationCap size={15} />
                </InteractiveIcon>
                {t("download.heroCtaTutorial")}
              </a>
            </div>
          )}

          {/* 版本信息行（同落地页 Hero 底部 tech-stack 行） */}
          {!failed && (
            <div
              data-reveal
              data-reveal-delay="4"
              className="download-release-meta"
            >
              <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2.5">
                {info?.latest_version && (
                  <span className="download-version">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                    {t("download.latestVersion", {
                      version: info.latest_version,
                    })}
                  </span>
                )}
                <a
                  href={releasesFallbackUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="download-release-link"
                >
                  <InteractiveIcon>
                    <ExternalLink size={11} />
                  </InteractiveIcon>
                  {t("download.viewAllReleases")}
                </a>
              </div>
            </div>
          )}
        </div>
        <img
          className="public-brand-art download-hero-art"
          src={
            theme === "dark"
              ? "/images/illustrations/auth-brand-workspace.webp"
              : "/images/illustrations/auth-brand-workspace-light.webp"
          }
          alt=""
          aria-hidden="true"
          fetchPriority="high"
        />
      </section>

      <SectionDivider />

      {/* 桌面端：检测到的平台置顶，所有平台共用下载行。 */}
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
          <div className="download-platform-grid">
            {platformOrder.map((platform, idx) => {
              const links = desktop[platform];
              const Icon = PLATFORM_ICONS[platform];
              const isDetected = platform === detected;
              return (
                <div
                  key={platform}
                  data-reveal
                  data-reveal-delay={String(idx)}
                  className="download-platform-card"
                >
                  <div className="download-platform-heading">
                    <Icon size={20} className="text-theme-text-secondary" />
                    <h3>{platformLabel(platform)}</h3>
                    {isDetected && (
                      <span className="download-platform-current">
                        {t("download.detectedPlatform")}
                      </span>
                    )}
                  </div>
                  <div className="space-y-2">
                    {links.length > 0 ? (
                      links.map((link, i) => (
                        <AssetRow
                          key={link.url}
                          {...link}
                          variant={isDetected && i === 0 ? "primary" : "ghost"}
                        />
                      ))
                    ) : (
                      <p className="text-13 text-theme-text-secondary">
                        {t("download.noAssets")}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {desktop.macos.length > 0 && <MacGatekeeperNote />}
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
              className="download-platform-card download-mobile-card"
            >
              <div className="mb-5 flex items-center gap-3.5">
                <span className="text-theme-text-secondary">
                  <Smartphone size={20} />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-18 font-bold text-stone-900 dark:text-stone-100 sm:text-20">
                      Android
                    </span>
                    <span className="rounded-full bg-emerald-100/90 px-2.5 py-1 text-10 font-semibold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 sm:text-11">
                      APK
                    </span>
                  </div>
                  {info?.latest_version && (
                    <p className="mt-0.5 truncate font-mono text-11 tabular-nums text-theme-text-secondary dark:text-theme-text-secondary">
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
                className="public-terminal blog-feature-card relative overflow-hidden rounded-xl border border-stone-200/70 bg-stone-900 dark:border-stone-800/60 dark:bg-black/50"
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
                      className="overflow-x-auto font-mono text-14 leading-relaxed whitespace-nowrap text-stone-200 sm:text-15"
                    >
                      <span className="select-none text-emerald-400/80">
                        ${" "}
                      </span>
                      {cmd}
                    </p>
                  ))}
                  <p className="flex items-center gap-2 border-t border-white/10 pt-4 font-mono text-12 text-emerald-400/90 sm:text-13">
                    <Check size={13} />
                    paired · daemon online
                  </p>
                </div>
              </div>

              {/* 二进制下载：四列紧凑行 */}
              {/* 二进制下载：说明 + 四列紧凑行 */}
              <div data-reveal data-reveal-delay="2" className="space-y-3">
                <p className="text-center text-13 leading-relaxed text-theme-text-secondary dark:text-theme-text-secondary sm:text-14">
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
              <p className="text-center text-14 text-theme-text-secondary dark:text-theme-text-secondary">
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
                className="absolute bottom-6 left-[1.4rem] top-6 w-px bg-linear-to-b from-amber-300/50 via-stone-200 to-transparent dark:via-stone-700/60 sm:left-[1.55rem]"
                aria-hidden="true"
              />
              {(["step1", "step2", "step3"] as const).map((key, idx) => (
                <li
                  key={key}
                  data-reveal
                  data-reveal-delay={String(idx + 1)}
                  className="blog-feature-card group relative flex gap-4 rounded-2xl border border-stone-100/80 bg-white/80 p-5 transition-all duration-500 hover:-translate-y-1 hover:bg-white dark:border-stone-800/40 dark:bg-stone-900/40 dark:hover:bg-theme-bg-hover sm:p-6"
                >
                  <span className="z-10 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-amber-400/90 to-orange-500/90 text-16 text-white shadow-md transition-all duration-500  sm:h-12 sm:w-12">
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
                    <p className="text-14 leading-[1.75] text-theme-text-secondary dark:text-theme-text-tertiary sm:text-15">
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
                <span className="mx-auto rounded-full bg-stone-200/60 px-3 py-0.5 text-10 font-medium text-theme-text-secondary dark:bg-stone-800 dark:text-theme-text-secondary sm:text-11">
                  {t("profile.preferences")} · {t("profile.sandbox")}
                </span>
              </div>

              <div className="space-y-3 p-4 sm:p-5">
                {/* 云端沙箱行 */}
                <div className="flex items-center gap-3 rounded-xl border border-stone-100/80 bg-stone-50/60 px-4 py-3 dark:border-stone-800/50 dark:bg-stone-800/30">
                  <Cloud
                    size={15}
                    className="shrink-0 text-theme-text-secondary"
                  />
                  <span className="min-w-0 truncate text-13 font-medium text-theme-text-secondary dark:text-stone-200 sm:text-14">
                    {t("profile.cloudSandbox")}
                  </span>
                  <span className="ml-auto shrink-0 whitespace-nowrap rounded-full border border-stone-200/80 px-2.5 py-1 text-10 text-theme-text-secondary dark:border-stone-700/60 dark:text-theme-text-secondary sm:px-3 sm:text-11">
                    {t("profile.localSandbox.policyOptions.none")}
                  </span>
                </div>

                {/* 本地沙箱行（在线高亮） */}
                <div className="relative flex items-center gap-3 overflow-hidden rounded-xl border border-amber-200/90 bg-amber-50/70 px-4 py-3 dark:border-amber-500/25 dark:bg-amber-500/[0.07]">
                  <div className="absolute inset-x-0 top-0 h-[2px] bg-linear-to-r from-amber-300 to-orange-400" />
                  <Monitor
                    size={15}
                    className="shrink-0 text-amber-600/90 dark:text-amber-400/90"
                  />
                  <span className="shrink-0 text-13 font-semibold text-stone-800 dark:text-stone-100 sm:text-14">
                    {t("profile.localSandbox.title")}
                  </span>
                  <span className="flex min-w-0 shrink items-center gap-1.5 text-11 text-theme-text-secondary dark:text-theme-text-secondary sm:text-12">
                    <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                    {t("profile.localSandbox.statusOnline")}
                    <span className="truncate font-mono text-10 opacity-70 sm:text-11">
                      {t("profile.localSandbox.version", {
                        version: info?.latest_version ?? "2.8.6",
                      })}
                    </span>
                  </span>
                  <span className="ml-auto hidden text-10 text-theme-text-secondary dark:text-theme-text-secondary sm:block sm:text-11">
                    {t("profile.localSandbox.webManaged")}
                  </span>
                </div>

                {/* 会话沙箱档位切换条 */}
                <div className="flex items-center gap-2 rounded-xl border border-stone-100/80 bg-stone-50/60 px-4 py-3 dark:border-stone-800/50 dark:bg-stone-800/30">
                  <span className="shrink-0 text-10 font-semibold uppercase tracking-[0.12em] text-theme-text-secondary dark:text-theme-text-secondary sm:text-11">
                    {t("agentOptions.sandbox.label")}
                  </span>
                  <span className="ml-auto flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-stone-200/80 px-2.5 py-1 text-11 text-theme-text-secondary dark:border-stone-700/60 dark:text-theme-text-secondary sm:px-3 sm:text-12">
                    {t("agentOptions.sandbox.options.cloud")}
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full bg-stone-900 px-3 py-1 text-11 font-semibold text-white dark:bg-stone-50 dark:text-stone-900 sm:px-3.5 sm:text-12">
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
          <div className="relative mx-auto max-w-2xl px-5 text-center sm:px-6 lg:max-w-3xl">
            <a
              data-reveal
              data-reveal-delay="1"
              href={releasesFallbackUrl}
              target="_blank"
              rel="noreferrer"
              className="download-action download-action-secondary"
            >
              <InteractiveIcon>
                <ExternalLink size={14} />
              </InteractiveIcon>
              {t("download.viewAllReleases")}
            </a>
          </div>
        </section>
      )}
    </div>
  );
}

export default DownloadPage;
