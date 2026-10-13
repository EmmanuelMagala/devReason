import { cn } from "@/lib/cn";
import type { ReviewStatus } from "@/types";

const statusClasses: Record<ReviewStatus, string> = {
  pending: "bg-slate-100 text-slate-700",
  running: "bg-blue-100 text-blue-700",
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  partial: "bg-amber-100 text-amber-900",
  cancelled: "bg-slate-100 text-slate-700",
};

export function StatusPill({ status }: { status: ReviewStatus }) {
  return (
    <span
      className={cn(
        "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
        statusClasses[status],
      )}
    >
      {status}
    </span>
  );
}
