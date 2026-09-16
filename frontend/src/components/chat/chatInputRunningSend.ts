import type { KeyboardEvent } from "react";

import { isSendEnterKey } from "../../hooks/sendModifier";
import type { MessageAttachment } from "../../types";
import { filterSendableAttachments } from "./attachmentValidation";

export interface RunningDraftState {
  isLoading: boolean;
  sendBlocked: boolean;
  input: string;
  visibleAttachments: MessageAttachment[];
  hasUploadingAttachment: boolean;
  hasFailedAttachment: boolean;
  hasInvalidAttachment: boolean;
}

export interface RunningSendHandlers {
  /** 补充当前问题：打断本条回答，结合新内容重新思考 */
  onSupplement?: (content: string, attachments?: MessageAttachment[]) => void;
  /** 追加提问：本轮结束后自动作为新消息发送 */
  onQueueFollowUp?: (
    content: string,
    attachments?: MessageAttachment[],
  ) => void;
}

interface EnterSubmitActions {
  clearDraft: () => void;
  openStopConfirm: () => void;
  submitForm: () => void;
}

export function isRunningDraftSendable(state: RunningDraftState): boolean {
  return (
    (!!state.input.trim() || state.visibleAttachments.length > 0) &&
    !state.hasUploadingAttachment &&
    !state.hasFailedAttachment &&
    !state.hasInvalidAttachment
  );
}

/** 执行运行中分流：发送草稿并清空输入；草稿不可发送/无回调时返回 false */
export function dispatchRunningEnterAction(
  state: RunningDraftState,
  handlers: RunningSendHandlers,
  clearDraft: () => void,
): boolean {
  if (!isRunningDraftSendable(state)) return false;
  const send = handlers.onQueueFollowUp;
  if (!send) return false;
  send(state.input, filterSendableAttachments(state.visibleAttachments));
  clearDraft();
  return true;
}

/** 发送键遵循用户偏好：空闲时发送，运行中默认追加排队。 */
export function handleEnterSubmit(
  event: KeyboardEvent<HTMLDivElement>,
  state: RunningDraftState,
  handlers: RunningSendHandlers,
  actions: EnterSubmitActions,
): void {
  if (!isSendEnterKey(event)) return;
  event.preventDefault();
  if (state.sendBlocked) return;
  if (!state.isLoading) {
    actions.submitForm();
    return;
  }
  if (!dispatchRunningEnterAction(state, handlers, actions.clearDraft)) {
    actions.openStopConfirm();
  }
}

/** 运行中发送（补充 / 追加提问）共用的草稿发送器工厂 */
export function createRunningDraftSender(
  input: string,
  visibleAttachments: MessageAttachment[],
  clearDraft: () => void,
) {
  return (
    send?: (content: string, attachments?: MessageAttachment[]) => void,
  ) =>
    send &&
    (() => {
      send(input, filterSendableAttachments(visibleAttachments));
      clearDraft();
    });
}

export interface RunningSendToolkitOptions {
  input: string;
  visibleAttachments: MessageAttachment[];
  clearDraft: () => void;
  setComposerText: (text: string) => void;
  restoreAttachments?: (attachments: MessageAttachment[]) => void;
  removeQueued?: (content: string, messageId: string) => void;
  focusComposer: () => void;
}

/**
 * 运行中发送与排队编辑的统一工厂：
 * - sendRunningDraft：按当前草稿发送（补充/追加）并清空输入
 * - editQueuedMessage：通过菜单
 *   把排队消息和附件弹回输入框继续编辑
 */
export function createRunningSendToolkit(options: RunningSendToolkitOptions) {
  const editQueuedMessage = (
    content: string,
    messageId: string,
    attachments: MessageAttachment[] = [],
  ) => {
    options.setComposerText(content);
    if (attachments.length) {
      const restored = new Map(
        [...options.visibleAttachments, ...attachments].map((attachment) => [
          attachment.id,
          { ...attachment, composerReferenceId: undefined },
        ]),
      );
      options.restoreAttachments?.([...restored.values()]);
    }
    options.removeQueued?.(content, messageId);
    options.focusComposer();
  };
  return {
    sendRunningDraft: createRunningDraftSender(
      options.input,
      options.visibleAttachments,
      options.clearDraft,
    ),
    editQueuedMessage,
  };
}
