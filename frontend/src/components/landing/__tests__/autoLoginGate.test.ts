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

test("no splash once auth resolves as authenticated (redirect effect takes over)", () => {
  expect(
    shouldShowAutoLoginSplash({
      isLoading: false,
      isAuthenticated: true,
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
