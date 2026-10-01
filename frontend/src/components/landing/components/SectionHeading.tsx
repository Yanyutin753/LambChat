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
    <div data-reveal className="public-section-heading">
      <div>
        {label && <p className="public-eyebrow">{label}</p>}
        <h2 className="font-serif">{title}</h2>
      </div>
      <p className="blog-prose">{description}</p>
    </div>
  );
}
