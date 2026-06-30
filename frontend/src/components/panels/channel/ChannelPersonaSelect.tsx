/**
 * Persona preset selector for channel configuration.
 * Channels can bind a persona so messages from that channel use the same role.
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown, Search, UserRound, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { personaPresetApi } from "../../../services/api/personaPreset";
import type { PersonaPreset } from "../../../types/personaPreset";
import {
  PersonaAvatarIcon,
  PersonaAvatarImage,
} from "../../persona/PersonaAvatarIcon";
import { isPersonaImageAvatar } from "../../persona/personaAvatar";
import { PanelSearchInput } from "../../common/PanelSearchInput";

const PAGE_LIMIT = 20;

interface ChannelPersonaSelectProps {
  value: string | null | undefined;
  onChange: (personaPresetId: string | null) => void;
}

function PersonaPresetIcon({ preset }: { preset: PersonaPreset }) {
  const [imageFailed, setImageFailed] = useState(false);
  const primaryTag = preset.tags?.[0];
  const showImage =
    isPersonaImageAvatar(preset.avatar) && imageFailed === false;

  return (
    <span className="team-toolbar-avatar" title={preset.name}>
      {showImage ? (
        <PersonaAvatarImage
          avatar={preset.avatar}
          alt=""
          className="scb__avatar-img"
          onError={() => setImageFailed(true)}
        />
      ) : (
        <PersonaAvatarIcon
          avatar={preset.avatar}
          primaryTag={primaryTag}
          size={14}
        />
      )}
    </span>
  );
}

export function ChannelPersonaSelect({
  value,
  onChange,
}: ChannelPersonaSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [presets, setPresets] = useState<PersonaPreset[]>([]);
  const [total, setTotal] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});
  const ref = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const selected = useMemo(
    () => presets.find((preset) => preset.id === value) || null,
    [presets, value],
  );
  const hasMore = presets.length < total;

  const fetchPresets = useCallback(
    async (nextSkip: number, mode: "replace" | "append") => {
      if (mode === "append") {
        setIsLoadingMore(true);
      } else {
        setIsLoading(true);
      }
      try {
        const response = await personaPresetApi.list({
          status: "published",
          q: debouncedSearch.trim() || undefined,
          skip: nextSkip,
          limit: PAGE_LIMIT,
        });
        setTotal(response.total);
        setPresets((prev) => {
          if (mode === "replace") return response.presets;
          const existingIds = new Set(prev.map((preset) => preset.id));
          return [
            ...prev,
            ...response.presets.filter((preset) => !existingIds.has(preset.id)),
          ];
        });
      } catch {
        if (mode === "replace") {
          setPresets([]);
          setTotal(0);
        }
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [debouncedSearch],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    if (!open) return;
    void fetchPresets(0, "replace");
  }, [fetchPresets, open]);

  useEffect(() => {
    if (!open) return;
    searchRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        ref.current &&
        !ref.current.contains(target) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = Math.max(rect.width, 220);
    const left = Math.max(16, Math.min(rect.left, vw - w - 16));
    const spaceBelow = vh - rect.bottom - 16;
    const spaceAbove = rect.top - 16;
    const preferBelow = spaceBelow >= 260 || spaceBelow >= spaceAbove;

    setDropdownStyle({
      position: "fixed",
      top: preferBelow ? rect.bottom + 4 : undefined,
      bottom: preferBelow ? undefined : vh - rect.top + 4,
      left,
      width: w,
      zIndex: 9999,
    });
  }, [open]);

  const handleScroll = useCallback(
    (event: React.UIEvent<HTMLDivElement>) => {
      if (!hasMore || isLoading || isLoadingMore) return;
      const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
      if (scrollHeight - scrollTop - clientHeight < 80) {
        void fetchPresets(presets.length, "append");
      }
    },
    [fetchPresets, hasMore, isLoading, isLoadingMore, presets.length],
  );

  const displayText = selected
    ? selected.name
    : t("channel.defaultPersona", "不使用角色");

  return (
    <div className="es-field">
      <label className="es-label">
        <div className="flex items-center gap-1.5">
          <UserRound size={14} />
          {t("channel.persona", "角色")}
        </div>
      </label>
      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="glass-input es-select-btn"
        >
          {selected && <PersonaPresetIcon preset={selected} />}
          <span className="truncate">{displayText}</span>
          <ChevronDown
            size={15}
            className="shrink-0 text-[var(--theme-text-secondary)] transition-transform duration-200"
            style={{ transform: open ? "rotate(180deg)" : undefined }}
          />
        </button>
      </div>

      {open &&
        createPortal(
          <div
            ref={dropdownRef}
            className="glass-select-dropdown channel-persona-select__dropdown"
            style={dropdownStyle}
          >
            <div className="channel-persona-select__search">
              <Search
                size={14}
                className="shrink-0 text-[var(--theme-text-secondary)]"
              />
              <PanelSearchInput
                ref={searchRef}
                type="search"
                value={searchQuery}
                onValueChange={setSearchQuery}
                placeholder={t("personaPresets.search", "搜索角色")}
                className="channel-persona-select__search-input"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery("")}
                  className="channel-persona-select__search-clear"
                  aria-label={t("common.clear", "清除")}
                >
                  <X size={13} />
                </button>
              )}
            </div>

            <div
              className="channel-persona-select__list"
              onScroll={handleScroll}
            >
              <button
                type="button"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
                className={`glass-select-option ${!value ? "active" : ""}`}
              >
                {!value && (
                  <Check size={14} className="glass-select-option-check" />
                )}
                <span className="glass-select-option-label">
                  {t("channel.clearPersona", "不使用角色")}
                </span>
              </button>

              {presets.map((preset) => {
                const active = preset.id === value;
                return (
                  <button
                    key={preset.id}
                    type="button"
                    onClick={() => {
                      onChange(preset.id);
                      setOpen(false);
                    }}
                    className={`glass-select-option ${active ? "active" : ""}`}
                  >
                    {active && (
                      <Check size={14} className="glass-select-option-check" />
                    )}
                    <span className="flex min-w-0 items-center gap-2">
                      <PersonaPresetIcon preset={preset} />
                      <span className="truncate">{preset.name}</span>
                    </span>
                  </button>
                );
              })}

              {isLoading && presets.length === 0 && (
                <div className="channel-persona-select__state">
                  {t("common.loading", "Loading...")}
                </div>
              )}
              {!isLoading && presets.length === 0 && (
                <div className="channel-persona-select__state">
                  {t("personaPresets.noMatch", "没有匹配的角色")}
                </div>
              )}
              {isLoadingMore && (
                <div className="channel-persona-select__state">
                  {t("common.loading", "Loading...")}
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}

      <p className="es-hint">
        {t("channel.personaHint", "选择这个渠道收到消息时使用的角色预设。")}
      </p>
    </div>
  );
}
