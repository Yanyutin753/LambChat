/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
const mocks = vi.hoisted(() => ({ custom:vi.fn(), remove:vi.fn(), dismiss:vi.fn(), navigate:vi.fn() }));
vi.mock("react-hot-toast",()=>({toast:mocks}));
vi.mock("react-router-dom",()=>({useNavigate:()=>mocks.navigate}));
vi.mock("react-i18next",async(importOriginal)=>({...await importOriginal<typeof import("react-i18next")>(),useTranslation:()=>({t:(key:string)=>key})}));
import { useBackgroundConversationAction } from "../useBackgroundConversationAction";
beforeEach(()=>{vi.clearAllMocks();mocks.custom.mockReturnValue("background-return-toast");});
const options = {userId:"a",sessionId:"chat/1",runId:"run 2",ready:true,onDetach:vi.fn()};
test("background continuation requires admission of the exact run",()=>{
 const hook=renderHook(()=>useBackgroundConversationAction({...options,ready:false}));
 act(()=>hook.result.current()); expect(options.onDetach).not.toHaveBeenCalled(); expect(mocks.custom).not.toHaveBeenCalled();
});
test("background continuation offers an owned return action to the accepted run",()=>{
 const hook=renderHook(()=>useBackgroundConversationAction(options)); act(()=>hook.result.current());
 expect(options.onDetach).toHaveBeenCalledOnce();
 const element=mocks.custom.mock.calls[0][0]({id:"background-return-toast",visible:true});
 act(()=>element.props.onOpen()); expect(mocks.navigate).toHaveBeenCalledWith("/chat/chat%2F1?run_id=run%202");
});
test.each(["unmount","switch-back"])("old background return action is removed and inert after %s",transition=>{
 const hook=renderHook(({userId})=>useBackgroundConversationAction({...options,userId}),{initialProps:{userId:"a"}});
 act(()=>hook.result.current()); const element=mocks.custom.mock.calls[0][0]({id:"background-return-toast",visible:true});
 if(transition==="unmount") hook.unmount(); else { hook.rerender({userId:"b"}); hook.rerender({userId:"a"}); }
 expect(mocks.remove).toHaveBeenCalledWith("background-return-toast");
 act(()=>element.props.onOpen()); expect(mocks.navigate).not.toHaveBeenCalled();
});
