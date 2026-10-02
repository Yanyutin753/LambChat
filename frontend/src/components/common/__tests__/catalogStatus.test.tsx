/** @vitest-environment jsdom */
import { readFileSync } from "node:fs";
import { useRef, useState } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { CatalogStatus } from "../CatalogStatus";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
afterEach(cleanup);
test("retry hands focus to the stable editor while feedback changes", async () => {
  let resolve!: () => void;
  const pending = new Promise<void>((r) => {
    resolve = r;
  });
  function Editor() {
    const ref = useRef<HTMLDivElement>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(true);
    return (
      <div ref={ref} tabIndex={-1} role="region" aria-label="Editor">
        <CatalogStatus
          label="Models"
          loading={loading}
          error={error}
          focusTargetRef={ref}
          onRetry={() => {
            setLoading(true);
            pending.then(() => {
              setLoading(false);
              setError(false);
            });
          }}
        />
      </div>
    );
  }
  render(<Editor />);
  await userEvent.click(
    screen.getByRole("button", { name: "common.retry: Models" }),
  );
  expect(screen.getByRole("region", { name: "Editor" })).toHaveFocus();
  await act(async () => resolve());
  expect(screen.getByRole("region", { name: "Editor" })).toHaveFocus();
  expect(screen.queryByRole("status")).toBeNull();
});

test("shared loading feedback stops rotating when reduced motion is requested", () => {
  const styles = readFileSync("src/styles/components.css", "utf8");
  expect(styles).toMatch(
    /@media \(prefers-reduced-motion: reduce\)\s*{\s*\.spinner-rotate\s*{[^}]*animation:\s*none/,
  );
});
