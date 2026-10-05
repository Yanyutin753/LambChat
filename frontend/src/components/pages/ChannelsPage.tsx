/**
 * Channels Page - Lists all available channels and their instances
 */

import { useState, useEffect, useRef } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  BotMessageSquare,
  Bot,
  Plus,
  ChevronRight,
  BellRing,
  MessageSquare,
  Send,
  Hash,
  Gamepad2,
  RadioTower,
  Dog,
  Bell,
  Megaphone,
  SendHorizontal,
  Zap,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { APP_NAME } from "../../constants";
import { channelApi } from "../../services/api/channel";
import { ChannelPanel } from "../panels/ChannelPanel";
import { FeishuPanel } from "../panels/channel/feishu/FeishuPanel";
import { PanelHeader } from "../common/PanelHeader";
import { Button } from "../common/ui";
import { ChannelsGridSkeleton } from "../skeletons";
import { EmptyState } from "../common/EmptyState";
import { ConfigPanelErrorCallout } from "../panels/ConfigPanelErrorCallout";
import { getRightPanelSnapshot } from "../common/rightPanelCoordinator";
import type { SkillBaseCardProps } from "../common/SkillBaseCard";
import { nameToGradient } from "../common/cardUtils";
import type {
  ChannelMetadata,
  ChannelConfigStatus,
  ChannelConfigResponse,
  ChannelType,
} from "../../types/channel";
import { formatDate } from "../../utils/datetime";

// Icon map for channel icons
const CHANNEL_ICONS: Record<string, React.FC<{ className?: string }>> = {
  BotMessageSquare,
  "message-circle": Bot,
  feishu: BotMessageSquare,
  // 出站推送渠道（键 = 后端渠道 icon 字段下发的 lucide 名）
  "bell-ring": BellRing,
  "message-square": MessageSquare,
  send: Send,
  hash: Hash,
  "gamepad-2": Gamepad2,
  "radio-tower": RadioTower,
  dog: Dog,
  bell: Bell,
  megaphone: Megaphone,
  "send-horizontal": SendHorizontal,
  zap: Zap,
};

// Get icon component
function getChannelIcon(iconName: string, className?: string) {
  const IconComponent = CHANNEL_ICONS[iconName] || Bot;
  return <IconComponent className={className} />;
}

// Keep the original channel presentation separate from the redesigned skill cards.
function ChannelCard({
  title,
  description,
  gradient,
  icon,
  statusPills,
  tags,
  bannerOverlay,
  onClick,
  className,
}: Pick<
  SkillBaseCardProps,
  | "title"
  | "description"
  | "gradient"
  | "icon"
  | "statusPills"
  | "tags"
  | "bannerOverlay"
  | "onClick"
  | "className"
>) {
  return (
    <div
      className={`scb group flex h-full flex-col overflow-hidden rounded-2xl bg-theme-bg-card shadow-sm dark:shadow-none ${
        className ?? ""
      }`}
      role="group"
      aria-label={title}
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(event) => {
        if (
          event.target === event.currentTarget &&
          (event.key === "Enter" || event.key === " ")
        ) {
          event.preventDefault();
          event.currentTarget.click();
        }
      }}
    >
      {gradient && (
        <div
          className="scb__banner relative h-12 shrink-0"
          style={{
            background: `linear-gradient(45deg, ${gradient[0]}, ${gradient[1]}, ${gradient[2]})`,
          }}
        >
          <div className="absolute inset-0 z-[3] flex items-start justify-end p-2">
            {bannerOverlay}
          </div>
        </div>
      )}
      <div className="flex flex-1 flex-col p-4 -mt-3 pt-5">
        <div className="flex items-start gap-3">
          <div className="scb__icon-ring shrink-0">{icon}</div>
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-16 font-semibold font-serif text-theme-text leading-tight">
              <button
                type="button"
                className="w-full text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
                onClick={(event) => {
                  event.stopPropagation();
                  onClick?.(event);
                }}
              >
                {title}
              </button>
            </h3>
            {statusPills}
          </div>
        </div>
        {description && (
          <p className="mt-3 text-13 leading-relaxed text-theme-text-secondary line-clamp-2 min-h-[3.25em]">
            {description}
          </p>
        )}
        {tags && <div className="mt-3">{tags}</div>}
      </div>
    </div>
  );
}

