import { Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";

export function LoadingSpinner({ className }: { className?: string }) {
  return (
    <Loader2 className={cn("animate-spin text-muted-foreground", className)} />
  );
}
