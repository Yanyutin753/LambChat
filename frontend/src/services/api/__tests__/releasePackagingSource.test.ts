import { existsSync, readFileSync } from "node:fs";

function readRepoFile(path: string): string {
  const url = new URL(`../../../../../${path}`, import.meta.url);
  return readFileSync(url, "utf8");
}

test("release workflow publishes branded desktop and mobile artifacts", () => {
  const workflowPath = ".github/workflows/app-release.yml";
  expect(
    existsSync(new URL(`../../../../../${workflowPath}`, import.meta.url)),
  ).toBe(true);

  const workflow = readRepoFile(workflowPath);
  expect(workflow).toMatch(/LambChat-/);
  expect(workflow).toMatch(/package:desktop/);
  expect(workflow).toMatch(/assembleRelease/);
  expect(workflow).toMatch(/softprops\/action-gh-release/);
  expect(workflow).toMatch(/java-version: '21'/);
  expect(workflow).toMatch(/if: always\(\)/);
  expect(workflow).toMatch(/continue-on-error: true/);
  expect(workflow).toMatch(/-workspace App\.xcworkspace/);
  expect(workflow).toMatch(/CARGO_BUILD_JOBS/);
  expect(workflow).toMatch(/pnpm config set store-dir D:\\pnpm-store/);
  expect(workflow).toMatch(/npm_config_cache=D:\\npm-cache/);
  expect(workflow).not.toMatch(/CARGO_TARGET_DIR:/);
  expect(workflow).toMatch(/timeout-minutes: 60/);
  expect(workflow).toMatch(/runner: windows-2022/);
  expect(workflow).toMatch(/label: Linux x86_64/);
  expect(workflow).toMatch(/label: Linux ARM64/);
  expect(workflow).toMatch(/runner: ubuntu-24\.04-arm/);
  expect(workflow).toMatch(/bundles: appimage,deb,rpm/);
  expect(workflow).toMatch(/target: universal-apple-darwin/);
  expect(workflow).toMatch(
    /rustup target add aarch64-apple-darwin x86_64-apple-darwin/,
  );
  expect(workflow).toMatch(/frontend\/src-tauri\/target\/release\/bundle/);
  expect(workflow).toMatch(
    /LambChat-\$\{RELEASE_TAG\}-Linux-\$\{arch\}\.AppImage/,
  );
  expect(workflow).toMatch(/LambChat-\$\{RELEASE_TAG\}-Linux-\$\{arch\}\.deb/);
  expect(workflow).toMatch(/LambChat-\$\{RELEASE_TAG\}-Linux-\$\{arch\}\.rpm/);
  expect(workflow).toMatch(/LambChat-\$env:RELEASE_TAG-Windows\.msi/);
  expect(workflow).toMatch(/LambChat-\$env:RELEASE_TAG-Windows-Portable\.zip/);
  expect(workflow).toMatch(/LambChat-\$\{RELEASE_TAG\}-macOS\.zip/);
  expect(workflow).toMatch(/LambChat-\$\{RELEASE_TAG\}-macOS\.dmg/);
  expect(workflow).not.toMatch(
    /if \[ -z "\$app_path" \]; then\s+echo "No macOS \.app bundle found"\s+exit 1\s+fi/,
  );
  expect(workflow).toMatch(/if \[ -n "\$app_path" \]; then[\s\S]*?ditto/);
  expect(workflow).not.toMatch(/find frontend -type f/);
  expect(workflow).not.toMatch(/-name '\*\.exe'/);
  expect(workflow).not.toMatch(/mapfile/);
});

test("release workflow publishes a debug Android APK when signing secrets are missing", () => {
  const workflow = readRepoFile(".github/workflows/app-release.yml");

  expect(workflow).not.toMatch(/LambChat-android-[^\n]*release-unsigned\.apk/);
  expect(workflow).toMatch(/assembleDebug/);
  expect(workflow).toMatch(/app-debug\.apk/);
  expect(workflow).toMatch(/LambChat-android-\$\{RELEASE_TAG\}-debug\.apk/);
  expect(workflow).toMatch(/LambChat-android-\$\{RELEASE_TAG\}-signed\.apk/);
});

test("mobile package scripts generate and validate branded native images", () => {
  const packageJson = JSON.parse(readRepoFile("frontend/package.json")) as {
    scripts: Record<string, string>;
  };
  const assetScript = readRepoFile(
    "frontend/scripts/generate-branded-assets.mjs",
  );
  const packagedBuildScript = readRepoFile(
    "frontend/scripts/build-packaged-frontend.mjs",
  );

  expect(packageJson.scripts["packaged:build"]).toMatch(/brand:assets/);
  expect(packageJson.scripts["packaged:build"]).toMatch(
    /build-packaged-frontend/,
  );
  expect(packageJson.scripts["mobile:sync"]).toMatch(/packaged:build/);
  expect(packageJson.scripts["mobile:sync:ios"]).toMatch(/cap sync ios/);
  expect(packageJson.scripts["mobile:ios:variant"]).toBe(undefined);
  expect(packageJson.scripts["mobile:build"]).toMatch(/packaged:build/);
  expect(packageJson.scripts["brand:assets"]).toMatch(
    /generate-branded-assets/,
  );
  expect(packageJson.scripts["brand:assets:check"]).toMatch(/--check/);
  expect(packagedBuildScript).toMatch(/VITE_API_BASE:\s*normalizedAppUrl/);
  expect(packagedBuildScript).toMatch(/LAMBCHAT_APP_URL:\s*normalizedAppUrl/);
  expect(assetScript).toMatch(/LambChat/);
  expect(assetScript).toMatch(/public\/icons\/icon-512\.png/);
  expect(assetScript).toMatch(/scalePngNearest/);
  expect(assetScript).toMatch(/1024/);
});

