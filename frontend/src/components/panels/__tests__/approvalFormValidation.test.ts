import { describe, expect, test } from "vitest";
import {
  isFieldValueFilled,
  isFormFieldsValid,
  toggleMultiSelectValue,
  toggleSingleSelectValue,
} from "../approvalFormValidation";
import type { FormField } from "../../../types";

const radioField: FormField = {
  name: "topic",
  label: "topic",
  type: "radio",
  required: true,
  options: ["a", "b"],
} as FormField;

const optionalText: FormField = {
  name: "_other",
  label: "other",
  type: "textarea",
  required: false,
} as FormField;

describe("isFieldValueFilled", () => {
  test("empty string / empty array / null are not filled", () => {
    expect(isFieldValueFilled("")).toBe(false);
    expect(isFieldValueFilled("   ")).toBe(false);
    expect(isFieldValueFilled([])).toBe(false);
    expect(isFieldValueFilled(null)).toBe(false);
    expect(isFieldValueFilled(undefined)).toBe(false);
  });

  test("real answers are filled", () => {
    expect(isFieldValueFilled("AI研究方向")).toBe(true);
    expect(isFieldValueFilled(["直接回复"])).toBe(true);
    expect(isFieldValueFilled(0)).toBe(true);
    expect(isFieldValueFilled(false)).toBe(true);
  });
});

describe("isFormFieldsValid", () => {
  test("required fields must be filled across all steps", () => {
    expect(
      isFormFieldsValid([radioField, optionalText], {
        topic: "",
        _other: "",
      }),
    ).toBe(false);
    expect(
      isFormFieldsValid([radioField, optionalText], {
        topic: "AI研究方向",
        _other: "",
      }),
    ).toBe(true);
  });
});

describe("toggleMultiSelectValue", () => {
  test("adds an option when absent", () => {
    expect(toggleMultiSelectValue([], "a")).toEqual(["a"]);
    expect(toggleMultiSelectValue(["a"], "b")).toEqual(["a", "b"]);
  });

  test("removes an option when already selected", () => {
    expect(toggleMultiSelectValue(["a", "b"], "a")).toEqual(["b"]);
  });
});

describe("toggleSingleSelectValue", () => {
  test("selects an option when nothing or something else is selected", () => {
    expect(toggleSingleSelectValue("", "a")).toBe("a");
    expect(toggleSingleSelectValue("b", "a")).toBe("a");
    expect(toggleSingleSelectValue(null, "a")).toBe("a");
  });

  test("deselects the option when clicking it again", () => {
    expect(toggleSingleSelectValue("a", "a")).toBe("");
  });
});
