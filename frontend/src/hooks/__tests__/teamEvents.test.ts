import test from "node:test";
import assert from "node:assert/strict";

import {
  dispatchTeamsChanged,
  subscribeTeamsChanged,
  type TeamsChangedDetail,
} from "../teamEvents.ts";

test("team change events can be subscribed and dispatched", () => {
  const target = new EventTarget();
  const seen: TeamsChangedDetail[] = [];

  const unsubscribe = subscribeTeamsChanged(
    (detail) => seen.push(detail),
    target,
  );

  const dispatched = dispatchTeamsChanged(
    { action: "created", teamId: "team-1", teamName: "Research Team" },
    target,
  );

  unsubscribe();

  assert.equal(dispatched, true);
  assert.deepEqual(seen, [
    { action: "created", teamId: "team-1", teamName: "Research Team" },
  ]);
});

test("unsubscribed listeners stop receiving team change events", () => {
  const target = new EventTarget();
  let seen = 0;

  const unsubscribe = subscribeTeamsChanged(() => {
    seen += 1;
  }, target);

  unsubscribe();
  dispatchTeamsChanged({ action: "updated" }, target);

  assert.equal(seen, 0);
});
