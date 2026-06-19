/**
 * Channels Page - Lists all available channels and their instances
 */

import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { BotMessageSquare, Bot, Radio, Plus, MoreVertical } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { APP_NAME } from "../../constants";
import { channelApi } from "../../services/api/channel";
import { ChannelPanel } from "../panels/ChannelPanel";
import { PanelHeader } from "../common/PanelHeader";
import { ChannelsGridSkeleton } from "../skeletons";
import { SkillBaseCard } from "../common/SkillBaseCard";
import { nameToGradient } from "../common/cardUtils";
import {
  findChannelConnectorContribution,
  hasChannelConnectorContribution,
  hasRuntimeManagedChannelConnector,
  type PluginRuntimeContributionStates,
} from "../../extensions/coreContributions";
import { getChannelConnectorPanelRenderer } from "./channelConnectorPanelRenderers";
import type {
  ChannelMetadata,
  ChannelConfigStatus,
  ChannelConfigResponse,
  ChannelType,
} from "../../types/channel";
import { formatDate } from "../../utils/datetime";

interface ChannelsPageProps {
  runtimePlugins?: PluginRuntimeContributionStates;
}

// Icon map for channel icons
const CHANNEL_ICONS: Record<string, React.FC<{ className?: string }>> = {
  BotMessageSquare,
  "message-circle": Bot,
  feishu: BotMessageSquare,
};

// Get icon component
function getChannelIcon(iconName: string, className?: string) {
  const IconComponent = CHANNEL_ICONS[iconName] || Bot;
  return <IconComponent className={className} />;
}

