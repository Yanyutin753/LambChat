export type IllustrationScene =
  | "welcome"
  | "reading"
  | "files"
  | "message"
  | "notification"
  | "avatar"
  | "panel-persona"
  | "panel-skills"
  | "panel-marketplace"
  | "panel-files"
  | "panel-bookmarks"
  | "panel-team"
  | "panel-memory"
  | "panel-notifications"
  | "panel-feedback"
  | "panel-feedback-positive"
  | "panel-schedule"
  | "panel-usage"
  | "panel-mcp"
  | "panel-users"
  | "panel-roles"
  | "panel-agents"
  | "panel-models"
  | "panel-settings"
  | "panel-channels";

/** Decorative artwork; the adjacent heading conveys the state to screen readers. */
export function SceneIllustration({
  scene = "welcome",
  className = "",
}: {
  scene?: IllustrationScene;
  className?: string;
}) {
  return (
    <img
      src={`/images/illustrations/lamb-${scene}.png`}
      alt=""
      aria-hidden="true"
      width={112}
      height={112}
      decoding="async"
      draggable={false}
      className={`scene-illustration ${
        scene.startsWith("panel-") ? "panel-artwork" : ""
      } ${className}`}
      onError={(event) => {
        const image = event.currentTarget;
        if (image.getAttribute("src") !== "/icons/icon-192.png") {
          image.src = "/icons/icon-192.png";
        }
      }}
    />
  );
}
