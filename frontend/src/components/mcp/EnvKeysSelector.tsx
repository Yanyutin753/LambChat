import { useState, useEffect, useRef } from "react";
import { ChevronDown, X, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { envvarApi } from "../../services/api/envvar";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types/auth";

interface EnvKeysSelectorProps {
  selectedKeys: string[];
  onChange: (keys: string[]) => void;
}

export function EnvKeysSelector({
  selectedKeys,
  onChange,
}: EnvKeysSelectorProps) {
  const { t } = useTranslation();
  const { hasAnyPermission } = useAuth();

  const [availableKeys, setAvailableKeys] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!hasAnyPermission([Permission.ENVVAR_READ])) return;
    setLoading(true);
    envvarApi
      .list()
      .then((res) => {
        setAvailableKeys(res.variables.map((v) => v.key).sort());
      })
      .catch(() => {
        setAvailableKeys([]);
      })
      .finally(() => setLoading(false));
  }, [hasAnyPermission]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
        setSearch("");
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isOpen]);

  const filteredKeys = search
    ? availableKeys.filter((k) =>
        k.toLowerCase().includes(search.toLowerCase()),
      )
    : availableKeys;

  const toggleKey = (key: string) => {
    if (selectedKeys.includes(key)) {
      onChange(selectedKeys.filter((k) => k !== key));
    } else {
      onChange([...selectedKeys, key]);
    }
  };

  const removeKey = (key: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(selectedKeys.filter((k) => k !== key));
  };

  return (
    <div ref={dropdownRef} className="relative">
      {/* Selected keys as chips */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="w-full min-h-[38px] rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm cursor-pointer flex flex-wrap items-center gap-1 focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
      >
        {selectedKeys.length === 0 ? (
          <span className="text-stone-400 dark:text-stone-500 text-xs">
            {loading ? "..." : t("mcp.form.envKeysPlaceholder")}
          </span>
        ) : (
          selectedKeys.map((key) => (
            <span
              key={key}
              className="inline-flex items-center gap-0.5 rounded bg-stone-100 dark:bg-stone-700 px-1.5 py-0.5 text-xs font-mono text-stone-700 dark:text-stone-200"
            >
              {key}
              <button
                type="button"
                onClick={(e) => removeKey(key, e)}
                className="ml-0.5 rounded hover:bg-stone-200 dark:hover:bg-stone-600 text-stone-400 hover:text-stone-600 dark:hover:text-stone-300"
              >
                <X size={12} />
              </button>
            </span>
          ))
        )}
        <ChevronDown
          size={14}
          className={`ml-auto text-stone-400 dark:text-stone-500 transition-transform ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute z-10 mt-1 w-full rounded-lg border border-stone-200 bg-white shadow-lg dark:border-stone-700 dark:bg-stone-800">
          {/* Search */}
          <div className="p-2 border-b border-stone-100 dark:border-stone-700">
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-stone-50 dark:bg-stone-700/50">
              <Search
                size={12}
                className="text-stone-400 dark:text-stone-500"
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t("mcp.form.envKeysSearch")}
                className="flex-1 bg-transparent text-xs text-stone-700 dark:text-stone-200 placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none"
                autoFocus
              />
            </div>
          </div>

          {/* Options */}
          <div className="max-h-48 overflow-y-auto p-1">
            {loading ? (
              <div className="py-3 text-center text-xs text-stone-400 dark:text-stone-500">
                ...
              </div>
            ) : availableKeys.length === 0 ? (
              <div className="py-3 text-center text-xs text-stone-400 dark:text-stone-500">
                {t("mcp.form.noEnvVars")}
              </div>
            ) : filteredKeys.length === 0 ? (
              <div className="py-3 text-center text-xs text-stone-400 dark:text-stone-500">
                {t("mcp.form.noMatchingKeys")}
              </div>
            ) : (
              filteredKeys.map((key) => (
                <label
                  key={key}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:bg-stone-50 dark:hover:bg-stone-700/50"
                >
                  <input
                    type="checkbox"
                    checked={selectedKeys.includes(key)}
                    onChange={() => toggleKey(key)}
                    className="rounded border-stone-300 dark:border-stone-600 text-amber-500 focus:ring-amber-400"
                  />
                  <code className="text-xs font-mono text-stone-700 dark:text-stone-200">
                    {key}
                  </code>
                </label>
              ))
            )}
          </div>

          {selectedKeys.length > 0 && (
            <div className="border-t border-stone-100 dark:border-stone-700 p-2">
              <button
                type="button"
                onClick={() => onChange([])}
                className="w-full text-center text-xs text-stone-400 hover:text-red-500 dark:hover:text-red-400 transition-colors"
              >
                {t("mcp.form.clearAll")}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
