/** @vitest-environment jsdom */
import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantWelcome } from "../AssistantWelcome";
import type { Assistant } from "../../../types/assistant";
import type { ChatInputProps } from "../../chat/ChatInput";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../chat/ChatInput", () => ({
  ChatInput: () => <div>Existing composer</div>,
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
