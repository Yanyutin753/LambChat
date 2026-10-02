/** Native-only data-location UI; commands are replaced by the fixture server. */
import { createRoot } from "react-dom/client";
import i18n from "../src/i18n";
import { applyThemeToDocument, isTheme } from "../src/utils/themeDom";
import { SandboxDataLocationCard } from "../src/components/profile/SandboxDataLocationCard";
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
createRoot(document.getElementById("root")!).render(
  <main className="mx-auto h-dvh w-full max-w-xl overflow-y-auto p-4 sm:p-6">
    <h1 className="profile-section-heading font-serif">
      {i18n.t("profile.localSandbox.title")}
    </h1>
    <SandboxDataLocationCard />
  </main>,
);
