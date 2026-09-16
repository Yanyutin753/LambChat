import { describe, expect, test } from "vitest";
import {
  releaseUnfinishedFollowUps,
  selectSteersForFollowUp,
  toFollowUpQueueItem,
} from "../steerQueue";

describe("toFollowUpQueueItem", () => {
  test("builds a follow-up item that run-end promotion can pick up", () => {
    const item = toFollowUpQueueItem("  追加的问题  ");

    expect(item).toMatchObject({
      content: "追加的问题",
      queued: true,
      status: "deferred",
      deferred: true,
    });
    expect(selectSteersForFollowUp([item!])).toHaveLength(1);
  });

  test("keeps attachments so the follow-up turn sends them", () => {
    const attachments = [{ id: "f1", name: "a.png" }] as never[];

    expect(toFollowUpQueueItem("追问", attachments)?.attachments).toBe(
      attachments,
    );
  });

  test("supports queueing multiple follow-ups and keeps FIFO order", () => {
    const first = toFollowUpQueueItem("第一个追加问题")!;
    const second = toFollowUpQueueItem("第二个追加问题")!;
    const third = toFollowUpQueueItem("第三个追加问题")!;

    expect(
      selectSteersForFollowUp([first, second, third]).map(
        (item) => item.content,
      ),
    ).toEqual(["第一个追加问题", "第二个追加问题", "第三个追加问题"]);
  });

  test("rejects blank drafts", () => {
    expect(toFollowUpQueueItem("   ")).toBeNull();
  });

  test("queues attachment-only drafts without losing their files", () => {
    const attachments = [{ id: "f1", name: "report.pdf" }] as never[];
    expect(toFollowUpQueueItem("  ", attachments)).toMatchObject({
      content: "",
      attachments,
      status: "deferred",
    });
  });
});

describe("releaseUnfinishedFollowUps", () => {
  test("unmarks items still queued so the next effect run can retake them", () => {
    const pending = toFollowUpQueueItem("还在排队")!;
    const sent = toFollowUpQueueItem("已补发")!;
    const marked = new Set([pending.id, sent.id]);

    releaseUnfinishedFollowUps(
      [pending, sent],
      // 已补发的项在补发前被 clearSteer 移出队列
      (id) => id === pending.id,
      marked,
    );

    expect(marked.has(pending.id)).toBe(false);
    expect(marked.has(sent.id)).toBe(true);
  });
});
