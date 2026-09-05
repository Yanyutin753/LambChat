// @vitest-environment jsdom
import { describe, it, expect } from "vitest";
import { fireEvent, render, within } from "@testing-library/react";
import { Tooltip } from "../Tooltip";

describe("Tooltip controlled open", () => {
  it("shows the bubble immediately when open is true", () => {
    render(
      <Tooltip content="运行中" open>
        <span data-testid="icon" />
      </Tooltip>,
    );
    const bubble = within(document.body).getByText("运行中");
    expect(bubble).toHaveClass("fixed", "pointer-events-none");
  });

  it("does not suppress hover behavior when open is false", () => {
    const view = render(
      <Tooltip content="运行中" open={false}>
        <span data-testid="icon" />
      </Tooltip>,
    );
    expect(within(document.body).queryByText("运行中")).not.toBeInTheDocument();
    fireEvent.mouseEnter(view.getByTestId("icon"));
    expect(within(document.body).getByText("运行中")).toBeInTheDocument();
  });
});
