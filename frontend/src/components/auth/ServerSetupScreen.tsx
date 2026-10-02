/**
 * 打包壳首启服务器配置：填一次 base_url，保存后整页生效。
 *
 * 打包安装包不烘焙服务器地址——任何人装上即可用，启动时只需指向自己的
 * LambChat 服务端（校验连通后落 localStorage，网络层改写在下次加载生效）。
 * Web/PWA 永不渲染此屏（同源部署无此概念）。
 */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Globe, Server } from "lucide-react";

import { normalizeServerUrl } from "../../services/api/serverConfig";
import { useServerConnection } from "../../hooks/useServerConnection";
import { Button } from "../common/ui/Button";
import { Input } from "../common/ui/Input";

export function ServerSetupScreen() {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const { testing, error, connect, cancel } = useServerConnection();
  const id = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const wasTesting = useRef(false);
  useEffect(() => {
    const active = document.activeElement;
    if (testing) formRef.current?.focus();
    else if (
      wasTesting.current &&
      (formRef.current?.contains(active) ||
        active === document.body ||
        !active?.isConnected ||
        active.matches(":disabled"))
    )
      inputRef.current?.focus();
    wasTesting.current = testing;
  }, [testing]);

  const normalized = normalizeServerUrl(input);

  return (
    <main className="flex h-[calc(100svh-var(--titlebar-inset,0px))] h-[calc(100dvh-var(--titlebar-inset,0px))] overflow-y-auto bg-theme-bg-card px-4 py-8 sm:px-6">
      <form
        ref={formRef}
        tabIndex={-1}
        aria-label={t("serverSetup.title")}
        aria-busy={testing}
        className="m-auto w-full max-w-md shrink-0 outline-none"
        onSubmit={(event) => {
          event.preventDefault();
          void connect(input);
        }}
      >
        <header className="mb-6">
          <Server
            size={24}
            className="mb-4 text-theme-text-secondary"
            aria-hidden="true"
          />
          <h1 className="text-24 font-serif font-semibold text-theme-text">
            {t("serverSetup.title")}
          </h1>
          <p className="mt-2 text-14 leading-relaxed text-theme-text-secondary">
            {t("serverSetup.desc")}
          </p>
        </header>

        <label
          htmlFor={id}
          className="mb-2 block text-13 font-medium text-theme-text-secondary"
        >
          {t("serverSetup.label")}
        </label>
        <Input
          id={id}
          ref={inputRef}
          inputMode="url"
          autoCapitalize="none"
          leadingIcon={<Globe size={16} aria-hidden="true" />}
          value={input}
          disabled={testing}
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
          placeholder="https://chat.example.com"
          spellCheck={false}
          autoComplete="off"
          aria-describedby={
            error || (input.trim() && !normalized) ? `${id}-error` : undefined
          }
          error={Boolean(error || (input.trim() && !normalized))}
          className="!min-h-11 max-sm:!text-16 [@media(pointer:coarse)]:!text-16"
        />

        {input.trim() && !normalized && (
          <p id={`${id}-error`} className="mt-2 text-12 text-theme-error">
            {t("serverSetup.invalid")}
          </p>
        )}
        {error && (
          <p
            id={`${id}-error`}
            role="alert"
            className="mt-2 text-12 text-theme-error"
          >
            {error}
          </p>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          <Button
            type="submit"
            variant="primary"
            loading={testing}
            disabled={!normalized || testing}
            className="!min-h-11 min-w-0 flex-1 [&_.ui-button__label]:!whitespace-normal"
          >
            {testing ? t("serverSetup.testing") : t("serverSetup.connect")}
          </Button>
          {testing && (
            <Button onClick={cancel} className="!min-h-11">
              {t("common.cancel")}
            </Button>
          )}
        </div>
      </form>
    </main>
  );
}
