import { clsx } from "clsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  const [imgError, setImgError] = useState(false);

  if (avatarUrl && !imgError) {
    return (
      <img
        src={avatarUrl}
        alt={username}
        className="size-[22px] object-cover rounded-full ring-1 ring-white/20"
        onError={() => setImgError(true)}
      />
    );
  }

  return (
    <div className="flex size-[22px] items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full shadow-[0_1px_3px_rgba(0,0,0,0.15)]">
      <span className="text-[10px] font-bold text-white leading-none">
        {username.charAt(0).toUpperCase() || "U"}
      </span>
    </div>
  );
}

function OutlineFlowNode({ data }: { data: OutlineNodeData }) {
  const isUser = data.kind === "user-message";

  return (
    <div
      className={clsx(
        "px-3 py-[10px] rounded-2xl w-[220px] cursor-pointer transition-all duration-200",
        "bg-stone-100/80 dark:bg-stone-700/40 border",
        "border-stone-200/80 dark:border-stone-600/50",
        "hover:-translate-y-[1px] hover:shadow-lg hover:border-stone-300 dark:hover:border-stone-500",
        data.isActive &&
          "border-[var(--theme-primary)] shadow-lg shadow-[color-mix(in_srgb,var(--theme-primary)_10%,transparent)] ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_15%,transparent)] -translate-y-[1px]",
        !data.isActive && "shadow-sm",
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
      <div className="flex items-start gap-2">
        <div className="shrink-0 pt-[1px]">
          {isUser ? (
            <UserAvatar avatarUrl={data.avatarUrl} username={data.username} />
          ) : (
            <AssistantAvatar
              className="size-[22px] rounded-full ring-1 ring-white/20"
              personaAvatar={data.personaAvatar}
              personaSize={16}
            />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <span className="text-[10px] font-medium text-[var(--theme-text-secondary)] leading-none">
            {isUser ? data.username : "Assistant"}
          </span>
          <div
            className="text-[12px] text-[var(--theme-text)] line-clamp-2 mt-1 leading-[1.45] [&_strong]:font-semibold [&_strong]:text-[var(--theme-primary)] [&_em]:italic [&_code]:text-[11px] [&_code]:rounded [&_code]:bg-[var(--theme-primary-light)] [&_code]:px-0.5 [&_code]:text-[var(--theme-primary)]"
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
  const { fitView, setViewport } = useReactFlow();
  const containerRef = useRef<HTMLDivElement>(null);

  const avatarUrl = user?.avatar_url;
  const username = user?.username || "You";
  const flowActiveId = useMemo(
    () => getOutlineFlowActiveAnchorId(items, activeId),
    [items, activeId],
  );

  const { nodes, edges } = useMemo(
    () =>
      buildFlowData(items, flowActiveId, avatarUrl, username, personaAvatar),
    [items, flowActiveId, avatarUrl, username, personaAvatar],
  );

  // zoom into the target node and position it at the top of the viewport
  useEffect(() => {
    if (nodes.length === 0) return;
    const target = flowActiveId ? nodes.find((n) => n.data.isActive) : nodes[0];
    if (target) {
      const zoom = 1.2;
      const padding = 48;
      const nodeWidth = 220;
      const containerWidth = containerRef.current?.clientWidth ?? 400;
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
  }, [nodes, flowActiveId, fitView, setViewport]);

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
    <div ref={containerRef} className="relative w-full h-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        minZoom={0.6}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        className="!bg-[var(--theme-bg)] rounded-lg"
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