test("iOS release builds only the modern package line", () => {
  const packageJson = JSON.parse(readRepoFile("frontend/package.json")) as {
    dependencies: Record<string, string>;
    devDependencies: Record<string, string>;
  };
  const podfile = readRepoFile("frontend/ios/App/Podfile");
  const project = readRepoFile(
    "frontend/ios/App/App.xcodeproj/project.pbxproj",
  );
  const infoPlist = readRepoFile("frontend/ios/App/App/Info.plist");
  const workflow = readRepoFile(".github/workflows/app-release.yml");

  expect(packageJson.dependencies["@capacitor/core"]).toBe("7.6.5");
  expect(packageJson.dependencies["@capacitor/local-notifications"]).toBe(
    "^7.0.6",
  );
  expect(packageJson.devDependencies["@capacitor/cli"]).toBe("7.6.5");
  expect(packageJson.devDependencies["@capacitor/ios"]).toBe("7.6.5");
  expect(podfile).toMatch(/platform :ios, '14\.0'/);
  expect(podfile).toMatch(/@capacitor\+ios@7\.6\.5_@capacitor\+core@7\.6\.5/);
  expect(podfile).toMatch(
    /@capacitor\+local-notifications@7\.0\.6_@capacitor\+core@7\.6\.5/,
  );
  expect(
    [...project.matchAll(/IPHONEOS_DEPLOYMENT_TARGET = ([0-9.]+);/g)].every(
      ([, target]) => target === "14.0",
    ),
  ).toBe(true);
  expect(infoPlist).toMatch(/<string>arm64<\/string>/);
  expect(infoPlist).not.toMatch(/<string>armv7<\/string>/);
  expect(workflow).not.toMatch(/legacy-ios12/);
  expect(workflow).not.toMatch(/iOS 12/);
  expect(workflow).not.toMatch(/@capacitor\/core@3\.9\.0/);
  expect(workflow).not.toMatch(/@capacitor\/ios@3\.9\.0/);
  expect(workflow).toMatch(/pnpm mobile:sync:ios/);
  expect(workflow).toMatch(/pod install/);
  expect(workflow).toMatch(/-destination generic\/platform=iOS/);
  expect(workflow).toMatch(/archive/);
  expect(workflow).toMatch(/CODE_SIGNING_ALLOWED=NO/);
  expect(workflow).toMatch(/CODE_SIGNING_REQUIRED=NO/);
  expect(workflow).toMatch(/CODE_SIGN_IDENTITY=""/);
  expect(workflow).toMatch(
    /LambChat-ios-\$\{RELEASE_TAG\}-unsigned-xcarchive\.zip/,
  );
});

test("desktop package script bundles the frontend before Tauri packaging", () => {
  const script = readRepoFile("frontend/scripts/package-desktop.mjs");

  expect(script).toMatch(/VITE_API_BASE:\s*normalizedAppUrl/);
  expect(script).toMatch(/LAMBCHAT_APP_URL:\s*normalizedAppUrl/);
  expect(script).not.toMatch(/spawnSync\(pnpmCommand, \["build"\]/);
  expect(script).not.toMatch(/spawnSync\(pnpmCommand, \["packaged:build"\]/);
  expect(script).toMatch(/tauriCliPackage = "@tauri-apps\/cli@2\.11\.2"/);
  expect(script).toMatch(/"icon", "public\/icons\/icon-512\.png"/);
  expect(script).toMatch(/TAURI_TARGET/);
  expect(script).toMatch(/"--target", target/);
  expect(script).toMatch(/TAURI_BUNDLES/);
  expect(script).not.toMatch(/pake-cli/);
  expect(script).not.toMatch(/PAKE_TARGETS/);
});

test("desktop package uses committed Tauri project and branded icons", () => {
  const config = readRepoFile("frontend/src-tauri/tauri.conf.json");
  const cargo = readRepoFile("frontend/src-tauri/Cargo.toml");

  expect(config).toMatch(/"productName": "LambChat"/);
  expect(config).toMatch(/"frontendDist": "\.\.\/dist"/);
  expect(config).toMatch(/"beforeBuildCommand": "pnpm packaged:build"/);
  expect(config).toMatch(/"icons\/icon\.ico"/);
  expect(config).toMatch(/"icons\/icon\.icns"/);
  expect(cargo).toMatch(/tauri = \{ version = "2\.11\.2"/);
  expect(readRepoFile(".gitignore")).toMatch(/frontend\/src-tauri\/icons\//);
});
