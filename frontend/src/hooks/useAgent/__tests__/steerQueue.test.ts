import { describe, expect, test } from "vitest";
import { selectSteersForFollowUp } from "../steerQueue";

describe("selectSteersForFollowUp", () => {
  test("selects only accepted pending items when the active run ends", () => {
    const selected = selectSteersForFollowUp([
      {
        id: "pending",
        content: "继续",
        queued: true,
        status: "pending",
        timestamp: new Date(1),
      },
      {
        id: "failed",
        content: "不要自动发送",
        queued: false,
        status: "failed",
        timestamp: new Date(2),
      },
      {
        id: "delivered",
        content: "已送达",
        queued: false,
        timestamp: new Date(3),
      },
    ]);

    expect(selected.map((item) => item.id)).toEqual(["pending"]);
  });
});
