/** @vitest-environment jsdom */
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import i18n from "../../../../../i18n";
import { ProviderSelect } from "../../../AgentPanel/shared/ProviderSelect";
import { ModelIconSelect } from "../ModelIconSelect";

vi.mock("../../../../../services/api/model", () => ({
  modelApi: {
    listProviders: async () => [{ value: "openai" }, { value: "anthropic" }],
  },
}));
vi.mock("../../../../agent/modelIcon.tsx", () => ({
  ModelIconImg: () => null,
}));
afterEach(cleanup);

test.each([
  ["provider", ProviderSelect, "agentConfig.modelProvider"],
  ["icon", ModelIconSelect, "agentConfig.modelIcon"],
] as const)(
  "%s picker keeps Escape local and restores focus after choosing",
  async (_, Picker, label) => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const editorKey = vi.fn();
    function ControlledPicker() {
      const [value, setValue] = useState("");
      return (
        <div onKeyDown={editorKey}>
          <Picker
            value={value}
            onChange={(next) => {
              setValue(next);
              onChange(next);
            }}
            placeholder="Auto"
          />
        </div>
      );
    }
    render(<ControlledPicker />);
    const trigger = screen.getByRole("button", { name: i18n.t(label) });
    expect(trigger).toHaveAccessibleDescription("Auto");
    await user.tab();
    await user.keyboard("{Enter}");
    const search = await screen.findByRole("textbox", {
      name: i18n.t("common.search"),
    });
    expect(search).toHaveFocus();
    editorKey.mockClear();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(editorKey).not.toHaveBeenCalled();
    await user.keyboard("{Enter}");
    await user.keyboard("{ArrowUp}");
    expect(screen.getAllByRole("option").at(-1)).toHaveFocus();
    await user.keyboard("{Escape}{Enter}");
    await user.type(
      screen.getByRole("textbox", { name: i18n.t("common.search") }),
      "openai",
    );
    const list = screen.getByRole("listbox", { name: i18n.t(label) });
    await user.click(within(list).getByRole("option", { name: /OpenAI/ }));
    expect(onChange).toHaveBeenCalledWith("openai");
    expect(trigger).toHaveAccessibleDescription("OpenAI");
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole("listbox")).toBeNull();
  },
);
