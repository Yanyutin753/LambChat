import { describe, expect, test } from "vitest";
import type { MessageAttachment } from "../../../../types";
import {
  createDraftAttachmentState,
  reduceDraftAttachments,
  selectActiveAttachments,
  selectSubmitAttachments,
} from "../draftAttachmentRegistry";

const file = new File(["pasted fragment"], "notes.txt", {
  type: "text/plain",
});

const readyAttachment: MessageAttachment = {
  id: "attachment-1",
  key: "key-1",
  name: "notes.txt",
  type: "document",
  mimeType: "text/plain",
  size: 15,
  url: "/files/key-1",
  composerReferenceId: "ref-1",
};

describe("draft attachment registry", () => {
  test("reconciles active file nodes without losing the upload resource", () => {
    const inserted = reduceDraftAttachments(createDraftAttachmentState(), {
      type: "insert",
      resource: {
        referenceId: "ref-1",
        file,
        status: "uploading",
        active: true,
      },
    });
    const removed = reduceDraftAttachments(inserted, {
      type: "reconcile-active",
      activeReferenceIds: [],
    });

    expect(removed.resources["ref-1"].active).toBe(false);
    expect(selectSubmitAttachments(removed)).toEqual([]);

    const restored = reduceDraftAttachments(removed, {
      type: "reconcile-active",
      activeReferenceIds: ["ref-1"],
    });
    expect(restored.resources["ref-1"].active).toBe(true);
    expect(restored.resources["ref-1"].file).toBe(file);
  });

  test("tracks ready, failed, and retry transitions", () => {
    const inserted = reduceDraftAttachments(createDraftAttachmentState(), {
      type: "insert",
      resource: {
        referenceId: "ref-1",
        file,
        status: "uploading",
        active: true,
      },
    });
    const failed = reduceDraftAttachments(inserted, {
      type: "upload-failed",
      referenceId: "ref-1",
      error: "network error",
    });
    expect(failed.resources["ref-1"]).toMatchObject({
      status: "failed",
      error: "network error",
    });

    const retrying = reduceDraftAttachments(failed, {
      type: "retry",
      referenceId: "ref-1",
    });
    expect(retrying.resources["ref-1"]).toMatchObject({
      status: "uploading",
      error: undefined,
    });

    const ready = reduceDraftAttachments(retrying, {
      type: "upload-ready",
      referenceId: "ref-1",
      attachment: readyAttachment,
    });
    expect(selectSubmitAttachments(ready)).toEqual([readyAttachment]);
  });

  test("keeps ordinary card-only attachments independent of rich nodes", () => {
    const image: MessageAttachment = {
      id: "image-1",
      key: "image-key",
      name: "photo.png",
      type: "image",
      mimeType: "image/png",
      size: 42,
      url: "/files/image-key",
    };
    const state = reduceDraftAttachments(createDraftAttachmentState(), {
      type: "sync-card-only",
      attachments: [image],
    });

    expect(selectActiveAttachments(state)).toEqual([image]);
    expect(selectSubmitAttachments(state)).toEqual([image]);
  });

  test("cleans up only inactive resources", () => {
    let state = createDraftAttachmentState();
    for (const referenceId of ["active", "inactive"]) {
      state = reduceDraftAttachments(state, {
        type: "insert",
        resource: {
          referenceId,
          file,
          status: "uploading",
          active: referenceId === "active",
        },
      });
    }

    state = reduceDraftAttachments(state, { type: "cleanup-inactive" });
    expect(Object.keys(state.resources)).toEqual(["active"]);
  });
});
