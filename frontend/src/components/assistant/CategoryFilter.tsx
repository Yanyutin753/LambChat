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
