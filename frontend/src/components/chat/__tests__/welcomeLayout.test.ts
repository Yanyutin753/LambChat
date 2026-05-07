import test from "node:test";
import assert from "node:assert/strict";
import { getWelcomeSuggestionButtonClass } from "../welcomeLayout.ts";

test("keeps the first two welcome suggestions visible on mobile", () => {
  assert.equal(
    getWelcomeSuggestionButtonClass(0).includes("hidden sm:flex"),
    false,
  );
  assert.equal(
    getWelcomeSuggestionButtonClass(1).includes("hidden sm:flex"),
    false,
  );
});

test("hides later welcome suggestions on narrow screens until keyboard pill mode restyles them", () => {
  const className = getWelcomeSuggestionButtonClass(2);

  assert.equal(className.includes("welcome-suggestion-pill"), true);
  assert.equal(className.includes("hidden sm:flex"), true);
});
