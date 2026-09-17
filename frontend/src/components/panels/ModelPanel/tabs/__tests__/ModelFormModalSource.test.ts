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

test("model form persists the image URL mode selection", () => {
  expect(source).toMatch(/formImageUrlMode/);
  expect(source).toMatch(/model\?\.profile\?\.image_url_mode/);
  // 旧配置只写 image_url_to_base64 时回退为 base64 模式
  expect(source).toMatch(/model\?\.profile\?\.image_url_to_base64 \? "base64" : "url"/);
  expect(source).toMatch(/image_url_mode:\s*formImageUrlMode/);
  // 显式 base64 模式时同步置位旧字段,保证回滚兼容
  expect(source).toMatch(/image_url_to_base64:\s*formImageUrlMode === "base64"/);
});

test("model form persists an explicit model icon selection", () => {
  expect(source).toMatch(/formIcon/);
  expect(source).toMatch(/model\?\.icon/);
  expect(source).toMatch(/icon:\s*formIcon\s*\|\|\s*undefined/);
  expect(source).toMatch(/<ModelIconSelect/);
});

test("model form persists the OpenAI wire format selection", () => {
  expect(source).toMatch(/formApiFormat/);
  expect(source).toMatch(/model\?\.api_format/);
  expect(source).toMatch(/api_format:\s*formApiFormat\s*\|\|\s*undefined/);
});
