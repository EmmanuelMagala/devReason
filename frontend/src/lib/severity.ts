import type { Severity } from "@/types";

export const severityConfig: Record<
  Severity,
  { label: string; className: string; dotClassName: string }
> = {
  critical: {
    label: "Critical",
    className: "border-red-200 bg-red-50 text-red-700",
    dotClassName: "bg-red-500",
  },
  high: {
    label: "High",
    className: "border-orange-200 bg-orange-50 text-orange-700",
    dotClassName: "bg-orange-500",
  },
  medium: {
    label: "Medium",
    className: "border-amber-200 bg-amber-50 text-amber-700",
    dotClassName: "bg-amber-500",
  },
  low: {
    label: "Low",
    className: "border-sky-200 bg-sky-50 text-sky-700",
    dotClassName: "bg-sky-500",
  },
};

export function sortBySeverity<T extends { severity: Severity }>(items: T[]) {
  const order = { critical: 0, high: 1, medium: 2, low: 3 };
  return [...items].sort(
    (left, right) => order[left.severity] - order[right.severity],
  );
}
