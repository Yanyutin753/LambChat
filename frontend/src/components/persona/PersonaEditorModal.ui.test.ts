import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const componentSource = readFileSync(
  join(import.meta.dirname, "PersonaEditorModal.tsx"),
  "utf8",
);

const personaCss = readFileSync(
  join(import.meta.dirname, "../../styles/persona.css"),
  "utf8",
);

test("skill dropdown clear action renders as a labeled soft button", () => {
  assert.match(
    componentSource,
    /className="ppe-skill-dropdown__clear-all"[\s\S]*>\s*\{\s*t\("personaPresets\.clearSkills", "清空"\)\s*\}\s*<\/button>/,
  );
  assert.doesNotMatch(
    componentSource,
    /className="ppe-skill-dropdown__clear-all"[\s\S]{0,260}<X size=\{14\}/,
  );
});

test("skill dropdown header uses the soft professional search treatment", () => {
  assert.match(
    personaCss,
    /\.ppe-skill-search\s*\{[\s\S]*border:\s*1px solid transparent;/,
  );
  assert.match(
    personaCss,
    /\.ppe-skill-search\s*\{[\s\S]*height:\s*2\.375rem;/,
  );
  assert.match(
    personaCss,
    /\.ppe-skill-dropdown__clear-all\s*\{[\s\S]*padding:\s*0 0\.625rem;/,
  );
  assert.match(
    personaCss,
    /\.ppe-skill-dropdown__clear-all\s*\{[\s\S]*font-weight:\s*600;/,
  );
});

test("skill dropdown options use structured professional rows", () => {
  assert.match(componentSource, /className="ppe-skill-option__content"/);
  assert.match(componentSource, /className="ppe-skill-option__meta"/);
  assert.match(componentSource, /className="ppe-skill-option__action"/);
  assert.match(
    personaCss,
    /\.ppe-skill-option\s*\{[\s\S]*min-height:\s*3\.125rem;/,
  );
  assert.match(
    personaCss,
    /\.ppe-skill-option__content\s*\{[\s\S]*display:\s*grid;/,
  );
  assert.match(
    personaCss,
    /\.ppe-skill-option--selected\s+\.ppe-skill-option__action\s*\{[\s\S]*background:\s*rgba\(239, 68, 68, 0\.1\);/,
  );
});
