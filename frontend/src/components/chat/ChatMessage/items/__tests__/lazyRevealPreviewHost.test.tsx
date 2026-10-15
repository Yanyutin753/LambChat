/** @vitest-environment jsdom */
import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { LazyRevealPreviewHost } from "../LazyRevealPreviewHost";
import {
  clearRevealPreviewTabs,
  setActiveRevealPreviewState,
} from "../activeRevealPreviewStore";
import type { RevealPreviewRequest } from "../revealPreviewData";

const host = vi.hoisted(() => ({ renders: vi.fn(), loads: vi.fn() }));
vi.mock("../RevealPreviewHost", () => {
  host.loads();
  return {
    RevealPreviewHost: (props: { onClose: () => void }) => {
      host.renders(props);
      return <button onClick={props.onClose}>Preview</button>;
    },
  };
});
const preview = { previewKey: "lazy-test" } as RevealPreviewRequest;
afterEach(() => {
  act(() => clearRevealPreviewTabs());
  vi.clearAllMocks();
});

test("an idle chat does not import or render the document preview graph", () => {
  const { container } = render(<LazyRevealPreviewHost preview={null} onClose={vi.fn()} />);
  expect(container).toBeEmptyDOMElement();
  expect(host.loads).not.toHaveBeenCalled();
  expect(host.renders).not.toHaveBeenCalled();
});

test("a preview request loads the host and forwards its callbacks", async () => {
  const onClose = vi.fn();
  const onUserInteraction = vi.fn();
  render(<LazyRevealPreviewHost preview={preview} onClose={onClose} onUserInteraction={onUserInteraction} />);
  await screen.findByText("Preview");
  expect(host.renders).toHaveBeenCalledWith(expect.objectContaining({ preview, onClose, onUserInteraction }));
});

test("existing tabs load the host even when the current preview prop is empty", async () => {
  const { container } = render(<LazyRevealPreviewHost preview={null} onClose={vi.fn()} />);
  expect(container).toBeEmptyDOMElement();
  act(() => setActiveRevealPreviewState({ request: preview, source: "manual", userInteracted: false }));
  await screen.findByText("Preview");
  act(() => clearRevealPreviewTabs());
  expect(container).toBeEmptyDOMElement();
});
