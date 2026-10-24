/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { DocumentParseItem } from "../DocumentParseItem";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

afterEach(() => {
  cleanup();
  closePersistentToolPanel();
});

test("a failed document parse exposes the provider error in its detail panel", () => {
  const item = render(
    <DocumentParseItem
      args={{ url: "https://example.com/report.pdf" }}
      result={{ error: "The document is encrypted." }}
      success={false}
    />,
  );
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.getByRole("alert")).toHaveTextContent(
    "The document is encrypted.",
  );
});

test("an attachment ID parse displays the returned filename and opens its details", () => {
  const item = render(
    <DocumentParseItem
      args={{ attachment_id: "file-1" }}
      result={{
        success: true,
        filename: "private-invoice.pdf",
        markdown: "Invoice total: 317",
        provider: "mineru:cloud",
        pages_processed: 1,
      }}
      success
    />,
  );
  expect(item.getByText(/private-invoice\.pdf/)).toBeInTheDocument();
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.getAllByText("Invoice total: 317").length).toBeGreaterThan(0);
});

test("a failed attachment ID parse remains expandable without a URL", () => {
  const item = render(
    <DocumentParseItem
      args={{ attachment_id: "file-1" }}
      result={{ error: "Attachment unavailable in this session" }}
      success={false}
    />,
  );
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.getByRole("alert")).toHaveTextContent(
    "Attachment unavailable in this session",
  );
});
