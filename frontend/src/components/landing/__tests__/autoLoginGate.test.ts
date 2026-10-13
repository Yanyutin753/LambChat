import { shouldShowAutoLoginSplash } from "../autoLoginGate";

test("shows splash while auth is loading and an access token exists", () => {
  expect(
    shouldShowAutoLoginSplash({
      isLoading: true,
      isAuthenticated: false,
      hasToken: true,
    }),
  ).toBe(true);
});

test("no splash for anonymous visitors without a token", () => {
  expect(
    shouldShowAutoLoginSplash({
      isLoading: true,
      isAuthenticated: false,
      hasToken: false,
    }),
  ).toBe(false);
});

test("keeps splash once auth resolves as authenticated until navigation completes", () => {
  expect(
    shouldShowAutoLoginSplash({
      isLoading: false,
      isAuthenticated: true,
      hasToken: true,
    }),
  ).toBe(true);
});

test("keeps splash when the user resolves before auth loading finishes", () => {
  expect(
    shouldShowAutoLoginSplash({
      isLoading: true,
      isAuthenticated: true,
      hasToken: true,
    }),
  ).toBe(true);
});

test("shows landing if a retained token fails to resolve a user", () => {
  expect(
    shouldShowAutoLoginSplash({
      isLoading: false,
      isAuthenticated: false,
      hasToken: true,
    }),
  ).toBe(false);
});

test("no splash once auth resolves as unauthenticated (landing renders normally)", () => {
  expect(
    shouldShowAutoLoginSplash({
      isLoading: false,
      isAuthenticated: false,
      hasToken: false,
    }),
  ).toBe(false);
});
