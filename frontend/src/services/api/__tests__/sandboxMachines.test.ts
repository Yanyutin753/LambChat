/** sandbox 多机服务：machines 接口与展示纯函数 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../sandbox.ts", import.meta.url), "utf-8");

describe("sandboxApi machines 接口", () => {
  it("定义 SandboxMachine 接口与四个 machines 方法", () => {
    expect(source).toContain("interface SandboxMachine");
    expect(source).toContain("listMachines");
    expect(source).toContain("setDefaultMachine");
    expect(source).toContain("renameMachine");
    expect(source).toContain("forgetMachine");
  });

  it("machines 端点路径与后端路由一致", () => {
    expect(source).toContain("/api/sandbox/machines");
    expect(source).toContain("/default");
  });
});
