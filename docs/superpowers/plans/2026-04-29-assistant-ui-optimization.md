# Assistant UI Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize the assistant management panel and chat selector with gradient cards, category system, detail page, and Fuse.js fuzzy search — borrowing YubbChat's "Assistant Square" visual elements adapted to LambChat's warm stone palette and glass-morphism design system.

**Architecture:** Add a `category` field to the assistant data model (backend + frontend). Build shared utility modules for gradient generation and category definitions. Extract `AssistantCard` as a reusable component. Add `CategoryFilter` bar. Create `AssistantDetailPage` for the detail view. Enhance `AssistantSelector` dropdown with category filtering and gradient accents. Use Fuse.js for client-side fuzzy search on the management panel.

**Tech Stack:** React 18, TypeScript, Tailwind CSS v3 (stone palette), lucide-react icons, Fuse.js, clsx

---

### Task 1: Backend — Add `category` field to assistant schema

**Files:**
- Modify: `src/infra/assistant/types.py`
- Modify: `src/api/routes/assistant.py`
- Modify: `src/infra/assistant/manager.py`
- Test: `tests/infra/assistant/test_manager.py`
- Test: `tests/api/routes/test_assistant_routes.py`

- [ ] **Step 1: Add `category` field to backend models**

In `src/infra/assistant/types.py`, add `category: str = "general"` to `AssistantRecord`, `AssistantCreate`, and `AssistantUpdate`:

```python
# In AssistantRecord, after tags field (line 29):
category: str = "general"

# In AssistantCreate, after tags field (line 49):
category: str = "general"

# In AssistantUpdate, add new optional field:
category: str | None = None
```

- [ ] **Step 2: Add `category` query param to list endpoint**

In `src/api/routes/assistant.py`, add a `category` query parameter to `list_assistants`:

```python
@router.get("", response_model=list[AssistantResponse])
async def list_assistants(
    scope: str = Query("public", pattern="^(public|mine|all)$"),
    search: str | None = Query(None),
    tags: str | None = Query(None),
    category: str | None = Query(None),
    user: TokenPayload = Depends(get_current_user_required),
    manager: AssistantManager = Depends(get_assistant_manager),
) -> list[AssistantResponse]:
    tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()] if tags else None
    items = await manager.list_assistants(user.sub, scope=scope, search=search, tags=tag_list, category=category)
    return [AssistantResponse.model_validate(item.model_dump()) for item in items]
```

- [ ] **Step 3: Add `category` filtering to manager**

In `src/infra/assistant/manager.py`, update `list_assistants` signature and add filter:

```python
async def list_assistants(
    self,
    user_id: str,
    scope: str = "public",
    search: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
) -> list[AssistantRecord]:
    public_items = await self.storage.list_public_assistants()
    private_items = await self.storage.list_user_assistants(user_id)

    if scope == "mine":
        items = private_items
    elif scope == "all":
        items = public_items + private_items
    else:
        items = public_items

    if category:
        items = [item for item in items if item.category == category]
    if search:
        needle = search.lower()
        items = [
            item
            for item in items
            if needle in item.name.lower() or needle in item.description.lower()
        ]
    if tags:
        required = set(tags)
        items = [item for item in items if required.issubset(set(item.tags))]
    return items
```

- [ ] **Step 4: Run existing backend tests to verify no regressions**

Run: `cd /home/yangyang/LambChat && python -m pytest tests/api/routes/test_assistant_routes.py tests/infra/assistant/ -v`
Expected: All existing tests pass (the new `category` field has a default value so existing data is unaffected)

- [ ] **Step 5: Commit**

```bash
git add src/infra/assistant/types.py src/api/routes/assistant.py src/infra/assistant/manager.py
git commit -m "feat(backend): add category field to assistant schema and list filter"
```

---

### Task 2: Frontend — Category definitions and gradient utilities

**Files:**
- Create: `frontend/src/components/assistant/categories.ts`
- Create: `frontend/src/components/assistant/gradientUtils.ts`

- [ ] **Step 1: Create category definitions**

Create `frontend/src/components/assistant/categories.ts`:

```typescript
import {
  Code,
  PenLine,
  Languages,
  GraduationCap,
  Briefcase,
  Palette,
  BarChart3,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

export interface AssistantCategory {
  id: string;
  label: string;
  icon: LucideIcon;
}

export const ASSISTANT_CATEGORIES: AssistantCategory[] = [
  { id: "programming", label: "Programming", icon: Code },
  { id: "writing", label: "Writing", icon: PenLine },
  { id: "translation", label: "Translation", icon: Languages },
  { id: "education", label: "Education", icon: GraduationCap },
  { id: "business", label: "Business", icon: Briefcase },
  { id: "creative", label: "Creative", icon: Palette },
  { id: "analysis", label: "Analysis", icon: BarChart3 },
  { id: "general", label: "General", icon: Sparkles },
];

export const CATEGORY_MAP = new Map(
  ASSISTANT_CATEGORIES.map((cat) => [cat.id, cat]),
);

export function getCategoryById(id: string): AssistantCategory | undefined {
  return CATEGORY_MAP.get(id);
}
```

- [ ] **Step 2: Create gradient utility**

Create `frontend/src/components/assistant/gradientUtils.ts`:

```typescript
/**
 * Generate a deterministic HSL gradient from a name string.
 * Uses a simple hash to pick a hue, then builds a warm, low-saturation gradient.
 */
export function nameToGradient(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
    hash = hash & hash; // Convert to 32bit int
  }

  const hue = ((hash % 360) + 360) % 360;
  const sat1 = 30 + ((hash >> 8) & 15); // 30-45%
  const sat2 = 25 + ((hash >> 12) & 15); // 25-40%
  const light1 = 72 + ((hash >> 16) & 8); // 72-80%
  const light2 = 65 + ((hash >> 20) & 10); // 65-75%
  const hue2 = (hue + 30) % 360;
  const hue3 = (hue + 60) % 360;

  return `linear-gradient(135deg, hsl(${hue}, ${sat1}%, ${light1}%), hsl(${hue2}, ${sat2}%, ${light2}%), hsl(${hue3}, ${sat1}%, ${light1}%))`;
}

/**
 * Generate a small gradient accent (e.g. for left border bar).
 */
export function nameToAccentColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
    hash = hash & hash;
  }
  const hue = ((hash % 360) + 360) % 360;
  return `hsl(${hue}, 40%, 55%)`;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/assistant/categories.ts frontend/src/components/assistant/gradientUtils.ts
git commit -m "feat(assistant): add category definitions and gradient utilities"
```

---

### Task 3: Frontend — Update types and API for category support

**Files:**
- Modify: `frontend/src/types/assistant.ts`
- Modify: `frontend/src/services/api/assistant.ts`
- Modify: `frontend/src/hooks/useAssistants.ts`
- Test: `frontend/src/services/api/assistant.test.ts`

- [ ] **Step 1: Add `category` to frontend types**

In `frontend/src/types/assistant.ts`, add `category` field:

```typescript
// In Assistant interface, after tags field (line 12):
category?: string;

// In AssistantCreate interface, after tags field (line 29):
category?: string;

// In AssistantUpdate interface, after tags field (line 39):
category?: string;
```

- [ ] **Step 2: Add `category` to API params**

In `frontend/src/services/api/assistant.ts`, update `AssistantListParams` and URL builder:

