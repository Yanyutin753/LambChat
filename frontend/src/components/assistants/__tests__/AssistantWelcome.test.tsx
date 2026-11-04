/** @vitest-environment jsdom */
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantWelcome } from "../AssistantWelcome";
import type { Assistant } from "../../../types/assistant";
import type { ChatInputProps } from "../../chat/ChatInput";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../chat/ChatInput", () => ({
  ChatInput: (props: ChatInputProps) => (
    <div>
      Existing composer
      <output data-testid="suggested-input">{props.pendingInput}</output>
    </div>
  ),
}));
afterEach(cleanup);
test("Chief welcome uses the current identity and existing composer without a role marketplace", () => {
  render(
    <AssistantWelcome
      assistant={{ name: "Chief", kind: "chief" } as Assistant}
      chatInputProps={{} as ChatInputProps}
    />,
  );
  expect(screen.getByRole("heading", { name: "Chief" })).toBeTruthy();
  expect(screen.getByText("assistants.chiefWelcome")).toBeTruthy();
  expect(screen.getByText("Existing composer")).toBeTruthy();
  expect(screen.queryByText("personaPresets.title")).toBeNull();
});

test.each(["chief", "assistant", "group"] as const)(
  "%s has three starters that fill the composer without sending",
  (kind) => {
    const onSend = vi.fn();
    render(
      <AssistantWelcome
        assistant={{ name: "Test", kind } as Assistant}
        chatInputProps={{ onSend } as unknown as ChatInputProps}
      />,
    );
    const suggestions = screen.getAllByRole("button");
    expect(suggestions).toHaveLength(3);
    expect(suggestions[0].textContent).toBe(
      `assistants.starters.${kind}.first`,
    );
    fireEvent.click(suggestions[0]);
    expect(screen.getByTestId("suggested-input").textContent).toBe(
      suggestions[0].textContent,
    );
    expect(onSend).not.toHaveBeenCalled();
  },
);

test.each([
  { disabled: true },
  { isLoading: true },
  { sendBlocked: true },
  { canSend: false },
])("starter suggestions respect composer availability: %j", (state) => {
  render(
    <AssistantWelcome
      assistant={{ name: "Chief", kind: "chief" } as Assistant}
      chatInputProps={state as ChatInputProps}
    />,
  );
  for (const button of screen.getAllByRole("button"))
    expect((button as HTMLButtonElement).disabled).toBe(true);
});
