import { describe, expect, it } from "vitest";
import { clearAllLoadingStates, hasPendingAskHuman } from "../messageParts";

const pendingAskHuman = {
  type: "tool" as const,
  id: "ask-1",
  name: "ask_human",
  args: { message: "请确认" },
  isPending: true,
};

describe("clearAllLoadingStates ask-human behavior", () => {
  it("keeps ask-human pending when a waiting-human run closes its stream", () => {
    const [part] = clearAllLoadingStates([pendingAskHuman], {
      preserveAskHuman: true,
    });

    expect(part).toMatchObject({
      name: "ask_human",
      isPending: true,
    });
    expect(part).not.toHaveProperty("cancelled", true);
  });

  it("still cancels ask-human on an actual cancellation", () => {
    const [part] = clearAllLoadingStates([pendingAskHuman]);

    expect(part).toMatchObject({
      name: "ask_human",
      isPending: false,
      cancelled: true,
    });
  });
});

describe("hasPendingAskHuman", () => {
  it("finds pending ask-human calls nested inside a subagent", () => {
    expect(
      hasPendingAskHuman([
        {
          type: "subagent",
          agent_id: "helper",
          agent_name: "Helper",
          input: "ask",
          depth: 1,
          isPending: true,
          status: "running",
          parts: [pendingAskHuman],
        },
      ]),
    ).toBe(true);
  });

  it("ignores answered ask-human calls", () => {
    expect(
      hasPendingAskHuman([
        { ...pendingAskHuman, isPending: false, success: true },
      ]),
    ).toBe(false);
  });
});
