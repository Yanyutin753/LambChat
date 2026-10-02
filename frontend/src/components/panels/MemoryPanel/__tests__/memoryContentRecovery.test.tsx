/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import { resetRightPanelCoordinator } from "../../../common/rightPanelCoordinator";
import { DetailModal } from "../DetailModal";
import { MemoryEditor } from "../MemoryEditor";
import { MemoryPanel } from "../index";
import type { MemoryItem } from "../../../../services/api/memory";

const { get, update, list } = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  list: vi.fn(),
}));
vi.mock("../../../../services/api/memory", () => ({
  memoryApi: { get, update, list },
}));

const memory: MemoryItem = {
  memory_id: "one",
  title: "Research notes",
  summary: "List summary",
  content: "Stored excerpt",
  memory_type: "user",
  source: "manual",
  tags: [],
  created_at: null,
  updated_at: null,
  access_count: 0,
  has_full_content: true,
};
const full = {
  ...memory,
  content: "Complete research notes with every constraint",
  summary: "Full summary",
};
const close = vi.fn();
const saved = vi.fn();
const time = () => "Updated recently";

beforeEach(() => {
  resetRightPanelCoordinator();
  vi.clearAllMocks();
  get.mockReset();
  update.mockReset();
  update.mockResolvedValue({ success: true });
});
afterEach(cleanup);

