import "../../styles/welcome.css";
import {
  WELCOME_PERSONA_CLASS_NAME,
  getWelcomePersonaSkeletonClass,
  getWelcomePersonaSkeletonCount,
} from "../chat/welcomeLayout";
import { SkeletonLine } from "./primitives";
import { SidebarSkeleton } from "./SidebarSkeleton";

const appSafeAreaTop =
  "max(var(--app-safe-area-top, 0px), var(--app-fullscreen-safe-area-top, 0px))";
const appSafeAreaBottom =
  "max(var(--app-safe-area-bottom, 0px), var(--app-fullscreen-safe-area-bottom, 0px))";

/** Full chat page skeleton: sidebar + header + welcome */
export function ChatPageSkeleton() {
  return (
    <div
      data-workspace-ui=""
      className="flex h-[100dvh] w-full overflow-hidden animate-fade-in"
      style={{
        backgroundColor: "var(--theme-bg)",
        boxSizing: "content-box",
        paddingTop: appSafeAreaTop,
        paddingBottom: appSafeAreaBottom,
        height: `calc(100dvh - ${appSafeAreaTop} - ${appSafeAreaBottom} - var(--titlebar-inset, 0px))`,
      }}
    >
      <SidebarSkeleton />

      {/* Main area */}
      <div
        data-workspace-content=""
        className="relative flex flex-1 min-w-0 flex-col overflow-hidden"
      >
        {/* Header skeleton — matches real Header layout */}
        <header className="chat-header relative z-50 flex h-12 items-center px-3 sm:px-5 shrink-0">
          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Mobile hamburger */}
            <div className="skeleton-line size-8 rounded-lg sm:hidden" />
            {/* Model selector — matches real ModelSelector text-16 font-semibold height */}
            <div className="flex items-center gap-1.5">
              <SkeletonLine
                width="w-24 sm:w-28 md:w-36"
                className="!h-6 !rounded-md"
              />
              <div className="skeleton-line size-3.5 rounded-sm" />
            </div>
          </div>
          <div className="flex-1" />
          <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
            {/* More menu */}
            <div className="skeleton-line size-8 rounded-lg" />
            {/* UserMenu avatar */}
            <div className="skeleton-line size-8 rounded-lg" />
          </div>
        </header>

        {/* Welcome skeleton */}
        <main className="flex-1 overflow-hidden">
          <WelcomeSkeleton />
        </main>
      </div>
    </div>
  );
}

