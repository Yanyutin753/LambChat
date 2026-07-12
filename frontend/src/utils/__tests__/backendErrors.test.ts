import type { TFunction } from "i18next";
import { translateBackendError } from "../backendErrors.ts";

const t = ((key: string, options?: { permission?: string }) =>
  options?.permission
    ? `translated:${key}:${options.permission}`
    : `translated:${key}`) as TFunction;

test("translates shared backend error codes", () => {
  expect(translateBackendError("model_not_found", t)).toBe(
    "translated:errors.modelNotFound",
  );
  expect(translateBackendError("persona_preset_no_delete_permission", t)).toBe(
    "translated:personaPresets.noDeletePermission",
  );
  expect(translateBackendError("File not found", t)).toBe(
    "translated:backendErrors.fileNotFound",
  );
});

test("translates backend error patterns", () => {
  expect(translateBackendError("缺少权限: model:admin", t)).toBe(
    "translated:backendErrors.permissionMissing:model:admin",
  );
});

test("returns unknown backend messages unchanged", () => {
  expect(translateBackendError("unexpected_backend_error", t)).toBe(
    "unexpected_backend_error",
  );
});
