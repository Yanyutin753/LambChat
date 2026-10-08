/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { WelcomePage } from "../WelcomePage";
import type { ChatInputProps } from "../ChatInput";
import type { PersonaPreset } from "../../../types";

const listTeams = vi.hoisted(() => vi.fn());
vi.mock("../../../services/api/team", () => ({ teamApi: { list: listTeams } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ settings: {}, isLoading: false }),
}));
vi.mock("../ChatInput", () => ({
  ChatInput: ({
    onMentionQueryChange,
    focusRequest,
  }: {
    onMentionQueryChange?: (query: string | null) => void;
    focusRequest?: number;
  }) => {
    const ref = useRef<HTMLDivElement>(null);
    useEffect(() => {
      if (focusRequest) ref.current?.focus();
    }, [focusRequest]);
    return (
      <div
        ref={ref}
        role="textbox"
        contentEditable
        aria-label="Composer"
        onInput={(event) => {
          const value = event.currentTarget.textContent || "";
          onMentionQueryChange?.(value.startsWith("@") ? value.slice(1) : null);
        }}
      />
    );
  },
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
afterEach(cleanup);
beforeEach(() => listTeams.mockReset());

test("persona mention no-match preserves the draft and offers management instead of creation", () => {
  render(
    <MemoryRouter>
      <WelcomePage
        {...props}
        personaPresets={[
          {
            id: "writer",
            name: "Writer",
            description: "Draft reports",
            tags: ["writing"],
          } as PersonaPreset,
        ]}
      />
    </MemoryRouter>,
  );
  const composer = screen.getByRole("textbox", { name: "Composer" });
  fireEvent.input(composer, { target: { textContent: "@unmatched" } });
  expect(screen.getByRole("status")).toHaveTextContent(
    "personaPresets.noMatch",
  );
  expect(screen.queryByText("persona.empty")).toBeNull();
  expect(screen.queryByRole("button", { name: "persona.addNew" })).toBeNull();
  expect(screen.getByRole("button", { name: "common.manage" })).toBeEnabled();
  expect(composer).toHaveTextContent("@unmatched");
  fireEvent.input(composer, { target: { textContent: "@writing" } });
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.getByRole("button", { name: /Writer/ })).toBeEnabled();
  expect(screen.getByRole("textbox", { name: "Composer" })).toBe(composer);
});

test("a successfully loaded empty persona library has an announced empty state", () => {
  render(
    <MemoryRouter>
      <WelcomePage {...props} />
    </MemoryRouter>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("persona.empty");
  expect(screen.queryByText("personaPresets.noMatch")).toBeNull();
  expect(screen.getByRole("button", { name: "common.manage" })).toBeEnabled();
});

test("team mention no-match does not report an empty library", async () => {
  listTeams.mockResolvedValueOnce({
    teams: [{ id: "research", name: "Research", members: [] }],
  });
  render(
    <MemoryRouter>
      <WelcomePage {...props} currentAgent="team" onSelectTeam={vi.fn()} />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: /Research/ });
  const composer = screen.getByRole("textbox", { name: "Composer" });
  fireEvent.input(composer, { target: { textContent: "@unmatched" } });
  expect(screen.getByRole("status")).toHaveTextContent("team.noMatchingTeams");
  expect(screen.queryByText("team.empty")).toBeNull();
  expect(screen.queryByRole("button", { name: "team.addNew" })).toBeNull();
  fireEvent.input(composer, { target: { textContent: "@Research" } });
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.getByRole("button", { name: /Research/ })).toBeEnabled();
});

test("loaded empty teams are announced separately from failed or loading teams", async () => {
  listTeams.mockResolvedValueOnce({ teams: [] });
  render(
    <MemoryRouter>
      <WelcomePage {...props} currentAgent="team" onSelectTeam={vi.fn()} />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("status")).toBeNull();
  expect(await screen.findByRole("status")).toHaveTextContent("team.empty");
  expect(screen.queryByRole("alert")).toBeNull();
});

test.each(["fast", "team"])(
  "management opens the correct library for %s",
  async (currentAgent) => {
    if (currentAgent === "team") listTeams.mockResolvedValueOnce({ teams: [] });
    function Path() {
      return (
        <output aria-label="Current page">{useLocation().pathname}</output>
      );
    }
    render(
      <MemoryRouter initialEntries={["/chat"]}>
        <WelcomePage {...props} currentAgent={currentAgent} />
        <Path />
      </MemoryRouter>,
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "common.manage" }),
    );
    expect(screen.getByLabelText("Current page")).toHaveTextContent(
      currentAgent === "team" ? "/team" : "/persona",
    );
  },
);

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

test("a selected team without starter prompts keeps the team heading and change action", async () => {
  listTeams.mockImplementationOnce(async () => {
    await new Promise((resolve) => setTimeout(resolve, 10));
    return { teams: [{ id: "research", name: "Research", members: [] }] };
  });
  render(
    <MemoryRouter>
      <WelcomePage
        {...props}
        currentAgent="team"
        selectedTeamId="research"
        onSelectTeam={vi.fn()}
      />
    </MemoryRouter>,
  );
  expect(await screen.findByText("team.plaza")).toBeInTheDocument();
  expect(listTeams).toHaveBeenCalledOnce();
  expect(screen.queryByText("personaPresets.title")).toBeNull();
  expect(screen.getByRole("button", { name: "team.change" })).toBeEnabled();
});

test("selecting and changing teams requests composer focus without replacing the draft", async () => {
  listTeams.mockResolvedValueOnce({
    teams: [{ id: "research", name: "Research", members: [] }],
  });
  function Welcome() {
    const [selectedTeamId, onSelectTeam] = useState<string | null>(null);
    return (
      <WelcomePage
        {...props}
        currentAgent="team"
        selectedTeamId={selectedTeamId}
        onSelectTeam={onSelectTeam}
      />
    );
  }
  render(
    <MemoryRouter>
      <Welcome />
    </MemoryRouter>,
  );
  const composer = await screen.findByRole("textbox", { name: "Composer" });
  fireEvent.input(composer, { target: { textContent: "Keep this draft" } });
  const team = await screen.findByRole("button", { name: /Research/ });
  team.focus();
  fireEvent.click(team);
  await waitFor(() => expect(composer).toHaveFocus());
  expect(composer).toHaveTextContent("Keep this draft");
  const change = screen.getByRole("button", { name: "team.change" });
  change.focus();
  fireEvent.click(change);
  await waitFor(() => expect(composer).toHaveFocus());
  expect(screen.getByRole("textbox", { name: "Composer" })).toBe(composer);
  expect(composer).toHaveTextContent("Keep this draft");
});
