import { bytesToBase64 } from "../bytesToBase64";

test("encodes empty bytes", () => {
  expect(bytesToBase64(new Uint8Array([]))).toBe("");
});

test("encodes known vectors", () => {
  expect(bytesToBase64(new Uint8Array([72, 101]))).toBe("SGU=");
  expect(bytesToBase64(new Uint8Array([104, 101, 108, 108, 111]))).toBe(
    "aGVsbG8=",
  );
});

test("handles chunks larger than the internal split threshold", () => {
  const bytes = new Uint8Array(70_000);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = i % 251;
  }
  expect(bytesToBase64(bytes)).toBe(Buffer.from(bytes).toString("base64"));
});
