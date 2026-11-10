/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { WelcomeSuggestions } from "../WelcomeSuggestions";

afterEach(cleanup);

test("suggestions pass the full prompt to the existing composer callback", () => {
  const onSelect = vi.fn();
  const text = "Plan a complex project and independently check the constraints";
  render(<WelcomeSuggestions suggestions={[{ text }]} onSelect={onSelect} />);
  fireEvent.click(screen.getByRole("button", { name: text }));
  expect(onSelect).toHaveBeenCalledExactlyOnceWith(text);
});

test("unavailable suggestions do not change the draft", () => {
  const onSelect = vi.fn();
  render(
    <WelcomeSuggestions
      suggestions={[{ text: "Start" }]}
      onSelect={onSelect}
      disabled
    />,
  );
  const button = screen.getByRole("button", { name: "Start" });
  expect(button).toBeDisabled();
  fireEvent.click(button);
  expect(onSelect).not.toHaveBeenCalled();
});
