/* eslint-disable react-refresh/only-export-components */
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { CollapsibleStatus } from "../../../common/CollapsiblePill";
import {
  openPersistentToolPanel,
  type PersistentToolPanelState,
} from "./persistentToolPanelState";
import {
  toolCallPanelStore,
  type ToolCallPanelData,
} from "../toolCallPanelStore";

/** 专属工具项的 detail 组件统一接收的 props 形状（即 store 数据的字段） */
export interface ToolDetailProps {
  args: Record<string, unknown>;
  result?: string | Record<string, unknown>;
  success?: boolean;
  isPending?: boolean;
  cancelled?: boolean;
  startedAt?: string;
  completedAt?: string;
}

export function toolDetailPropsFromPanelData(
  data: ToolCallPanelData,
): ToolDetailProps {
  return {
    args: data.args,
    result: data.result,
    success: data.success,
    isPending: data.isPending,
    cancelled: data.cancelled,
    startedAt: data.startedAt,
    completedAt: data.completedAt,
  };
}

/** 面板正文距底部不足该距离时，流式更新保持贴底跟随 */
const PANEL_STICK_TO_BOTTOM_PX = 24;

export function shouldStickPanelOutputToBottom(
  scroller: HTMLElement,
  threshold = PANEL_STICK_TO_BOTTOM_PX,
): boolean {
  const distance =
    scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  return distance <= threshold;
}

/**
 * 订阅 toolCallPanelStore 的活面板内容。
 *
 * 面板 children 在打开时固化为一个元素，无法跟随流式更新；本组件按
 * toolCallId 订阅 store（由 ChatView 全量同步，与消息虚拟化无关），
 * 数据每次变化都用 build 重建详情。build 返回的组件类型保持稳定，
 * 内部状态（CodeMirror 滚动位置、表单输入等）不会被重置。
 */
export function ToolLivePanelContent({
  toolCallId,
  build,
  fallback,
}: {
  toolCallId: string;
  build: (data: ToolCallPanelData) => ReactNode;
  /** store 尚无该工具数据时（如历史消息缺 id）显示打开时刻的快照 */
  fallback?: ReactNode;
}) {
  const [, forceRender] = useState(0);
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const listener = () => forceRender((count) => count + 1);
    return toolCallPanelStore.subscribe(toolCallId, listener);
  }, [toolCallId]);

  const data = toolCallPanelStore.get(toolCallId);

  // 流式内容增长时贴底跟随；用户在面板内上滑后不再强行拉底
  useLayoutEffect(() => {
    if (!data) return;
    const scroller = hostRef.current?.closest<HTMLElement>(
      "[data-sidebar-snapshot-key='panel-body']",
    );
    if (!scroller) return;
    if (shouldStickPanelOutputToBottom(scroller)) {
      scroller.scrollTop = scroller.scrollHeight;
    }
  }, [data]);

  return (
    <div ref={hostRef} className="flex min-h-full flex-col">
      {data ? build(data) : fallback}
    </div>
  );
}

/**
 * 打开实时工具面板：有 id 时内容订阅 store 流式刷新（面板状态/页脚由
 * PersistentToolPanelHost 按 panelKey 同步刷新），无 id 时退回静态快照。
 */
export function openToolLivePanel(options: {
  id?: string;
  title: string;
  status: CollapsibleStatus;
  icon?: ReactNode;
  subtitle?: string;
  fallback?: ReactNode;
  buildDetail: (data: ToolCallPanelData) => ReactNode;
  footer?: ReactNode;
  onUserClose?: PersistentToolPanelState["onUserClose"];
}): void {
  const { id } = options;
  openPersistentToolPanel({
    title: options.title,
    icon: options.icon,
    status: options.status,
    subtitle: options.subtitle,
    panelKey: id ? `tool:${id}` : undefined,
    children: id ? (
      <ToolLivePanelContent
        toolCallId={id}
        build={options.buildDetail}
        fallback={options.fallback}
      />
    ) : (
      options.fallback ?? null
    ),
    footer: options.footer,
    onUserClose: options.onUserClose,
  });
}
