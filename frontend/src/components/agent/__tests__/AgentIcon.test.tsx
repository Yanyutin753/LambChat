/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AgentIcon } from "../AgentIcon";
import { AgentAvatar } from "../../common/AgentAvatar";
import { ModelIconImg } from "../modelIcon.tsx";

afterEach(cleanup);

test("missing and unknown icons get a stable local color avatar", () => {
  const { container, rerender } = render(<AgentIcon seed="avatar-1" />);
  const shapes = () => container.querySelector("[data-avatar-style=boring]")?.getAttribute("style");
  expect(shapes()).toBeTruthy();
  const first = shapes();
  rerender(<AgentIcon seed="avatar-1" icon="unrecognized" />);
  expect(shapes()).toBe(first);
  rerender(<AgentIcon seed="avatar-2" />);
  expect(shapes()).not.toBe(first);
  expect(container.querySelector("img")).toBeNull();
});

test("legacy category icons use avatars and emoji keep their meaning", () => {
  const { container, rerender } = render(<AgentIcon icon="icon:security" />);
  expect(container.querySelector("[data-avatar-style=boring]")).not.toBeNull();
  rerender(<AgentIcon icon="🤖" />);
  expect(container.querySelector("img")?.src).toContain("1f916");
});

test("a broken uploaded avatar falls back locally", () => {
  const { container } = render(<AgentIcon icon="https://example.com/avatar.png" seed="avatar-1" />);
  fireEvent.error(container.querySelector("img")!);
  expect(container.querySelector("[data-avatar-style=boring]")).not.toBeNull();
});


test("a brand avatar fills a percentage-sized panel frame", () => {
  const { container } = render(
    <AgentAvatar avatar="lobe:openai" size="100%" />,
  );
  const frame = container.firstElementChild as HTMLElement;
  expect(frame.style.width).toBe("100%");
  expect(frame.style.height).toBe("100%");
  expect(frame.style.borderRadius).toBe("50%");
  expect(container.querySelector("img")).not.toBeNull();
});

test("default and legacy identities use Boring avatars while custom icons remain", () => {
  const { container, rerender } = render(<AgentIcon seed="research" />);
  expect(container.querySelector("svg")).not.toBeNull();
  expect((container.firstElementChild as HTMLElement).style.borderRadius).toBe("50%");
  rerender(<AgentIcon icon="Bot" seed="research" />);
  expect(container.querySelector(".lucide-bot")).toBeNull();
  rerender(<AgentIcon icon="Zap" seed="research" />);
  expect(container.querySelector(".lucide-zap")).toBeNull();
  rerender(<AgentIcon icon="icon:security" seed="research" />);
  expect(container.querySelector("[data-avatar-style=boring]")).not.toBeNull();
});


test("model icons and initials retain circular frames", () => {
  const { container, rerender } = render(<ModelIconImg model="gpt-4o" icon="openai" size={32} />);
  const frame = container.firstElementChild as HTMLElement;
  expect(frame.style.width).toBe("32px");
  expect(frame.style.height).toBe("32px");
  expect(container.querySelector("img")?.style.width).toBe("100%");
  rerender(<ModelIconImg model="custom-model" size={32} />);
  expect(container.textContent).toBe("C");
  expect((container.firstElementChild as HTMLElement).style.borderRadius).toBe("50%");
});


test("monochrome model marks stay visible in dark panels without recoloring brand logos", () => {
  const { container, rerender } = render(<ModelIconImg model="gpt-4o" icon="openai" />);
  expect(container.querySelector("img")?.parentElement?.className).toContain("dark:[&>img]:invert");
  expect(container.querySelector("img")?.style.objectFit).toBe("contain");
  rerender(<ModelIconImg model="gemini" icon="gemini" />);
  expect(container.querySelector("img")?.parentElement?.className).not.toContain("dark:[&>img]:invert");
});

test("dedicated channel logos remain in the circular frame", async () => {
 const { ChannelIcon } = await import("../../panels/channel/ChannelIcon");
 const { container } = render(<AgentAvatar seed="Slack" size={36}><ChannelIcon channelType="slack" /></AgentAvatar>);
 expect(container.querySelector("img")?.src).toContain("slack");
 expect(container.querySelector("[data-avatar-style=boring]")).toBeNull();
 expect((container.firstElementChild as HTMLElement).style.borderRadius).toBe("50%");
});

test("only generated artwork receives theme toning, uploaded photos keep their colors", () => {
 const { container, rerender } = render(<AgentAvatar seed="research" />);
 expect(container.querySelector(".agent-avatar__artwork svg")).not.toBeNull();
 rerender(<AgentAvatar avatar="https://example.test/photo.png" seed="research" />);
 expect(container.querySelector("img")?.closest(".agent-avatar__artwork")).toBeNull();
});

test("brand model icons render clean without tinted chip background", () => {
  const { container, rerender } = render(<AgentAvatar avatar="lobe:openai" size={36} />);
  let frame = container.firstElementChild as HTMLElement;
  expect(frame.style.background).toBe("");
  rerender(<AgentAvatar avatar="lobe:zhipu" size={36} />);
  frame = container.firstElementChild as HTMLElement;
  expect(frame.style.background).toBe("");
  // 生成的 boring 头像仍保留染色底（共享头像的设计语义）
  rerender(<AgentAvatar avatar="generated:research" seed="research" size={36} />);
  frame = container.firstElementChild as HTMLElement;
  expect(frame.style.background).toContain("color-mix");
});
