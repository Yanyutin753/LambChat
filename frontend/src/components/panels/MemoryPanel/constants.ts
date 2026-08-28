export const TYPE_OPTIONS_LIST = [
  { value: "user", labelKey: "memory.type.user" },
  { value: "feedback", labelKey: "memory.type.feedback" },
  { value: "project", labelKey: "memory.type.project" },
  { value: "reference", labelKey: "memory.type.reference" },
];

export const TYPE_STYLES: Record<string, string> = {
  user: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  feedback:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
  project:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  reference:
    "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

export const TYPE_DOTS: Record<string, string> = {
  user: "bg-blue-500",
  feedback: "bg-amber-500",
  project: "bg-emerald-500",
  reference: "bg-purple-500",
};

export const TYPE_OPTIONS = [
  { value: "", labelKey: "memory.allTypes" },
  { value: "user", labelKey: "memory.type.user" },
  { value: "feedback", labelKey: "memory.type.feedback" },
  { value: "project", labelKey: "memory.type.project" },
  { value: "reference", labelKey: "memory.type.reference" },
] as const;

export const SOURCE_OPTIONS = [
  { value: "", labelKey: "memory.allSources" },
  { value: "manual", labelKey: "memory.source.manual" },
  { value: "auto_retained", labelKey: "memory.source.auto_retained" },
  { value: "imported", labelKey: "memory.source.imported" },
  { value: "consolidated", labelKey: "memory.source.consolidated" },
  { value: "self_evolved", labelKey: "memory.source.selfEvolved" },
] as const;

export const SOURCE_OPTIONS_LIST = [
  { value: "manual", labelKey: "memory.source.manual" },
  { value: "auto_retained", labelKey: "memory.source.auto_retained" },
  { value: "imported", labelKey: "memory.source.imported" },
  { value: "consolidated", labelKey: "memory.source.consolidated" },
  { value: "self_evolved", labelKey: "memory.source.selfEvolved" },
];

export const SOURCE_STYLES: Record<string, string> = {
  manual: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-300",
  auto_retained:
    "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300",
  imported: "bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300",
  consolidated:
    "bg-gray-100 text-gray-600 dark:bg-gray-800/40 dark:text-gray-400",
  self_evolved:
    "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
};

export const SOURCE_DOTS: Record<string, string> = {
  manual: "bg-sky-500",
  auto_retained: "bg-indigo-500",
  imported: "bg-teal-500",
  consolidated: "bg-gray-400",
  self_evolved: "bg-rose-500",
};

export const PAGE_SIZE = 20;
