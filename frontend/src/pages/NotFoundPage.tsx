import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        404
      </p>
      <h1 className="text-4xl font-semibold">Page not found</h1>
      <p className="max-w-md text-muted-foreground">
        This route is not part of the current frontend build.
      </p>
      <Button asChild>
        <Link to="/">Return to dashboard</Link>
      </Button>
    </div>
  );
}
