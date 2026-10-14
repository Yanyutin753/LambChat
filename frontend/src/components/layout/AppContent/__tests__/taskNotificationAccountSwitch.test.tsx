/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  user: {id:"old"},
  handlers: {} as {onTaskComplete?:(event:unknown)=>void; onWsOpen?:()=>void},
  get:vi.fn(), events:vi.fn(), toast:vi.fn(), remove:vi.fn(), dismiss:vi.fn(), navigate:vi.fn(), journal:vi.fn(),
}));
vi.mock("../../../../hooks/useAuth",()=>({useAuth:()=>({user:mocks.user})}));
vi.mock("../../../../hooks/useWebSocket",()=>({useWebSocket:(handlers:typeof mocks.handlers)=>{mocks.handlers=handlers}}));
vi.mock("../../../../hooks/useBrowserNotification",()=>({useBrowserNotification:()=>({notify:vi.fn(),isSupported:false,permission:"denied"})}));
vi.mock("react-router-dom",()=>({useNavigate:()=>mocks.navigate}));
vi.mock("react-hot-toast",()=>({toast:{custom:mocks.toast, remove:mocks.remove, dismiss:mocks.dismiss}}));
vi.mock("../../../../services/api",()=>({sessionApi:{get:mocks.get,getEvents:mocks.events}}));
vi.mock("../../../../services/api/taskCompletions",()=>({getTaskCompletions:mocks.journal}));
vi.mock("../../../../services/notifications/appNotificationService",()=>({appNotificationService:{getRuntime:()=>"unsupported"}}));
import { useWebSocketNotifications } from "../useWebSocketNotifications";

let sequence = 0;
beforeEach(() => {
  vi.clearAllMocks();
  mocks.user = {id:"old"};
  mocks.get.mockResolvedValue({name:"Private task"});
  mocks.events.mockResolvedValue({events:[]});
  mocks.journal.mockResolvedValue({items:[],cursor:null,next_cursor:null});
  mocks.toast.mockReturnValue("owned-task-toast");
});
afterEach(cleanup);

function emitCompletion() {
  mocks.handlers.onTaskComplete?.({data:{session_id:"old-session",run_id:`private-run-${++sequence}`,status:"completed"}});
}
function delayedLookup() {
  let resolve!: (value:unknown)=>void;
  mocks.get.mockReturnValue(new Promise(r=>{resolve=r}));
  return () => resolve({name:"Old private task"});
}

for (const transition of ["switch", "unmount", "switch-back", "disabled"] as const) {
  test(`a completion fetch never surfaces after ${transition}`, async () => {
    const resolve = delayedLookup();
    const hook = renderHook(({enabled})=>useWebSocketNotifications({sessionId:"other",enabled}), {initialProps:{enabled:true}});
    act(emitCompletion);
    if (transition === "unmount") hook.unmount();
    else if (transition === "disabled") hook.rerender({enabled:false});
    else {
      mocks.user = {id:"new"}; hook.rerender({enabled:true});
      if (transition === "switch-back") { mocks.user = {id:"old"}; hook.rerender({enabled:true}); }
    }
    await act(async()=>{resolve();});
    expect(mocks.toast).not.toHaveBeenCalled();
  });
}

for (const transition of ["unmount", "switch", "switch-back"] as const) {
  test(`removes only owned task toasts and fences their old Open action after ${transition}`, async () => {
    const hook = renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
    await act(async()=>{emitCompletion();});
    expect(mocks.toast).toHaveBeenCalledOnce();
    const renderToast = mocks.toast.mock.calls[0][0];
    const element = renderToast({id:"owned-task-toast",visible:true});
    if (transition === "unmount") hook.unmount();
    else {
      mocks.user={id:"new"}; hook.rerender();
      if (transition === "switch-back") {mocks.user={id:"old"}; hook.rerender();}
    }
    expect(mocks.remove).toHaveBeenCalledWith("owned-task-toast");
    expect(mocks.remove.mock.calls.every(([id])=>id === "owned-task-toast")).toBe(true);
    act(()=>element.props.onOpen());
    expect(mocks.navigate).not.toHaveBeenCalled();
  });
}

test("a stale websocket handler cannot fetch a completion after unmount", async () => {
  const hook = renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  const oldHandler = mocks.handlers.onTaskComplete;
  hook.unmount();
  await act(async()=>{oldHandler?.({data:{session_id:"old-session",run_id:`private-run-${++sequence}`,status:"completed"}});});
  expect(mocks.get).not.toHaveBeenCalled();
  expect(mocks.toast).not.toHaveBeenCalled();
});

test("an old websocket open callback cannot restore the new account journal", async () => {
  const hook = renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  await act(async()=>{});
  const oldOpen = mocks.handlers.onWsOpen;
  mocks.user={id:"new"}; hook.rerender();
  await act(async()=>{});
  mocks.journal.mockClear();
  await act(async()=>{oldOpen?.();});
  expect(mocks.journal).not.toHaveBeenCalled();
});

