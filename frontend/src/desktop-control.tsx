import { createRoot } from "react-dom/client";
import { DesktopControl } from "./components/desktop/DesktopControl";
import { i18nReady } from "./i18n";
import {
  applyThemeToDocument,
  getInitialThemePreference,
} from "./utils/themeDom";
import "./styles/tokens.css";
const overlay =
  new URLSearchParams(location.search).get("surface") === "overlay";
applyThemeToDocument(getInitialThemePreference());
// Native transparency also requires transparent HTML and body backgrounds.
if (overlay) {
  document.documentElement.style.backgroundColor = "transparent";
  document.body.style.backgroundColor = "transparent";
}
document.body.style.margin = "0";
void i18nReady.then(() =>
  createRoot(document.getElementById("root")!).render(
    <DesktopControl overlay={overlay} />,
  ),
);