```typescript
export interface AssistantListParams {
  scope?: AssistantListScope;
  search?: string;
  tags?: string[];
  category?: string;
}

export function buildAssistantListUrl(params?: AssistantListParams): string {
  const searchParams = new URLSearchParams();
  if (params?.scope && params.scope !== "public") {
    searchParams.set("scope", params.scope);
  }
  if (params?.search) {
    searchParams.set("search", params.search);
  }
  if (params?.tags && params.tags.length > 0) {
    searchParams.set("tags", params.tags.join(","));
  }
  if (params?.category) {
    searchParams.set("category", params.category);
  }

  const query = searchParams.toString();
  return `${ASSISTANTS_API}${query ? `?${query}` : ""}`;
}
```

- [ ] **Step 3: Add `category` to useAssistants hook**

In `frontend/src/hooks/useAssistants.ts`, add `category` to options and pass to API:

```typescript
interface UseAssistantsOptions {
  scope?: AssistantListScope;
  search?: string;
  tags?: string[];
  category?: string;
  enabled?: boolean;
}

export function useAssistants(options: UseAssistantsOptions = {}) {
  const {
    scope = "all",
    search = "",
    tags,
    category,
    enabled = true,
  } = options;
  // ... existing state ...

  const refresh = useCallback(async (): Promise<Assistant[]> => {
    if (!enabled) {
      setAssistants([]);
      return [];
    }

    setIsLoading(true);
    try {
      const items = coerceAssistantList(
        await assistantApi.list({ scope, search, tags: stableTags, category }),
      );
      setAssistants(items);
      setError(null);
      return items;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load assistants";
      setError(message);
      setAssistants([]);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, [enabled, scope, search, stableTags, category]);
  // ... rest unchanged ...
}
```

- [ ] **Step 4: Update API URL builder test**

In `frontend/src/services/api/assistant.test.ts`, add test for category param:

```typescript
test("includes category when building assistant list url", () => {
  assert.equal(
    buildAssistantListUrl({ category: "programming" }),
    "/api/assistants?category=programming",
  );
});
```

- [ ] **Step 5: Run frontend tests**

Run: `cd /home/yangyang/LambChat/frontend && npx tsx --test src/services/api/assistant.test.ts`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/assistant.ts frontend/src/services/api/assistant.ts frontend/src/hooks/useAssistants.ts frontend/src/services/api/assistant.test.ts
git commit -m "feat(frontend): add category support to assistant types, API, and hook"
```

---

### Task 4: Frontend — CategoryFilter component

**Files:**
- Create: `frontend/src/components/assistant/CategoryFilter.tsx`

- [ ] **Step 1: Create CategoryFilter component**

Create `frontend/src/components/assistant/CategoryFilter.tsx`:

```typescript
import { ASSISTANT_CATEGORIES } from "./categories";

interface CategoryFilterProps {
  selected: string | null;
  onSelect: (category: string | null) => void;
}

export function CategoryFilter({ selected, onSelect }: CategoryFilterProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <button
        type="button"
        onClick={() => onSelect(null)}
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition-all duration-150 ${
          selected === null
            ? "bg-stone-900 text-white shadow-sm dark:bg-stone-100 dark:text-stone-900"
            : "bg-stone-100 text-stone-500 hover:bg-stone-200 hover:text-stone-700 dark:bg-stone-800/60 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-200"
        }`}
      >
        All
      </button>
      {ASSISTANT_CATEGORIES.map((cat) => {
        const Icon = cat.icon;
        return (
          <button
            key={cat.id}
            type="button"
            onClick={() => onSelect(cat.id)}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] font-medium transition-all duration-150 ${
              selected === cat.id
                ? "bg-stone-900 text-white shadow-sm dark:bg-stone-100 dark:text-stone-900"
                : "bg-stone-100 text-stone-500 hover:bg-stone-200 hover:text-stone-700 dark:bg-stone-800/60 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-200"
            }`}
          >
            <Icon size={12} strokeWidth={2} />
            {cat.label}
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/assistant/CategoryFilter.tsx
git commit -m "feat(assistant): add CategoryFilter component"
```

---

### Task 5: Frontend — AssistantCard component with gradient header

**Files:**
- Create: `frontend/src/components/assistant/AssistantCard.tsx`

- [ ] **Step 1: Create AssistantCard component**

Create `frontend/src/components/assistant/AssistantCard.tsx`:

```typescript
import {
  CopyPlus,
  Eye,
  Globe,
  Lock,
  Pencil,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import type { Assistant } from "../../types";
import { nameToGradient } from "./gradientUtils";
import { getCategoryById } from "./categories";

interface AssistantCardProps {
  assistant: Assistant;
  isAdmin: boolean;
  onClone: (assistant: Assistant) => void;
  onEdit: (assistant: Assistant) => void;
  onDelete: (assistant: Assistant) => void;
  onView: (assistant: Assistant) => void;
}

export function AssistantCard({
  assistant,
  isAdmin,
  onClone,
  onEdit,
  onDelete,
  onView,
}: AssistantCardProps) {
  const { t } = useTranslation();
  const gradient = nameToGradient(assistant.name);
  const category = getCategoryById(assistant.category || "general");
  const canEdit =
    assistant.scope === "private" ||
    (assistant.scope === "public" && isAdmin);

  return (
    <article
      className="group flex h-full flex-col overflow-hidden rounded-xl border border-stone-200/70 bg-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md dark:border-stone-800/50 dark:bg-stone-900/60"
    >
      {/* Gradient header bar */}
      <div
        className="h-12 w-full"
        style={{ background: gradient }}
      />

      {/* Card body */}
      <div
        className="flex flex-1 cursor-pointer flex-col p-4"
        onClick={() => onView(assistant)}
      >
        {/* Top row: avatar + name + scope icon */}
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-amber-50 to-orange-50 ring-1 ring-amber-100/50 dark:from-amber-900/30 dark:to-orange-900/20 dark:ring-amber-800/20">
            {assistant.avatar_url ? (
              <img
                src={assistant.avatar_url}
                alt={assistant.name}
                className="size-full object-cover"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            ) : (
              <Sparkles
                size={16}
                className="text-amber-500 dark:text-amber-400"
              />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <h3 className="truncate text-[14px] font-semibold text-stone-900 dark:text-stone-50">
                {assistant.name}
              </h3>
              {assistant.scope === "public" ? (
                <Globe size={12} className="shrink-0 text-sky-500 dark:text-sky-400" />
              ) : (
                <Lock size={12} className="shrink-0 text-stone-400 dark:text-stone-500" />
              )}
            </div>
            {category && (
              <div className="mt-1 inline-flex items-center gap-1 rounded-full bg-stone-100 px-2 py-0.5 text-[10px] font-medium text-stone-500 dark:bg-stone-800/60 dark:text-stone-400">
                <category.icon size={10} strokeWidth={2} />
                {category.label}
              </div>
            )}
          </div>
        </div>

        {/* Description */}
        <p className="mt-3 line-clamp-2 text-[12.5px] leading-relaxed text-stone-500 dark:text-stone-400">
          {assistant.description ||
            t("assistants.noDescription", {
              defaultValue: "No description yet.",
            })}
        </p>

        {/* Tags */}
        {assistant.tags.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1">
            {assistant.tags.map((tag) => (
              <span
                key={tag}
                className="rounded bg-stone-100 px-2 py-0.5 text-[11px] text-stone-500 dark:bg-stone-800/50 dark:text-stone-400"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Prompt preview */}
        <div className="mt-3 flex-1 rounded-lg bg-stone-50 px-3 py-2.5 dark:bg-stone-800/40">
          <p className="line-clamp-3 whitespace-pre-wrap font-mono text-[11px] leading-5 text-stone-400 dark:text-stone-500">
            {assistant.system_prompt}
          </p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1.5 border-t border-stone-100 px-4 py-3 dark:border-stone-800/40">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onView(assistant);
          }}
          className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
        >
          <Eye size={12} />
          {t("common.view", { defaultValue: "View" })}
        </button>

        {assistant.scope === "public" && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClone(assistant);
            }}
            className="inline-flex items-center gap-1 rounded-md bg-stone-900 px-2.5 py-1.5 text-[11px] font-medium text-white transition-colors hover:bg-stone-700 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
          >
            <CopyPlus size={12} />
            {t("assistants.clone", { defaultValue: "Clone" })}
          </button>
        )}

        {canEdit && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onEdit(assistant);
            }}
            className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
          >
            <Pencil size={12} />
            {t("common.edit", { defaultValue: "Edit" })}
          </button>
        )}

        {assistant.scope === "private" && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(assistant);
            }}
            className="inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium text-rose-500 transition-colors hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/30"
          >
            <Trash2 size={12} />
            {t("common.delete", { defaultValue: "Delete" })}
          </button>
        )}
      </div>
    </article>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/assistant/AssistantCard.tsx
