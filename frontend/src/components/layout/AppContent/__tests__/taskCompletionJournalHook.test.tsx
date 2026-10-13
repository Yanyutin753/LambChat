/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
const mocks=vi.hoisted(()=>({load:vi.fn()}));
vi.mock("../../../../services/api/taskCompletions",()=>({getTaskCompletions:mocks.load}));
import { useTaskCompletionJournal } from "../taskCompletionJournal";
beforeEach(()=>{localStorage.clear();mocks.load.mockReset();mocks.load.mockResolvedValue({items:[],cursor:null,next_cursor:null});});

test("reconnect and foreground restore the durable cursor without a status polling timer",async()=>{
 mocks.load.mockResolvedValueOnce({items:[],cursor:"saved",next_cursor:null});
 const deliver=vi.fn();
 const {result,unmount}=renderHook(()=>useTaskCompletionJournal("user-one",true,deliver));
 await waitFor(()=>expect(mocks.load).toHaveBeenCalledOnce());
 await act(async()=>{await result.current();});
 expect(mocks.load.mock.calls).toEqual([[null],["saved"]]);
 await act(async()=>{window.dispatchEvent(new Event("online"));});
 expect(mocks.load).toHaveBeenCalledTimes(3);
 unmount();
 await act(async()=>{window.dispatchEvent(new Event("online"));});
 expect(mocks.load).toHaveBeenCalledTimes(3);
});

test("switching account during a request discards the late completion page",async()=>{
 let resolve!:(value:unknown)=>void;
 mocks.load.mockReturnValueOnce(new Promise(r=>{resolve=r}));
 const deliver=vi.fn();
 const {rerender}=renderHook(({user})=>useTaskCompletionJournal(user,true,deliver),{initialProps:{user:"old"}});
 rerender({user:"new"});
 await act(async()=>{resolve({items:[{id:"old-event",session_id:"old-session",run_id:"old-run",status:"completed"}],cursor:"old-cursor",next_cursor:null});});
 expect(deliver).not.toHaveBeenCalled();
 expect(localStorage.getItem("lambchat.taskCompletions.cursor.new")).toBeNull();
});