/** Shared user message skeleton block */
function UserMessageSkeleton({
  msg,
}: {
  msg: { bubble: string; lines: string[] };
}) {
  return (
    <div className="w-full px-4 sm:px-6 py-4 group">
      <div className="mx-auto flex max-w-4xl lg:max-w-5xl xl:max-w-6xl justify-end">
        <div className={`flex flex-col items-end max-w-[90%] ${msg.bubble}`}>
          <div
            className="w-full px-5 py-2.5 shadow-sm border transition-shadow duration-200"
            style={{
              background:
                "linear-gradient(135deg, var(--theme-primary-light), var(--theme-bg))",
              borderColor: "var(--theme-border)",
              borderRadius: "var(--radius-chat)",
              boxShadow: "var(--shadow-low)",
            }}
          >
            <div className="leading-relaxed text-15 sm:text-16 space-y-1.5">
              {msg.lines.map((w, li) => (
                <SkeletonLine key={li} width={w} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Shared assistant message skeleton block */
function AssistantMessageSkeleton() {
  return (
    <div className="group w-full animate-[fade-in_0.3s_ease-out] scroll-mt-6 rounded-2xl">
      <div className="mx-auto flex flex-col max-w-4xl lg:max-w-5xl xl:max-w-6xl px-4 sm:px-6">
        {/* Avatar + name */}
        <div className="mb-3 flex flex-nowrap items-center gap-2">
          <div className="skeleton-line size-5 sm:size-6 rounded-full shrink-0" />
          <SkeletonLine
            width="w-16 sm:w-20"
            className="!h-[18px] sm:!h-[20px]"
          />
        </div>
        {/* Response content skeleton */}
        <div className="min-w-0 min-h-0 py-1 sm:py-2">
          <div className="space-y-3 my-2">
            <div className="skeleton-line w-full h-2 sm:h-[7px] rounded-full" />
            <div className="flex gap-2 sm:gap-3">
              <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
              <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
              <div className="skeleton-line w-2/5 h-2 sm:h-[7px] rounded-full hidden sm:block" />
            </div>
            <div className="flex gap-2 sm:gap-3">
              <div className="skeleton-line flex-1 h-2 sm:h-[7px] rounded-full" />
              <div className="skeleton-line w-1/3 h-2 sm:h-[7px] rounded-full" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Skeleton for the chat input area (reused in ChatSkeleton / WelcomeSkeleton) */
function ChatInputSkeleton({
  formClassName = "mx-auto max-w-4xl lg:max-w-5xl xl:max-w-6xl px-2",
  shellClassName = "shrink-0",
}: {
  formClassName?: string;
  shellClassName?: string;
} = {}) {
  return (
    <div className={shellClassName}>
      <div className="chat-input-shell sm:px-4 pb-3 sm:pb-5">
        <div className={formClassName}>
          <ChatInputShellSkeleton />
        </div>
      </div>
    </div>
  );
}

/** Shared ChatInput shell skeleton — identical for welcome + conversation */
function ChatInputShellSkeleton() {
  return (
    <div
      className="chat-input-container flex flex-col relative w-full rounded-2xl px-1 border"
      style={{
        backgroundColor: "var(--theme-bg-card)",
      }}
    >
      {/* Textarea area — 1:1 with real: div.px-2.5.pt-1 > div.relative > textarea */}
      <div className="chat-composer-editor-wrap px-2.5 pt-1">
        <div className="relative">
          <div
            data-composer-editor-skeleton=""
            className="bg-transparent w-full pt-[10px] text-15 leading-relaxed min-h-[40px] sm:min-h-[44px]"
            style={{ paddingLeft: 4 }}
          >
            <div className="skeleton-line h-[15px] w-3/5 rounded-full mt-[3px]" />
          </div>
        </div>
      </div>
      {/* Toolbar — 1:1 with real ChatInputToolbar default idle state */}
      <div className="chat-input-toolbar font-serif flex max-w-full flex-nowrap justify-between gap-2.5 px-1 py-2.5 sm:px-2 sm:py-3 mx-0.5">
        <div className="flex min-h-9 min-w-0 flex-1 items-center gap-2.5">
          {/* FeatureMenu button (chat-tool-btn: fixed 2.25rem height, rounded-lg) */}
          <div className="skeleton-line h-9 w-9 rounded-lg shrink-0" />
          {/* Agent chip (chat-tool-btn + avatar 18px + text-14 label) */}
          <div className="chat-tool-btn group shrink min-w-0 overflow-hidden pointer-events-none">
            <div className="flex flex-row items-center gap-2 min-w-0">
              <span className="relative h-[18px] w-[18px] shrink-0 inline-flex items-center justify-center overflow-hidden">
                <div className="skeleton-line h-[18px] w-[18px] rounded-full" />
              </span>
              <div className="skeleton-line h-3.5 w-20 sm:w-24 rounded-full" />
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2.5 self-center">
          {/* Settings / Run Mode button (chat-tool-btn) */}
          <div className="skeleton-line h-9 w-9 rounded-lg shrink-0" />
          {/* Send button */}
          <div className="skeleton-line h-9 w-9 rounded-full shrink-0" />
        </div>
      </div>
    </div>
  );
}

/** Skeleton that mimics a chat conversation layout (user + assistant alternating) with input */
export function ChatSkeleton({ count = 5 }: { count?: number }) {
  const userMsgs = [
    { bubble: "w-[65%] sm:w-[55%]", lines: ["w-full", "w-[82%]"] },
    { bubble: "w-[50%] sm:w-[40%]", lines: ["w-full"] },
    { bubble: "w-[70%] sm:w-[60%]", lines: ["w-full", "w-[75%]"] },
    { bubble: "w-[55%] sm:w-[45%]", lines: ["w-full"] },
    { bubble: "w-[60%] sm:w-[50%]", lines: ["w-full", "w-[88%]"] },
  ];

  return (
    <div className="flex flex-col h-full animate-fade-in">
      {/* Message area */}
      <div className="flex-1 overflow-hidden space-y-3 sm:space-y-4">
        {Array.from({ length: count }).map((_, i) => {
          const msg = userMsgs[i % userMsgs.length];
          return (
            <div key={i}>
              <UserMessageSkeleton msg={msg} />
              <AssistantMessageSkeleton />
            </div>
          );
        })}
      </div>
      {/* Input area skeleton */}
      <ChatInputSkeleton />
    </div>
  );
}

/** Messages-only skeleton (for streaming footer, no input box) */
export function ChatSkeletonMessagesOnly({ count = 3 }: { count?: number }) {
  const userMsgs = [
    { bubble: "w-[65%] sm:w-[55%]", lines: ["w-full", "w-[82%]"] },
    { bubble: "w-[50%] sm:w-[40%]", lines: ["w-full"] },
    { bubble: "w-[70%] sm:w-[60%]", lines: ["w-full", "w-[75%]"] },
    { bubble: "w-[55%] sm:w-[45%]", lines: ["w-full"] },
    { bubble: "w-[60%] sm:w-[50%]", lines: ["w-full", "w-[88%]"] },
  ];

  return (
    <div className="animate-fade-in space-y-3 sm:space-y-4">
      {Array.from({ length: count }).map((_, i) => {
        const msg = userMsgs[i % userMsgs.length];
        return (
          <div key={i}>
            <UserMessageSkeleton msg={msg} />
            <AssistantMessageSkeleton />
          </div>
        );
      })}
    </div>
  );
}

/** Uses the loaded welcome card's header so responsive spacing stays in sync. */
export function WelcomePersonaCardSkeleton({
  showTag = false,
}: {
  showTag?: boolean;
}) {
  return (
    <div
      className={getWelcomePersonaSkeletonClass()}
      style={{
        backgroundColor: "var(--theme-bg-card)",
        borderColor: "var(--theme-border)",
      }}
      aria-hidden="true"
    >
      <span className="welcome-persona-header relative flex items-center gap-3">
        <span className="welcome-persona-avatar welcome-skeleton-avatar size-11 rounded-xl shrink-0" />
        <span className="welcome-persona-info min-w-0 flex-1">
          <span className="flex items-center justify-between gap-2">
            <span className="welcome-persona-name-row relative flex flex-1 items-center gap-1.5 min-w-0">
              <span className="welcome-skeleton-line welcome-skeleton-title !h-[13px] sm:!h-[15px]" />
            </span>
            {showTag && (
              <span className="welcome-skeleton-line welcome-skeleton-tag shrink-0" />
            )}
          </span>
          <span className="welcome-persona-description block mt-1 text-12 leading-[1.5]">
            <span className="welcome-skeleton-line w-full !h-2.5 mt-1" />
            <span className="welcome-skeleton-line welcome-skeleton-desc !h-2.5 mt-1.5" />
          </span>
        </span>
      </span>
    </div>
  );
}

/** Skeleton for the welcome page (greeting + input + persona cards) */
export function WelcomeSkeleton() {
  return (
    <div className="welcome-root relative flex h-full flex-col items-center justify-center px-4 overflow-hidden animate-fade-in">
      {/* Hero section */}
      <div className="welcome-hero relative flex flex-col items-center mb-1 sm:mb-2 md:mb-2.5 xl:mb-3 2xl:mb-3 w-full sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem]">
        {/* Mobile icon */}
        <div className="sm:hidden relative mb-2">
          <div className="welcome-skeleton-avatar" />
        </div>
        {/* Greeting line — desktop icon inline */}
        <div className="max-w-full w-full flex items-center justify-center">
          <div className="welcome-skeleton-avatar hidden sm:block shrink-0 mr-4" />
          <div
            className="welcome-skeleton-line w-48 sm:w-64 md:w-72 lg:w-80 xl:w-[22rem] 2xl:w-96"
            style={{ height: "1.65rem", borderRadius: "0.5rem" }}
          />
        </div>
        {/* Subtitle */}
        <div
          className="welcome-skeleton-line w-36 sm:w-44 md:w-48 xl:w-56 2xl:w-60 mt-1.5 sm:mt-2 md:mt-2.5 xl:mt-3 2xl:mt-3"
          style={{ height: "14px", borderRadius: "0.5rem" }}
        />
      </div>

      {/* ChatInput skeleton — same component as conversation input skeleton */}
      <div className="welcome-input flex w-full flex-col mx-auto sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem]">
        <ChatInputSkeleton
          shellClassName="w-full"
          formClassName="mx-auto w-full px-2"
        />
      </div>

      {/* Persona cards skeleton — matches real initial state (no persona selected) */}
      <div className={WELCOME_PERSONA_CLASS_NAME}>
        {/* Label + manage */}
        <div className="welcome-suggestions-header flex items-center justify-between mb-2 sm:mb-2.5 md:mb-2.5 xl:mb-3 2xl:mb-3">
          <div className="flex items-center gap-1.5">
            <div
              className="welcome-skeleton-line size-[13px] rounded-full"
              style={{ opacity: 0.6 }}
            />
            <div
              className="welcome-skeleton-line w-20 sm:w-24"
              style={{ height: "13px" }}
            />
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-2 py-1 rounded-lg">
              <div
                className="welcome-skeleton-line w-14 sm:w-16"
                style={{ height: "12px" }}
              />
              <div className="welcome-skeleton-line size-3" />
            </div>
          </div>
        </div>
        {/* Persona card grid skeleton */}
        <div className="welcome-persona-gallery welcome-persona-gallery--loading relative pb-1 sm:pb-0">
          {Array.from({ length: getWelcomePersonaSkeletonCount(true) }).map(
            (_, i) => (
              <WelcomePersonaCardSkeleton key={i} />
            ),
          )}
        </div>
      </div>
    </div>
  );
}