export function ChannelsPage({ runtimePlugins }: ChannelsPageProps) {
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
  const [statuses, setStatuses] = useState<Record<string, ChannelConfigStatus>>(
    {},
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runtimePlugins]);

  useEffect(() => {
    // Load instances when a channel type is selected
    if (selectedChannel) {
      loadInstances(selectedChannel);
    }
  }, [selectedChannel]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const types = await channelApi.getTypes();
      const visibleTypes = types.filter((ct) => {
        if (!hasRuntimeManagedChannelConnector(ct.channel_type, runtimePlugins)) {
          return true;
        }
        return hasChannelConnectorContribution(ct.channel_type, runtimePlugins);
      });
      setChannelTypes(visibleTypes);

      // Load instances for all channel types in parallel
      await Promise.all(visibleTypes.map((ct) => loadInstances(ct.channel_type)));
    } catch (error) {
      console.error("Failed to load channel types:", error);
      toast.error(
        t("channel.loadTypesError", "Failed to load available channels"),
      );
    } finally {
      setIsLoading(false);
    }
  };

  const loadInstances = async (channelType: string) => {
    try {
      const instanceList = await channelApi.listByType(
        channelType as ChannelType,
      );
      setInstances((prev) => ({ ...prev, [channelType]: instanceList }));

      // Load statuses for all instances in parallel
      const statusEntries = await Promise.all(
        instanceList.map(async (instance) => {
          try {
            const status = await channelApi.getStatus(
              channelType as ChannelType,
              instance.instance_id,
            );
            return [`${channelType}:${instance.instance_id}`, status] as const;
          } catch {
            return null;
          }
        }),
      );

      const nextStatuses: Record<string, ChannelConfigStatus> = {};
      for (const entry of statusEntries) {
        if (!entry) continue;
        const [key, status] = entry;
        nextStatuses[key] = status;
      }

      if (Object.keys(nextStatuses).length > 0) {
        setStatuses((prev) => ({ ...prev, ...nextStatuses }));
      }
    } catch (error) {
      console.error(`Failed to load ${channelType} instances:`, error);
    }
  };

  const closeSidebar = () => {
    if (selectedChannel) {
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

    const connector = findChannelConnectorContribution(
      selectedChannel,
      runtimePlugins,
    );
    const ConnectorPanel = getChannelConnectorPanelRenderer(
      connector?.panelRenderer,
    );
    if (ConnectorPanel) {
      const instance = instances[selectedChannel]?.find(
        (i) => i.instance_id === selectedInstance,
      );
      const status =
        selectedInstance !== "new"
          ? statuses[`${selectedChannel}:${selectedInstance}`]
          : null;
      return (
        <ConnectorPanel
          instanceId={selectedInstance}
          initialConfig={instance}
          initialStatus={status}
          isLoading={false}
          onClose={closeSidebar}
        />
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
    if (isLoading) {
      return <ChannelsGridSkeleton />;
    }

    return (
      <div className="flex h-full flex-col">
        <PanelHeader
          title={t("channel.title", "Channels")}
          subtitle={t(
            "channel.description",
            `Connect your favorite chat platforms to ${APP_NAME}`,
          )}
          icon={
            <Radio size={24} className="text-[var(--theme-text-secondary)]" />
          }
        />
        <div className="flex-1 overflow-y-auto py-4">
          <div className="mx-auto max-w-full">
            {channelTypes.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-[var(--theme-primary)]/20" />
                  <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-[var(--theme-primary-light)]">
                    <Radio className="h-10 w-10 text-[var(--theme-text-secondary)]" />
                  </div>
                </div>
                <h3 className="mt-6 text-xl font-semibold text-[var(--theme-text)]">
                  {t("channel.noChannels", "No channels available")}
                </h3>
                <p className="mt-2 max-w-md text-sm text-[var(--theme-text-secondary)]">
                  {t(
                    "channel.noChannelsDesc",
                    "Check back later for available integrations",
                  )}
                </p>
              </div>
            ) : (
              <div className="grid auto-grid-cols gap-4 p-3 sm:p-4">
                {channelTypes.map((ct) => {
                  const channelInstances = instances[ct.channel_type] || [];
                  const instanceCount = channelInstances.length;
                  const hasAnyConnected = channelInstances.some(
                    (i) =>
                      statuses[`${ct.channel_type}:${i.instance_id}`]
                        ?.connected,
                  );
                  const gradient = nameToGradient(ct.display_name);

                  return (
                    <SkillBaseCard
                      key={ct.channel_type}
                      title={ct.display_name}
                      description={ct.description}
                      gradient={gradient}
                      icon={getChannelIcon(ct.icon, "w-5 h-5")}
                      statusPills={
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {instanceCount > 0 &&
                            (hasAnyConnected ? (
                              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/50 dark:text-green-300">
                                Connected
                              </span>
                            ) : (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                                Disconnected
                              </span>
                            ))}
                          {ct.capabilities.includes("websocket") && (
                            <span className="rounded-full bg-[var(--theme-primary-light)] px-2 py-0.5 text-xs font-medium text-[var(--theme-text-secondary)]">
                              WS
                            </span>
                          )}
                          {ct.capabilities.includes("webhook") && (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                              Hook
                            </span>
                          )}
                        </div>
                      }
                      tags={
                        instanceCount > 0 ? (
                          <span className="inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-medium bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)] border border-[var(--theme-border)]">
                            {instanceCount}{" "}
                            {instanceCount === 1 ? "instance" : "instances"}
                          </span>
                        ) : undefined
                      }
                      bannerOverlay={
                        instanceCount > 0 &&
                        (hasAnyConnected ? (
                          <span className="rounded-full bg-green-400/30 backdrop-blur-sm px-2 py-0.5 text-xs font-medium text-green-50 dark:bg-green-400/20 dark:text-green-100">
                            Connected
                          </span>
                        ) : (
                          <span className="rounded-full bg-amber-400/30 backdrop-blur-sm px-2 py-0.5 text-xs font-medium text-amber-50 dark:bg-amber-400/20 dark:text-amber-100">
                            Disconnected
                          </span>
                        ))
                      }
                      onClick={() => navigate(`/channels/${ct.channel_type}`)}
                      className="cursor-pointer"
                    />
                  );
                })}
              </div>
            )}
          </div>
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
      <div className="flex h-full flex-col">
        <PanelHeader
          title={metadata?.display_name || selectedChannel!}
          subtitle={metadata?.description || ""}
          icon={getChannelIcon(
            metadata?.icon || selectedChannel!,
            "h-6 w-6 text-[var(--theme-text-secondary)]",
          )}
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

        <div className="flex-1 overflow-y-auto py-4">
          {channelInstances.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-sm text-[var(--theme-text-secondary)]">
                {t("channel.noInstances", "No instances configured")}
              </p>
              {canWrite && (
                <button
                  onClick={() => navigate(`/channels/${selectedChannel}/new`)}
                  className="mt-4 btn-primary"
                >
                  <Plus size={16} />
                  <span>
                    {t("channel.addFirstInstance", "Add First Instance")}
                  </span>
                </button>
              )}
            </div>
          ) : (
            <div className="mx-auto max-w-full space-y-3 p-3 sm:p-4">
              {channelInstances.map((instance) => {
                const status =
                  statuses[`${selectedChannel}:${instance.instance_id}`];

                return (
                  <div
                    key={instance.instance_id}
                    onClick={() =>
                      navigate(
                        `/channels/${selectedChannel}/${instance.instance_id}`,
                      )
                    }
                    className="panel-card cursor-pointer"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="font-medium text-[var(--theme-text)]">
                            {instance.name}
                          </h4>
                          {status?.enabled &&
                            (status.connected ? (
                              <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/50 dark:text-green-300">
                                Connected
                              </span>
                            ) : (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                                Disconnected
                              </span>
                            ))}
                          {!status?.enabled && (
                            <span className="rounded-full bg-[var(--theme-primary-light)] px-2 py-0.5 text-xs text-[var(--theme-text-secondary)]">
                              Disabled
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-[var(--theme-text-secondary)]">
                          {t("channel.createdAt", "Created")}:{" "}
                          {instance.created_at
                            ? formatDate(instance.created_at)
                            : "-"}
                        </p>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(
                            `/channels/${selectedChannel}/${instance.instance_id}`,
                          );
                        }}
                        className="flex-shrink-0 rounded p-1 hover:bg-stone-200/60 dark:hover:bg-stone-700/60 transition-colors"
                        title={t("channel.moreOptions", "View details")}
                      >
                        <MoreVertical
                          size={18}
                          className="text-[var(--theme-text-secondary)]"
                        />
                      </button>
                    </div>
                  </div>
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
