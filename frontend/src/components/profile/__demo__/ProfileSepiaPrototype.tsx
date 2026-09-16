/**
 * PROTOTYPE（一次性代码，不进 main）
 *
 * 问题：护眼（sepia）模式下「个人信息」模块的视觉表现是否统一？
 * 现状：模块内 theme-* token（随 sepia 变暖）与硬编码 stone/white/black
 * 亮色类（不随 sepia 变化）混用，导致米黄底上出现冷灰色块、纯白光环、
 * 近乎不可见的分隔线和过饱和的红/黑控件。
 *
 * 一行计划：个人信息弹窗原型的四个变体，?variant= 切换（current 基线 /
 * A 纯 token 替换 / B token+暖色重校准 / C 分组信息架构），路由
 * /dev/profile-sepia，底栏循环切换并可循环主题（默认进入 sepia）。
 *
 * 结论落定后：胜出方案折叠进正式组件，本文件整体迁往一次性分支留存。
 * 原型内底栏/横幅文案为开发者向硬编码中文，不进 i18n。
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router-dom";
import {
  X,
  User,
  Bell,
  Settings,
  Braces,
  Wrench,
  Cpu,
  Scale,
  LogOut,
  Pencil,
  Check,
  Mail,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  Palette,
} from "lucide-react";
import { Button, IconButton, Input } from "../../common";
import { BrandWordmark } from "../../common/BrandWordmark";
import { APP_VERSION } from "../../../utils/appVersion";
import { applyThemeToDocument, type Theme } from "../../../utils/themeDom";

/* ── mock 数据：无后端依赖，纯视觉评审 ── */

const MOCK_USER = {
  username: "Arisewind",
  email: "arisewind@lambchat.com",
  roles: ["admin", "user"] as string[],
};
const MOCK_ADMIN_EMAIL = "support@lambchat.com";
const MOCK_ADMIN_URL = "https://docs.lambchat.com";

/* ── 主题控制：进入强制 sepia，卸载恢复原状；底栏可循环三主题 ── */

const DEMO_THEME_ORDER: Theme[] = ["sepia", "light", "dark"];
const DEMO_THEME_LABEL: Record<Theme, string> = {
  sepia: "护眼 sepia",
  light: "浅色 light",
  dark: "深色 dark",
};

function useDemoTheme() {
  const [theme, setTheme] = useState<Theme>("sepia");

  // 进入时保存 <html>/<body> 主题痕迹，离开时整体恢复
  useEffect(() => {
    const html = document.documentElement;
    const prevHtmlClass = html.className;
    const prevHtmlStyle = html.getAttribute("style");
    const prevBodyStyle = document.body.getAttribute("style");
    return () => {
      html.className = prevHtmlClass;
      if (prevHtmlStyle === null) html.removeAttribute("style");
      else html.setAttribute("style", prevHtmlStyle);
      if (prevBodyStyle === null) document.body.removeAttribute("style");
      else document.body.setAttribute("style", prevBodyStyle);
    };
  }, []);

  useEffect(() => {
    applyThemeToDocument(theme);
  }, [theme]);

  const cycleTheme = () => {
    setTheme((cur) => {
      const next =
        DEMO_THEME_ORDER[
          (DEMO_THEME_ORDER.indexOf(cur) + 1) % DEMO_THEME_ORDER.length
        ];
      return next ?? "sepia";
    });
  };

  return { theme, cycleTheme };
}

/* ── 变体注册 ── */

type VariantKey = "current" | "a" | "b" | "c";

const VARIANTS: { key: VariantKey; label: string }[] = [
  { key: "current", label: "Current — 现状基线" },
  { key: "a", label: "A — 纯 token 替换" },
  { key: "b", label: "B — token + 暖色重校准" },
  { key: "c", label: "C — 分组信息架构" },
];

/* ── 弹窗壳层共用件（正式代码中已是 token 写法，各变体原样保留） ── */

const TAB_ICONS: Record<
  string,
  React.FC<{ size?: number; className?: string }>
