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
          <span className="text-10 sm:text-11 font-bold tracking-[0.16em] uppercase text-stone-400 dark:text-stone-500">
            {label}
          </span>
          <span className="block w-8 h-px bg-gradient-to-l from-transparent to-stone-300/40 dark:to-stone-600/25" />
        </div>
      )}
      <h2 className="text-[1.65rem] sm:text-3xl lg:text-4xl font-extrabold font-serif tracking-[-0.025em] text-stone-900 dark:text-stone-50 mb-5 leading-[1.15] bg-gradient-to-b from-stone-900 via-stone-800 to-stone-600 dark:from-stone-50 dark:via-stone-200 dark:to-stone-400 bg-clip-text text-transparent">
        {title}
      </h2>
      <p className="blog-prose text-stone-400 dark:text-stone-500 max-w-md lg:max-w-lg mx-auto text-sm sm:text-15 leading-[1.8]">
        {description}
      </p>
    </div>
  );
}
