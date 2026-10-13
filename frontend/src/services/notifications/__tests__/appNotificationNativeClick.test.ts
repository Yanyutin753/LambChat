import { beforeEach, expect, test, vi } from "vitest";
const native = vi.hoisted(() => ({invoke:vi.fn(), listen:vi.fn(), permission:vi.fn(), send:vi.fn(), capacitorListen:vi.fn()}));
vi.mock("@capacitor/local-notifications",()=>({LocalNotifications:{addListener:native.capacitorListen}}));
vi.mock("@tauri-apps/api/core",()=>({invoke:native.invoke}));
vi.mock("@tauri-apps/api/event",()=>({listen:native.listen}));
vi.mock("@tauri-apps/plugin-notification",()=>({requestPermission:native.permission, sendNotification:native.send}));
import { createAppNotificationService } from "../appNotificationService";

beforeEach(() => {
  vi.clearAllMocks();
  native.invoke.mockImplementation(async (command:string) => command === "desktop_notification_supports_actions" ? true : command === "desktop_notification_permission" ? "granted" : undefined);
  native.listen.mockResolvedValue(vi.fn());
  native.capacitorListen.mockResolvedValue({remove:vi.fn()});
  native.permission.mockResolvedValue("granted");
});

test("macOS notifications preserve route and account through the native command", async () => {
  const service = createAppNotificationService({runtime:"tauri"});
  service.setActiveUserId("owner");
  await service.notify({type:"task",title:"Finished",route:"/chat/session?run_id=run",ownerUserId:"owner"});
  expect(native.invoke).toHaveBeenCalledWith("desktop_notification_send",{payload:expect.objectContaining({title:"Finished",route:"/chat/session?run_id=run",ownerUserId:"owner"})});
  expect(native.send).not.toHaveBeenCalled();
});

test("desktop without native action support retains the existing platform plugin path", async () => {
  native.invoke.mockResolvedValue(false);
  const service = createAppNotificationService({runtime:"tauri"});
  service.setActiveUserId("owner");
  await service.notify({type:"task",title:"Finished",ownerUserId:"owner"});
  expect(native.permission).toHaveBeenCalledOnce();
  expect(native.send).toHaveBeenCalledWith({title:"Finished",body:undefined});
  expect(native.invoke.mock.calls.some(([command])=>command === "desktop_notification_send")).toBe(false);
});

test("native click only navigates a local route for the current account", async () => {
  const navigate = vi.fn();
  const service = createAppNotificationService({runtime:"tauri",onNavigate:navigate});
  service.setActiveUserId("A");
  service.initializeNativeClickHandlers();
  await vi.waitFor(()=>expect(native.listen).toHaveBeenCalledWith("desktop-notification-action",expect.any(Function)));
  const click = native.listen.mock.calls[0][1];
  click({payload:{route:"/chat/s?run_id=r",ownerUserId:"A"}});
  expect(navigate).toHaveBeenCalledWith("/chat/s?run_id=r");
  navigate.mockClear();
  service.setActiveUserId("B");
  for (const payload of [{route:"/chat/s",ownerUserId:"A"},{route:"https://foreign.example",ownerUserId:"B"},{route:"//foreign.example",ownerUserId:"B"},{route:"/chat/s"}]) click({payload});
  expect(navigate).not.toHaveBeenCalled();
});

test("an account switch during native permission request does not send the old task", async () => {
  let granted!:(value:string)=>void;
  native.invoke.mockImplementation((command:string)=>command === "desktop_notification_supports_actions" ? Promise.resolve(true) : new Promise(resolve=>{granted=resolve;}));
  const service = createAppNotificationService({runtime:"tauri"});
  service.setActiveUserId("A");
  const pending = service.notify({type:"task",title:"Private",ownerUserId:"A"});
  await vi.waitFor(()=>expect(granted).toBeDefined());
  service.setActiveUserId("B");
  service.setActiveUserId("A");
  granted("granted");
  await pending;
  expect(native.invoke.mock.calls.some(([command])=>command === "desktop_notification_send")).toBe(false);
});

test("failed native action delivery never falls back or reports delivered", async () => {
  native.invoke.mockImplementation(async (command:string) => {
    if (command === "desktop_notification_supports_actions") return true;
    if (command === "desktop_notification_permission") return "granted";
    throw new Error("native_notification_delivery_failed");
  });
  const service = createAppNotificationService({runtime:"tauri",onWarning:vi.fn()});
  service.setActiveUserId("A");
  expect(await service.notify({type:"task",title:"Task",ownerUserId:"A"})).toBe("failed");
  expect(native.send).not.toHaveBeenCalled();
});

test("native listener initialization can recover and reads the latest account", async () => {
  native.listen.mockRejectedValueOnce(new Error("temporarily unavailable"));
  const warning = vi.fn();
  const navigate = vi.fn();
  const service = createAppNotificationService({runtime:"tauri",onNavigate:navigate,onWarning:warning});
  service.setActiveUserId("A");
  service.initializeNativeClickHandlers();
  await vi.waitFor(()=>expect(warning).toHaveBeenCalled());
  service.setActiveUserId("B");
  service.initializeNativeClickHandlers();
  await vi.waitFor(()=>expect(native.listen).toHaveBeenCalledTimes(2));
  const click = native.listen.mock.calls[1][1];
  click({payload:{route:"/chat/a",ownerUserId:"A"}});
  click({payload:{route:"/chat/b",ownerUserId:"B"}});
  expect(navigate).toHaveBeenCalledExactlyOnceWith("/chat/b");
});


test("Android notification action retains the same account and local-route guard", async () => {
  const navigate = vi.fn();
  const service = createAppNotificationService({runtime:"capacitor-android",onNavigate:navigate});
  service.setActiveUserId("A");
  service.initializeNativeClickHandlers();
  await vi.waitFor(()=>expect(native.capacitorListen).toHaveBeenCalledWith("localNotificationActionPerformed",expect.any(Function)));
  const click = native.capacitorListen.mock.calls[0][1];
  click({notification:{extra:{route:"/chat/a?run_id=r",ownerUserId:"A"}}});
  service.setActiveUserId("B");
  click({notification:{extra:{route:"/chat/a?run_id=r",ownerUserId:"A"}}});
  expect(navigate).toHaveBeenCalledExactlyOnceWith("/chat/a?run_id=r");
});
