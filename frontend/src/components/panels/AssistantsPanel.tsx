import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Fuse from "fuse.js";
import { Bot, Plus, Save, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";

import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { CategoryFilter } from "../assistant/CategoryFilter";
import { AssistantCard } from "../assistant/AssistantCard";
import { AssistantDetailPage } from "../assistant/AssistantDetailPage";
import { ASSISTANT_CATEGORIES } from "../assistant/categories";
import { useAssistants } from "../../hooks/useAssistants";
import { useAuth } from "../../hooks/useAuth";
import type {
  Assistant,
  AssistantCreate,
  AssistantListScope,
  AssistantUpdate,
} from "../../types";

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
  const { user } = useAuth();
  const navigate = useNavigate();
  const [scope, setScope] = useState<AssistantListScope>("all");
  const [searchText, setSearchText] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [viewingAssistantId, setViewingAssistantId] = useState<string | null>(
    null,
  );
  const [editingAssistant, setEditingAssistant] = useState<Assistant | null>(
    null,
  );
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [deleteTarget, setDeleteTarget] = useState<Assistant | null>(null);
  const isAdmin = user?.roles?.includes("admin") ?? false;

  const fuseRef = useRef(
    new Fuse<Assistant>([], {
      keys: ["name", "description", "system_prompt", "tags"],
      threshold: 0.4,
    }),
  );

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

  const visibleAssistants = useMemo(() => {
    let filtered = assistants.filter(
      (assistant) => assistant.scope !== "public" || assistant.is_active,
    );
    if (searchText.trim()) {
      fuseRef.current.setCollection(filtered);
      filtered = fuseRef.current.search(searchText.trim()).map((r) => r.item);
    }
    return filtered;
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
      category: assistant.category ?? "general",
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

  const handleStartChat = (assistant: Assistant) => {
    const selection = {
      assistantId: assistant.assistant_id,
      assistantName: assistant.name,
      assistantPromptSnapshot: assistant.system_prompt,
      avatarUrl: assistant.avatar_url,
    };
    localStorage.setItem(
      "lambchat_pending_assistant_selection",
      JSON.stringify(selection),
    );
    navigate("/chat");
  };

  // Detail page view
  if (viewingAssistantId) {
    return (
      <div className="flex h-full min-h-0 flex-col bg-stone-50/50 dark:bg-[#0c0a09]">
        <AssistantDetailPage
          assistantId={viewingAssistantId}
          onBack={() => setViewingAssistantId(null)}
          onStartChat={handleStartChat}
          onViewAssistant={(id) => setViewingAssistantId(id)}
        />
      </div>
    );
  }

  const hasActiveFilters =
    selectedCategory !== null || searchText.trim() !== "";

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

        <div className="mt-2">
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
                <p className="mt-0.5 text-[12px] text-stone-400 dark:text-stone-500">
                  {t("assistants.formHint", {
                    defaultValue:
                      "Phase 1 keeps it simple: we only persist the system prompt and display metadata.",
                  })}
                </p>
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
                className="animate-pulse overflow-hidden rounded-xl bg-stone-100 dark:bg-stone-800/40"
              >
                <div className="h-12 bg-stone-200 dark:bg-stone-700/60" />
                <div className="p-4 space-y-3">
                  <div className="h-4 w-3/4 rounded bg-stone-200 dark:bg-stone-700/60" />
                  <div className="h-3 w-full rounded bg-stone-200 dark:bg-stone-700/60" />
                  <div className="h-3 w-2/3 rounded bg-stone-200 dark:bg-stone-700/60" />
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
              {hasActiveFilters
                ? t("assistants.noMatchTitle", {
                    defaultValue: "No assistants match your filters",
                  })
                : t("assistants.emptyTitle", {
                    defaultValue: "No assistants found",
                  })}
            </h3>
            <p className="mt-1.5 text-[13px] text-stone-400 dark:text-stone-500">
              {hasActiveFilters
                ? t("assistants.noMatchSubtitle", {
                    defaultValue:
                      "Try adjusting your search or category filter, or browse the marketplace.",
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
                onClone={handleClone}
                onEdit={openEditForm}
                onDelete={(a) => setDeleteTarget(a)}
                onView={(a) => setViewingAssistantId(a.assistant_id)}
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
