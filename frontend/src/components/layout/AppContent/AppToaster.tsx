import { Toaster, ToastBar, toast } from "react-hot-toast";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { APP_TOASTER_CLASS_NAME } from "./appToastLayout";
import { IconButton } from "../../common/ui/IconButton";
import { topmostVisibleModalDialog } from "../../../utils/modalDialog";

export function AppToaster() {
  const { t } = useTranslation();
  return createPortal(
    <Toaster
      position="top-center"
      containerClassName={APP_TOASTER_CLASS_NAME}
      containerStyle={{
        top: "calc(56px + var(--app-safe-area-top, 0px) + var(--titlebar-inset, 0px))",
      }}
      toastOptions={{
        duration: 4000,
        style: {
          background: "var(--theme-bg-elevated)",
          color: "var(--theme-text)",
          borderRadius: "8px",
          padding: "var(--app-toast-padding, 12px 16px)",
          minWidth: "var(--app-toast-min-width, 280px)",
        },
        success: {
          duration: 3000,
          iconTheme: {
            primary: "var(--theme-success)",
            secondary: "var(--theme-bg-elevated)",
          },
        },
        error: {
          duration: 5000,
          iconTheme: {
            primary: "var(--theme-error)",
            secondary: "var(--theme-bg-elevated)",
          },
        },
      }}
    >
      {(currentToast) => {
        if (currentToast.type === "custom") {
          return <ToastBar toast={currentToast} />;
        }

        return (
          <ToastBar toast={currentToast}>
            {({ icon, message }) => (
              <div className="app-toast-content flex w-full items-center gap-3 text-left">
                <span className="flex shrink-0 items-center">{icon}</span>
                <div className="app-toast-message min-w-0 flex-1 text-14 leading-snug">
                  {message}
                </div>
                <IconButton
                  size="sm"
                  icon={<X size={14} aria-hidden="true" />}
                  className="shrink-0"
                  aria-label={t("common.dismiss", "关闭")}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (document.activeElement === event.currentTarget)
                      topmostVisibleModalDialog()?.focus({
                        preventScroll: true,
                      });
                    toast.dismiss(currentToast.id);
                  }}
                />
              </div>
            )}
          </ToastBar>
        );
      }}
    </Toaster>,
    document.body,
  );
}
