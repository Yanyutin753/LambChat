import { expect, test } from "vitest";
import i18n from "../../../i18n";
import { processMessageEvent } from "../eventProcessor";
import type { MessagePart } from "../../../types";

test.each([true, false])(
  "provider limit feedback preserves progress and raw evidence during streaming/history replay (%s)",
  (streaming) => {
    const event = {
      code: "internal_error",
      type: "AnthropicRateLimitError",
      error:
        "Error code: 429 - {'message': '[1308][Usage limit reached for 5 hour. Your limit will reset at 2026-11-05 18:12:57][request-123]'}",
    };
    const original = JSON.stringify(event);
    const parts: MessagePart[] = [{ type: "text", content: "Existing result" }];
    const result = processMessageEvent(
      "error",
      event,
      parts,
      "Existing result",
      [],
      0,
      [],
      streaming,
    );
    const message = i18n.t("chat.errorPrefix", {
      error: i18n.t("errors.providerQuotaExhaustedUntil", {
        resetAt: "2026-11-05 18:12:57",
      }),
    });
    expect(result.content).toBe(message);
    expect(result.parts).toEqual([
      ...parts,
      { type: "text", content: message, isError: true },
    ]);
    expect(result.content).not.toContain("request-123");
    expect(JSON.stringify(event)).toBe(original);
    const replay = processMessageEvent(
      "error",
      event,
      result.parts,
      result.content,
      [],
      0,
      [],
      false,
    );
    expect(replay.parts).toEqual(result.parts);
  },
);