> = {
  info: User,
  notification: Bell,
  preferences: Settings,
  envvars: Braces,
  tools: Wrench,
  models: Cpu,
  terms: Scale,
};

function useDemoTabs() {
  const { t } = useTranslation();
  return [
    { key: "info", label: t("profile.title") },
    { key: "notification", label: t("profile.notifications") },
    { key: "preferences", label: t("profile.preferences") },
    { key: "envvars", label: t("envVars.title") },
    { key: "tools", label: t("profile.toolsTab", "Tools") },
    { key: "models", label: t("profile.modelIntro") },
    { key: "terms", label: t("profile.termsTab") },
  ] as const;
}

function DemoCloseButton() {
  return (
    <button className="p-1.5 rounded-lg text-theme-text-tertiary hover:text-theme-text-secondary hover:bg-theme-bg-subtle dark:text-stone-500 dark:hover:text-stone-300 dark:hover:bg-stone-700/60 transition-all">
      <X size={18} />
    </button>
  );
}

function DemoFooter() {
  const { t } = useTranslation();
  return (
    <div className="px-4 sm:px-5 py-2.5 sm:py-3 border-t border-theme-border-subtle dark:border-stone-700/50 flex items-center justify-between bg-theme-bg-subtle dark:bg-stone-900/30 whitespace-nowrap">
      <span className="text-11 text-theme-text-tertiary dark:text-stone-500 tabular-nums flex items-center gap-1 leading-none">
        <BrandWordmark
          decorative
          className="inline-block h-4 w-auto text-theme-text-secondary dark:text-stone-400"
        />
        <span className="opacity-70 font-serif leading-none">
          v{APP_VERSION}
        </span>
      </span>
      <span className="px-1.5 sm:px-2 text-11 font-medium text-theme-text-tertiary dark:text-stone-500 py-1 rounded-md font-serif leading-none">
        {t("common.poweredBy")}
      </span>
    </div>
  );
}

function DemoHeader() {
  const { t } = useTranslation();
  return (
    <div className="px-5 py-4 flex items-center justify-between border-b border-theme-border-subtle dark:border-stone-700/50">
      <div>
        <h3 className="text-14 font-semibold font-serif text-theme-text dark:text-stone-100 tracking-tight">
          {t("profile.title")}
        </h3>
        <p className="text-11 text-theme-text-tertiary dark:text-stone-500 mt-0.5">
          {t("profile.title")}
        </p>
      </div>
      <DemoCloseButton />
    </div>
  );
}

function DemoOtherTabPlaceholder() {
  const { t } = useTranslation();
  return (
    <div className="py-16 text-center text-12 text-theme-text-tertiary">
      原型范围：仅「{t("profile.title")}」标签。其余标签存在同类硬编码问题，
      修正方案与其共享同一套替换规则。
    </div>
  );
}

/* ── 变体内容：个人信息标签 ──
 * 各变体自持编辑态；切换变体即重挂载重置。 */

