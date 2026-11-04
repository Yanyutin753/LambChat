import { expect, test, vi } from "vitest";
import { promoteSteerFollowUps, toFollowUpQueueItem } from "../steerQueue";

test("a user stop preserves queued input without deleting or submitting it", async () => {
  const cancelSteer = vi.fn(),
    sendMessage = vi.fn();
  await promoteSteerFollowUps([toFollowUpQueueItem("保留我")!], {
    sessionId: "s1",
    cancelSteer,
    sendMessage,
    isPaused: () => true,
  });
  expect(cancelSteer).not.toHaveBeenCalled();
  expect(sendMessage).not.toHaveBeenCalled();
});

test("a stop received during a server status check wins over automatic promotion", async () => {
  let paused = false;
  const cancelSteer = vi.fn(),
    sendMessage = vi.fn();
  await promoteSteerFollowUps([toFollowUpQueueItem("保留我")!], {
    sessionId: "s1",
    cancelSteer,
    sendMessage,
    isPaused: () => paused,
    isSessionActive: async () => {
      paused = true;
      return false;
    },
  });
  expect(cancelSteer).not.toHaveBeenCalled();
  expect(sendMessage).not.toHaveBeenCalled();
});
