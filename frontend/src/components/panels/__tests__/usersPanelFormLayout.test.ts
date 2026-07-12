import { readFileSync } from "node:fs";
import { join } from "node:path";

const usersPanelSource = readFileSync(
  join(import.meta.dirname, "../UsersPanel.tsx"),
  "utf8",
);

const componentsCss = readFileSync(
  join(import.meta.dirname, "../../../styles/components.css"),
  "utf8",
);

test("user form icon inputs use shared Input leading icon spacing", () => {
  const leadingIconMatches = usersPanelSource.match(/leadingIcon=\{/g);

  expect(leadingIconMatches?.length).toBe(3);
  expect(usersPanelSource).toMatch(/import \{[\s\S]*Input[\s\S]*\}/);
  expect(usersPanelSource).not.toMatch(/className="glass-input/);
  expect(componentsCss).toMatch(
    /\.ui-input--with-leading-icon[\s\S]*?\.glass-input\.es-input\.es-input--with-leading-icon\s*\{[\s\S]*padding-left:\s*2\.5rem;/,
  );
});
