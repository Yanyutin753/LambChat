import { readFileSync } from "node:fs";
import { join } from "node:path";

const componentSource = readFileSync(
  join(import.meta.dirname, "../PersonaEditorSkillSelector.tsx"),
  "utf8",
);

const personaCss = readFileSync(
  join(import.meta.dirname, "../../../styles/persona.css"),
  "utf8",
);

test("skill dropdown clear action renders as a labeled soft button", () => {
  expect(componentSource).toMatch(
    /className="ppe-skill-dropdown__clear-all"[\s\S]*>\s*\{\s*t\("common\.clearAll", "清除全部"\)\s*\}\s*<\/button>/,
  );
  expect(componentSource).not.toMatch(
    /className="ppe-skill-dropdown__clear-all"[\s\S]{0,260}<X size=\{14\}/,
  );
});

test("skill dropdown loads more skills when scrolled near the bottom", () => {
  expect(componentSource).toMatch(/PERSONA_SKILL_PAGE_SIZE/);
  expect(componentSource).toMatch(/appendPages: true/);
  expect(componentSource).toMatch(
    /const distanceToBottom =\s*target\.scrollHeight - target\.scrollTop - target\.clientHeight;/,
  );
  expect(componentSource).toMatch(/onScroll=\{handleSkillListScroll\}/);
  expect(componentSource).toMatch(/setSkillPage\(\(page\) => page \+ 1\)/);
});

test("skill dropdown header uses the soft professional search treatment", () => {
  expect(personaCss).toMatch(
    /\.ppe-skill-search\s*\{[\s\S]*border:\s*1px solid transparent;/,
  );
  expect(personaCss).toMatch(
    /\.ppe-skill-search\s*\{[\s\S]*height:\s*2\.25rem;/,
  );
  expect(personaCss).toMatch(
    /\.ppe-skill-dropdown__clear-all\s*\{[\s\S]*padding:\s*0 0\.625rem;/,
  );
  expect(personaCss).toMatch(
    /\.ppe-skill-dropdown__clear-all\s*\{[\s\S]*font-weight:\s*600;/,
  );
  expect(personaCss).toMatch(
    /\.ppe-skill-dropdown__loading\s*\{[\s\S]*display:\s*flex;/,
  );
});

test("skill dropdown options use structured professional rows", () => {
  expect(componentSource).toMatch(/className=\{`ppe-skill-option \$\{/);
  expect(componentSource).toMatch(/className="ppe-skill-option__check-ring"/);
  expect(componentSource).toMatch(/className="ppe-skill-option__check-icon"/);
  expect(componentSource).toMatch(/className="ppe-skill-option__plus-icon"/);
  expect(personaCss).toMatch(
    /\.ppe-skill-option\s*\{[\s\S]*min-height:\s*2\.75rem;/,
  );
  expect(personaCss).toMatch(
    /\.ppe-skill-option--selected\s+\.ppe-skill-option__check-ring\s*\{[\s\S]*border-color:\s*var\(--theme-text-secondary\);/,
  );
});
