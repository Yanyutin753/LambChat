/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { PersonaPlazaPanel } from "../PersonaPlazaPanel";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../i18n", () => ({ default: { language: "en" } }));
vi.mock("../usePersonaPlaza", () => ({
  usePersonaPlaza: () => ({
    presets: [],
    filtered: [],
    paged: [],
    allTags: [],
    scopeTabs: [{ key: "all", label: "All", icon: "Users" }],
    total: 0,
    page: 1,
    pageSize: 20,
    query: "",
    scopeFilter: "all",
    error: "Request failed",
    refresh,
    scopeBtnRef: { current: null },
    tagBtnRef: { current: null },
    importInputRef: { current: null },
  }),
}));
vi.mock("../../common/PanelHeader", () => ({ PanelHeader: () => null }));
vi.mock("../PersonaEditorModal", () => ({ PersonaEditorModal: () => null }));
vi.mock("../PersonaScopeDropdown", () => ({
  PersonaScopeDropdown: () => null,
}));
vi.mock("../PersonaTagFilterDropdown", () => ({
  PersonaTagFilterDropdown: () => null,
}));
afterEach(cleanup);

test("failed persona requests offer retry without claiming the list is empty", () => {
  render(<PersonaPlazaPanel />);
  expect(screen.getByRole("alert").textContent).toContain("common.loadFailed");
  expect(screen.queryByText("personaPresets.empty")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.refresh" }));
  expect(refresh).toHaveBeenCalledOnce();
});