/** current：逐类复制 ProfileInfoTab 现状标记（含硬编码 stone/white） */
function InfoTabCurrent() {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [username, setUsername] = useState(MOCK_USER.username);

  return (
    <>
      {/* Avatar */}
      <div className="flex flex-col items-center mb-6">
        <div className="size-16 sm:size-20 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center border-4 border-white dark:border-stone-700 shadow-lg ring-2 ring-stone-100 dark:ring-stone-600">
          <span className="text-30 font-bold text-white font-serif">
            {username.charAt(0).toUpperCase() || "U"}
          </span>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <label className="cursor-pointer rounded-lg bg-stone-100 dark:bg-stone-700 px-3 py-1.5 text-12 font-medium text-stone-600 dark:text-stone-300 hover:bg-stone-200 dark:hover:bg-stone-600 transition-colors">
            {t("profile.changeAvatar")}
          </label>
          <Button variant="danger" size="sm">
            {t("profile.deleteAvatar")}
          </Button>
        </div>
      </div>

      <div className="space-y-0">
        <div className="py-3.5 border-b border-stone-100 dark:border-stone-700/60">
          {editing ? (
            <div className="space-y-2">
              <Input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                minLength={3}
                maxLength={50}
                autoFocus
              />
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  leftIcon={<Check size={14} />}
                  onClick={() => {
                    setUsername(draft);
                    setEditing(false);
                  }}
                  className="flex-1 sm:flex-none"
                >
                  {t("common.save")}
                </Button>
                <Button
                  onClick={() => setEditing(false)}
                  className="flex-1 sm:flex-none"
                >
                  {t("common.cancel")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3 font-serif">
              <span className="text-14 text-stone-500 dark:text-stone-400 shrink-0">
                {t("profile.username")}
              </span>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-14 font-medium text-stone-900 dark:text-stone-100 truncate">
                  {username}
                </span>
                <IconButton
                  aria-label={t("common.edit")}
                  onClick={() => {
                    setDraft(username);
                    setEditing(true);
                  }}
                  icon={<Pencil size={13} />}
                  size="sm"
                  className="shrink-0 text-amber-500 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/30 rounded-md"
                  title={t("common.edit")}
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between py-3.5 border-b border-stone-100 dark:border-stone-700/60 gap-3">
          <span className="text-14 text-stone-500 dark:text-stone-400 shrink-0">
            {t("profile.email")}
          </span>
          <span className="text-14 font-medium text-stone-900 dark:text-stone-100 truncate text-right">
            {MOCK_USER.email}
          </span>
        </div>
        <div className="flex items-center justify-between py-3.5 gap-3">
          <span className="text-14 text-stone-500 dark:text-stone-400 shrink-0">
            {t("profile.roles")}
          </span>
          <div className="flex flex-wrap justify-end gap-1.5">
            {MOCK_USER.roles.map((role) => (
              <span
                key={role}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-12 font-medium bg-stone-100 dark:bg-stone-700 text-stone-600 dark:text-stone-300"
              >
                {role}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-5 pt-5 border-t border-stone-100 dark:border-stone-700/60 space-y-0">
          <p className="text-12 text-stone-400 dark:text-stone-500 mb-1">
            Contact
          </p>
          <a className="flex items-center justify-between py-3.5 border-b border-stone-100 dark:border-stone-700/60 gap-3 group cursor-pointer">
            <span className="flex items-center gap-2 text-14 text-stone-500 dark:text-stone-400 shrink-0">
              <Mail size={14} />
              {t("profile.email", "Email")}
            </span>
            <span className="text-14 font-medium text-stone-900 dark:text-stone-100 truncate group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
              {MOCK_ADMIN_EMAIL}
            </span>
          </a>
          <a
            href={MOCK_ADMIN_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-between py-3.5 gap-3 group cursor-pointer"
          >
            <span className="flex items-center gap-2 text-14 text-stone-500 dark:text-stone-400 shrink-0">
              <ExternalLink size={14} />
              Support
            </span>
            <span className="text-14 font-medium text-stone-400 dark:text-stone-500 group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
              →
            </span>
          </a>
        </div>
      </div>
    </>
  );
}

/** A：结构零改动，硬编码亮色类逐项换成 theme-* token（sepia 自动变暖） */
function InfoTabA() {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [username, setUsername] = useState(MOCK_USER.username);

  return (
    <>
      <div className="flex flex-col items-center mb-6">
        <div className="size-16 sm:size-20 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center border-4 border-theme-bg-card shadow-lg ring-2 ring-theme-border">
          <span className="text-30 font-bold text-white font-serif">
            {username.charAt(0).toUpperCase() || "U"}
          </span>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <label className="cursor-pointer rounded-lg bg-theme-bg-subtle px-3 py-1.5 text-12 font-medium text-theme-text-secondary hover:bg-theme-border-hover hover:text-theme-text transition-colors">
            {t("profile.changeAvatar")}
          </label>
          <Button variant="danger" size="sm">
            {t("profile.deleteAvatar")}
          </Button>
        </div>
      </div>

      <div className="space-y-0">
        <div className="py-3.5 border-b border-theme-border-subtle">
          {editing ? (
            <div className="space-y-2">
              <Input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                minLength={3}
                maxLength={50}
                autoFocus
              />
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  leftIcon={<Check size={14} />}
                  onClick={() => {
                    setUsername(draft);
                    setEditing(false);
                  }}
                  className="flex-1 sm:flex-none"
                >
                  {t("common.save")}
                </Button>
                <Button
                  onClick={() => setEditing(false)}
                  className="flex-1 sm:flex-none"
                >
                  {t("common.cancel")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3 font-serif">
              <span className="text-14 text-theme-text-secondary shrink-0">
                {t("profile.username")}
              </span>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-14 font-medium text-theme-text truncate">
                  {username}
                </span>
                <IconButton
                  aria-label={t("common.edit")}
                  onClick={() => {
                    setDraft(username);
                    setEditing(true);
                  }}
                  icon={<Pencil size={13} />}
                  size="sm"
                  className="shrink-0 text-amber-500 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/30 rounded-md"
                  title={t("common.edit")}
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between py-3.5 border-b border-theme-border-subtle gap-3">
          <span className="text-14 text-theme-text-secondary shrink-0">
            {t("profile.email")}
          </span>
          <span className="text-14 font-medium text-theme-text truncate text-right">
            {MOCK_USER.email}
          </span>
        </div>
        <div className="flex items-center justify-between py-3.5 gap-3">
          <span className="text-14 text-theme-text-secondary shrink-0">
            {t("profile.roles")}
          </span>
          <div className="flex flex-wrap justify-end gap-1.5">
            {MOCK_USER.roles.map((role) => (
              <span
                key={role}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-12 font-medium bg-theme-bg-subtle text-theme-text-secondary"
              >
                {role}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-5 pt-5 border-t border-theme-border-subtle space-y-0">
          <p className="text-12 text-theme-text-tertiary mb-1">Contact</p>
          <a className="flex items-center justify-between py-3.5 border-b border-theme-border-subtle gap-3 group cursor-pointer">
            <span className="flex items-center gap-2 text-14 text-theme-text-secondary shrink-0">
              <Mail size={14} />
              {t("profile.email", "Email")}
            </span>
            <span className="text-14 font-medium text-theme-text truncate group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
              {MOCK_ADMIN_EMAIL}
            </span>
          </a>
          <a className="flex items-center justify-between py-3.5 gap-3 group cursor-pointer">
            <span className="flex items-center gap-2 text-14 text-theme-text-secondary shrink-0">
              <ExternalLink size={14} />
              Support
            </span>
            <span className="text-14 font-medium text-theme-text-tertiary group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
              →
            </span>
          </a>
        </div>
      </div>
    </>
  );
}

/** B：在 A 之上重校准强调体系——激活胶囊用 theme-text 反色、
 *  危险操作用 theme-error、琥珀 hover 底用 theme-accent-light */
function InfoTabB() {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [username, setUsername] = useState(MOCK_USER.username);

  return (
    <>
      <div className="flex flex-col items-center mb-6">
        <div className="size-16 sm:size-20 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center border-4 border-theme-bg-card shadow-lg ring-2 ring-theme-border">
          <span className="text-30 font-bold text-white font-serif">
            {username.charAt(0).toUpperCase() || "U"}
          </span>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <label className="cursor-pointer rounded-lg bg-theme-bg-subtle px-3 py-1.5 text-12 font-medium text-theme-text-secondary hover:bg-theme-border-hover hover:text-theme-text transition-colors">
            {t("profile.changeAvatar")}
          </label>
          <Button variant="danger" size="sm">
            {t("profile.deleteAvatar")}
          </Button>
        </div>
      </div>

      <div className="space-y-0">
        <div className="py-3.5 border-b border-theme-border-subtle">
          {editing ? (
            <div className="space-y-2">
              <Input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                minLength={3}
                maxLength={50}
                autoFocus
              />
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  leftIcon={<Check size={14} />}
                  onClick={() => {
                    setUsername(draft);
                    setEditing(false);
                  }}
                  className="flex-1 sm:flex-none"
                >
                  {t("common.save")}
                </Button>
                <Button
                  onClick={() => setEditing(false)}
                  className="flex-1 sm:flex-none"
                >
                  {t("common.cancel")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3 font-serif">
              <span className="text-14 text-theme-text-secondary shrink-0">
                {t("profile.username")}
              </span>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-14 font-medium text-theme-text truncate">
                  {username}
                </span>
                <IconButton
                  aria-label={t("common.edit")}
                  onClick={() => {
                    setDraft(username);
                    setEditing(true);
                  }}
                  icon={<Pencil size={13} />}
                  size="sm"
                  className="shrink-0 text-amber-500 dark:text-amber-400 hover:bg-theme-accent-light rounded-md"
                  title={t("common.edit")}
                />
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between py-3.5 border-b border-theme-border-subtle gap-3">
          <span className="text-14 text-theme-text-secondary shrink-0">
            {t("profile.email")}
          </span>
          <span className="text-14 font-medium text-theme-text truncate text-right">
            {MOCK_USER.email}
          </span>
        </div>
        <div className="flex items-center justify-between py-3.5 gap-3">
          <span className="text-14 text-theme-text-secondary shrink-0">
            {t("profile.roles")}
          </span>
          <div className="flex flex-wrap justify-end gap-1.5">
            {MOCK_USER.roles.map((role) => (
              <span
                key={role}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-12 font-medium bg-theme-bg-subtle text-theme-text-secondary"
              >
                {role}
              </span>
            ))}
          </div>
        </div>

        <div className="mt-5 pt-5 border-t border-theme-border-subtle space-y-0">
          <p className="text-12 text-theme-text-tertiary mb-1">Contact</p>
          <a className="flex items-center justify-between py-3.5 border-b border-theme-border-subtle gap-3 group cursor-pointer">
            <span className="flex items-center gap-2 text-14 text-theme-text-secondary shrink-0">
              <Mail size={14} />
              {t("profile.email", "Email")}
            </span>
            <span className="text-14 font-medium text-theme-text truncate group-hover:text-theme-primary-hover transition-colors">
              {MOCK_ADMIN_EMAIL}
            </span>
          </a>
          <a className="flex items-center justify-between py-3.5 gap-3 group cursor-pointer">
            <span className="flex items-center gap-2 text-14 text-theme-text-secondary shrink-0">
              <ExternalLink size={14} />
              Support
            </span>
            <span className="text-14 font-medium text-theme-text-tertiary group-hover:text-theme-primary-hover transition-colors">
              →
            </span>
          </a>
        </div>
      </div>
    </>
  );
}

/** C：分组信息架构——头像+身份做头部，字段装进带边框的分组容器，
 *  联系方式独立成组；配色沿用 B 的 token 化结果 */
function InfoTabC() {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [username, setUsername] = useState(MOCK_USER.username);

  return (
    <div className="space-y-5">
      {/* 头部：头像 + 身份摘要 */}
      <div className="flex items-center gap-4">
        <div className="size-14 shrink-0 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center border-2 border-theme-bg-card shadow-md ring-2 ring-theme-border">
          <span className="text-20 font-bold text-white font-serif">
            {username.charAt(0).toUpperCase() || "U"}
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-16 font-semibold font-serif text-theme-text truncate">
            {username}
          </p>
          <p className="text-12 text-theme-text-secondary truncate">
            {MOCK_USER.email}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {MOCK_USER.roles.map((role) => (
              <span
                key={role}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-12 font-medium bg-theme-bg-subtle text-theme-text-secondary"
              >
                {role}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <label className="cursor-pointer rounded-lg bg-theme-bg-subtle px-3 py-1.5 text-12 font-medium text-theme-text-secondary hover:bg-theme-border-hover hover:text-theme-text transition-colors">
          {t("profile.changeAvatar")}
        </label>
        <Button variant="danger" size="sm">
          {t("profile.deleteAvatar")}
        </Button>
      </div>

      {/* 账户字段组 */}
      <div className="rounded-xl border border-theme-border divide-y divide-theme-border-subtle overflow-hidden">
        <div className="px-4 py-3">
          {editing ? (
            <div className="space-y-2">
              <Input
                type="text"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                minLength={3}
                maxLength={50}
                autoFocus
              />
              <div className="flex gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  leftIcon={<Check size={14} />}
                  onClick={() => {
                    setUsername(draft);
                    setEditing(false);
                  }}
                >
                  {t("common.save")}
                </Button>
                <Button size="sm" onClick={() => setEditing(false)}>
                  {t("common.cancel")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-3">
              <span className="text-13 text-theme-text-secondary shrink-0">
                {t("profile.username")}
              </span>
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-13 font-medium text-theme-text truncate">
                  {username}
                </span>
                <IconButton
                  aria-label={t("common.edit")}
                  onClick={() => {
                    setDraft(username);
                    setEditing(true);
                  }}
                  icon={<Pencil size={13} />}
                  size="sm"
                  className="shrink-0 text-amber-500 dark:text-amber-400 hover:bg-theme-accent-light rounded-md"
                  title={t("common.edit")}
                />
              </div>
            </div>
          )}
        </div>
        <div className="px-4 py-3 flex items-center justify-between gap-3">
          <span className="text-13 text-theme-text-secondary shrink-0">
            {t("profile.email")}
          </span>
          <span className="text-13 font-medium text-theme-text truncate text-right">
            {MOCK_USER.email}
          </span>
        </div>
      </div>

      {/* 联系组 */}
      <div>
        <p className="text-12 text-theme-text-tertiary mb-1.5">Contact</p>
        <div className="rounded-xl border border-theme-border divide-y divide-theme-border-subtle overflow-hidden">
          <a className="px-4 py-3 flex items-center justify-between gap-3 group cursor-pointer">
            <span className="flex items-center gap-2 text-13 text-theme-text-secondary shrink-0">
              <Mail size={14} />
              {t("profile.email", "Email")}
            </span>
            <span className="text-13 font-medium text-theme-text truncate group-hover:text-theme-primary-hover transition-colors">
              {MOCK_ADMIN_EMAIL}
            </span>
          </a>
          <a className="px-4 py-3 flex items-center justify-between gap-3 group cursor-pointer">
            <span className="flex items-center gap-2 text-13 text-theme-text-secondary shrink-0">
              <ExternalLink size={14} />
              Support
            </span>
            <span className="text-13 font-medium text-theme-text-tertiary group-hover:text-theme-primary-hover transition-colors">
              →
            </span>
          </a>
        </div>
      </div>
    </div>
  );
}

/* ── 弹窗壳层 × 变体 ──
 * 移动端底部抽屉 + 桌面侧栏双布局，响应式断点与正式组件一致。
 * 差异点只在：移动端激活胶囊样式、登出按钮样式、右栏信息内容。 */

function navPillClass(variant: VariantKey, active: boolean): string {
  const base =
    "relative shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-12 font-medium transition-all whitespace-nowrap";
  if (active) {
    if (variant === "current") {
      return `${base} bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900`;
    }
    // a/b/c：反色胶囊 token 化（sepia 下暖深底 + 米黄字）
    return `${base} bg-theme-text text-theme-bg-card`;
  }
  return `${base} text-theme-text-secondary dark:text-stone-400 hover:bg-theme-bg-subtle dark:hover:bg-stone-700/50`;
}

function logoutPillClass(variant: VariantKey): string {
  if (variant === "current") {
    return "relative shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-12 font-medium transition-all whitespace-nowrap text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20";
  }
  return "relative shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-12 font-medium transition-all whitespace-nowrap text-theme-error hover:bg-[color-mix(in_srgb,var(--theme-error)_12%,transparent)]";
}

function logoutSidebarClass(variant: VariantKey): string {
  if (variant === "current") {
    return "w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-12 font-medium transition-all text-red-500 dark:text-red-400 hover:text-red-600 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 border border-transparent";
  }
  return "w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-12 font-medium transition-all text-theme-error hover:opacity-80 hover:bg-[color-mix(in_srgb,var(--theme-error)_12%,transparent)] border border-transparent";
}

function InfoContent({ variant }: { variant: VariantKey }) {
  if (variant === "current") return <InfoTabCurrent />;
  if (variant === "a") return <InfoTabA />;
  if (variant === "b") return <InfoTabB />;
  return <InfoTabC />;
}

function DemoModal({ variant }: { variant: VariantKey }) {
  const { t } = useTranslation();
  const tabs = useDemoTabs();
  const [activeTab, setActiveTab] = useState<string>("info");

  const tabList = tabs.map((tab) => ({
    ...tab,
    Icon: TAB_ICONS[tab.key],
  }));

  const content =
    activeTab === "info" ? (
      <div className="animate-fade-in">
        <InfoContent variant={variant} />
      </div>
    ) : (
      <DemoOtherTabPlaceholder />
    );

  return (
    <div className="flex min-h-[82dvh] items-end sm:items-center sm:justify-center">
      {/* ===== Mobile: bottom sheet ===== */}
      <div className="sm:hidden relative z-10 w-full bg-theme-bg-card dark:bg-stone-800 rounded-t-2xl shadow-2xl shadow-black/20 dark:shadow-black/50 border-x border-t border-theme-border dark:border-stone-700/60 overflow-hidden max-h-[90dvh] flex flex-col">
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-9 h-1 bg-theme-border-hover dark:bg-stone-600 rounded-full" />
        </div>
        <div className="px-4 py-2.5 flex items-center justify-between">
          <h3 className="text-15 font-semibold text-theme-text dark:text-stone-100 tracking-tight font-serif">
            {t("profile.title")}
          </h3>
          <DemoCloseButton />
        </div>
        <div className="px-3 pb-1">
          <div className="flex gap-1 overflow-x-auto scrollbar-none scroll-smooth">
            {tabList.map(({ key, label, Icon }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={navPillClass(variant, activeTab === key)}
              >
                {Icon && <Icon size={14} />}
                {label}
              </button>
            ))}
            <button className={logoutPillClass(variant)}>
              <LogOut size={14} />
              {t("auth.logout")}
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
          {content}
        </div>
        <DemoFooter />
      </div>

      {/* ===== Desktop: centered with sidebar ===== */}
      <div className="hidden sm:flex relative z-10 w-[80vw] max-w-[680px] h-[75dvh] max-h-[640px] bg-theme-bg-card dark:bg-stone-800 rounded-2xl shadow-2xl shadow-stone-900/10 dark:shadow-black/40 border border-theme-border dark:border-stone-700/50 overflow-hidden flex-col">
        <DemoHeader />
        <div className="flex flex-1 min-h-0">
          <div className="w-[152px] shrink-0 border-r border-theme-border-subtle dark:border-stone-700/50 py-2 px-2 space-y-0.5 bg-theme-bg-subtle dark:bg-stone-900/20">
            {tabList.map(({ key, label, Icon }) => {
              const isActive = activeTab === key;
              return (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-12 font-medium transition-all ${
                    isActive
                      ? "bg-theme-bg-card dark:bg-stone-800 text-theme-text dark:text-stone-100 shadow-sm border border-theme-border dark:border-stone-700/60"
                      : "text-theme-text-secondary dark:text-stone-400 hover:text-theme-text dark:hover:text-stone-200 hover:bg-theme-bg-card dark:hover:bg-stone-800/60 border border-transparent"
                  }`}
                >
                  {Icon && (
                    <Icon
                      size={15}
                      className={
                        isActive
                          ? "text-amber-500 dark:text-amber-400"
                          : "opacity-60"
                      }
                    />
                  )}
                  {label}
                </button>
              );
            })}
            <div className="!mt-3 pt-3 border-t border-theme-border dark:border-stone-700/50">
              <button className={logoutSidebarClass(variant)}>
                <LogOut size={15} className="opacity-70" />
                {t("auth.logout")}
              </button>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-5 sm:p-8">{content}</div>
        </div>
        <DemoFooter />
      </div>
    </div>
  );
}

/* ── 原型页 + 底部切换器 ── */

export function ProfileSepiaPrototype() {
  const { theme, cycleTheme } = useDemoTheme();
  const [searchParams, setSearchParams] = useSearchParams();

  const raw = searchParams.get("variant") ?? "current";
  const variant: VariantKey = VARIANTS.some((v) => v.key === raw)
    ? (raw as VariantKey)
    : "current";

  const cycleVariant = (dir: 1 | -1) => {
    const index = VARIANTS.findIndex((v) => v.key === variant);
    const next =
      VARIANTS[(index + dir + VARIANTS.length) % VARIANTS.length] ??
      VARIANTS[0];
    setSearchParams({ variant: next.key }, { replace: true });
  };

  // 键盘 ←/→ 循环变体；输入焦点时让位
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.closest("input, textarea, select") || target.isContentEditable)
      ) {
        return;
      }
      if (e.key === "ArrowLeft") cycleVariant(-1);
      if (e.key === "ArrowRight") cycleVariant(1);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
    // 无依赖数组：每次渲染重挂监听，保证 cycleVariant 捕获最新 variant
  });

  const currentLabel =
    VARIANTS.find((v) => v.key === variant)?.label ?? variant;

  return (
    <div className="min-h-dvh bg-theme-bg">
      {/* 原型横幅：说明被验证的问题，明显区别于被评审的设计 */}
      <div className="border-b border-dashed border-amber-500/50 bg-amber-50 dark:bg-stone-900 px-4 py-2.5 text-12 text-stone-600 dark:text-stone-300 flex items-center gap-2 flex-wrap">
        <span className="font-semibold text-amber-700 dark:text-amber-400">
          PROTOTYPE（一次性）
        </span>
        <span>
          验证问题：护眼（sepia）模式下个人信息模块的视觉统一性。底栏或 ←/→
          切换变体，Palette 按钮循环主题对比（浅色应保持不变，护眼应全暖）。
        </span>
        <span className="tabular-nums opacity-70">
          当前主题：{DEMO_THEME_LABEL[theme]}
        </span>
      </div>

      <div className="px-4 pt-6">
        <DemoModal variant={variant} />
      </div>

      {/* 浮动切换器 */}
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[999] flex items-center gap-0.5 rounded-full bg-stone-900 text-white shadow-lg px-1.5 py-1 dark:bg-stone-100 dark:text-stone-900">
        <button
          onClick={() => cycleVariant(-1)}
          aria-label="上一个变体"
          className="p-1.5 rounded-full hover:bg-white/10 dark:hover:bg-black/10"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-12 font-medium px-2 min-w-[13.5rem] text-center tabular-nums">
          {currentLabel}
        </span>
        <button
          onClick={() => cycleVariant(1)}
          aria-label="下一个变体"
          className="p-1.5 rounded-full hover:bg-white/10 dark:hover:bg-black/10"
        >
          <ChevronRight size={16} />
        </button>
        <div className="w-px h-4 bg-current opacity-20 mx-1" />
        <button
          onClick={cycleTheme}
          aria-label="循环主题"
          title={`当前主题：${DEMO_THEME_LABEL[theme]}（点击切换）`}
          className="p-1.5 rounded-full hover:bg-white/10 dark:hover:bg-black/10 flex items-center gap-1"
        >
          <Palette size={16} />
          <span className="text-11 pr-1">{DEMO_THEME_LABEL[theme]}</span>
        </button>
      </div>
    </div>
  );
}
