import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const nginxSource = readFileSync(
  resolve(import.meta.dirname, "../../../nginx/nginx.conf"),
  "utf8",
);

test("nginx keeps service worker and manifest metadata fresh", () => {
  expect(nginxSource).toMatch(
    /location = \/sw\.js \{[^}]*Cache-Control[^}]*no-cache/s,
  );
  expect(nginxSource).toMatch(
    /location = \/manifest\.json \{[^}]*Cache-Control[^}]*no-cache/s,
  );
});

test("nginx serves stable icon assets with immutable long-lived caching", () => {
  expect(nginxSource).toMatch(
    /location \/icons\/ \{[^}]*Cache-Control[^}]*max-age=31536000, immutable/s,
  );
  expect(nginxSource).toMatch(
    /location = \/favicon\.ico \{[^}]*Cache-Control[^}]*max-age=31536000, immutable/s,
  );
});

test("nginx keeps only the chat event stream open for 24 hours", () => {
  expect(nginxSource).toMatch(
    /location ~ \^\/api\/chat\/sessions\/\[\^\/\]\+\/stream\$ \{[^}]*proxy_read_timeout 86400s;/s,
  );
  expect(nginxSource).toMatch(
    /location \/api\/chat\/ \{[^}]*proxy_read_timeout 3600s;/s,
  );
  expect(nginxSource).toMatch(
    /location \/api\/ \{[^}]*proxy_read_timeout 3600s;/s,
  );
});
