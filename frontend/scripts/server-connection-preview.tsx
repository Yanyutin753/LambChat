/** Fixture entry only: native-only forms without a native bridge or real API. */
import { createRoot } from "react-dom/client";
import i18n from "../src/i18n";
import { applyThemeToDocument, isTheme } from "../src/utils/themeDom";
import { ServerSetupScreen } from "../src/components/auth/ServerSetupScreen";
import { ServerUrlSection } from "../src/components/profile/ServerUrlSection";
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
  params.get("view") === "setup" ? (
    <ServerSetupScreen />
  ) : (
    <main className="mx-auto w-full max-w-xl p-4 sm:p-6">
      <ServerUrlSection />
    </main>
  ),
);
