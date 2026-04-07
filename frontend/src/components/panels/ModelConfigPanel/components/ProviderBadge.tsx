/**
 * Provider icon badge using theme color
 */
export function ProviderBadge({ provider }: { provider: string }) {
  return (
    <div
      className="flex items-center justify-center w-10 h-10 rounded-xl text-white font-bold text-sm flex-shrink-0"
      style={{
        background: "var(--theme-primary)",
        boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
      }}
    >
      {provider.charAt(0).toUpperCase()}
    </div>
  );
}
