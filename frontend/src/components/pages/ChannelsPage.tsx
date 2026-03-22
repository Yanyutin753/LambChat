/**
 * Channels Page - Lists all available channels and their instances
 */

import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Loader2,
  MessageCircle,
  Radio,
  Plus,
  MoreVertical,
} from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { APP_NAME } from "../../constants";
import { channelApi } from "../../services/api/channel";
import { ChannelPanel } from "../panels/ChannelPanel";
import { FeishuPanel } from "../panels/channel/feishu/FeishuPanel";
import { PanelHeader } from "../common/PanelHeader";
import type {
  ChannelMetadata,
  ChannelConfigStatus,
  ChannelConfigResponse,
  ChannelType,
} from "../../types/channel";

// Icon map for channel icons
const CHANNEL_ICONS: Record<string, React.FC<{ className?: string }>> = {
  "message-circle": MessageCircle,
  feishu: Radio,
};

// Get icon component
function getChannelIcon(iconName: string, className?: string) {
  const IconComponent = CHANNEL_ICONS[iconName] || MessageCircle;
  return <IconComponent className={className} />;
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
  const [statuses, setStatuses] = useState<Record<string, ChannelConfigStatus>>(
    {},
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      setChannelTypes(types);

      // Load instances for all channel types
      for (const ct of types) {
        await loadInstances(ct.channel_type);
      }
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

      // Load status for each instance
      for (const instance of instanceList) {
        try {
          const status = await channelApi.getStatus(
            channelType as ChannelType,
            instance.instance_id,
          );
          setStatuses((prev) => ({
            ...prev,
            [`${channelType}:${instance.instance_id}`]: status,
          }));
        } catch {
          // Instance might not have status
        }
      }
    } catch (error) {
      console.error(`Failed to load ${channelType} instances:`, error);
    }
  };

  // If a specific instance is selected, show the panel
  if (selectedChannel && selectedInstance) {
    const metadata = channelTypes.find(
      (ct) => ct.channel_type === selectedChannel,
    );
    if (metadata) {
      // Use specialized FeishuPanel for Feishu channel (both new and existing instances)
      if (selectedChannel === "feishu") {
        const instance = instances[selectedChannel]?.find(
          (i) => i.instance_id === selectedInstance,
        );
        const status =
          selectedInstance !== "new"
            ? statuses[`${selectedChannel}:${selectedInstance}`]
            : null;
        return (
          <FeishuPanel
            instanceId={selectedInstance}
            initialConfig={instance}
            initialStatus={status}
            isLoading={false}
          />
        );
      }
      return (
        <ChannelPanel
          channelType={selectedChannel as ChannelType}
          instanceId={selectedInstance}
          metadata={metadata}
        />
      );
    }
  }

  // If a channel type is selected but no instance, show instance list
  if (selectedChannel) {
    const metadata = channelTypes.find(
      (ct) => ct.channel_type === selectedChannel,
    );
    const channelInstances = instances[selectedChannel] || [];

    return (
      <div className="flex h-full flex-col bg-stone-50 dark:bg-stone-950">
        <PanelHeader
          title={metadata?.display_name || selectedChannel}
          subtitle={metadata?.description || ""}
          icon={
            <Radio size={18} className="text-stone-600 dark:text-stone-400" />
          }
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

        <div className="flex-1 overflow-y-auto px-2 py-4 sm:px-4 lg:px-6">
          {channelInstances.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <p className="text-sm text-stone-500 dark:text-stone-400">
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
                          <h4 className="font-medium text-stone-900 dark:text-stone-100">
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
                            <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-500 dark:bg-stone-800 dark:text-stone-500">
                              Disabled
                            </span>
                          )}
                        </div>
                        <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
                          {t("channel.createdAt", "Created")}:{" "}
                          {instance.created_at
                            ? new Date(instance.created_at).toLocaleDateString()
                            : "-"}
                        </p>
                      </div>
                      <MoreVertical
                        size={18}
                        className="text-stone-400 dark:text-stone-500"
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Show channel type list
  return (
    <div className="flex h-full flex-col bg-stone-50 dark:bg-stone-950">
      {/* Header */}
      <PanelHeader
        title={t("channel.title", "Channels")}
        subtitle={t(
          "channel.description",
          `Connect your favorite chat platforms to ${APP_NAME}`,
        )}
        icon={
          <Radio size={18} className="text-stone-600 dark:text-stone-400" />
        }
      />

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-2 py-4 sm:px-4 lg:px-6">
        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="relative">
                <div className="absolute inset-0 animate-ping rounded-full bg-stone-400/20" />
                <Loader2 className="relative h-10 w-10 animate-spin text-stone-600 dark:text-stone-400" />
              </div>
              <p className="text-sm text-stone-500 dark:text-stone-400">
                {t("common.loading", "Loading...")}
              </p>
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-full">
            {channelTypes.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center xl:py-20 2xl:py-24">
                <div className="relative">
                  <div className="absolute inset-0 rounded-full bg-stone-300/20 blur-xl dark:bg-stone-600/20" />
                  <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-br from-stone-100 to-stone-200 dark:from-stone-800 dark:to-stone-700">
                    <Radio className="h-10 w-10 text-stone-400 dark:text-stone-500" />
                  </div>
                </div>
                <h3 className="mt-6 text-xl font-semibold text-stone-900 dark:text-stone-100">
                  {t("channel.noChannels", "No channels available")}
                </h3>
                <p className="mt-2 max-w-md text-sm text-stone-500 dark:text-stone-400">
                  {t(
                    "channel.noChannelsDesc",
                    "Check back later for available integrations",
                  )}
                </p>
              </div>
            ) : (
              <div className="space-y-3 p-3 sm:p-4">
                {channelTypes.map((ct) => {
                  const channelInstances = instances[ct.channel_type] || [];
                  const instanceCount = channelInstances.length;
                  const hasAnyConnected = channelInstances.some(
                    (i) =>
                      statuses[`${ct.channel_type}:${i.instance_id}`]
                        ?.connected,
                  );

                  return (
                    <div
                      key={ct.channel_type}
                      onClick={() => navigate(`/channels/${ct.channel_type}`)}
                      className="panel-card cursor-pointer"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            {getChannelIcon(
                              ct.icon,
                              "text-stone-400 dark:text-stone-500 flex-shrink-0",
                            )}
                            <h4 className="font-medium text-stone-900 dark:text-stone-100 truncate">
                              {ct.display_name}
                            </h4>
                            {/* Capabilities badges */}
                            {ct.capabilities.includes("websocket") && (
                              <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600 dark:bg-stone-800 dark:text-stone-300">
                                WS
                              </span>
                            )}
                            {ct.capabilities.includes("webhook") && (
                              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">
                                Hook
                              </span>
                            )}
                            {/* Instance count badge */}
                            {instanceCount > 0 && (
                              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/50 dark:text-blue-300">
                                {instanceCount}{" "}
                                {instanceCount === 1 ? "instance" : "instances"}
                              </span>
                            )}
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
                          </div>
                          <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">
                            {ct.description}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
