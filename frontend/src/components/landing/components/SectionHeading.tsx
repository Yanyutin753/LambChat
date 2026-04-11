interface SectionHeadingProps {
  label?: string;
  title: string;
  description: string;
}

export function SectionHeading({
  label,
  title,
  description,
}: SectionHeadingProps) {
  return (
    <div data-reveal className="text-center mb-14 sm:mb-18 lg:mb-20 px-2">
      {label && (
        <div className="flex items-center justify-center gap-3 mb-6 sm:mb-7">
          <span className="block w-8 h-px bg-gradient-to-r from-transparent to-stone-300/40 dark:to-stone-600/25" />
          <span className="text-[10px] sm:text-[11px] font-bold tracking-[0.16em] uppercase text-stone-400 dark:text-stone-500">
            {label}
          </span>
          <span className="block w-8 h-px bg-gradient-to-l from-transparent to-stone-300/40 dark:to-stone-600/25" />
        </div>
      )}
      <h2 className="text-[1.65rem] sm:text-3xl lg:text-4xl font-extrabold font-serif tracking-[-0.025em] text-stone-900 dark:text-stone-50 mb-5 leading-[1.15]">
        {title}
      </h2>
      <p className="blog-prose text-stone-400 dark:text-stone-500 max-w-md mx-auto text-sm sm:text-[15px] leading-[1.8]">
        {description}
      </p>
    </div>
  );
}
