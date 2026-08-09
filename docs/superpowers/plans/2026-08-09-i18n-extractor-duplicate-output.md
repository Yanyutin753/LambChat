# i18n Extractor Duplicate Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one extraction run report and write each new translation key once, then replace the two newly generated placeholders with real localized copy.

**Architecture:** Exercise the existing CLI as a black box in an isolated temporary fixture. Remove only the duplicated mutation block and preserve the extractor's established placeholder policy.

**Tech Stack:** TypeScript, tsx, Vitest, i18next JSON locales.

## Global Constraints

- Preserve unrelated uncommitted frontend changes.
- Do not push or commit.
- Keep locale key structure identical across en, zh, ja, ko, and ru.

---

### Task 1: Prevent duplicate extraction side effects

**Files:**
- Create: `frontend/src/i18n/__tests__/extractI18nScript.test.ts`
- Modify: `frontend/scripts/extract-i18n.ts`

**Interfaces:**
- Consumes: the existing `pnpm exec tsx scripts/extract-i18n.ts` command and its stdout.
- Produces: a CLI that logs `Added to en.json: example.newKey` exactly once per new key.

- [ ] Write an integration test that creates one TSX source and five empty locale JSON files in a temporary directory, runs the real script there, and counts the addition log.
- [ ] Run the focused test and confirm it fails because the count is `2`.
- [ ] Delete the first duplicated mutation/write block, retaining one mutation path after the completeness check.
- [ ] Run the focused test and confirm it passes.

### Task 2: Replace generated locale placeholders

**Files:**
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/zh.json`
- Modify: `frontend/src/i18n/locales/ja.json`
- Modify: `frontend/src/i18n/locales/ko.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Consumes: `chat.messageInput` and `documents.wordPreviewTitle`.
- Produces: localized accessible labels in all five supported locales.

- [ ] Replace key-path and TODO values with concise native-language labels.
- [ ] Run the focused extractor regression and locale completeness tests.
- [ ] Run `pnpm i18n:extract` and verify it reports all keys up to date without modifying locale files.
