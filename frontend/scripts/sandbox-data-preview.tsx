/** Native-only data-location UI; commands are replaced by the fixture server. */
import { createRoot } from "react-dom/client";
import { useState } from "react";
import i18n from "../src/i18n";
import { applyThemeToDocument, isTheme } from "../src/utils/themeDom";
import { SandboxDataLocationCard } from "../src/components/profile/SandboxDataLocationCard";
import { LocalSandboxSection } from "../src/components/profile/LocalSandboxSection";
import { MemoryRouter } from "react-router-dom";
import { Button } from "../src/components/common/ui/Button";
import "../src/fonts.css";
import "../src/styles/tailwind.css";
import "../src/styles/tokens.css";
import "../src/styles/base.css";
import "../src/styles/components.css";
import "../src/styles/animations.css";
import "../src/components/profile/profile.css";

void import("../src/fonts-cjk");
const params = new URLSearchParams(location.search);
const theme = params.get("theme");
applyThemeToDocument(isTheme(theme) ? theme : "light");
await i18n.changeLanguage(params.get("lang") || "zh");
export function Preview() {
  const [open, setOpen] = useState(true);
  return (
    <main
      className={`mx-auto w-full overflow-y-auto p-4 sm:p-6 ${params.has("shell") ? "max-w-3xl" : "max-w-xl"}`}
      style={{ height: "100dvh" }}
    >
      <h1 className="profile-section-heading font-serif">
        {i18n.t(
          params.has("shell")
            ? "profile.preferences"
            : "profile.localSandbox.title",
        )}
      </h1>
      {params.has("reopen") && (
        <Button
          variant="ghost"
          size="sm"
          aria-expanded={open}
          onClick={() => setOpen(!open)}
        >
          {i18n.t(open ? "common.close" : "profile.preferences")}
        </Button>
      )}
      {open &&
        (params.has("shell") ? (
          <MemoryRouter>
            <LocalSandboxSection embedded />
          </MemoryRouter>
        ) : (
          <SandboxDataLocationCard />
        ))}
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<Preview />);
