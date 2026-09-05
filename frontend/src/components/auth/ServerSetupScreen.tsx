/**
 * 打包壳首启服务器配置：填一次 base_url，保存后整页生效。
 *
 * 打包安装包不烘焙服务器地址——任何人装上即可用，启动时只需指向自己的
 * LambChat 服务端（校验连通后落 localStorage，网络层改写在下次加载生效）。
 * Web/PWA 永不渲染此屏（同源部署无此概念）。
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Server } from "lucide-react";

import { normalizeServerUrl, setStoredServerUrl } from "../../services/api/serverConfig";

export function ServerSetupScreen() {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState("");

  const normalized = normalizeServerUrl(input);

  const handleConnect = async () => {
    if (!normalized || testing) return;
    setTesting(true);
    setError("");
    try {
      // 直连绝对地址探测（此刻网络改写尚未安装/未指向新地址）
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

  return (
    <div className="flex min-h-screen items-center justify-center bg-stone-100 p-6 dark:bg-stone-900">
      <div className="w-full max-w-md rounded-3xl border border-stone-200/70 bg-white/90 p-8 shadow-xl backdrop-blur dark:border-stone-700/60 dark:bg-stone-800/90">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex size-11 items-center justify-center rounded-2xl bg-amber-500/10">
            <Server size={20} className="text-amber-600 dark:text-amber-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-stone-800 dark:text-stone-100">
              {t("serverSetup.title")}
            </h1>
            <p className="mt-0.5 text-xs text-stone-500 dark:text-stone-400">
              {t("serverSetup.desc")}
            </p>
          </div>
        </div>

        <label className="block text-xs font-medium text-stone-500 dark:text-stone-400">
          {t("serverSetup.label")}
        </label>
        <div className="mt-1.5 flex items-center gap-2 rounded-xl border border-stone-300/70 bg-white px-3 py-2.5 focus-within:border-amber-500/60 dark:border-stone-600/70 dark:bg-stone-900/60">
          <Globe size={15} className="shrink-0 text-stone-400" />
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void handleConnect();
            }}
            placeholder="https://chat.example.com"
            spellCheck={false}
            autoComplete="off"
            className="w-full bg-transparent text-sm text-stone-800 outline-none placeholder:text-stone-400 dark:text-stone-100"
          />
        </div>

        {input && !normalized && (
          <p className="mt-2 text-xs text-red-500">{t("serverSetup.invalid")}</p>
        )}
        {error && <p className="mt-2 text-xs text-red-500">{error}</p>}

        <button
          type="button"
          disabled={!normalized || testing}
          onClick={() => void handleConnect()}
          className="mt-5 w-full rounded-xl bg-amber-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {testing ? t("serverSetup.testing") : t("serverSetup.connect")}
        </button>
      </div>
    </div>
  );
}
