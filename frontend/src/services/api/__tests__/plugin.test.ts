import { describe, expect, it, vi, beforeEach } from "vitest";

const { get: mockGet, post: mockPost, put: mockPut, patch: mockPatch, deleteRequest: mockDelete } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  deleteRequest: vi.fn(),
}));

vi.mock("../fetch", () => ({
  authFetch: Object.assign(
    vi.fn(),
    { get: mockGet, post: mockPost, put: mockPut, patch: mockPatch, delete: mockDelete },
  ),
}));

import { pluginApi } from "../plugin";
import { authFetch } from "../fetch";

describe("pluginApi", () => {
  beforeEach(() => {
    vi.mocked(authFetch).mockReset();
  });

  it("lists plugins with query params", async () => {
    vi.mocked(authFetch).mockResolvedValue({ plugins: [], total: 0 });
    await pluginApi.list({ tags: "a,b", search: "kit", skip: 0, limit: 20 });
    expect(authFetch).toHaveBeenCalledWith(
      "/api/plugins/?tags=a%2Cb&search=kit&skip=0&limit=20",
    );
  });

  it("installs a plugin by name", async () => {
    vi.mocked(authFetch).mockResolvedValue({ message: "ok" });
    await pluginApi.install("research-kit");
    expect(authFetch).toHaveBeenCalledWith(
      "/api/plugins/research-kit/install",
      { method: "POST" },
    );
  });

  it("uninstalls via POST uninstall endpoint", async () => {
    vi.mocked(authFetch).mockResolvedValue({ message: "ok" });
    await pluginApi.uninstall("research-kit");
    expect(authFetch).toHaveBeenCalledWith(
      "/api/plugins/research-kit/uninstall",
      { method: "POST" },
    );
  });

  it("activates with PATCH", async () => {
    vi.mocked(authFetch).mockResolvedValue({});
    await pluginApi.activate("research-kit", false);
    expect(authFetch).toHaveBeenCalledWith(
      "/api/plugins/research-kit/activate",
      { method: "PATCH", body: JSON.stringify({ is_active: false }) },
    );
  });

  it("reads a skill payload file", async () => {
    vi.mocked(authFetch).mockResolvedValue({ content: "# hi" });
    await pluginApi.readSkillFile("research-kit", "deep-research", "SKILL.md");
    expect(authFetch).toHaveBeenCalledWith(
      "/api/plugins/research-kit/skills/deep-research/files/SKILL.md",
    );
  });
});
