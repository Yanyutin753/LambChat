export function BackIcon({
  size = 16,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 1024 1024"
      fill="currentColor"
      className={className}
    >
      <path d="M342.99904 549.23264a36.864 36.864 0 0 1 0.08192-52.0192l285.696-285.696a36.864 36.864 0 1 1 52.14208 52.10112l-259.6864 259.72736 259.76832 261.69344a36.864 36.864 0 0 1-52.30592 51.93728L342.99904 549.2736z" />
    </svg>
  );
}
