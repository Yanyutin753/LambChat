import { clsx } from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ImageWithSkeleton } from "../../chat/ChatMessage/ImageWithSkeleton";
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  Handle,
  Position,
  useReactFlow,
  BackgroundVariant,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  getOutlineFlowActiveAnchorId,
  type MessageOutlineItem,
} from "./messageOutline";
import { useAuth } from "../../../hooks/useAuth";
import { getFullUrl } from "../../../services/api";
import { AssistantAvatar } from "../../chat/ChatMessage/AssistantAvatar";
import "./outlineFlow.css";

// ---- custom node ----

interface OutlineNodeData {
  label: string;
  kind: "user-message" | "assistant-message";
  anchorId: string;
  messageIndex: number;
  isActive: boolean;
  avatarUrl: string | undefined;
  username: string;
  personaAvatar?: string | null;
  [key: string]: unknown;
}

function UserAvatar({
  avatarUrl,
  username,
}: {
  avatarUrl: string | undefined;
  username: string;
}) {
  const fallback = (
    <div className="flex size-[26px] items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full shadow-[0_2px_6px_rgba(0,0,0,0.18)]">
      <span className="text-[11px] font-bold text-white leading-none tracking-wide">
        {username.charAt(0).toUpperCase() || "U"}
      </span>
    </div>
  );

  if (!avatarUrl) return fallback;

  return (
    <ImageWithSkeleton
      src={avatarUrl}
      alt={username}
      skipUrlResolve
      inline
      className="size-[26px] rounded-full ring-1 ring-white/30 shadow-[0_2px_6px_rgba(0,0,0,0.12)]"
      errorFallback={fallback}
    />
  );
}

