import { ArrowUp, ArrowDown } from "lucide-react";
import type { SortOrder } from "../types";

export function SortIcon({
  order,
  className,
}: {
  order: SortOrder;
  className?: string;
}) {
  return order === "desc" ? (
    <ArrowDown size={14} className={className} />
  ) : (
    <ArrowUp size={14} className={className} />
  );
}
