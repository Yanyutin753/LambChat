import { buildReleaseAssetDownloadUrl } from "../version";

test("builds same-origin proxy URL for release asset download", () => {
  expect(
    buildReleaseAssetDownloadUrl(
      "LambChat-android-v2.8.2-signed.apk",
      "https://lambchat.com",
    ),
  ).toBe(
    "https://lambchat.com/api/version/assets/LambChat-android-v2.8.2-signed.apk/download",
  );
});

test("encodes asset names with special characters", () => {
  expect(
    buildReleaseAssetDownloadUrl("my app (1).apk", "https://lambchat.com"),
  ).toBe("https://lambchat.com/api/version/assets/my%20app%20(1).apk/download");
});

test("falls back to relative path without api base", () => {
  expect(buildReleaseAssetDownloadUrl("x.apk", "")).toBe(
    "/api/version/assets/x.apk/download",
  );
});