export function ChannelsPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const navigate = useNavigate();

  const canWrite = hasPermission(Permission.CHANNEL_WRITE);
  const { channelType: selectedChannel, instanceId: selectedInstance } =
    useParams<{
      channelType?: string;
      instanceId?: string;
    }>();

  const [channelTypes, setChannelTypes] = useState<ChannelMetadata[]>([]);
  const [instances, setInstances] = useState<
    Record<string, ChannelConfigResponse[]>
  >({});
  const [statuses, setStatuses] = useState<
    Record<string, ChannelConfigStatus | null>
  >({});
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [instanceLoading, setInstanceLoading] = useState<
    Record<string, boolean>
  >({});
  const [instanceErrors, setInstanceErrors] = useState<Record<string, boolean>>(
    {},
  );
  const [statusLoading, setStatusLoading] = useState<Record<string, boolean>>(
    {},
  );
  const instanceGenerations = useRef<Record<string, number>>({});
  const catalogGeneration = useRef(0);
  const pageRef = useRef<HTMLDivElement>(null);
  const previousChannel = useRef(selectedChannel);
  const previousInstance = useRef(selectedInstance);

  useEffect(() => {
    const catalogRef = catalogGeneration;
    const instancesRef = instanceGenerations;
    loadData();
    return () => {
      catalogRef.current++;
      for (const type of Object.keys(instancesRef.current))
        instancesRef.current[type]++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (previousChannel.current === selectedChannel) return;
    previousChannel.current = selectedChannel;
    if (selectedChannel) void loadInstances(selectedChannel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedChannel]);

  useEffect(() => {
    const closed = previousInstance.current && !selectedInstance;
    previousInstance.current = selectedInstance;
    if (!closed) return;
    const frame = requestAnimationFrame(() => {
      if (
        !getRightPanelSnapshot().activeId &&
        document.activeElement === document.body
      ) {
        pageRef.current?.focus({ preventScroll: true });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [selectedInstance]);

  const loadData = async () => {
    const generation = ++catalogGeneration.current;
    setIsLoading(true);
    setLoadError(false);
    try {
      const types = await channelApi.getTypes();
      if (generation !== catalogGeneration.current) return;
      setChannelTypes(types);

      // Load instances for all channel types in parallel
      await Promise.all(types.map((ct) => loadInstances(ct.channel_type)));
    } catch {
      if (generation === catalogGeneration.current) setLoadError(true);
    } finally {
      if (generation === catalogGeneration.current) setIsLoading(false);
    }
  };

  const loadInstances = async (channelType: string) => {
    const generation = (instanceGenerations.current[channelType] || 0) + 1;
    instanceGenerations.current[channelType] = generation;
    setInstanceLoading((prev) => ({ ...prev, [channelType]: true }));
    setInstanceErrors((prev) => ({ ...prev, [channelType]: false }));
    try {
      const instanceList = await channelApi.listByType(
        channelType as ChannelType,
      );
      if (generation !== instanceGenerations.current[channelType]) return;
      setInstances((prev) => ({ ...prev, [channelType]: instanceList }));
      await loadStatuses(channelType, instanceList, generation);
    } catch (error) {
      if (generation !== instanceGenerations.current[channelType]) return;
      console.error(`Failed to load ${channelType} instances:`, error);
      setInstanceErrors((prev) => ({ ...prev, [channelType]: true }));
    } finally {
      if (generation === instanceGenerations.current[channelType])
        setInstanceLoading((prev) => ({ ...prev, [channelType]: false }));
    }
  };

  const loadStatuses = async (
    channelType: string,
    instanceList: ChannelConfigResponse[],
    generation = instanceGenerations.current[channelType],
  ) => {
    setStatusLoading((prev) => ({ ...prev, [channelType]: true }));
    const statusEntries = await Promise.all(
      instanceList.map(async (instance) => {
        try {
          const status = await channelApi.getStatus(
            channelType as ChannelType,
            instance.instance_id,
          );
          return [`${channelType}:${instance.instance_id}`, status] as const;
        } catch {
          return [`${channelType}:${instance.instance_id}`, null] as const;
        }
      }),
    );
    if (generation !== instanceGenerations.current[channelType]) return;
    const nextStatuses: Record<string, ChannelConfigStatus | null> = {};
    for (const entry of statusEntries) {
      const [key, status] = entry;
      nextStatuses[key] = status;
    }

    setStatuses((prev) => ({ ...prev, ...nextStatuses }));
    setStatusLoading((prev) => ({ ...prev, [channelType]: false }));
  };

  const retryNotice = (retry: () => Promise<void>) => (
    <div role="alert" className="flex min-h-full items-center justify-center">
      <EmptyState
        illustration="panel-channels"
        title={t("common.loadFailed")}
        action={
          <Button
            onClick={() => {
              pageRef.current?.focus();
              void retry();
            }}
          >
            {t("common.refresh")}
          </Button>
        }
      />
    </div>
  );

  const closeSidebar = () => {
    if (selectedChannel) {
      void loadInstances(selectedChannel);
      navigate(`/channels/${selectedChannel}`, { replace: true });
    } else {
      navigate("/channels", { replace: true });
    }
  };

  // Determine what the sidebar should render
  const renderSidebar = () => {
    if (!selectedChannel || !selectedInstance) return null;

    const metadata = channelTypes.find(
      (ct) => ct.channel_type === selectedChannel,
    );
    if (!metadata) return null;

    if (selectedChannel === "feishu") {
      return (
        <FeishuPanel instanceId={selectedInstance} onClose={closeSidebar} />
      );
    }

    return (
      <ChannelPanel
        channelType={selectedChannel as ChannelType}
        instanceId={selectedInstance}
        metadata={metadata}
        onClose={closeSidebar}
      />
    );
  };

  // Render channel type list
  const renderChannelList = () => {
    return (
      <div ref={pageRef} tabIndex={-1} className="flex h-full min-h-0 flex-col">
        <PanelHeader
          title={t("channel.title", "Channels")}
          subtitle={t(
            "channel.description",
            `Connect your favorite chat platforms to ${APP_NAME}`,
          )}
          illustration="panel-channels"
        />
        <div className="panel-body flex-1 overflow-y-auto">
          {isLoading ? (
            <ChannelsGridSkeleton />
          ) : loadError ? (
            retryNotice(loadData)
          ) : (
            <div className="mx-auto max-w-full h-full">
              {channelTypes.length === 0 ? (
                <div className="flex h-full flex-col items-center justify-center text-center">
                  <EmptyState
                    illustration="panel-channels"
                    title={t("channel.noChannels")}
                    description={t("channel.noChannelsDesc")}
                  />
                </div>
              ) : (
                <div className="grid auto-grid-cols gap-4">
                  {channelTypes.map((ct) => {
                    const channelInstances = instances[ct.channel_type] || [];
                    const instanceCount = channelInstances.length;
                    const hasAnyConnected = channelInstances.some(
                      (i) =>
                        i.enabled &&
                        statuses[`${ct.channel_type}:${i.instance_id}`]
                          ?.connected,
                    );
                    const statusUnavailable = channelInstances.some(
                      (i) =>
                        i.enabled &&
                        !statuses[`${ct.channel_type}:${i.instance_id}`],
                    );
                    const allDisabled = channelInstances.every(
                      (i) => !i.enabled,
                    );
                    const summaryStatus = hasAnyConnected
                      ? "channel.connected"
                      : allDisabled
                        ? "channel.disabled"
                        : statusUnavailable
                          ? "channel.statusUnavailable"
                          : "channel.disconnected";
                    const gradient = nameToGradient(ct.display_name);

                    return (
                      <ChannelCard
                        key={ct.channel_type}
                        title={ct.display_name}
                        description={ct.description}
                        gradient={gradient}
                        icon={getChannelIcon(ct.icon, "w-5 h-5")}
                        statusPills={
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            {instanceCount > 0 && (
                              <span
                                className={`rounded-full px-2 py-0.5 text-12 font-medium ${hasAnyConnected ? "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300" : allDisabled || statusUnavailable ? "bg-[var(--theme-primary-light)] text-theme-text-secondary" : "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300"}`}
                              >
                                {t(summaryStatus)}
                              </span>
                            )}
                            {ct.capabilities.includes("websocket") && (
                              <span className="rounded-full bg-[var(--theme-primary-light)] px-2 py-0.5 text-12 font-medium text-[var(--theme-text-secondary)]">
                                {t("channel.websocketShort", "WS")}
                              </span>
                            )}
                            {ct.capabilities.includes("webhook") && (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-12 font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                                {t("channel.webhookShort", "Hook")}
                              </span>
                            )}
                          </div>
                        }
                        tags={
                          instanceErrors[ct.channel_type] ? (
                            <Button
                              size="sm"
                              loading={instanceLoading[ct.channel_type]}
                              onClick={(event) => {
                                event.stopPropagation();
                                pageRef.current?.focus();
                                void loadInstances(ct.channel_type);
                              }}
                            >
                              {t("common.loadFailed")} · {t("common.refresh")}
                            </Button>
                          ) : instanceCount > 0 ? (
                            <span className="inline-flex items-center rounded-lg px-2.5 py-1 text-12 font-medium bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)] border border-[var(--theme-border)]">
                              {t(
                                instanceCount === 1
                                  ? "channel.instanceCount_one"
                                  : "channel.instanceCount_other",
                                "{{count}} instances",
                                { count: instanceCount },
                              )}
                            </span>
                          ) : undefined
                        }
                        onClick={() => navigate(`/channels/${ct.channel_type}`)}
                        className="cursor-pointer"
                      />
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  // Render instance list for a selected channel type
  const renderInstanceList = () => {
    const metadata = channelTypes.find(
      (ct) => ct.channel_type === selectedChannel,
    );
    const channelInstances = instances[selectedChannel!] || [];

    return (
      <div ref={pageRef} tabIndex={-1} className="flex h-full min-h-0 flex-col">
        <PanelHeader
          title={metadata?.display_name || selectedChannel!}
          subtitle={metadata?.description || ""}
          illustration="panel-channels"
          actions={
            canWrite && (
              <button
                onClick={() => navigate(`/channels/${selectedChannel}/new`)}
                className="btn-primary btn-sm"
              >
                <Plus size={16} />
                <span>{t("channel.addInstance", "Add Instance")}</span>
              </button>
            )
          }
        />

        <div className="panel-body flex-1 overflow-y-auto">
          {isLoading || instanceLoading[selectedChannel!] ? (
            <ChannelsGridSkeleton />
          ) : loadError ? (
            retryNotice(loadData)
          ) : instanceErrors[selectedChannel!] ? (
            retryNotice(() => loadInstances(selectedChannel!))
          ) : channelInstances.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center py-8 text-center">
              <EmptyState
                illustration="panel-channels"
                title={t("channel.noInstances")}
                action={
                  canWrite ? (
                    <Button
                      variant="primary"
                      leftIcon={<Plus size={16} />}
                      onClick={() =>
                        navigate(`/channels/${selectedChannel}/new`)
                      }
                    >
                      {t("channel.addFirstInstance")}
                    </Button>
                  ) : undefined
                }
              />
            </div>
          ) : (
            <div className="panel-stack mx-auto max-w-full">
              {channelInstances.some(
                (instance) =>
                  instance.enabled &&
                  statuses[`${selectedChannel}:${instance.instance_id}`] ===
                    null,
              ) && (
                <div className="flex items-start gap-2">
                  <ConfigPanelErrorCallout
                    message={t("common.loadFailed")}
                    className="min-w-0 flex-1"
                  />
                  <Button
                    loading={statusLoading[selectedChannel!]}
                    onClick={() => {
                      pageRef.current?.focus();
                      void loadStatuses(selectedChannel!, channelInstances);
                    }}
                  >
                    {t("common.refresh")}
                  </Button>
                </div>
              )}
              {channelInstances.map((instance) => {
                const status =
                  statuses[`${selectedChannel}:${instance.instance_id}`];
                const statusKey = !instance.enabled
                  ? "channel.disabled"
                  : !status
                    ? "channel.statusUnavailable"
                    : status.connected
                      ? "channel.connected"
                      : "channel.disconnected";
                const statusClass =
                  instance.enabled && status?.connected
                    ? "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300"
                    : instance.enabled && status
                      ? "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300"
                      : "bg-[var(--theme-primary-light)] text-theme-text-secondary";
                return (
                  <Link
                    key={instance.instance_id}
                    to={`/channels/${selectedChannel}/${instance.instance_id}`}
                    className="panel-card flex items-center gap-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
                  >
                    <div className="min-w-0 flex-1">
                      <h4 className="break-words font-medium text-theme-text [overflow-wrap:anywhere]">
                        {instance.name}
                      </h4>
                      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-12 font-medium ${statusClass}`}
                        >
                          {t(statusKey)}
                        </span>
                        <p className="text-12 text-theme-text-secondary">
                          {t("channel.createdAt")}:{" "}
                          {instance.created_at
                            ? formatDate(instance.created_at)
                            : "-"}
                        </p>
                      </div>
                    </div>
                    <ChevronRight
                      size={18}
                      className="shrink-0 text-theme-text-tertiary"
                      aria-hidden="true"
                    />
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <>
      {/* Main content: channel type list or instance list */}
      {selectedChannel ? renderInstanceList() : renderChannelList()}

      {/* Sidebar for editing/creating instances */}
      {renderSidebar()}
    </>
  );
}
