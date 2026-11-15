import { useEffect, useRef, useState } from "react";
import { isAndroidLocalDevice, LocalDevice } from "./localDevice";
import type { ChatViewProps } from "../../components/layout/AppContent/ChatViewProps";

type Options = Pick<
  ChatViewProps,
  | "draftKey"
  | "agentOptionValues"
  | "approvals"
  | "approvalLoading"
  | "onRespondApproval"
  | "onSendMessage"
  | "onStopGeneration"
> & { ready: boolean; running: boolean };

/** Native actions are bound to this mounted account/server/conversation scope. */
export function usePhoneOverlay(options: Options) {
  const [machine, setMachine] = useState<string>();
  const selectedHere =
    !!machine && options.agentOptionValues?.sandbox_machine_id === machine;
  const safeOptions = { ...options, ready: options.ready && selectedHere };
  const current = useRef(safeOptions);
  useEffect(() => {
    if (!isAndroidLocalDevice()) return;
    let disposed = false;
    void LocalDevice.invoke({ command: "read_machine_id" })
      .then((result) => {
        if (!disposed && typeof result?.value === "string")
          setMachine(result.value);
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, []);
  useEffect(() => {
    current.current = safeOptions;
  });
  useEffect(() => {
    if (!isAndroidLocalDevice() || !options.draftKey) return;
    let disposed = false;
    const scope = options.draftKey;
    const listener = LocalDevice.addListener("overlayAction", (event) => {
      void (async () => {
      // Resume can replay native clicks before the current chat and approvals finish restoring.
      for (let attempt = 0; attempt < 20; attempt++) {
        const restored = current.current;
        if (disposed || event.scope !== restored.draftKey || !Number.isFinite(event.expiresAt) || event.expiresAt! <= Date.now()) break;
        const ready = event.action === "task"
          ? restored.ready && !restored.running && !restored.approvals.length
          : event.action === "approve" || event.action === "reject"
            ? restored.approvals.some((approval) => approval.id === event.approvalId)
            : true;
        if (ready) break;
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      const value = current.current;
      const reply = (accepted: boolean) => {
        void LocalDevice.overlayResult({ id: event.id, accepted }).catch(
          () => {},
        );
      };
      if (disposed || event.scope !== value.draftKey || (event.expiresAt !== undefined && (!Number.isFinite(event.expiresAt) || event.expiresAt <= Date.now()))) {
        reply(false);
        return;
      }
      if (event.action === "stop") {
        value.onStopGeneration();
        reply(true);
        return;
      }
      if (event.action === "task") {
        if (
          !value.ready ||
          value.running ||
          value.approvals.length ||
          !event.text?.trim() ||
          event.text.length > 16000
        ) {
          reply(false);
          return;
        }
        value.onSendMessage(event.text, [], undefined, {
          onAccepted: () => reply(true),
          onRejected: () => reply(false),
        });
        return;
      }
      const approval = value.approvals.find(
        (item) => item.id === event.approvalId,
      );
      if (
        !approval ||
        value.approvalLoading ||
        approval.fields.length ||
        approval.status !== "pending" ||
        approval.message !== event.message ||
        (approval.expires_at && Date.parse(approval.expires_at) <= Date.now())
      ) {
        reply(false);
        return;
      }
      if (event.action !== "approve" && event.action !== "reject") {
        reply(false);
        return;
      }
      void Promise.resolve(value.onRespondApproval(approval.id, {}, event.action === "approve"))
        .then((accepted) => reply(accepted === true))
        .catch(() => reply(false));
      })();
    });
    return () => {
      disposed = true;
      void listener.then((handle) => handle.remove()).catch(() => {});
      void LocalDevice.clearOverlayContext({ scope }).catch(() => {});
    };
  }, [options.draftKey]);
  useEffect(() => {
    if (!isAndroidLocalDevice() || !options.draftKey) return;
    const approval = options.approvals[0];
    void LocalDevice.setOverlayContext({
      scope: options.draftKey,
      ready: options.ready && selectedHere && !options.running && !approval,
      running: options.running,
      approvalId: approval?.id ?? "",
      message: approval?.message.slice(0, 16000) ?? "",
      canApprove:
        !!approval &&
        !approval.fields.length &&
        approval.message.length <= 16000 &&
        !options.approvalLoading,
    }).catch(() => {});
  }, [
    options.draftKey,
    options.ready,
    selectedHere,
    options.running,
    options.approvals,
    options.approvalLoading,
  ]);
}
