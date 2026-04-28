import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAssistantCloneUrl,
  buildAssistantDetailUrl,
  buildAssistantListUrl,
  buildAssistantSelectUrl,
} from "./assistant.ts";

test("builds the default public assistant list url", () => {
  assert.equal(buildAssistantListUrl(), "/api/assistants");
});

test("includes scope, search, and tags when building assistant list url", () => {
  assert.equal(
    buildAssistantListUrl({
      scope: "all",
      search: "writer",
      tags: ["creative", "long-form"],
    }),
    "/api/assistants?scope=all&search=writer&tags=creative%2Clong-form",
  );
});

test("includes category when building assistant list url", () => {
  assert.equal(
    buildAssistantListUrl({ category: "programming" }),
    "/api/assistants?category=programming",
  );
});

test("builds assistant detail, clone, and select urls", () => {
  assert.equal(
    buildAssistantDetailUrl("assistant/alpha"),
    "/api/assistants/assistant%2Falpha",
  );
  assert.equal(
    buildAssistantCloneUrl("assistant/alpha"),
    "/api/assistants/assistant%2Falpha/clone",
  );
  assert.equal(
    buildAssistantSelectUrl("assistant/alpha"),
    "/api/assistants/assistant%2Falpha/select",
  );
});
