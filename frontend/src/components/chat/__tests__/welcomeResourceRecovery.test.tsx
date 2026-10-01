/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { WelcomePage } from "../WelcomePage";
import type { ChatInputProps } from "../ChatInput";

const listTeams = vi.hoisted(() => vi.fn());
vi.mock("../../../services/api/team", () => ({ teamApi: { list: listTeams } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ settings: {}, isLoading: false }),
}));
vi.mock("../ChatInput", () => ({
  ChatInput: () => <div role="textbox" contentEditable aria-label="Composer" />,
}));
vi.mock("../../common/ContactAdminDialog", () => ({
  ContactAdminDialog: () => null,
}));
vi.mock("../../notification/NotificationBanner", () => ({
  NotificationBanner: () => null,
}));
vi.mock("../../persona/PersonaAvatarWithLoading", () => ({
  PersonaAvatarWithLoading: () => null,
}));
vi.mock("../../team/TeamAvatar", () => ({ TeamAvatar: () => null }));
vi.mock("../../skeletons/ChatSkeletons", () => ({
  WelcomeSkeleton: () => <div>Loading welcome</div>,
}));

const props = {
  greeting: "Hello",
  subtitle: "How can I help?",
  refreshLabel: "Refresh",
  personaPresets: [],
  personaPresetsLoaded: true,
  currentAgent: "fast",
  canSendMessage: true,
  chatInputProps: {} as ChatInputProps,
};

test("persona failures offer retry instead of suggesting an empty library", () => {
  const retry = vi.fn();
  render(
    <MemoryRouter>
      <WelcomePage
        {...props}
        personaPresetsError="Request timed out"
        onRetryPersonaPresets={retry}
      />
    </MemoryRouter>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Request timed out");
  expect(screen.queryByText("persona.empty")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  expect(retry).toHaveBeenCalledOnce();
  expect(screen.getByRole("textbox", { name: "Composer" })).toHaveFocus();
});

test("team failures recover without remounting the composer", async () => {
  listTeams.mockRejectedValueOnce(new Error("Unavailable"));
  listTeams.mockResolvedValueOnce({ teams: [] });
  render(
    <MemoryRouter>
      <WelcomePage {...props} currentAgent="team" onSelectTeam={vi.fn()} />
    </MemoryRouter>,
  );
  await screen.findByRole("alert");
  const composer = screen.getByRole("textbox", { name: "Composer" });
  expect(screen.queryByText("team.empty")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.retry" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  await screen.findByText("team.empty");
  expect(listTeams).toHaveBeenCalledTimes(2);
  expect(screen.getByRole("textbox", { name: "Composer" })).toBe(composer);
});
