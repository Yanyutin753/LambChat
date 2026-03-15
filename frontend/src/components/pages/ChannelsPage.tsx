/**
 * Channels Page - Lists all available channels and their configurations
 */

import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Loader2, MessageCircle, Radio, ArrowRight } from "lucide-react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { channelApi } from "../../services/api/channel";
import { ChannelPanel } from "../panels/ChannelPanel";
import type {
  ChannelMetadata,
  ChannelConfigStatus,
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
  const navigate = useNavigate();
  const { channelType: selectedChannel } = useParams<{
    channelType?: string;
  }>();

  const [channelTypes, setChannelTypes] = useState<ChannelMetadata[]>([]);
  const [statuses, setStatuses] = useState<Record<string, ChannelConfigStatus>>(
    {},
  );
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const types = await channelApi.getTypes();
      setChannelTypes(types);

      // Load status for each channel type
      const statusPromises = types.map(async (ct) => {
        try {
          const status = await channelApi.getStatus(
            ct.channel_type as ChannelType,
          );
          return [ct.channel_type, status] as const;
        } catch {
          return [ct.channel_type, null] as const;
        }
      });

      const statusResults = await Promise.all(statusPromises);
      const statusMap: Record<string, ChannelConfigStatus> = {};
      statusResults.forEach(([type, status]) => {
        if (status) {
          statusMap[type] = status;
        }
      });
      setStatuses(statusMap);
    } catch (error) {
      console.error("Failed to load channel types:", error);
      toast.error(
        t("channel.loadTypesError", "Failed to load available channels"),
      );
    } finally {
      setIsLoading(false);
    }
  };

  // If a specific channel is selected, show the panel
  if (selectedChannel) {
    const metadata = channelTypes.find(
      (ct) => ct.channel_type === selectedChannel,
    );
    if (metadata) {
      return (
        <ChannelPanel
          channelType={selectedChannel as ChannelType}
          metadata={metadata}
        />
      );
    }
  }

  // Show channel list
  return (
    <div className="flex h-full flex-col bg-stone-50 dark:bg-stone-950">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-stone-200 bg-white/80 backdrop-blur-sm px-4 py-5 dark:border-stone-800 dark:bg-stone-900/80 sm:px-6 lg:px-8 xl:py-6">
        <div className="mx-auto max-w-5xl xl:max-w-6xl 2xl:max-w-7xl">
          <div className="flex items-center gap-3 xl:gap-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-stone-900 shadow-lg dark:bg-stone-100 xl:h-12 xl:w-12">
              <Radio className="h-5 w-5 text-stone-100 dark:text-stone-900 xl:h-6 xl:w-6" />
            </div>
            <div>
              <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100 sm:text-2xl xl:text-3xl">
                {t("channel.title", "Channels")}
              </h1>
              <p className="text-sm text-stone-500 dark:text-stone-400 xl:text-base">
                {t(
                  "channel.description",
                  "Connect your favorite chat platforms to LambChat",
                )}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8 xl:py-8 2xl:py-10">
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
          <div className="mx-auto max-w-5xl xl:max-w-6xl 2xl:max-w-7xl">
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
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 2xl:gap-6">
                {channelTypes.map((ct) => {
                  const status = statuses[ct.channel_type];
                  const isSelected = selectedChannel === ct.channel_type;

                  return (
                    <button
                      key={ct.channel_type}
                      onClick={() => navigate(`/channels/${ct.channel_type}`)}
                      className={`group relative flex flex-col rounded-2xl border p-5 text-left transition-all duration-300 hover:-translate-y-1 hover:shadow-xl 2xl:p-6 ${
                        isSelected
                          ? "border-stone-400 bg-gradient-to-br from-stone-100 to-stone-200/50 shadow-xl dark:border-stone-600 dark:from-stone-800 dark:to-stone-700/50"
                          : "border-stone-200 bg-white hover:border-stone-300 hover:shadow-stone-200/50 dark:border-stone-800 dark:bg-stone-900 dark:hover:border-stone-700 dark:hover:shadow-stone-900/50"
                      }`}
                    >
                      {/* Icon and Status */}
                      <div className="relative flex items-start justify-between">
                        <div className="flex items-center gap-3 2xl:gap-4">
                          <div
                            className={`flex h-12 w-12 items-center justify-center rounded-xl transition-all duration-300 group-hover:scale-110 group-hover:shadow-lg 2xl:h-14 2xl:w-14 ${
                              isSelected
                                ? "bg-stone-200 shadow-md dark:bg-stone-700"
                                : "bg-stone-100 dark:bg-stone-800 group-hover:bg-stone-200 dark:group-hover:bg-stone-700"
                            }`}
                          >
                            {getChannelIcon(
                              ct.icon,
                              `h-6 w-6 transition-colors duration-300 2xl:h-7 2xl:w-7 ${
                                isSelected
                                  ? "text-stone-700 dark:text-stone-200"
                                  : "text-stone-600 group-hover:text-stone-700 dark:text-stone-400 dark:group-hover:text-stone-200"
                              }`,
                            )}
                          </div>
                          <div className="min-w-0">
                            <h3 className="font-semibold text-stone-900 transition-colors group-hover:text-stone-700 dark:text-stone-100 dark:group-hover:text-stone-200 2xl:text-lg">
                              {ct.display_name}
                            </h3>
                            <p className="mt-0.5 line-clamp-2 text-sm text-stone-500 dark:text-stone-400 2xl:mt-1">
                              {ct.description}
                            </p>
                          </div>
                        </div>
                        <ArrowRight className="h-5 w-5 text-stone-300 transition-all duration-300 group-hover:translate-x-1 group-hover:text-stone-500 dark:text-stone-600 dark:group-hover:text-stone-400 2xl:h-6 2xl:w-6" />
                      </div>

                      {/* Footer: Status and Capabilities */}
                      <div className="relative mt-4 flex items-center justify-between 2xl:mt-5">
                        <div className="flex items-center gap-2">
                          {status?.enabled ? (
                            status.connected ? (
                              <>
                                <span className="relative flex h-2.5 w-2.5">
                                  <span className="absolute inset-0 animate-ping rounded-full bg-green-400 opacity-75" />
                                  <span className="relative flex h-2.5 w-2.5 rounded-full bg-green-500 shadow-sm shadow-green-500/50" />
                                </span>
                                <span className="text-sm font-medium text-green-600 dark:text-green-400">
                                  {t("channel.connected", "Connected")}
                                </span>
                              </>
                            ) : (
                              <>
                                <span className="flex h-2.5 w-2.5 rounded-full bg-amber-500 shadow-sm shadow-amber-500/50" />
                                <span className="text-sm font-medium text-amber-600 dark:text-amber-400">
                                  {t("channel.disconnected", "Disconnected")}
                                </span>
                              </>
                            )
                          ) : (
                            <span className="text-sm text-stone-400 dark:text-stone-500">
                              {t("channel.notConfigured", "Not configured")}
                            </span>
                          )}
                        </div>

                        {/* Capabilities badges */}
                        <div className="flex gap-1.5">
                          {ct.capabilities.includes("websocket") && (
                            <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs font-medium text-stone-600 shadow-sm dark:bg-stone-800 dark:text-stone-300">
                              WS
                            </span>
                          )}
                          {ct.capabilities.includes("webhook") && (
                            <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-700 shadow-sm dark:bg-amber-900/50 dark:text-amber-300">
                              Hook
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
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
