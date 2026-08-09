/** @vitest-environment jsdom */

import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, test, vi } from "vitest";
import {
  DocumentViewerFrame,
  ScaledDocumentContent,
} from "../DocumentViewerFrame";
import { calculateDocumentFitScale } from "../documentViewerLayout";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) =>
      ({
        "imageViewer.zoomIn": "Zoom in",
        "imageViewer.zoomOut": "Zoom out",
        "imageViewer.reset": "Fit window",
      })[key] ?? key,
  }),
}));

class ResizeObserverStub {
  observe() {}
  disconnect() {}
  unobserve() {}
}

beforeAll(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    get: () => 800,
  });
});

describe("DocumentViewerFrame", () => {
  test("treats 100 percent as a fitted view without upscaling wide canvases", () => {
    expect(calculateDocumentFitScale(800, 960, 40)).toBeCloseTo(760 / 960);
    expect(calculateDocumentFitScale(1200, 960, 40)).toBe(1);
  });

  test("renders native scrolling content with shared zoom controls", () => {
    render(
      <DocumentViewerFrame naturalWidth={960} ariaLabel="Document pages">
        {({ displayScale }) => (
          <output data-testid="display-scale">{displayScale.toFixed(3)}</output>
        )}
      </DocumentViewerFrame>,
    );

    expect(screen.getByLabelText("Document pages")).toHaveClass(
      "overflow-auto",
    );
    expect(screen.getByTestId("display-scale")).toHaveTextContent("0.792");
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Zoom out" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Fit window" }),
    ).toBeInTheDocument();
  });
});

test("ScaledDocumentContent reserves transformed scroll geometry", () => {
  render(
    <ScaledDocumentContent
      naturalWidth={960}
      naturalHeight={540}
      displayScale={0.5}
    />,
  );

  expect(screen.getByTestId("scaled-document-bounds")).toHaveStyle({
    width: "480px",
    height: "270px",
  });
  expect(screen.getByTestId("scaled-document-content")).toHaveStyle({
    width: "960px",
    height: "540px",
    transform: "scale(0.5)",
    transformOrigin: "top left",
  });
});
