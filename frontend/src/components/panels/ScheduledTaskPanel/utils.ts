import type { TFunction } from "i18next";
import type { ScheduledTask } from "../../../types/scheduledTask";
import type { SSEEventRecord } from "../../../types/session";
import { formatDateTimeShort } from "../../../utils/datetime";
import type { RunConversationMessage, ScheduledTaskDefaults } from "./types";

const SCHEDULED_TASK_DEFAULTS_KEY = "lambchat_scheduled_task_defaults";

export type SchedulePreset =
  | ScheduledTask["trigger_type"]
  | "daily"
  | "weekdays"
  | "weekly";

export function getSchedulePreset(
  task?: Pick<ScheduledTask, "trigger_type" | "trigger_config"> | null,
): SchedulePreset {
  if (!task || task.trigger_type !== "cron")
    return task?.trigger_type ?? "interval";
  const config = task.trigger_config as Record<string, unknown>;
  // Only collapse schedules that the simple controls can represent without loss.
  if (
    Object.keys(config).some(
      (key) => !["hour", "minute", "second", "day_of_week"].includes(key),
    ) ||
    !/^(?:[01]?\d|2[0-3])$/.test(String(config.hour)) ||
    !/^[0-5]?\d$/.test(String(config.minute ?? "0")) ||
    Number(config.second ?? 0) !== 0
  )
    return "cron";
  if (!config.day_of_week || config.day_of_week === "*") return "daily";
  if (config.day_of_week === "mon-fri") return "weekdays";
  return /^(mon|tue|wed|thu|fri|sat|sun)$/.test(String(config.day_of_week))
    ? "weekly"
    : "cron";
}

export function getBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

export function readScheduledTaskDefaults(): ScheduledTaskDefaults {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(SCHEDULED_TASK_DEFAULTS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as ScheduledTaskDefaults;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function extractRunConversationMessages(
  events: SSEEventRecord[],
): RunConversationMessage[] {
  const messages: RunConversationMessage[] = [];

  for (const event of events) {
    if (event.event_type === "user:message") {
      const content = event.data?.content as string | undefined;
      if (content) {
        messages.push({
          role: "user",
          content,
          timestamp: event.timestamp,
        });
      }
      continue;
    }

    if (event.event_type === "assistant:text") {
      const content = event.data?.content as string | undefined;
      if (!content) continue;

      const last = messages[messages.length - 1];
      if (last?.role === "assistant" && last.timestamp === event.timestamp) {
        last.content += content;
      } else {
        messages.push({
          role: "assistant",
          content,
          timestamp: event.timestamp,
        });
      }
    }
  }

  return messages;
}

export function toDateTimeLocalValue(value: string | null | undefined): string {
  const date = value ? new Date(value) : new Date(Date.now() + 5 * 60 * 1000);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

export function formatTaskTrigger(task: ScheduledTask, t: TFunction): string {
  if (task.trigger_type === "interval") {
    const cfg = task.trigger_config as { seconds?: number };
    const seconds = cfg.seconds ?? 0;
    if (seconds > 0 && seconds % 3600 === 0)
      return t("scheduledTask.everyHours", { count: seconds / 3600 });
    if (seconds > 0 && seconds % 60 === 0)
      return t("scheduledTask.everyMinutes", { count: seconds / 60 });
    return t("scheduledTask.everySeconds", { count: seconds });
  }

  if (task.trigger_type === "date") {
    const cfg = task.trigger_config as { run_date?: string };
    return `${t("scheduledTask.date")}: ${
      cfg.run_date ? formatDateTimeShort(cfg.run_date) : "-"
    }`;
  }

  const cfg = task.trigger_config as {
    hour?: string;
    minute?: string;
    day?: string;
    month?: string;
    day_of_week?: string;
  };
  const preset = getSchedulePreset(task);
  if (preset === "daily" || preset === "weekdays" || preset === "weekly") {
    const time = `${String(cfg.hour).padStart(2, "0")}:${String(
      cfg.minute ?? "0",
    ).padStart(2, "0")}`;
    const day =
      preset === "weekly"
        ? ` · ${t(`scheduledTask.weekday.${cfg.day_of_week}`)}`
        : "";
    return `${t(`scheduledTask.${preset}`)}${day} · ${time} (${task.timezone})`;
  }
  return `${t("scheduledTask.cron")}: ${[
    cfg.minute ?? "*",
    cfg.hour ?? "*",
    cfg.day ?? "*",
    cfg.month ?? "*",
    cfg.day_of_week ?? "*",
  ].join(" ")}`;
}
