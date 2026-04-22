import { useState, useEffect, useRef } from "react";
import { ChevronDown, X, Search, Shield } from "lucide-react";
import { useTranslation } from "react-i18next";
import { roleApi } from "../../services/api/role";

interface RoleSelectorProps {
  selectedRoles: string[];
  onChange: (roles: string[]) => void;
}

interface RoleInfo {
  name: string;
  description?: string;
  is_system: boolean;
}

export function RoleSelector({
  selectedRoles,
  onChange,
}: RoleSelectorProps) {
  const { t } = useTranslation();

  const [availableRoles, setAvailableRoles] = useState<RoleInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    roleApi
      .list()
      .then((roles) => {
        setAvailableRoles(
          roles.map((r) => ({
            name: r.name,
            description: r.description,
            is_system: r.is_system,
          })),
        );
      })
      .catch(() => setAvailableRoles([]))
      .finally(() => setLoading(false));
  }, []);

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

  const filteredRoles = search
    ? availableRoles.filter((r) =>
        r.name.toLowerCase().includes(search.toLowerCase()),
      )
    : availableRoles;

  const toggleRole = (name: string) => {
    if (selectedRoles.includes(name)) {
      onChange(selectedRoles.filter((r) => r !== name));
    } else {
      onChange([...selectedRoles, name]);
    }
  };

  const removeRole = (name: string, e: React.MouseEvent) => {
    e.stopPropagation();
    onChange(selectedRoles.filter((r) => r !== name));
  };

  return (
    <div ref={dropdownRef} className="relative">
      {/* Selected roles as chips */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="w-full min-h-[38px] rounded-lg border border-stone-200 bg-white px-2 py-1.5 text-sm cursor-pointer flex flex-wrap items-center gap-1 focus:border-stone-500 focus:outline-none focus:ring-1 focus:ring-stone-500 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:focus:border-amber-500 dark:focus:ring-amber-500"
      >
        {selectedRoles.length === 0 ? (
          <span className="text-stone-400 dark:text-stone-500 text-xs">
            {loading ? "..." : t("mcp.form.allRoles")}
          </span>
        ) : (
          selectedRoles.map((name) => (
            <span
              key={name}
              className="inline-flex items-center gap-0.5 rounded bg-blue-100 dark:bg-blue-900/50 px-1.5 py-0.5 text-xs text-blue-700 dark:text-blue-300"
            >
              <Shield size={10} />
              {name}
              <button
                type="button"
                onClick={(e) => removeRole(name, e)}
                className="ml-0.5 rounded hover:bg-blue-200 dark:hover:bg-blue-800 text-blue-400 hover:text-blue-600 dark:hover:text-blue-200"
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
                placeholder={t("mcp.form.searchRoles")}
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
            ) : availableRoles.length === 0 ? (
              <div className="py-3 text-center text-xs text-stone-400 dark:text-stone-500">
                {t("mcp.form.noRoles")}
              </div>
            ) : filteredRoles.length === 0 ? (
              <div className="py-3 text-center text-xs text-stone-400 dark:text-stone-500">
                {t("mcp.form.noMatchingRoles")}
              </div>
            ) : (
              filteredRoles.map((role) => (
                <label
                  key={role.name}
                  className="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:bg-stone-50 dark:hover:bg-stone-700/50"
                >
                  <input
                    type="checkbox"
                    checked={selectedRoles.includes(role.name)}
                    onChange={() => toggleRole(role.name)}
                    className="rounded border-stone-300 dark:border-stone-600 text-amber-500 focus:ring-amber-400"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-medium text-stone-700 dark:text-stone-200">
                      {role.name}
                    </span>
                    {role.description && (
                      <span className="ml-1.5 text-[10px] text-stone-400 dark:text-stone-500 truncate">
                        {role.description}
                      </span>
                    )}
                  </div>
                  {role.is_system && (
                    <span className="text-[9px] px-1 py-0.5 rounded bg-stone-100 dark:bg-stone-700 text-stone-400 dark:text-stone-500">
                      {t("mcp.card.system")}
                    </span>
                  )}
                </label>
              ))
            )}
          </div>

          {selectedRoles.length > 0 && (
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
