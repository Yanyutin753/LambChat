/** @vitest-environment jsdom */
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AudioTranscribeItem } from "../AudioTranscribeItem";
import {
  closePersistentToolPanel,
  getPersistentToolPanelState,
} from "../persistentToolPanelState";

afterEach(() => {
  cleanup();
  closePersistentToolPanel();
});

test("a structured transcription displays the transcript rather than its JSON envelope", () => {
  const transcript = "这是一段真实格式的转写文本。";
  const item = render(
    <AudioTranscribeItem
      args={{ url: "https://example.com/voice.m4a" }}
      result={JSON.stringify({ success: true, text: transcript })}
      success
    />,
  );
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.getByText(transcript, { exact: true })).toBeVisible();
  expect(panel.container.textContent).not.toContain('"success"');
});

test("an already decoded transcript preserves JSON spoken as its literal text", () => {
  const transcript = '{"text":"原文的一部分"}';
  const item = render(
    <AudioTranscribeItem
      args={{}}
      result={{ success: true, text: transcript }}
      success
    />,
  );
  fireEvent.click(item.container.querySelector("button")!);
  const panel = render(getPersistentToolPanelState()!.children);
  expect(panel.getByText(transcript, { exact: true })).toBeVisible();
});