function OutlineFlowNode({ data }: { data: OutlineNodeData }) {
  const { t } = useTranslation();
  const isUser = data.kind === "user-message";

  return (
    <div
      className={clsx(
        "outline-flow-node",
        "px-3.5 py-3 rounded-xl w-[232px] cursor-pointer",
        "transition-all duration-200 ease-out",
        "border",
        isUser
          ? "bg-white/70 dark:bg-stone-800/50 border-stone-200/60 dark:border-stone-600/40"
          : "bg-stone-50/80 dark:bg-stone-800/60 border-stone-200/50 dark:border-stone-600/30",
        !data.isActive && "shadow-sm hover:shadow-md",
        "hover:-translate-y-[1.5px] hover:border-stone-300/70 dark:hover:border-stone-500/60",
        data.isActive &&
          "!border-[var(--theme-primary)] shadow-lg shadow-[color-mix(in_srgb,var(--theme-primary)_12%,transparent)] ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_18%,transparent)] -translate-y-[1.5px]",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className={clsx(
          "!w-[5px] !h-[5px] !border-none !-top-[2.5px] !rounded-full transition-colors duration-200",
          data.isActive
            ? "!bg-[var(--theme-primary)]"
            : "!bg-stone-300 dark:!bg-stone-500",
        )}
      />
      <div className="flex items-start gap-2.5">
        <div className="shrink-0 pt-[0.5px]">
          {isUser ? (
            <UserAvatar avatarUrl={data.avatarUrl} username={data.username} />
          ) : (
            <AssistantAvatar
              className="size-[26px] rounded-full ring-1 ring-white/25 shadow-[0_2px_6px_rgba(0,0,0,0.12)]"
              personaAvatar={data.personaAvatar}
              personaSize={18}
            />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span
              className={clsx(
                "text-[10.5px] font-semibold leading-none tracking-wide",
                isUser
                  ? "text-stone-500 dark:text-stone-400"
                  : "text-[var(--theme-primary)]",
              )}
            >
              {isUser ? data.username : t("common.assistant")}
            </span>
            {data.isActive && (
              <span className="inline-block size-[4px] rounded-full bg-[var(--theme-primary)] animate-pulse" />
            )}
          </div>
          <div
            className="text-[12.5px] text-[var(--theme-text)] line-clamp-2 mt-[5px] leading-[1.5] [&_strong]:font-semibold [&_strong]:text-[var(--theme-primary)] [&_em]:italic [&_code]:text-[11px] [&_code]:rounded [&_code]:bg-[var(--theme-primary-light)] [&_code]:px-0.5 [&_code]:text-[var(--theme-primary)]"
            dangerouslySetInnerHTML={{
              __html: renderInlineMarkdown(data.label),
            }}
          />
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className={clsx(
          "!w-[5px] !h-[5px] !border-none !-bottom-[2.5px] !rounded-full transition-colors duration-200",
          data.isActive
            ? "!bg-[var(--theme-primary)]"
            : "!bg-stone-300 dark:!bg-stone-500",
        )}
      />
    </div>
  );
}

function renderInlineMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

const nodeTypes = { outline: OutlineFlowNode };

// ---- flow data ----

const NODE_GAP_Y = 110;

function buildFlowData(
  items: MessageOutlineItem[],
  activeId: string | null,
  avatarUrl: string | undefined,
  username: string,
  personaAvatar?: string | null,
) {
  const flowItems = items.filter(
    (item) => item.kind === "user-message" || item.kind === "assistant-message",
  );

  const nodes: Node<OutlineNodeData>[] = flowItems.map((item, i) => ({
    id: item.id,
    type: "outline",
    position: { x: 0, y: i * NODE_GAP_Y },
    data: {
      label: item.label,
      kind: item.kind,
      anchorId: item.anchorId,
      messageIndex: item.messageIndex,
      isActive: activeId === item.anchorId,
      avatarUrl,
      username,
      personaAvatar,
    },
  }));

  const edges: Edge[] = flowItems.slice(0, -1).map((item, i) => ({
    id: `e-${item.id}`,
    source: item.id,
    target: flowItems[i + 1].id,
    type: "smoothstep",
    style: {
      stroke: "var(--theme-primary)",
      strokeWidth: 1.5,
      opacity: 0.35,
    },
  }));

  return { nodes, edges };
}

// ---- inner flow (needs ReactFlowProvider) ----

interface MessageOutlinePanelProps {
  items: MessageOutlineItem[];
  activeId: string | null;
  onNavigate: (anchorId: string, messageIndex: number) => void;
  personaAvatar?: string | null;
}

function OutlineFlowInner({
  items,
  activeId,
  onNavigate,
  personaAvatar,
}: MessageOutlinePanelProps) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const { fitView, setViewport } = useReactFlow();
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(400);

  const avatarUrl = user?.avatar_url
    ? getFullUrl(user.avatar_url) ?? user.avatar_url
    : undefined;
  const username = user?.username || t("common.you");
  const flowActiveId = useMemo(
    () => getOutlineFlowActiveAnchorId(items, activeId),
    [items, activeId],
  );

  const { nodes, edges } = useMemo(
    () =>
      buildFlowData(items, flowActiveId, avatarUrl, username, personaAvatar),
    [items, flowActiveId, avatarUrl, username, personaAvatar],
  );

  // track container size for responsive zoom
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setContainerWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // dynamically scale nodes to fill ~60% of container width
  useEffect(() => {
    if (nodes.length === 0) return;
    const target = flowActiveId ? nodes.find((n) => n.data.isActive) : nodes[0];
    if (target) {
      const nodeWidth = 232;
      const fillRatio = 0.75;
      const zoom = Math.min(
        Math.max((containerWidth * fillRatio) / nodeWidth, 0.7),
        2.0,
      );
      const padding = 48;
      setViewport(
        {
          x: containerWidth / 2 - (target.position.x + nodeWidth / 2) * zoom,
          y: padding - target.position.y * zoom,
          zoom,
        },
        { duration: 300 },
      );
    } else {
      fitView({ padding: 0.2, duration: 200 });
    }
  }, [nodes, flowActiveId, containerWidth, fitView, setViewport]);

  const onNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      onNavigate(
        node.data.anchorId as string,
        node.data.messageIndex as number,
      );
    },
    [onNavigate],
  );

  return (
    <div
      ref={containerRef}
      className="outline-flow-shell relative w-full h-full"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        minZoom={0.6}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        className="!bg-transparent"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="var(--theme-primary)"
          className="!opacity-[0.12]"
        />
        <Controls
          showInteractive={false}
          position="bottom-left"
          className="outline-flow-controls"
        />
      </ReactFlow>
    </div>
  );
}

// ---- exported wrapper ----

export function MessageOutlinePanel(props: MessageOutlinePanelProps) {
  if (props.items.length === 0) return null;

  return (
    <ReactFlowProvider>
      <OutlineFlowInner {...props} />
    </ReactFlowProvider>
  );
}