git commit -m "feat(assistant): add AssistantCard component with gradient header"
```

---

### Task 6: Frontend — AssistantDetailPage component

**Files:**
- Create: `frontend/src/components/assistant/AssistantDetailPage.tsx`

- [ ] **Step 1: Create AssistantDetailPage component**

Create `frontend/src/components/assistant/AssistantDetailPage.tsx`:

```typescript
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Check,
  ChevronRight,
  Clipboard,
  Globe,
  Lock,
  Package,
  Sparkles,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import { assistantApi } from "../../services/api/assistant";
import { useAssistants } from "../../hooks/useAssistants";
import type { Assistant } from "../../types";
import { nameToGradient } from "./gradientUtils";
import { getCategoryById } from "./categories";

interface AssistantDetailPageProps {
  assistantId: string;
  onBack: () => void;
  onStartChat: (assistant: Assistant) => void;
  onViewAssistant: (assistantId: string) => void;
}

export function AssistantDetailPage({
  assistantId,
  onBack,
  onStartChat,
  onViewAssistant,
}: AssistantDetailPageProps) {
  const { t } = useTranslation();
  const [assistant, setAssistant] = useState<Assistant | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const { assistants: allAssistants } = useAssistants({ scope: "all" });

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    assistantApi
      .get(assistantId)
      .then((data) => {
        if (!cancelled) setAssistant(data);
      })
      .catch(() => {
        if (!cancelled) setAssistant(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [assistantId]);

  const category = useMemo(
    () => getCategoryById(assistant?.category || "general"),
    [assistant],
  );

  const relatedAssistants = useMemo(() => {
    if (!assistant) return [];
    return allAssistants
      .filter(
        (a) =>
          a.assistant_id !== assistant.assistant_id &&
          (a.category || "general") === (assistant.category || "general"),
      )
      .slice(0, 6);
  }, [allAssistants, assistant]);

  const handleCopy = useCallback(async () => {
    if (!assistant) return;
    try {
      await navigator.clipboard.writeText(assistant.system_prompt);
      setCopied(true);
      toast.success(t("assistants.copied", { defaultValue: "Copied!" }));
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error(
        t("assistants.copyFailed", { defaultValue: "Failed to copy." }),
      );
    }
  }, [assistant, t]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-pulse text-stone-400 dark:text-stone-500">
          Loading...
        </div>
      </div>
    );
  }

  if (!assistant) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <Package size={48} className="text-stone-300 dark:text-stone-600" />
        <p className="text-sm text-stone-500 dark:text-stone-400">
          {t("assistants.notFound", { defaultValue: "Assistant not found." })}
        </p>
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-stone-500 underline hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
        >
          {t("common.back", { defaultValue: "Go back" })}
        </button>
      </div>
    );
  }

  const gradient = nameToGradient(assistant.name);

  return (
    <div className="flex h-full flex-col">
      {/* Sticky header */}
      <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3 dark:border-stone-800/40 sm:px-6">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-stone-600 transition-colors hover:bg-stone-100 hover:text-stone-800 dark:text-stone-300 dark:hover:bg-stone-800 dark:hover:text-stone-100"
        >
          <ArrowLeft size={16} />
          {t("common.back", { defaultValue: "Back" })}
        </button>
        <button
          type="button"
          onClick={() => onStartChat(assistant)}
          className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-stone-700 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
        >
          <Sparkles size={14} />
          {t("assistants.startChat", { defaultValue: "Start Chat" })}
        </button>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          {/* Info card */}
          <div
            className="overflow-hidden rounded-xl border border-stone-200/70 bg-white shadow-sm dark:border-stone-800/50 dark:bg-stone-900/60"
          >
            <div className="p-5">
              <div className="flex flex-col items-center gap-4 lg:flex-row lg:items-start lg:gap-5">
                {/* Avatar */}
                <div
                  className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-xl ring-2 ring-stone-200/60 dark:ring-stone-700/40"
                  style={{ background: gradient }}
                >
                  {assistant.avatar_url ? (
                    <img
                      src={assistant.avatar_url}
                      alt={assistant.name}
                      className="size-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ) : (
                    <Sparkles
                      size={24}
                      className="text-white/80"
                    />
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 text-center lg:text-left">
                  <div className="flex items-center justify-center gap-2 lg:justify-start">
                    <h1 className="text-xl font-bold text-stone-900 dark:text-stone-50">
                      {assistant.name}
                    </h1>
                    {assistant.scope === "public" ? (
                      <Globe size={14} className="text-sky-500 dark:text-sky-400" />
                    ) : (
                      <Lock size={14} className="text-stone-400 dark:text-stone-500" />
                    )}
                  </div>
                  {category && (
                    <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-stone-100 px-2.5 py-1 text-[11px] font-medium text-stone-500 dark:bg-stone-800/60 dark:text-stone-400">
                      <category.icon size={11} strokeWidth={2} />
                      {category.label}
                    </div>
                  )}
                  {assistant.description && (
                    <p className="mt-2 text-sm text-stone-500 dark:text-stone-400">
                      {assistant.description}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Two-column layout: prompt + related */}
          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            {/* System prompt */}
            <div className="lg:col-span-2">
              <div className="mb-3 flex items-center gap-2">
                <div className="flex size-8 items-center justify-center rounded-lg bg-stone-100 dark:bg-stone-800">
                  <Clipboard size={16} className="text-stone-500 dark:text-stone-400" />
                </div>
                <h2 className="text-[15px] font-semibold text-stone-800 dark:text-stone-100">
                  {t("assistants.systemPrompt", {
                    defaultValue: "System Prompt",
                  })}
                </h2>
              </div>
              <div className="relative overflow-hidden rounded-xl border border-stone-200/70 bg-stone-50 dark:border-stone-800/50 dark:bg-stone-800/40">
                <button
                  type="button"
                  onClick={() => void handleCopy()}
                  className="absolute right-3 top-3 inline-flex items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 text-[11px] font-medium text-stone-600 shadow-sm transition-colors hover:bg-stone-100 dark:bg-stone-700 dark:text-stone-300 dark:hover:bg-stone-600"
                >
                  {copied ? (
                    <>
                      <Check size={12} className="text-green-500" />
                      {t("assistants.copied", { defaultValue: "Copied!" })}
                    </>
                  ) : (
                    <>
                      <Clipboard size={12} />
                      {t("common.copy", { defaultValue: "Copy" })}
                    </>
                  )}
                </button>
                <pre className="max-h-[400px] overflow-y-auto p-4 pt-12 font-mono text-[12.5px] leading-6 text-stone-700 dark:text-stone-300">
                  {assistant.system_prompt}
                </pre>
              </div>
              <div className="mt-3 rounded-lg bg-blue-50/50 px-4 py-2.5 text-[12px] text-blue-600 dark:bg-blue-950/20 dark:text-blue-400">
                {t("assistants.promptTip", {
                  defaultValue:
                    "Use this prompt to get the best results from this assistant.",
                })}
              </div>
            </div>

            {/* Related assistants */}
            <div>
              <div className="mb-3 flex items-center gap-2">
                <div className="flex size-8 items-center justify-center rounded-lg bg-purple-50 dark:bg-purple-950/30">
                  <Sparkles size={16} className="text-purple-500 dark:text-purple-400" />
                </div>
                <h2 className="text-[15px] font-semibold text-stone-800 dark:text-stone-100">
                  {t("assistants.related", {
                    defaultValue: "Related Assistants",
                  })}
                </h2>
              </div>
              <div className="overflow-hidden rounded-xl border border-stone-200/70 bg-white dark:border-stone-800/50 dark:bg-stone-900/60">
                {relatedAssistants.length === 0 ? (
                  <div className="flex flex-col items-center gap-2 px-4 py-8">
                    <Package
                      size={32}
                      className="text-stone-300 dark:text-stone-600"
                    />
                    <p className="text-[12px] text-stone-400 dark:text-stone-500">
                      {t("assistants.noRelated", {
                        defaultValue: "No similar assistants found.",
                      })}
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-stone-100 dark:divide-stone-800/40">
                    {relatedAssistants.map((related) => (
                      <button
                        key={related.assistant_id}
                        type="button"
                        onClick={() =>
                          onViewAssistant(related.assistant_id)
                        }
                        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-stone-50 dark:hover:bg-stone-800/40"
                      >
                        <div className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-amber-50 to-orange-50 ring-1 ring-amber-100/50 dark:from-amber-900/30 dark:to-orange-900/20 dark:ring-amber-800/20">
                          {related.avatar_url ? (
                            <img
                              src={related.avatar_url}
                              alt={related.name}
                              className="size-full object-cover"
                              onError={(e) => {
                                (e.target as HTMLImageElement).style.display =
                                  "none";
                              }}
                            />
                          ) : (
                            <Sparkles
                              size={14}
                              className="text-amber-500 dark:text-amber-400"
                            />
                          )}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium text-stone-800 dark:text-stone-100">
                            {related.name}
                          </p>
                          <p className="truncate text-[11px] text-stone-400 dark:text-stone-500">
                            {related.description}
                          </p>
                        </div>
                        <ChevronRight
                          size={14}
                          className="shrink-0 text-stone-300 transition-transform group-hover:translate-x-0.5 dark:text-stone-600"
                        />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Mobile Start Chat button */}
          <div className="mt-6 lg:hidden">
            <button
              type="button"
              onClick={() => onStartChat(assistant)}
              className="w-full rounded-xl bg-stone-900 py-3 text-[14px] font-medium text-white shadow-sm transition-all hover:bg-stone-700 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
            >
              {t("assistants.startChatMobile", {
                defaultValue: "Start Chatting with This Assistant",
              })}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/assistant/AssistantDetailPage.tsx
git commit -m "feat(assistant): add AssistantDetailPage with prompt preview and related assistants"
```

---

### Task 7: Frontend — Integrate detail page into routing and TabContent

**Files:**
- Modify: `frontend/src/components/layout/AppContent/types.ts`
- Modify: `frontend/src/components/layout/AppContent/TabContent.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add `assistant-detail` tab type**

In `frontend/src/components/layout/AppContent/types.ts`, add the new tab type:

```typescript
export type TabType =
  | "chat"
  | "skills"
  | "marketplace"
  | "assistants"
  | "assistant-detail"
  | "users"
  | "roles"
  | "settings"
  | "mcp"
  | "feedback"
  | "channels"
  | "agents"
  | "models"
  | "files"
  | "notifications"
  | "memory";
```

- [ ] **Step 2: Register detail page in TabContent**

In `frontend/src/components/layout/AppContent/TabContent.tsx`, add lazy import and panel mapping. The detail page needs access to `assistantId` from URL params, so we'll use React Router's `useParams` inside the component. Update the file:

Add import and lazy load at top:
```typescript
const AssistantDetailPage = lazy(() =>
  import("../../assistant/AssistantDetailPage").then((m) => ({
    default: m.AssistantDetailPage,
  })),
);
```

Add to `panelMap`:
```typescript
panelMap["assistant-detail"] = AssistantDetailPage;
```

But wait — the detail page needs an `assistantId` prop and navigation callbacks. Instead of using panelMap (which doesn't pass props), we handle `assistant-detail` specially in the `TabContent` component. Replace the direct panelMap lookup with a special case:

```typescript
export function TabContent({ activeTab }: { activeTab: TabType }) {
  if (activeTab === "chat") return null;
  if (activeTab === "assistant-detail") return null; // handled by AppContent

  const Panel = panelMap[activeTab];
  if (!Panel) return null;

  return (
    <main className="flex-1 overflow-hidden">
      <div className="mx-auto max-w-3xl xl:max-w-5xl w-full h-full flex flex-col">
        <Suspense fallback={<PanelLoader />}>
          <Panel />
        </Suspense>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Add route in App.tsx**

In `frontend/src/App.tsx`, add the detail page route and a new component. First, add a new page component:

```typescript
function AssistantDetailRoute() {
  usePageTitle("nav.assistantDetail", undefined, {
    description: "navDesc.assistants",
  });
  return <AppContent key="assistant-detail" activeTab="assistant-detail" />;
}
```

Then add the route in the routes section, right after the `/assistants` route:

```tsx
<Route
  path="/assistants/:assistantId"
  element={
    <ProtectedRoute>
      <AssistantDetailRoute />
    </ProtectedRoute>
  }
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/AppContent/types.ts frontend/src/components/layout/AppContent/TabContent.tsx frontend/src/App.tsx
git commit -m "feat(assistant): add assistant detail page routing"
```

---

### Task 8: Frontend — Install Fuse.js and add client-side fuzzy search

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install Fuse.js**

Run: `cd /home/yangyang/LambChat/frontend && npm install fuse.js`

- [ ] **Step 2: Verify installation**

Run: `cd /home/yangyang/LambChat/frontend && node -e "const Fuse = require('fuse.js'); console.log('Fuse.js version:', Fuse.default ? 'ESM' : 'CJS')"`
Expected: No errors, Fuse.js module loads successfully

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: add fuse.js dependency for assistant fuzzy search"
```

---

### Task 9: Frontend — Rewrite AssistantsPanel with new components

**Files:**
- Modify: `frontend/src/components/panels/AssistantsPanel.tsx`

- [ ] **Step 1: Rewrite AssistantsPanel**

This is the largest change. Replace the entire content of `frontend/src/components/panels/AssistantsPanel.tsx` with the new version that integrates:
- `CategoryFilter` bar below scope tabs
- `AssistantCard` with gradient headers
- `AssistantDetailPage` view (when an assistant is selected)
- Fuse.js client-side fuzzy search (instead of server-side search for instant filtering)
- Category field in create/edit form

Key changes from current code:
1. Add state: `selectedCategory`, `viewingAssistantId` (for detail page)
2. Add `category` to `FormState` type
3. Replace server-side `search` with local Fuse.js filtering
4. Use `AssistantCard` component instead of inline card JSX
5. When `viewingAssistantId` is set, render `AssistantDetailPage`
6. Add `CategoryFilter` between scope tabs and card grid
7. Use `useAssistants` with `category` param for server-side category filtering (combine with client-side Fuse.js for text search)
8. Add category dropdown to create/edit form

Here is the full replacement. Note: we keep the same imports structure but add the new ones, and restructure the JSX:

```typescript
import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bot,
  CopyPlus,
  Pencil,
  Plus,
  Save,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import Fuse from "fuse.js";
import toast from "react-hot-toast";

import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { useAssistants } from "../../hooks/useAssistants";
import { useAuth } from "../../hooks/useAuth";
import type {
  Assistant,
  AssistantCreate,
  AssistantListScope,
  AssistantUpdate,
  AssistantSelection,
} from "../../types";
import { EMPTY_ASSISTANT_SELECTION } from "../../types";
import { CategoryFilter } from "../assistant/CategoryFilter";
import { AssistantCard } from "../assistant/AssistantCard";
import { AssistantDetailPage } from "../assistant/AssistantDetailPage";
import { ASSISTANT_CATEGORIES } from "../assistant/categories";

type FormState = {
  name: string;
  description: string;
  tagsText: string;
  systemPrompt: string;
  avatarUrl: string;
  category: string;
};

const EMPTY_FORM: FormState = {
  name: "",
  description: "",
  tagsText: "",
  systemPrompt: "",
  avatarUrl: "",
  category: "general",
};

const inputCls =
  "w-full rounded-lg border border-stone-200 bg-white px-3.5 py-2.5 text-sm text-stone-900 outline-none transition-all duration-150 placeholder:text-stone-300 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 dark:border-stone-700 dark:bg-stone-800/80 dark:text-stone-100 dark:placeholder:text-stone-600 dark:focus:border-stone-500 dark:focus:ring-stone-800";

const selectCls =
  "w-full rounded-lg border border-stone-200 bg-white px-3.5 py-2.5 text-sm text-stone-900 outline-none transition-all duration-150 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 dark:border-stone-700 dark:bg-stone-800/80 dark:text-stone-100 dark:focus:border-stone-500 dark:focus:ring-stone-800";

export function AssistantsPanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [scope, setScope] = useState<AssistantListScope>("all");
  const [searchText, setSearchText] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [editingAssistant, setEditingAssistant] = useState<Assistant | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [deleteTarget, setDeleteTarget] = useState<Assistant | null>(null);
  const [viewingAssistantId, setViewingAssistantId] = useState<string | null>(null);
  const isAdmin = user?.roles?.includes("admin") ?? false;

  const {
    assistants,
    isLoading,
    isMutating,
    error,
    createAssistant,
    updateAssistant,
    deleteAssistant,
    cloneAssistant,
  } = useAssistants({
    scope,
    category: selectedCategory ?? undefined,
  });

  // Fuse.js for client-side text search
  const fuseRef = useRef(
    new Fuse<Assistant>([], {
      keys: ["name", "description", "system_prompt", "tags"],
      threshold: 0.4,
    }),
  );

  const visibleAssistants = useMemo(() => {
    const filtered = assistants.filter(
      (assistant) => assistant.scope !== "public" || assistant.is_active,
    );
    if (!searchText.trim()) return filtered;
    fuseRef.current.setCollection(filtered);
    return fuseRef.current.search(searchText).map((r) => r.item);
  }, [assistants, searchText]);

  const openCreateForm = () => {
    setIsCreating(true);
    setEditingAssistant(null);
    setForm(EMPTY_FORM);
  };

  const openEditForm = (assistant: Assistant) => {
    setIsCreating(false);
    setEditingAssistant(assistant);
    setForm({
      name: assistant.name,
      description: assistant.description,
      tagsText: assistant.tags.join(", "),
      systemPrompt: assistant.system_prompt,
      avatarUrl: assistant.avatar_url || "",
      category: assistant.category || "general",
    });
  };

  const closeForm = () => {
    setIsCreating(false);
    setEditingAssistant(null);
    setForm(EMPTY_FORM);
  };

  const parseTags = () =>
    form.tagsText
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);

  const handleSubmit = async () => {
    if (!form.name.trim() || !form.systemPrompt.trim()) {
      toast.error(
        t("assistants.validation", {
          defaultValue: "Name and system prompt are required.",
        }),
      );
      return;
    }

    const payload: AssistantCreate = {
      name: form.name.trim(),
      description: form.description.trim(),
      system_prompt: form.systemPrompt.trim(),
      tags: parseTags(),
      avatar_url: form.avatarUrl.trim() || null,
      category: form.category,
    };

    try {
      if (editingAssistant) {
        const updatePayload: AssistantUpdate = payload;
        await updateAssistant(editingAssistant.assistant_id, updatePayload);
        toast.success(
          t("assistants.updateSuccess", {
            defaultValue: "Assistant updated.",
          }),
        );
      } else {
        await createAssistant(payload);
        toast.success(
          t("assistants.createSuccess", {
            defaultValue: "Assistant created.",
          }),
        );
      }
      closeForm();
    } catch {
      toast.error(
        t("assistants.saveFailed", {
          defaultValue: "Failed to save assistant.",
        }),
      );
    }
  };

  const handleClone = async (assistant: Assistant) => {
    try {
      await cloneAssistant(assistant.assistant_id);
      toast.success(
        t("assistants.cloneSuccess", {
          defaultValue: "Assistant cloned to your library.",
        }),
      );
      setScope("all");
    } catch {
      toast.error(
        t("assistants.cloneFailed", {
          defaultValue: "Failed to clone assistant.",
        }),
      );
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteAssistant(deleteTarget.assistant_id);
      toast.success(
        t("assistants.deleteSuccess", {
          defaultValue: "Assistant deleted.",
        }),
      );
      setDeleteTarget(null);
      if (editingAssistant?.assistant_id === deleteTarget.assistant_id) {
        closeForm();
      }
    } catch {
      toast.error(
        t("assistants.deleteFailed", {
          defaultValue: "Failed to delete assistant.",
        }),
      );
    }
  };

  const handleView = (assistant: Assistant) => {
    setViewingAssistantId(assistant.assistant_id);
  };

  const handleStartChat = (assistant: Assistant) => {
    const selection: AssistantSelection = {
      assistantId: assistant.assistant_id,
      assistantName: assistant.name,
      assistantPromptSnapshot: assistant.system_prompt,
      avatarUrl: assistant.avatar_url,
    };
    // Store selection in localStorage so the chat tab can pick it up
    localStorage.setItem(
      "lambchat_pending_assistant_selection",
      JSON.stringify(selection),
    );
    navigate("/chat");
  };

  // Detail page view
  if (viewingAssistantId) {
    return (
      <div className="flex h-full flex-col bg-stone-50/50 dark:bg-[#0c0a09]">
        <AssistantDetailPage
          assistantId={viewingAssistantId}
          onBack={() => setViewingAssistantId(null)}
          onStartChat={handleStartChat}
          onViewAssistant={(id) => setViewingAssistantId(id)}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-stone-50/50 dark:bg-[#0c0a09]">
      <PanelHeader
        title={t("assistants.title", { defaultValue: "Assistants" })}
        subtitle={t("assistants.subtitle", {
          defaultValue:
            "Browse public presets, save your own personas, and inject them as session system prompts.",
        })}
        icon={<Sparkles />}
        searchValue={searchText}
        onSearchChange={setSearchText}
        searchPlaceholder={t("assistants.searchPlaceholder", {
          defaultValue: "Search assistants",
        })}
        actions={
          <button
            type="button"
            onClick={openCreateForm}
            className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-3.5 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-stone-700 hover:shadow dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
          >
            <Plus size={15} />
            {t("assistants.new", { defaultValue: "New Assistant" })}
          </button>
        }
      >
        {/* Scope tabs */}
        <div className="mt-3 flex flex-wrap gap-1.5">
          {[
            ["all", t("assistants.scopeAll", { defaultValue: "All" })],
            [
              "public",
              t("assistants.scopePublic", { defaultValue: "Marketplace" }),
            ],
            ["mine", t("assistants.scopeMine", { defaultValue: "My Library" })],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setScope(value as AssistantListScope)}
              className={`rounded-md px-3 py-1.5 text-[13px] font-medium transition-all duration-150 ${
                scope === value
                  ? "bg-stone-900 text-white shadow-sm dark:bg-white dark:text-stone-900"
                  : "text-stone-500 hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Category filter */}
        <div className="mt-3">
          <CategoryFilter
            selected={selectedCategory}
            onSelect={setSelectedCategory}
          />
        </div>
      </PanelHeader>

      <div className="flex-1 overflow-y-auto px-4 pb-6 pt-4 sm:px-6">
        {/* Create/Edit Form */}
        {(isCreating || editingAssistant) && (
          <section className="mb-6 overflow-hidden rounded-xl border border-stone-200/80 bg-white shadow-sm dark:border-stone-800/60 dark:bg-stone-900/80">
            <div className="flex items-center justify-between border-b border-stone-100 px-5 py-4 dark:border-stone-800/40">
              <div>
                <h2 className="text-[15px] font-semibold text-stone-900 dark:text-stone-50">
                  {editingAssistant
                    ? t("assistants.edit", {
                        defaultValue: "Edit Assistant",
                      })
                    : t("assistants.create", {
                        defaultValue: "Create Assistant",
                      })}
                </h2>
              </div>
              <button
                type="button"
                onClick={closeForm}
                className="rounded-md p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-200"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-4 p-5">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <span className="mb-1.5 block text-[12px] font-medium text-stone-600 dark:text-stone-300">
                    {t("assistants.name", { defaultValue: "Name" })}
                  </span>
                  <input
                    value={form.name}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        name: event.target.value,
                      }))
                    }
                    className={inputCls}
                    placeholder={t("assistants.namePlaceholder", {
                      defaultValue: "Research Planner",
                    })}
                  />
                </label>

                <label className="block">
                  <span className="mb-1.5 block text-[12px] font-medium text-stone-600 dark:text-stone-300">
                    {t("assistants.category", { defaultValue: "Category" })}
                  </span>
                  <select
                    value={form.category}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        category: event.target.value,
                      }))
                    }
                    className={selectCls}
                  >
                    {ASSISTANT_CATEGORIES.map((cat) => (
                      <option key={cat.id} value={cat.id}>
                        {cat.label}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="block">
                  <span className="mb-1.5 block text-[12px] font-medium text-stone-600 dark:text-stone-300">
                    {t("assistants.avatarUrl", { defaultValue: "Avatar URL" })}
                  </span>
                  <div className="flex items-center gap-2.5">
                    <input
                      value={form.avatarUrl}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          avatarUrl: event.target.value,
                        }))
                      }
                      className={inputCls}
                      placeholder="https://example.com/avatar.png"
                    />
                    <div className="size-10 shrink-0 overflow-hidden rounded-lg border border-stone-200 bg-stone-50 dark:border-stone-700 dark:bg-stone-800">
                      {form.avatarUrl ? (
                        <img
                          src={form.avatarUrl}
                          alt="Preview"
                          className="size-full object-cover"
                          onError={(e) => {
                            (e.target as HTMLImageElement).style.display =
                              "none";
                          }}
                        />
                      ) : (
                        <div className="flex size-full items-center justify-center text-stone-300 dark:text-stone-600">
                          <Sparkles size={14} />
                        </div>
                      )}
                    </div>
                  </div>
                </label>

                <label className="block">
                  <span className="mb-1.5 block text-[12px] font-medium text-stone-600 dark:text-stone-300">
                    {t("assistants.tags", { defaultValue: "Tags" })}
                  </span>
                  <input
                    value={form.tagsText}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        tagsText: event.target.value,
                      }))
                    }
                    className={inputCls}
                    placeholder={t("assistants.tagsPlaceholder", {
                      defaultValue: "planning, strategy, writing",
                    })}
                  />
                </label>

                <label className="block md:col-span-2">
                  <span className="mb-1.5 block text-[12px] font-medium text-stone-600 dark:text-stone-300">
                    {t("assistants.description", {
                      defaultValue: "Description",
                    })}
                  </span>
                  <textarea
                    value={form.description}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        description: event.target.value,
                      }))
                    }
                    rows={3}
                    className={`${inputCls} resize-none`}
                    placeholder={t("assistants.descriptionPlaceholder", {
                      defaultValue:
                        "Tell people what mindset or workflow this assistant is optimized for.",
                    })}
                  />
                </label>

                <label className="block md:col-span-2">
                  <span className="mb-1.5 block text-[12px] font-medium text-stone-600 dark:text-stone-300">
                    {t("assistants.systemPrompt", {
                      defaultValue: "System Prompt",
                    })}
                  </span>
                  <textarea
                    value={form.systemPrompt}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        systemPrompt: event.target.value,
                      }))
                    }
                    rows={10}
                    className="w-full resize-none rounded-lg border border-stone-200 bg-stone-950/95 px-4 py-3 font-mono text-[12.5px] leading-6 text-stone-200 outline-none transition-all dark:border-stone-700 focus:border-stone-400 focus:ring-2 focus:ring-stone-800 dark:focus:border-stone-500"
                    placeholder={t("assistants.promptPlaceholder", {
                      defaultValue:
                        "You are a strategic research partner. Break goals into decision-ready plans...",
                    })}
                  />
                </label>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={closeForm}
                  className="rounded-lg px-3.5 py-2 text-[13px] text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700 dark:text-stone-400 dark:hover:bg-stone-800 dark:hover:text-stone-200"
                >
                  {t("common.cancel", { defaultValue: "Cancel" })}
                </button>
                <button
                  type="button"
                  onClick={() => void handleSubmit()}
                  disabled={isMutating}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-stone-900 px-4 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-stone-900 dark:hover:bg-stone-200"
                >
                  <Save size={14} />
                  {editingAssistant
                    ? t("common.save", { defaultValue: "Save" })
                    : t("assistants.createAction", {
                        defaultValue: "Create",
                      })}
                </button>
              </div>
            </div>
          </section>
        )}

        {error && (
          <div className="mb-4 rounded-lg border border-rose-200/60 bg-rose-50 px-4 py-3 text-[13px] text-rose-600 dark:border-rose-900/30 dark:bg-rose-950/20 dark:text-rose-400">
            {error}
          </div>
        )}

        {isLoading ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <div
                key={index}
                className="h-64 animate-pulse overflow-hidden rounded-xl bg-white dark:bg-stone-900/60"
              >
                <div className="h-12 bg-stone-200 dark:bg-stone-700" />
                <div className="space-y-3 p-4">
                  <div className="h-4 w-2/3 rounded bg-stone-200 dark:bg-stone-700" />
                  <div className="h-3 w-full rounded bg-stone-100 dark:bg-stone-800" />
                  <div className="h-3 w-4/5 rounded bg-stone-100 dark:bg-stone-800" />
                </div>
              </div>
            ))}
          </div>
        ) : visibleAssistants.length === 0 ? (
          <div className="rounded-xl border border-dashed border-stone-300 bg-white/50 px-6 py-14 text-center dark:border-stone-700/50 dark:bg-stone-900/30">
            <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-gradient-to-br from-amber-50 to-orange-50 text-amber-500 dark:from-amber-900/30 dark:to-orange-900/20 dark:text-amber-400">
              <Bot size={22} />
            </div>
            <h3 className="mt-4 text-[15px] font-semibold text-stone-800 dark:text-stone-100">
              {t("assistants.emptyTitle", {
                defaultValue: "No assistants found",
              })}
            </h3>
            <p className="mt-1.5 text-[13px] text-stone-400 dark:text-stone-500">
              {selectedCategory || searchText
                ? t("assistants.emptyFiltered", {
                    defaultValue:
                      "No assistants match your current filters. Try adjusting your search or category.",
                  })
                : t("assistants.emptySubtitle", {
                    defaultValue:
                      "Try a different search, browse the marketplace, or create your own assistant preset.",
                  })}
            </p>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {visibleAssistants.map((assistant) => (
              <AssistantCard
                key={assistant.assistant_id}
                assistant={assistant}
                isAdmin={isAdmin}
                onClone={(a) => void handleClone(a)}
                onEdit={openEditForm}
                onDelete={setDeleteTarget}
                onView={handleView}
              />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onConfirm={() => void handleDelete()}
        onCancel={() => setDeleteTarget(null)}
        title={t("assistants.deleteConfirmTitle", {
          defaultValue: "Delete assistant?",
        })}
        message={t("assistants.deleteConfirmMessage", {
          defaultValue:
            "This will remove the assistant from your private library. Existing chat snapshots will stay unchanged.",
        })}
        confirmText={t("common.delete", { defaultValue: "Delete" })}
        cancelText={t("common.cancel", { defaultValue: "Cancel" })}
        variant="danger"
      />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/panels/AssistantsPanel.tsx
git commit -m "feat(assistant): rewrite AssistantsPanel with gradient cards, category filter, and detail view"
```

---

### Task 10: Frontend — Enhance AssistantSelector dropdown

**Files:**
- Modify: `frontend/src/components/assistant/AssistantSelector.tsx`

- [ ] **Step 1: Enhance AssistantSelector**

Replace the entire `AssistantSelector.tsx` with an enhanced version that includes:
- Wider dropdown (400px)
- Category quick-filter bar
- 4px left gradient bar on each option (using `nameToAccentColor`)
- Improved hover effect with `translateX(4px)`
- Search input at top of dropdown

Key changes:
1. Add `selectedCategory` state for dropdown filtering
2. Add `dropdownSearch` state
3. Group assistants by category, then by scope
4. Each option gets a left border gradient accent
5. Add category filter pills at top of dropdown
6. Fuse.js for local search filtering

Full replacement code for `frontend/src/components/assistant/AssistantSelector.tsx`:

```typescript
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Check, ChevronDown, Search, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import Fuse from "fuse.js";

import { useAssistants } from "../../hooks/useAssistants";
import type { Assistant, AssistantSelection } from "../../types";
import { nameToAccentColor } from "./gradientUtils";
import { getCategoryById, ASSISTANT_CATEGORIES } from "./categories";

interface AssistantSelectorProps {
  currentAssistantId: string;
  currentAssistantName: string;
  onSelectAssistant: (selection: AssistantSelection) => void;
}

export const AssistantSelector = memo(function AssistantSelector({
  currentAssistantId,
  currentAssistantName,
  onSelectAssistant,
}: AssistantSelectorProps) {
  const { t } = useTranslation();
  const { assistants, isLoading } = useAssistants({ scope: "all" });
  const [isOpen, setIsOpen] = useState(false);
  const [dropdownSearch, setDropdownSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const currentAssistant = useMemo(
    () =>
      assistants.find(
        (assistant) => assistant.assistant_id === currentAssistantId,
      ),
    [assistants, currentAssistantId],
  );

  const fuseRef = useRef(
    new Fuse<Assistant>([], {
      keys: ["name", "description", "tags"],
      threshold: 0.4,
    }),
  );

  const filteredAssistants = useMemo(() => {
    let items = assistants;
    if (selectedCategory) {
      items = items.filter(
        (a) => (a.category || "general") === selectedCategory,
      );
    }
    if (dropdownSearch.trim()) {
      fuseRef.current.setCollection(items);
      items = fuseRef.current.search(dropdownSearch).map((r) => r.item);
    }
    return items;
  }, [assistants, selectedCategory, dropdownSearch]);

  // Group by category
  const groupedByCategory = useMemo(() => {
    const groups = new Map<string, Assistant[]>();
    for (const assistant of filteredAssistants) {
      const cat = assistant.category || "general";
      if (!groups.has(cat)) groups.set(cat, []);
      groups.get(cat)!.push(assistant);
    }
    return groups;
  }, [filteredAssistants]);

  useEffect(() => {
    if (!isOpen) return;

    const handleOutsideClick = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [isOpen]);

  // Focus search input when dropdown opens
  useEffect(() => {
    if (isOpen && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [isOpen]);

  // Reset filters when dropdown closes
  const handleClose = useCallback(() => {
    setIsOpen(false);
    setDropdownSearch("");
    setSelectedCategory(null);
  }, []);

  const label =
    currentAssistantName ||
    currentAssistant?.name ||
    t("assistants.none", { defaultValue: "Default Assistant" });

  const hasAvatar = currentAssistant?.avatar_url;

  return (
    <div
      ref={containerRef}
      className="relative"
      onClick={(event) => event.stopPropagation()}
    >
      {/* Trigger button */}
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.06] px-2.5 py-1.5 text-sm backdrop-blur-sm transition-all duration-200 hover:border-white/20 hover:bg-white/[0.1] dark:border-stone-700/60 dark:bg-stone-800/40 dark:hover:border-stone-600 dark:hover:bg-stone-800/70"
      >
        {hasAvatar ? (
          <img
            src={currentAssistant!.avatar_url!}
            alt={label}
            className="size-5 shrink-0 rounded-full object-cover ring-1 ring-black/5 dark:ring-white/10"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <Sparkles size={14} className="shrink-0 text-amber-500/90 dark:text-amber-400/80" />
        )}
        <span className="max-w-[160px] truncate font-medium text-stone-700 dark:text-stone-200">
          {label}
        </span>
        <ChevronDown
          size={13}
          className={`shrink-0 text-stone-400 transition-transform duration-200 dark:text-stone-500 ${
            isOpen ? "rotate-180" : ""
          }`}
        />
      </button>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-[400px] origin-top-left animate-[scale-in_0.15s_ease-out] overflow-hidden rounded-xl border border-stone-200/80 bg-white/95 shadow-xl shadow-stone-900/10 backdrop-blur-xl dark:border-stone-700/60 dark:bg-stone-900/95 dark:shadow-stone-950/40">
          {/* Header + Search */}
          <div className="border-b border-stone-100 px-4 py-3 dark:border-stone-800/60">
            <p className="text-[13px] font-semibold text-stone-800 dark:text-stone-100">
              {t("assistants.selectorTitle", { defaultValue: "Choose Assistant" })}
            </p>
            <p className="mt-0.5 mb-2.5 text-[11px] leading-relaxed text-stone-400 dark:text-stone-500">
              {t("assistants.selectorSubtitle", {
                defaultValue:
                  "Switch the system prompt persona for this conversation.",
              })}
            </p>
            {/* Search input */}
            <div className="relative">
              <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500" />
              <input
                ref={searchInputRef}
                type="text"
                value={dropdownSearch}
                onChange={(e) => setDropdownSearch(e.target.value)}
                placeholder={t("assistants.searchPlaceholder", {
                  defaultValue: "Search...",
                })}
                className="w-full rounded-lg border border-stone-200 bg-stone-50 py-1.5 pl-8 pr-3 text-[12px] text-stone-800 outline-none transition-all placeholder:text-stone-400 focus:border-stone-300 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:border-stone-600"
              />
            </div>
          </div>

          {/* Category quick filter */}
          <div className="flex flex-wrap gap-1 border-b border-stone-100 px-4 py-2 dark:border-stone-800/60">
            <button
              type="button"
              onClick={() => setSelectedCategory(null)}
              className={`rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                selectedCategory === null
                  ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900"
                  : "text-stone-400 hover:bg-stone-100 hover:text-stone-600 dark:text-stone-500 dark:hover:bg-stone-800"
              }`}
            >
              All
            </button>
            {ASSISTANT_CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                type="button"
                onClick={() => setSelectedCategory(cat.id)}
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[10px] font-medium transition-colors ${
                  selectedCategory === cat.id
                    ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900"
                    : "text-stone-400 hover:bg-stone-100 hover:text-stone-600 dark:text-stone-500 dark:hover:bg-stone-800"
                }`}
              >
                <cat.icon size={10} strokeWidth={2} />
                {cat.label}
              </button>
            ))}
          </div>

          {/* Options list */}
          <div className="max-h-[320px] overflow-y-auto py-1">
            {/* Default option */}
            <button
              type="button"
              onClick={() => {
                onSelectAssistant({
                  assistantId: "",
                  assistantName: "",
                  assistantPromptSnapshot: "",
                });
                handleClose();
              }}
              className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors ${
                !currentAssistantId
                  ? "bg-amber-50/70 dark:bg-amber-500/10"
                  : "hover:bg-stone-50 dark:hover:bg-stone-800/40"
              }`}
            >
              <div className="flex size-8 items-center justify-center rounded-lg bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-400">
                <Bot size={15} strokeWidth={1.8} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium text-stone-800 dark:text-stone-100">
                  {t("assistants.none", { defaultValue: "Default Assistant" })}
                </div>
                <div className="text-[11px] text-stone-400 dark:text-stone-500">
                  {t("assistants.noneDescription", {
                    defaultValue:
                      "Use the base agent prompt without an extra assistant preset.",
                  })}
                </div>
              </div>
              {!currentAssistantId && (
                <Check size={15} className="shrink-0 text-amber-600 dark:text-amber-400" />
              )}
            </button>

            {isLoading ? (
              <div className="px-4 py-8 text-center text-[13px] text-stone-400 dark:text-stone-500">
                {t("common.loading", { defaultValue: "Loading..." })}
              </div>
            ) : filteredAssistants.length === 0 ? (
              <div className="px-4 py-8 text-center text-[13px] text-stone-400 dark:text-stone-500">
                {t("assistants.noResults", { defaultValue: "No results found." })}
              </div>
            ) : (
              Array.from(groupedByCategory.entries()).map(([catId, items]) => {
                const cat = getCategoryById(catId);
                return (
                  <div key={catId} className="px-3 pt-2 pb-1">
                    <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-stone-400 dark:text-stone-600">
                      {cat?.label || catId}
                    </p>
                    <div className="space-y-0.5">
                      {items.map((assistant) => (
                        <AssistantDropdownOption
                          key={assistant.assistant_id}
                          assistant={assistant}
                          isSelected={
                            assistant.assistant_id === currentAssistantId
                          }
                          onSelect={() => {
                            onSelectAssistant({
                              assistantId: assistant.assistant_id,
                              assistantName: assistant.name,
                              assistantPromptSnapshot: assistant.system_prompt,
                              avatarUrl: assistant.avatar_url,
                            });
                            handleClose();
                          }}
                        />
                      ))}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
});

function AssistantDropdownOption({
  assistant,
  isSelected,
  onSelect,
}: {
  assistant: {
    assistant_id: string;
    name: string;
    description: string;
    tags: string[];
    avatar_url?: string | null;
    cloned_from_assistant_id?: string | null;
    scope?: string;
  };
  isSelected: boolean;
  onSelect: () => void;
}) {
  const accentColor = nameToAccentColor(assistant.name);

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex w-full items-start gap-3 rounded-lg border-l-[3px] px-3 py-2 text-left transition-all duration-150 ${
        isSelected
          ? "border-l-amber-500 bg-amber-50/70 dark:border-l-amber-400 dark:bg-amber-500/10"
          : `border-l-transparent hover:border-l-[${accentColor}] hover:bg-stone-50 hover:translate-x-0.5 dark:hover:bg-stone-800/40`
      }`}
      style={!isSelected ? { borderLeftColor: accentColor } : undefined}
    >
      <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-amber-50 to-orange-50 text-amber-600 ring-1 ring-amber-100/50 dark:from-amber-900/30 dark:to-orange-900/20 dark:text-amber-400 dark:ring-amber-800/30">
        {assistant.avatar_url ? (
          <img
            src={assistant.avatar_url}
            alt={assistant.name}
            className="size-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <Sparkles size={14} strokeWidth={2} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[13px] font-medium text-stone-800 dark:text-stone-100">
            {assistant.name}
          </span>
          {assistant.cloned_from_assistant_id && (
            <span className="rounded bg-stone-100 px-1.5 py-px text-[9px] font-medium uppercase tracking-wide text-stone-400 dark:bg-stone-800 dark:text-stone-500">
              Clone
            </span>
          )}
        </div>
        <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-stone-400 dark:text-stone-500">
          {assistant.description || assistant.tags.join(" · ")}
        </p>
      </div>
      {isSelected && (
        <Check size={15} className="mt-1 shrink-0 text-amber-600 dark:text-amber-400" />
      )}
    </button>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/assistant/AssistantSelector.tsx
git commit -m "feat(assistant): enhance selector with category filter, search, and gradient accents"
```

---

### Task 11: Frontend — Wire up "Start Chat" from detail page to chat tab

**Files:**
- Modify: `frontend/src/components/layout/AppContent/index.tsx`
- Modify: `frontend/src/components/layout/AppContent/Header.tsx`

- [ ] **Step 1: Read pending assistant selection on chat mount**

In `frontend/src/components/layout/AppContent/index.tsx`, inside the `ChatAppContent` component, add logic to check for a pending assistant selection from localStorage (set by the detail page's "Start Chat" button). Add this effect after the existing `useEffect` hooks:

```typescript
// Handle pending assistant selection from detail page
useEffect(() => {
  const pending = localStorage.getItem("lambchat_pending_assistant_selection");
  if (pending) {
    localStorage.removeItem("lambchat_pending_assistant_selection");
    try {
      const selection: AssistantSelection = JSON.parse(pending);
      if (selection.assistantId) {
        setAssistantSelection(selection);
      }
    } catch {
      // Ignore parse errors
    }
  }
}, [setAssistantSelection]);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/AppContent/index.tsx
git commit -m "feat(assistant): wire up Start Chat from detail page to chat session"
```

---

### Task 12: Build verification and final checks

**Files:**
- No new files

- [ ] **Step 1: Run TypeScript type check**

Run: `cd /home/yangyang/LambChat/frontend && npx tsc --noEmit`
Expected: No type errors

- [ ] **Step 2: Run frontend build**

Run: `cd /home/yangyang/LambChat/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Run backend tests**

Run: `cd /home/yangyang/LambChat && python -m pytest tests/api/routes/test_assistant_routes.py tests/infra/assistant/ -v`
Expected: All tests pass

- [ ] **Step 4: Run frontend tests**

Run: `cd /home/yangyang/LambChat/frontend && npx tsx --test src/services/api/assistant.test.ts`
Expected: All tests pass

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address build/type issues from assistant UI optimization"
```
