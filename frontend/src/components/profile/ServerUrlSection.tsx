/**
 * 设置页"服务器地址"分区（挂载点按 isNativeAppRuntime() 门控，仅原生客户端渲染）。
 *
 * 构建期烘焙了 VITE_API_BASE 的包首启不会出 ServerSetupScreen（needsServerSetup
 * 为 false）——本分区是安装后唯一的改址入口：展示当前生效基址（运行时配置优先、
 * 烘焙值兜底），支持修改（探活 ``/health`` 后落 localStorage 并整页刷新，复用
 * 首启屏的网络改写生效链路）与恢复默认（清除运行时覆盖，回到烘焙值）。
 */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Pencil, RotateCcw } from "lucide-react";

import {
  clearStoredServerUrl,
  effectiveApiBase,
  getStoredServerUrl,
  normalizeServerUrl,
} from "../../services/api/serverConfig";
import { useServerConnection } from "../../hooks/useServerConnection";
import { Button } from "../common/ui/Button";
import { Input } from "../common/ui/Input";

export function ServerUrlSection() {
  const { t } = useTranslation();
  // 展示值：运行时配置优先、烘焙值兜底；web 同源场景回退 origin（与
  // SandboxMachinesCard 的展示口径一致——本组件原生端才挂载，兜底仅测试触达）
  const current = effectiveApiBase() || window.location.origin;
  const hasOverride = getStoredServerUrl() !== null;

  const [editing, setEditing] = useState(false);
  const [input, setInput] = useState("");
  const { testing, error, connect, cancel } = useServerConnection();
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const sectionRef = useRef<HTMLDivElement>(null);
  const wasEditing = useRef(false);
  useEffect(() => {
    const active = document.activeElement;
    if (editing) {
      if (
        testing ||
        !wasEditing.current ||
        formRef.current?.contains(active) ||
        active === document.body ||
        !active?.isConnected ||
        active.matches(":disabled")
      )
        (testing ? formRef : inputRef).current?.focus();
    } else if (wasEditing.current)
      sectionRef.current
        ?.querySelector<HTMLButtonElement>("[data-server-change]")
        ?.focus();
    wasEditing.current = editing;
  }, [editing, testing]);

  const normalized = normalizeServerUrl(input);

  const startEdit = () => {
    setInput(current);
    cancel();
    setEditing(true);
  };

  const cancelEdit = () => {
    cancel();
    setEditing(false);
  };

  const handleReset = () => {
    clearStoredServerUrl();
    window.location.reload();
  };

  return (
    <div ref={sectionRef} className="profile-section">
      <div className="flex items-center gap-2 mb-3">
        <Globe size={13} className="text-theme-primary" aria-hidden="true" />
        <h3 className="profile-section-heading font-serif">
          {t("profile.serverUrl.title")}
        </h3>
      </div>
      <p className="text-12 text-theme-text-secondary leading-relaxed">
        {t("profile.serverUrl.desc")}
      </p>

      {editing ? (
        <form
          ref={formRef}
          tabIndex={-1}
          aria-label={t("serverSetup.title")}
          aria-busy={testing}
          className="mt-3 space-y-2 outline-none"
          onSubmit={(event) => {
            event.preventDefault();
            void connect(input);
          }}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing || event.keyCode === 229) return;
            if (event.key === "Escape") {
              event.preventDefault();
              event.stopPropagation();
              cancelEdit();
            }
          }}
        >
          <label
            htmlFor={id}
            className="block text-12 font-medium text-theme-text-secondary"
          >
            {t("serverSetup.label")}
          </label>
          <Input
            id={id}
            ref={inputRef}
            type="text"
            inputMode="url"
            autoCapitalize="none"
            autoComplete="url"
            spellCheck={false}
            disabled={testing}
            value={input}
            onChange={(e) => {
              cancel();
              setInput(e.target.value);
            }}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                (e.nativeEvent.isComposing || e.keyCode === 229)
              )
                e.preventDefault();
            }}
            aria-describedby={
              error || (input.trim() && !normalized) ? `${id}-error` : undefined
            }
            error={Boolean(error || (input.trim() && !normalized))}
            className="max-sm:!min-h-11 max-sm:!text-16 [@media(pointer:coarse)]:!min-h-11 [@media(pointer:coarse)]:!text-16"
          />
          {input.trim() !== "" && !normalized && (
            <p id={`${id}-error`} className="text-12 text-theme-error">
              {t("serverSetup.invalid")}
            </p>
          )}
          {error && (
            <p
              id={`${id}-error`}
              className="text-12 text-theme-error"
              role="alert"
            >
              {error}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              variant="primary"
              loading={testing}
              disabled={!normalized || testing}
              className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
            >
              {testing ? t("serverSetup.testing") : t("serverSetup.connect")}
            </Button>
            <Button
              onClick={cancelEdit}
              className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
            >
              {t("profile.serverUrl.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <span
            className="min-w-0 font-mono text-13 text-theme-text [overflow-wrap:anywhere]"
            title={current}
            data-server-url-current
          >
            {current}
          </span>
          <span className="flex shrink-0 flex-wrap gap-2">
            <Button
              size="sm"
              data-server-change
              onClick={startEdit}
              leftIcon={<Pencil size={13} aria-hidden="true" />}
              className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
            >
              {t("profile.serverUrl.change")}
            </Button>
            {hasOverride && (
              <Button
                size="sm"
                onClick={handleReset}
                title={t("profile.serverUrl.resetTitle")}
                leftIcon={<RotateCcw size={13} aria-hidden="true" />}
                className="max-sm:!min-h-11 [@media(pointer:coarse)]:!min-h-11"
              >
                {t("profile.serverUrl.reset")}
              </Button>
            )}
          </span>
        </div>
      )}
    </div>
  );
}

export default ServerUrlSection;
