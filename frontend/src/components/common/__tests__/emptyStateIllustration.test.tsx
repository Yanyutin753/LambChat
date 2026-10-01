/** @vitest-environment jsdom */
import { fireEvent, render, screen } from "@testing-library/react";
import { EmptyState } from "../EmptyState";

test("empty states show the selected local illustration without duplicating accessible text", () => {
  const { container } = render(
    <EmptyState
      illustration="files"
      title="No files"
      description="Start a chat"
    />,
  );
  const image = container.querySelector("img");
  expect(image).toHaveAttribute("src", "/images/illustrations/lamb-files.png");
  expect(image).toHaveAttribute("alt", "");
  expect(screen.getByText("No files")).toBeVisible();
  expect(screen.getByText("Start a chat")).toBeVisible();
});

test("an unavailable illustration falls back to the static brand avatar", () => {
  const { container } = render(
    <EmptyState illustration="welcome" title="No results" />,
  );
  const image = container.querySelector("img");
  expect(image).not.toBeNull();
  fireEvent.error(image!);
  expect(image).toHaveAttribute("src", "/icons/icon-192.png");
  fireEvent.error(image!);
  expect(image).toHaveAttribute("src", "/icons/icon-192.png");
});

test("empty state actions remain operable alongside the illustration", () => {
  const action = vi.fn();
  render(
    <EmptyState
      title="No messages"
      action={<button onClick={action}>Start</button>}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Start" }));
  expect(action).toHaveBeenCalledOnce();
});
