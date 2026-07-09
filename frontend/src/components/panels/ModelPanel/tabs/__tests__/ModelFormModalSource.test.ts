import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../ModelFormModal.tsx", import.meta.url),
  "utf8",
);

test("model form persists the supports vision profile flag", () => {
  expect(source).toMatch(/formSupportsVision/);
  expect(source).toMatch(/model\?\.profile\?\.supports_vision/);
  expect(source).toMatch(/supports_vision:\s*formSupportsVision/);
  expect(source).toMatch(/max_input_tokens:\s*maxInputTokens/);
});

test("model form persists the image URL base64 profile flag", () => {
  expect(source).toMatch(/formImageUrlToBase64/);
  expect(source).toMatch(/model\?\.profile\?\.image_url_to_base64/);
  expect(source).toMatch(/image_url_to_base64:\s*formImageUrlToBase64/);
});

test("model form persists an explicit model icon selection", () => {
  expect(source).toMatch(/formIcon/);
  expect(source).toMatch(/model\?\.icon/);
  expect(source).toMatch(/icon:\s*formIcon\s*\|\|\s*undefined/);
  expect(source).toMatch(/<ModelIconSelect/);
});
