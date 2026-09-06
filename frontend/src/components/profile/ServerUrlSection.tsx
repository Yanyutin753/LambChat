/**
 * 设置页"服务器地址"分区（挂载点按 isNativeAppRuntime() 门控，仅原生客户端渲染）。
 *
 * 构建期烘焙了 VITE_API_BASE 的包首启不会出 ServerSetupScreen（needsServerSetup
 * 为 false）——本分区是安装后唯一的改址入口：展示当前生效基址（运行时配置优先、
 * 烘焙值兜底），支持修改（探活 ``/health`` 后落 localStorage 并整页刷新，复用
 * 首启屏的网络改写生效链路）与恢复默认（清除运行时覆盖，回到烘焙值）。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Pencil, RotateCcw } from "lucide-react";

import {
  clearStoredServerUrl,
  effectiveApiBase,
  getStoredServerUrl,
  normalizeServerUrl,
  setStoredServerUrl,
} from "../../services/api/serverConfig";

export function ServerUrlSection() {
  const { t } = useTranslation();
  // 展示值：运行时配置优先、烘焙值兜底；web 同源场景回退 origin（与
  // SandboxMachinesCard 的展示口径一致——本组件原生端才挂载，兜底仅测试触达）
  const current = effectiveApiBase() || window.location.origin;
  const hasOverride = getStoredServerUrl() !== null;

  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState("");
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");

  const normalized = normalizeServerUrl(input);

  const startEdit = () => {
    setInput(current);
    setError("");
    setEditing(true);
  };

  const handleConnect = async () => {
    if (!normalized || testing) return;
    setTesting(true);
    setError("");
    try {
      // 直连绝对地址探测（此刻网络改写仍指向旧地址，不能走改写层）
      const resp = await fetch(`${normalized}/health`, { method: "GET" });
      if (!resp.ok) {
        setError(t("serverSetup.fail", { status: String(resp.status) }));
        return;
      }
      setStoredServerUrl(normalized);
      window.location.reload();
    } catch {
      setError(t("serverSetup.unreachable"));
    } finally {
      setTesting(false);
    }
  };

  const handleReset = () => {
    clearStoredServerUrl();
    window.location.reload();
  };

  return (
    <div className="rounded-2xl bg-theme-bg-subtle dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
      <div className="flex items-center gap-2 mb-3">
        <Globe size={13} className="text-amber-500 dark:text-amber-400" />
        <h3 className="text-12 font-semibold font-serif uppercase tracking-wider text-stone-400 dark:text-stone-500">
          {t("profile.serverUrl.title")}
        </h3>
      </div>
      <p className="text-xs text-stone-500 dark:text-stone-400 leading-relaxed">
        {t("profile.serverUrl.desc")}
      </p>

      {editing ? (
        <div className="mt-3 space-y-2">
          <label
            htmlFor="server-url-input"
            className="block text-xs font-medium text-stone-500 dark:text-stone-400"
          >
            {t("serverSetup.label")}
          </label>
          <input
            id="server-url-input"
            type="text"
            autoFocus
            spellCheck={false}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleConnect();
              if (e.key === "Escape") setEditing(false);
            }}
            className="w-full rounded-xl border border-stone-200 dark:border-stone-600 bg-theme-bg-card dark:bg-stone-800 px-3 py-2 text-sm text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
          />
          {input.trim() !== "" && !normalized && (
            <p className="text-xs text-red-500 dark:text-red-400">
              {t("serverSetup.invalid")}
            </p>
          )}
          {error && (
            <p className="text-xs text-red-500 dark:text-red-400" role="alert">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleConnect()}
              disabled={!normalized || testing}
              className="rounded-xl bg-amber-500 disabled:opacity-50 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-600"
            >
              {testing ? t("serverSetup.testing") : t("serverSetup.connect")}
            </button>
            <button
              type="button"
              onClick={() => setEditing(false)}
              className="rounded-xl border border-stone-200 dark:border-stone-600 px-3 py-2 text-sm text-stone-600 dark:text-stone-300 transition-colors hover:bg-stone-100 dark:hover:bg-stone-700/50"
            >
              {t("profile.serverUrl.cancel")}
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex items-center justify-between gap-2">
          <span
            className="min-w-0 truncate font-mono text-sm text-stone-700 dark:text-stone-200"
            data-server-url-current
          >
            {current}
          </span>
          <span className="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              onClick={startEdit}
              className="flex items-center gap-1 rounded-xl border border-stone-200 dark:border-stone-600 px-2.5 py-1.5 text-xs text-stone-600 dark:text-stone-300 transition-colors hover:bg-stone-100 dark:hover:bg-stone-700/50"
            >
              <Pencil size={12} className="opacity-60" />
              {t("profile.serverUrl.change")}
            </button>
            {hasOverride && (
              <button
                type="button"
                onClick={handleReset}
                title={t("profile.serverUrl.resetTitle")}
                className="flex items-center gap-1 rounded-xl border border-stone-200 dark:border-stone-600 px-2.5 py-1.5 text-xs text-stone-600 dark:text-stone-300 transition-colors hover:bg-stone-100 dark:hover:bg-stone-700/50"
              >
                <RotateCcw size={12} className="opacity-60" />
                {t("profile.serverUrl.reset")}
              </button>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

export default ServerUrlSection;
