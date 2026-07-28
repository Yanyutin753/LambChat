import { PASTE_TEXT_THRESHOLD } from "../../components/chat/chatInputConstants";

test("paste threshold stays aligned with long-text conversion threshold", async () => {
  const { LONG_TEXT_THRESHOLD } = await import(
    "../../components/chat/longTextConversion"
  );
  expect(PASTE_TEXT_THRESHOLD).toBe(LONG_TEXT_THRESHOLD);
  expect(PASTE_TEXT_THRESHOLD).toBeGreaterThan(0);
});
