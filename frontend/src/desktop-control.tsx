import { createRoot } from "react-dom/client";
import { DesktopControl } from "./components/desktop/DesktopControl";
import { i18nReady } from "./i18n";
import {
  applyThemeToDocument,
  getInitialThemePreference,
} from "./utils/themeDom";
import "./styles/tokens.css";
applyThemeToDocument(getInitialThemePreference());
document.body.style.margin = "0";
void i18nReady.then(() =>
  createRoot(document.getElementById("root")!).render(
    <DesktopControl
      overlay={
        new URLSearchParams(location.search).get("surface") === "overlay"
      }
    />,
  ),
);