test("memory detail reports a failed full read instead of showing the excerpt, and retries", async () => {
  get.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(full);
  render(
    <DetailModal
      memory={memory}
      onClose={close}
      onDelete={vi.fn()}
      onEdit={vi.fn()}
      relativeTime={time}
    />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
  expect(screen.queryByText(memory.content)).toBeNull();
  const retry = screen.getByRole("button", { name: i18n.t("common.retry") });
  retry.focus();
  fireEvent.click(retry);
  expect(document.activeElement?.isConnected).toBe(true);
  expect(await screen.findByText(full.content)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
  expect(get).toHaveBeenCalledTimes(2);
});

test("memory editor cannot save a failed read and retry retains metadata edits before saving full content", async () => {
  let resolve!: (value: MemoryItem) => void;
  get.mockRejectedValueOnce(new Error("offline")).mockImplementationOnce(
    () =>
      new Promise<MemoryItem>((done) => {
        resolve = done;
      }),
  );
  render(
    <MemoryEditor
      memory={memory}
      onClose={close}
      onSaved={saved}
      relativeTime={time}
    />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
  const save = screen.getByRole("button", { name: i18n.t("common.save") });
  expect(save).toBeDisabled();
  fireEvent.click(save);
  expect(update).not.toHaveBeenCalled();
  expect(screen.queryByLabelText(i18n.t("memory.contentLabel"))).toBeNull();
  fireEvent.change(screen.getByLabelText(i18n.t("memory.titleLabel")), {
    target: { value: "My revised title" },
  });
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  expect(save).toBeDisabled();
  await act(async () => resolve(full));
  expect(screen.getByLabelText(i18n.t("memory.contentLabel"))).toHaveValue(
    full.content,
  );
  expect(screen.getByLabelText(i18n.t("memory.titleLabel"))).toHaveValue(
    "My revised title",
  );
  fireEvent.click(save);
  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      "one",
      expect.objectContaining({
        title: "My revised title",
        content: full.content,
        summary: full.summary,
      }),
    ),
  );
  expect(saved).toHaveBeenCalledTimes(1);
});

test("switching detail during a pending read cannot display the previous record", async () => {
  let resolve!: (value: MemoryItem) => void;
  get.mockImplementationOnce(
    () =>
      new Promise<MemoryItem>((done) => {
        resolve = done;
      }),
  );
  const props = {
    onClose: close,
    onDelete: vi.fn(),
    onEdit: vi.fn(),
    relativeTime: time,
  };
  const { rerender } = render(<DetailModal memory={memory} {...props} />);
  const other = {
    ...memory,
    memory_id: "two",
    title: "Other notes",
    content: "Inline complete notes",
    has_full_content: false,
  };
  rerender(<DetailModal memory={other} {...props} />);
  expect(await screen.findByText(other.content)).toBeInTheDocument();
  await act(async () => resolve(full));
  expect(screen.getByText(other.content)).toBeInTheDocument();
  expect(screen.queryByText(full.content)).toBeNull();
});

test("switching card editors starts the new draft and ignores a late full read", async () => {
  let resolve!: (value: MemoryItem) => void;
  get.mockImplementationOnce(
    () =>
      new Promise<MemoryItem>((done) => {
        resolve = done;
      }),
  );
  const other = {
    ...memory,
    memory_id: "two",
    title: "Other notes",
    content: "Inline complete notes",
    has_full_content: false,
  };
  list.mockResolvedValue({ memories: [memory, other], total: 2 });
  render(<MemoryPanel />);
  await screen.findByRole("button", { name: memory.title });
  fireEvent.click(
    screen.getAllByRole("button", {
      name: i18n.t("common.edit"),
      exact: true,
    })[0],
  );
  expect(
    screen.getByRole("button", { name: i18n.t("common.save") }),
  ).toBeDisabled();
  fireEvent.click(
    screen.getAllByRole("button", {
      name: i18n.t("common.edit"),
      exact: true,
    })[1],
  );
  expect(screen.getByLabelText(i18n.t("memory.titleLabel"))).toHaveValue(
    other.title,
  );
  expect(screen.getByLabelText(i18n.t("memory.contentLabel"))).toHaveValue(
    other.content,
  );
  await act(async () => resolve(full));
  expect(screen.getByLabelText(i18n.t("memory.contentLabel"))).toHaveValue(
    other.content,
  );
});

test("a pending save freezes its draft and cannot close a subsequently opened editor", async () => {
  let resolve!: (value: { success: boolean }) => void;
  update.mockImplementationOnce(
    () =>
      new Promise<{ success: boolean }>((done) => {
        resolve = done;
      }),
  );
  const first = { ...memory, has_full_content: false };
  const other = {
    ...first,
    memory_id: "two",
    title: "Other notes",
    content: "Inline complete notes",
  };
  list.mockResolvedValue({ memories: [first, other], total: 2 });
  render(<MemoryPanel />);
  await screen.findByRole("button", { name: memory.title });
  fireEvent.click(
    screen.getAllByRole("button", {
      name: i18n.t("common.edit"),
      exact: true,
    })[0],
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  expect(screen.getByLabelText(i18n.t("memory.titleLabel"))).toBeDisabled();
  fireEvent.click(
    screen.getAllByRole("button", {
      name: i18n.t("common.edit"),
      exact: true,
    })[1],
  );
  await act(async () => resolve({ success: true }));
  expect(screen.getByLabelText(i18n.t("memory.titleLabel"))).toHaveValue(
    other.title,
  );
  expect(
    screen.getByRole("button", { name: i18n.t("common.save") }),
  ).toBeEnabled();
});

test("a failed memory save keeps a persistent error and retries the same draft", async () => {
  update
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ success: true });
  render(
    <MemoryEditor
      memory={{ ...memory, has_full_content: false }}
      onClose={close}
      onSaved={saved}
      relativeTime={time}
    />,
  );
  fireEvent.change(screen.getByLabelText(i18n.t("memory.titleLabel")), {
    target: { value: "Revised title" },
  });
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.save") }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    i18n.t("memory.saveError"),
  );
  expect(close).not.toHaveBeenCalled();
  expect(saved).not.toHaveBeenCalled();
  expect(screen.getByLabelText(i18n.t("memory.titleLabel"))).toHaveValue(
    "Revised title",
  );
  expect(screen.getByLabelText(i18n.t("memory.contentLabel"))).toHaveValue(
    memory.content,
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.retry") }));
  await waitFor(() => expect(saved).toHaveBeenCalledTimes(1));
  expect(update).toHaveBeenCalledTimes(2);
  expect(update.mock.calls[1]).toEqual(update.mock.calls[0]);
});
