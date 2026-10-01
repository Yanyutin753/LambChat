import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";

// Layering contract for the expanded composer band: body-level pickers that
// can be opened from the expanded composer (z-280) must sit above it but
// below the dialog band (z-299+).
const personaSelectorSource = readFileSync(
  join(import.meta.dirname, "../PersonaPresetSelector.tsx"),
  "utf8",
);

const teamPickerSource = readFileSync(
  join(import.meta.dirname, "../../team/TeamPickerModal.tsx"),
  "utf8",
);

test("persona picker overlay sits above the expanded composer band", () => {
  expect(personaSelectorSource).toContain("<ModalSurface");
  expect(personaSelectorSource).not.toContain("z-[250]");
});

test("team picker overlay sits above the expanded composer band", () => {
  expect(teamPickerSource).toContain("<ModalSurface");
  expect(teamPickerSource).not.toContain("z-[250]");
});

test("shared modal layer sits above the expanded composer", () => {expect(readFileSync(join(import.meta.dirname,"../../common/modalSurface.css"),"utf8")).toMatch(/z-index:\s*300/);});
