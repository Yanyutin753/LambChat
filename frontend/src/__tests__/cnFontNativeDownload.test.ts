import { spawn } from "node:child_process";
import { createServer } from "node:http";
import {
  copyFileSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { expect, test } from "vitest";

const require = createRequire(import.meta.url);
const fontRequire = createRequire(require.resolve("vite-plugin-font"));
const packagePath = fontRequire.resolve("cn-font-split/package.json");
const target = "aarch64-unknown-linux-gnu";

test.each([true, false])(
  "native font download retries temporary failure and preserves old files on permanent failure (%s)",
  async (recover) => {
    const folder = mkdtempSync(join(tmpdir(), "lambchat-font-download-"));
    const library = join(folder, `libffi-${target}.so`);
    const version = join(folder, "version");
    copyFileSync(
      join(dirname(packagePath), "dist/init.sh"),
      join(folder, "init.sh"),
    );
    writeFileSync(library, "old-library");
    writeFileSync(version, `${target}@old\n`);
    let requests = 0;
    const server = createServer((_request, response) => {
      requests += 1;
      response.statusCode = recover && requests > 1 ? 200 : 500;
      response.end(
        response.statusCode === 200 ? "new-library" : "temporary error",
      );
    });
    try {
      await new Promise<void>((resolve) =>
        server.listen(0, "127.0.0.1", resolve),
      );
      const address = server.address();
      if (!address || typeof address === "string")
        throw new Error("Missing server port");
      const exitCode = await new Promise<number | null>((resolve, reject) => {
        const child = spawn(
          "bash",
          [join(folder, "init.sh"), "i", `${target}@7.6.8`],
          {
            cwd: folder,
            env: {
              ...process.env,
              CN_FONT_SPLIT_GH_HOST: `http://127.0.0.1:${address.port}`,
            },
            stdio: "ignore",
          },
        );
        child.once("error", reject);
        child.once("close", resolve);
      });
      expect(requests).toBeGreaterThan(1);
      expect(exitCode === 0).toBe(recover);
      expect(readFileSync(library, "utf8")).toBe(
        recover ? "new-library" : "old-library",
      );
      expect(readFileSync(version, "utf8")).toBe(
        recover ? `${target}@7.6.8\n` : `${target}@old\n`,
      );
    } finally {
      await new Promise<void>((resolve) => server.close(() => resolve()));
      rmSync(folder, { recursive: true, force: true });
    }
  },
  15000,
);

test("native font postinstall propagates installation failure", () => {
  const pkg = JSON.parse(readFileSync(packagePath, "utf8"));
  expect(pkg.scripts.postinstall).toBe("node ./dist/cli.js i default@7.6.8");
});