test("account switch removes a dismissed task toast that can still be fading out", async () => {
  const hook = renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  await act(async()=>{emitCompletion();});
  const element = mocks.toast.mock.calls[0][0]({id:"owned-task-toast",visible:true});
  act(()=>element.props.onDismiss());
  expect(mocks.dismiss).toHaveBeenCalledWith("owned-task-toast");
  mocks.user={id:"new"}; hook.rerender();
  expect(mocks.remove).toHaveBeenCalledWith("owned-task-toast");
});

test("an abandoned completion remains deliverable when its account returns", async () => {
  const resolveOldLookup = delayedLookup();
  const hook = renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  const event = {data:{session_id:"old-session",run_id:`retryable-run-${++sequence}`,status:"completed"}};
  act(()=>mocks.handlers.onTaskComplete?.(event));
  mocks.user={id:"new"}; hook.rerender();
  mocks.user={id:"old"}; hook.rerender();
  await act(async()=>{resolveOldLookup();});
  expect(mocks.toast).not.toHaveBeenCalled();
  mocks.get.mockResolvedValue({name:"Returned account task"});
  await act(async()=>{mocks.handlers.onTaskComplete?.(event);});
  expect(mocks.toast).toHaveBeenCalledOnce();
  await act(async()=>{mocks.handlers.onTaskComplete?.(event);});
  expect(mocks.toast).toHaveBeenCalledOnce();
});

test("concurrent websocket and journal completion deliveries publish one toast", async () => {
  const lookupResolvers: Array<(value:unknown)=>void> = [];
  mocks.get.mockImplementation(()=>new Promise(resolve=>{lookupResolvers.push(resolve);}));
  const event = {session_id:"old-session",run_id:`concurrent-run-${++sequence}`,status:"completed"};
  let resolveJournal!: (value:unknown)=>void;
  mocks.journal.mockReturnValue(new Promise(resolve=>{resolveJournal=resolve;}));
  renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  act(()=>mocks.handlers.onTaskComplete?.({data:event}));
  await act(async()=>{resolveJournal({items:[event],cursor:null,next_cursor:null});});
  await act(async()=>{
    for (const resolve of lookupResolvers) resolve({name:"One completed task"});
  });
  expect(mocks.toast).toHaveBeenCalledOnce();
});

function markRead(detail: {sessionId?: string; projectId?: string; scheduledTaskId?: string} = {}) {
  window.dispatchEvent(new CustomEvent("lambchat:sessions-read", {detail}));
}

test("mark all read removes existing task toasts", async () => {
  renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  await act(async()=>{emitCompletion();});
  act(()=>markRead());
  expect(mocks.remove).toHaveBeenCalledWith("owned-task-toast");
});

test("mark all read prevents an in-flight completion from showing a toast", async () => {
  const resolve = delayedLookup();
  renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  act(emitCompletion);
  act(()=>markRead());
  await act(async()=>{resolve();});
  expect(mocks.toast).not.toHaveBeenCalled();
});

test("marking a different project read leaves a task toast visible", async () => {
  renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  await act(async()=>{emitCompletion();});
  act(()=>markRead({projectId:"different-project"}));
  expect(mocks.remove).not.toHaveBeenCalled();
});

test("journal replay skips a completion whose session is already read", async () => {
  mocks.get.mockResolvedValue({name:"Read task",unread_count:0});
  mocks.journal.mockResolvedValue({items:[{session_id:"old-session",run_id:`read-run-${++sequence}`,status:"completed"}],cursor:"read-cursor",next_cursor:null});
  renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  await act(async()=>{});
  expect(mocks.toast).not.toHaveBeenCalled();
});

test("new live completions still notify after mark all read", async () => {
  renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  act(()=>markRead());
  await act(async()=>{emitCompletion();});
  expect(mocks.toast).toHaveBeenCalledOnce();
});

for (const scope of [{sessionId:"old-session"}, {projectId:"project-one"}, {scheduledTaskId:"schedule-one"}]) {
  test(`reading a matching scope clears its task toast ${JSON.stringify(scope)}`, async () => {
    renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
    await act(async()=>{mocks.handlers.onTaskComplete?.({data:{session_id:"old-session",project_id:"project-one",scheduled_task_id:"schedule-one",run_id:`scoped-run-${++sequence}`,status:"completed"}});});
    act(()=>markRead(scope));
    expect(mocks.remove).toHaveBeenCalledWith("owned-task-toast");
  });
}

test("journal replay keeps notifications for unread sessions", async () => {
  mocks.get.mockResolvedValue({name:"Unread task",unread_count:1});
  mocks.journal.mockResolvedValue({items:[{session_id:"old-session",run_id:`unread-run-${++sequence}`,status:"completed"}],cursor:"unread-cursor",next_cursor:null});
  renderHook(()=>useWebSocketNotifications({sessionId:"other"}));
  await act(async()=>{});
  expect(mocks.toast).toHaveBeenCalledOnce();
});
