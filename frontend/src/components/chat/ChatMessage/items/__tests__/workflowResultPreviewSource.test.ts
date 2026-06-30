import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const previewSource = readFileSync(new URL("../McpBlockPreview.tsx", import.meta.url), "utf8");

test("Workflow tool results render as workflow blocks even before a run id exists", () => {
  assert.match(previewSource, /function looksLikeWorkflowRunResult/);
  assert.match(previewSource, /data\.plugin_id !== "workflow"/);
  assert.match(previewSource, /!nonEmptyString\(data\.workflow_id\)/);
  assert.match(previewSource, /nonEmptyString\(data\.run_id\) \|\|/);
  assert.match(previewSource, /nonEmptyString\(data\.status\) \|\|/);
  assert.match(previewSource, /typeof data\.error === "string"/);
  assert.match(previewSource, /isRecord\(data\.output\) \|\|/);
  assert.match(previewSource, /isRecord\(data\.interface\) \|\|/);
  assert.match(previewSource, /isRecord\(data\.next_action\) \|\|/);
  assert.match(previewSource, /isRecord\(data\.output_contract\)/);
  assert.match(previewSource, /next_action: isRecord\(data\.next_action\) \? data\.next_action : null/);
  assert.doesNotMatch(previewSource, /if \(!runId \|\| !workflowId\) return null/);
});

const workflowItemSource = readFileSync(new URL("../WorkflowItem.tsx", import.meta.url), "utf8");

test("workflow result preview exposes human approval resume outlet", () => {
  assert.match(workflowItemSource, /function workflowApprovalAction/);
  assert.match(workflowItemSource, /const actionType = stringValue\(action\?\.type\)/);
  assert.match(workflowItemSource, /actionType !== "await_human_approval" && actionType !== "wait_for_human_approval"/);
  assert.match(workflowItemSource, /resumeTool: stringValue\(resume\?\.tool\) \|\| "workflow_resume"/);
  assert.match(workflowItemSource, /function HumanApprovalNextAction/);
  assert.match(workflowItemSource, /workflowAwaitingApproval/);
  assert.match(workflowItemSource, /workflowApprovalResumeTool/);
  assert.match(workflowItemSource, /workflowApprovalPending/);
  assert.match(workflowItemSource, /workflowApprovalResumePath/);
  assert.match(workflowItemSource, /<HumanApprovalNextAction[\s\S]*action=\{approvalAction\}[\s\S]*canResume=\{canResumeApproval\}/);
});

test("workflow result preview can resume human approval from chat", () => {
  assert.match(workflowItemSource, /import \{ workflowApi, type WorkflowRunResponse \}/);
  assert.match(workflowItemSource, /function workflowPartFromRun\(run: WorkflowRunResponse\): WorkflowPart/);
  assert.match(workflowItemSource, /const \[localPart, setLocalPart\] = useState<WorkflowPart \| null>\(null\)/);
  assert.match(workflowItemSource, /const displayPart = localPart \?\? part/);
  assert.match(workflowItemSource, /const handleResumeApproval = async \(approved: boolean\) =>/);
  assert.match(workflowItemSource, /workflowApi\.resumeRun\(workflowId, runId, \{/);
  assert.match(workflowItemSource, /comment: approvalComment \|\| null/);
  assert.match(workflowItemSource, /const nextPart = workflowPartFromRun\(run\)/);
  assert.match(workflowItemSource, /setLocalPart\(nextPart\)/);
  assert.match(workflowItemSource, /workflowApprovalComment/);
  assert.match(workflowItemSource, /workflowApprove/);
  assert.match(workflowItemSource, /workflowReject/);
  assert.match(workflowItemSource, /onResume=\{handleResumeApproval\}/);
});
