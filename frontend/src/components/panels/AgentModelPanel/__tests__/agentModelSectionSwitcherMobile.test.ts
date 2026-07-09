import { readFileSync } from "node:fs";
const panelSource = readFileSync(
  new URL("../AgentModelPanel.tsx", import.meta.url),
  "utf8",
);
const componentsCss = readFileSync(
  new URL("../../../../styles/components.css", import.meta.url),
  "utf8",
);

test("agent model section switcher keeps a compact segmented layout in the mobile header menu", () => {
  expect(panelSource).toMatch(/agent-model-section-switcher/);
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item > \.agent-model-section-switcher\s*\{[\s\S]*?display:\s*grid;[\s\S]*?width:\s*min\(18rem,\s*calc\(100vw - 2rem\)\);/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item > \.agent-model-section-switcher > button\s*\{[\s\S]*?height:\s*2\.625rem;[\s\S]*?justify-content:\s*center;/,
  );
  expect(componentsCss).toMatch(
    /\.panel-header__mobile-menu-item[\s\S]*?> \.agent-model-section-switcher[\s\S]*?> button[\s\S]*?> span\s*\{[\s\S]*?overflow:\s*hidden;[\s\S]*?text-overflow:\s*ellipsis;/,
  );
});
