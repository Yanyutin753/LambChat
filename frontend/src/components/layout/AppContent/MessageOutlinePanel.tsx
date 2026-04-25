import { clsx } from "clsx";
import { ListTree } from "lucide-react";
import { useTranslation } from "react-i18next";
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
import type { MessageOutlineItem } from "./messageOutline";
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
        className="size-5 object-cover rounded-full"
        onError={() => setImgError(true)}
      />
    );
  }

  return (
    <div className="flex size-5 items-center justify-center bg-[var(--theme-primary)] rounded-full">
      <span className="text-[10px] font-semibold text-white">
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
        "px-3 py-2.5 rounded-xl w-[220px] cursor-pointer transition-all",
        "bg-[var(--theme-bg-card)] border",
        data.isActive
          ? "border-[var(--theme-primary)] shadow-md ring-1 ring-[color-mix(in_srgb,var(--theme-primary)_20%,transparent)]"
          : "border-[var(--theme-border)] shadow-sm hover:shadow-md hover:border-[color-mix(in_srgb,var(--theme-primary)_30%,var(--theme-border))]",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className={clsx(
          "!w-[6px] !h-[6px] !border-none !-top-[3px]",
          data.isActive
            ? "!bg-[var(--theme-primary)]"
            : "!bg-[var(--theme-border)]",
        )}
      />
      <div className="flex items-center gap-2.5">
        <div className="shrink-0">
          {isUser ? (
            <UserAvatar avatarUrl={data.avatarUrl} username={data.username} />
          ) : (
            <AssistantAvatar className="size-5 rounded-full" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <span className="text-[10px] font-medium text-[var(--theme-text-secondary)]">
            {isUser ? data.username : "Assistant"}
          </span>
          <div
            className="text-[12px] text-[var(--theme-text)] line-clamp-2 mt-[2px] leading-snug [&_strong]:font-semibold [&_strong]:text-[var(--theme-primary)] [&_em]:italic [&_code]:text-[11px] [&_code]:rounded [&_code]:bg-[var(--theme-primary-light)] [&_code]:px-0.5 [&_code]:text-[var(--theme-primary)]"
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
          "!w-[6px] !h-[6px] !border-none !-bottom-[3px]",
          data.isActive
            ? "!bg-[var(--theme-primary)]"
            : "!bg-[var(--theme-border)]",
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
}

function OutlineFlowInner({
  items,
  activeId,
  onNavigate,
}: MessageOutlinePanelProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { fitView, setViewport } = useReactFlow();
  const containerRef = useRef<HTMLDivElement>(null);

  const avatarUrl = user?.avatar_url;
  const username = user?.username || "You";

  const { nodes, edges } = useMemo(
    () => buildFlowData(items, activeId, avatarUrl, username),
    [items, activeId, avatarUrl, username],
  );

  // zoom into the target node and position it at the top of the viewport
  useEffect(() => {
    if (nodes.length === 0) return;
    const target = activeId ? nodes.find((n) => n.data.isActive) : nodes[0];
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
  }, [nodes, activeId, fitView, setViewport]);

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
      {/* header */}
      <div className="absolute top-0 left-0 right-0 z-10 flex items-center px-4 py-3 pointer-events-none">
        <div className="flex items-center gap-2">
          <ListTree
            size={14}
            className="text-[var(--theme-primary)] opacity-60"
          />
          <span className="text-[13px] font-medium text-[var(--theme-text-secondary)]">
            {t("chat.outline")}
          </span>
          <span className="text-[13px] text-[var(--theme-text-secondary)] opacity-40">
            {items.length}
          </span>
        </div>
      </div>

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
