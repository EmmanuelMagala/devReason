import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { LoadingSpinner } from "@/components/shared/LoadingSpinner";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  const location = useLocation();

  if (!isLoaded) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner className="h-10 w-10" />
      </div>
    );
  }

  if (!isSignedIn) {
    return <Navigate replace to={`/sign-in?redirect_url=${encodeURIComponent(location.pathname + location.search)}`} />;
  }

  return <>{children}</>;
}
