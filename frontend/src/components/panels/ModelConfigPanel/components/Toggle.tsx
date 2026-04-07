/**
 * Modern toggle switch component
 */
export function Toggle({
  checked,
  onChange,
  color,
}: {
  checked: boolean;
  onChange: () => void;
  color?: string;
}) {
  const activeColor = color || "var(--theme-primary)";

  return (
    <button
      onClick={onChange}
      className="model-config-toggle relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-all duration-200"
      style={checked ? { background: activeColor } : undefined}
    >
      <span
        className={`model-config-toggle-thumb inline-block h-3.5 w-3.5 transform rounded-full shadow-sm transition-transform duration-200 ${
          checked ? "translate-x-[18px]" : "translate-x-[5px]"
        }`}
      />
    </button>
  );
}
