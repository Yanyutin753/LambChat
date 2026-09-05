import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const read = (rel: string) => readFileSync(resolve(__dirname, rel), "utf8");

// Touch devices never show native title attributes; every icon-only affordance
// in the sidebar must surface its label through the shared Tooltip instead.
describe("sidebar touch tooltips", () => {
  it("rail buttons use Tooltip instead of native titles", () => {
    const source = read("../../panels/SidebarParts/SidebarRail.tsx");
    expect(source).toMatch(/from "\.\.\/\.\.\/common\/Tooltip"/);
    expect(source).toMatch(/<Tooltip content=\{t\(/);
    expect(source).not.toMatch(/title=\{t\(/);
  });
  it("session list header and toolbar buttons use Tooltip instead of native titles", () => {
    const source = read("../../panels/SidebarParts/SessionListContent.tsx");
    expect(source).toMatch(/from "\.\.\/\.\.\/common\/Tooltip"/);
    expect(source).toMatch(/<Tooltip content=\{t\(/);
    expect(source).not.toMatch(/title=\{t\(/);
  });
  it("project item icon affordances use Tooltip instead of native titles", () => {
    const source = read("../ProjectItem.tsx");
    expect(source).toMatch(/from "\.\.\/common\/Tooltip"/);
    expect(source).toMatch(/open=\{isTouched && !isMenuOpen\}/);
    expect(source).not.toMatch(/title=\{t\(/);
  });
  it("session item more button uses Tooltip instead of a native title", () => {
    const source = read("../SessionItem.tsx");
    expect(source).toMatch(/open=\{isTouched && !isMenuOpen\}/);
    expect(source).not.toMatch(/title=\{t\(/);
  });
  it("mark-all-read badge renders a Tooltip instead of a native title", () => {
    const source = read("../MarkAllReadBadge.tsx");
    expect(source).toMatch(/from "\.\.\/common\/Tooltip"/);
    expect(source).toMatch(/<Tooltip content=\{tooltip\}/);
    expect(source).not.toMatch(/title=\{tooltip\}/);
  });
});
