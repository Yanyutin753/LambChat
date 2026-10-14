/** @vitest-environment jsdom */
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { resolveChatAssistantIdentity } from "../ChatViewProps";
import { AssistantAvatar } from "../../../chat/ChatMessage/AssistantAvatar";
import { AgentIcon } from "../../../agent/AgentIcon";
import { AgentAvatar } from "../../../common/AgentAvatar";

afterEach(cleanup);

const baseArgs = {
  currentAgent: "fast",
  currentPersonaAvatar: null,
  currentTeam: null,
  selectedPersonaName: null,
};

function artwork(container: HTMLElement) {
  return Array.from(container.querySelectorAll("svg path, svg rect, svg circle"))
    .map((shape) => [shape.tagName, shape.getAttribute("d"), shape.getAttribute("fill"), shape.getAttribute("transform")]);
}

test("message and selector use the same fast avatar across languages", () => {
  const selector = render(<AgentIcon icon="Zap" seed="fast" />);
  for (const name of ["快速助手", "Fast Agent"]) {
    const identity = resolveChatAssistantIdentity({ ...baseArgs, agentDisplayName: name });
    const message = render(<AssistantAvatar personaAvatar={identity.avatar} personaName={identity.name} personaSeed={identity.seed} />);
    expect(artwork(message.container)).toEqual(artwork(selector.container));
    message.unmount();
  }
});

test("persona avatars use the preset id instead of the display name", () => {
  const identity = resolveChatAssistantIdentity({
    ...baseArgs,
    selectedPersonaName: "Researcher",
    selectedPersonaPresetId: "role-42",
  });
  const selector = render(<AgentAvatar seed="role-42" />);
  const message = render(<AssistantAvatar personaAvatar={identity.avatar} personaName={identity.name} personaSeed={identity.seed} />);
  expect(artwork(message.container)).toEqual(artwork(selector.container));
});

test("custom agent and persona avatars remain preferred", () => {
  expect(resolveChatAssistantIdentity({ ...baseArgs, agentIcon: "🤖" }).avatar).toBe("🤖");
  expect(resolveChatAssistantIdentity({ ...baseArgs, agentIcon: "🤖", currentPersonaAvatar: "/role.png", selectedPersonaName: "Role" }).avatar).toBe("/role.png");
});
