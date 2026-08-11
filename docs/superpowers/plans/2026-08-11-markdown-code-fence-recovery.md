# Markdown Code-Fence Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent malformed fenced Markdown from causing every later LambChat code block to alternate between code and plain text.

**Architecture:** Keep the existing string normalizer and correct its closing-fence classification to follow CommonMark. A marker with non-whitespace content after it cannot close an open fence, so it stays untouched until a valid bare closing marker arrives.

**Tech Stack:** TypeScript, ReactMarkdown, Vitest.

## Global Constraints

- Preserve repair of opening code fences attached to preceding prose.
- Do not rewrite model text or change shared CJK Markdown plugins.
- Work in the current checkout and preserve unrelated changes.

---

### Task 1: Correct closing-fence classification

**Files:**
- Modify: `frontend/src/components/chat/ChatMessage/markdownCodeFences.ts`
- Test: `frontend/src/components/chat/ChatMessage/__tests__/markdownCodeFences.test.ts`

**Interfaces:**
- Consumes: `normalizeMarkdownCodeFences(markdown: string): string`
- Produces: the same function with CommonMark-compatible recovery for an info string encountered while a fence is open.

- [x] **Step 1: Write the failing regression test**

Add a hand-derived malformed SystemVerilog fixture whose second
`\`\`\`systemverilog` marker occurs before a bare closing marker. Assert the
normalizer preserves the fixture exactly so the bare marker closes the first
block and later Markdown remains correctly aligned.

- [x] **Step 2: Run the focused test and verify RED**

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/markdownCodeFences.test.ts
```

Expected: the new test fails because the normalizer currently strips the
language marker into plain text and reverses the later fences.

- [x] **Step 3: Implement the minimal classification guard**

In the `inFence` branch, inspect `afterMarkerOnLine`. When it contains any
non-space or non-tab character, skip that match without changing `lastIndex`
or `inFence`. Existing processing handles a later bare marker normally.

- [x] **Step 4: Run focused tests and verify GREEN**

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/markdownCodeFences.test.ts
```

Expected: all normalizer tests pass.

- [x] **Step 5: Run related and frontend verification**

```bash
cd frontend && pnpm test -- src/components/chat/ChatMessage/__tests__/markdownCodeFences.test.ts src/components/common/__tests__/markdownRendererSources.test.ts
cd frontend && pnpm run lint
cd frontend && pnpm run build
```

Expected: every command exits zero.
