import { expect, test } from "vitest";
import { readFileSync } from "node:fs";
import { Permission } from "../../../types";
import en from "../../../i18n/locales/en.json";
import zh from "../../../i18n/locales/zh.json";
import ja from "../../../i18n/locales/ja.json";
import ko from "../../../i18n/locales/ko.json";
import ru from "../../../i18n/locales/ru.json";

test("frontend permission values exactly match the backend contract", () => {
  const source = readFileSync(
    new URL("../../../../../src/kernel/types.py", import.meta.url),
    "utf8",
  );
  const body =
    source.split("class Permission(str, Enum):")[1]?.split("\nclass ")[0] ?? "";
  const backend = Array.from(
    body.matchAll(/^\s+[A-Z_]+\s*=\s*"([^"]+)"/gm),
    (match) => match[1],
  );
  expect(backend.length).toBeGreaterThan(0);
  expect(Object.values(Permission).sort()).toEqual(backend.sort());
});

test.each(Object.entries({ en, zh, ja, ko, ru }))(
  "%s describes each split capability and delegation scope",
  (_locale, messages) => {
    const catalog = (
      messages as unknown as {
        permissionCatalog: Record<
          string,
          { label: string; description: string }
        >;
      }
    ).permissionCatalog;
    const retired = new Set([
      "chat:read",
      "session:admin",
      "skill:admin",
      "role:manage",
    ]);
    for (const permission of Object.values(Permission).filter(
      (value) => !retired.has(value),
    )) {
      expect(catalog?.[permission]?.label, permission).toBeTruthy();
      expect(catalog?.[permission]?.description, permission).toBeTruthy();
    }
    expect(messages.roles).toHaveProperty("grantablePermissions");
    expect(messages.roles).toHaveProperty("assignableRoles");
    expect(messages.roles).toHaveProperty("delegationHint");
  },
);
