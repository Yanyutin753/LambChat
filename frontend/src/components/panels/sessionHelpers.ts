/**
 * Session display helpers
 */

import type { BackendSession } from "../../services/api";
import type { TFunction } from "i18next";
import { parseDate } from "../../utils/datetime";
import { isSessionPinned } from "../sidebar/sessionPin";

export function getSessionTitle(session: BackendSession, t: TFunction): string {
  if (session.name) return session.name;
  const meta = session.metadata as Record<string, unknown>;
  if (meta?.title) return meta.title as string;
  return t("sidebar.newChat");
}

export function groupSessionsByTime(
  sessionList: BackendSession[],
  t: TFunction,
): { label: string; sessions: BackendSession[] }[] {
  const groups: { label: string; sessions: BackendSession[] }[] = [];
  const today: BackendSession[] = [];
  const yesterday: BackendSession[] = [];
  const thisWeek: BackendSession[] = [];
  const older: BackendSession[] = [];

  const now = new Date();
  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);
  const weekStart = new Date(todayStart.getTime() - 7 * 24 * 60 * 60 * 1000);

  sessionList.forEach((session) => {
    const sessionDate = parseDate(session.updated_at);
    if (sessionDate >= todayStart) {
      today.push(session);
    } else if (sessionDate >= yesterdayStart) {
      yesterday.push(session);
    } else if (sessionDate >= weekStart) {
      thisWeek.push(session);
    } else {
      older.push(session);
    }
  });

  if (today.length > 0)
    groups.push({ label: t("sidebar.today"), sessions: today });
  if (yesterday.length > 0)
    groups.push({ label: t("sidebar.yesterday"), sessions: yesterday });
  if (thisWeek.length > 0)
    groups.push({ label: t("sidebar.previous7Days"), sessions: thisWeek });
  if (older.length > 0)
    groups.push({ label: t("sidebar.older"), sessions: older });

  return groups;
}

/**
 * 侧边栏「对话」区分组：置顶会话由独立的「置顶」分类展示
 * （跨项目聚合），时间分组里排除置顶，避免同一会话重复出现。
 */
export function groupSessionsForSidebar(
  sessionList: BackendSession[],
  t: TFunction,
): { label: string; sessions: BackendSession[] }[] {
  return groupSessionsByTime(
    sessionList.filter((session) => !isSessionPinned(session)),
    t,
  );
}
