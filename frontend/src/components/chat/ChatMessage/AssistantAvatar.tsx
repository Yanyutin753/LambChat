import { useState, useEffect } from "react";
import {
  getPersonaAvatarIcon,
  isPersonaImageAvatar,
  type PersonaAvatarIconKey,
} from "../../persona/personaAvatar";
import {
  Code2,
  Database,
  GraduationCap,
  Package,
  PenTool,
  Shield,
  Sparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<PersonaAvatarIconKey, LucideIcon> = {
  sparkles: Sparkles,
  academic: GraduationCap,
  coding: Code2,
  writing: PenTool,
  security: Shield,
  data: Database,
  productivity: Zap,
  general: Package,
};

const ICON_SRC = "/icons/icon.svg";
let cachedDataUrl: string | null = null;
let pending: Promise<string> | null = null;

function loadDataUrl(): Promise<string> {
  if (cachedDataUrl) return Promise.resolve(cachedDataUrl);
  if (pending) return pending;
  pending = fetch(ICON_SRC)
    .then((r) => r.text())
    .then((svg) => {
      cachedDataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
        svg,
      )}`;
      pending = null;
      return cachedDataUrl;
    })
    .catch(() => {
      pending = null;
      return ICON_SRC;
    });
  return pending;
}

// Pre-fetch on module load
loadDataUrl();

export function AssistantAvatar({
  className,
  personaAvatar,
  personaSize = 22,
}: {
  className?: string;
  personaAvatar?: string | null;
  personaSize?: number;
}) {
  const [src, setSrc] = useState(ICON_SRC);

  useEffect(() => {
    loadDataUrl().then(setSrc);
  }, []);

  const builtInIcon = getPersonaAvatarIcon(personaAvatar);
  if (builtInIcon) {
    const Icon = ICONS[builtInIcon.key];
    return (
      <div
        className={className}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: builtInIcon.bg,
          borderRadius: "50%",
          width: personaSize + 6,
          height: personaSize + 6,
        }}
      >
        <Icon size={personaSize} style={{ color: builtInIcon.color }} />
      </div>
    );
  }

  if (isPersonaImageAvatar(personaAvatar)) {
    return (
      <img
        src={personaAvatar}
        alt="Assistant"
        width={personaSize + 6}
        height={personaSize + 6}
        className={className}
      />
    );
  }

  return (
    <img
      src={src}
      alt="Assistant"
      width={28}
      height={28}
      className={className}
    />
  );
}
