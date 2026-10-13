import { ClerkProvider, useAuth } from "@clerk/clerk-react";
import { useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { router } from "@/router";

const publishableKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

function getClerkConfigError(key: string | undefined) {
  if (!key?.trim()) {
    return "Missing VITE_CLERK_PUBLISHABLE_KEY.";
  }

  if (key.includes("your_key_here")) {
    return "VITE_CLERK_PUBLISHABLE_KEY is still using the placeholder value.";
  }

  if (!/^pk_(test|live)_[A-Za-z0-9]+$/.test(key)) {
    return "VITE_CLERK_PUBLISHABLE_KEY does not match Clerk's publishable key format.";
  }

  return null;
}

const clerkConfigError = getClerkConfigError(publishableKey);

function createQueryClient(accountId?: string | null) { return new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 60_000,
      meta: {accountId},
    },
  },
}); }

function AccountWorkspace() {
  const {userId} = useAuth();
  const client = useMemo(() => createQueryClient(userId), [userId]);
  return <QueryClientProvider client={client}><RouterProvider key={userId || 'signed-out'} router={router} /></QueryClientProvider>;
}

function App() {
  if (clerkConfigError) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 py-10">
        <div className="surface-glow w-full max-w-2xl rounded-[28px] border bg-card/95 p-8 text-card-foreground">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-devreason-coral">
            Clerk Setup Required
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">
            Frontend auth is not configured yet.
          </h1>
          <p className="mt-4 text-sm text-muted-foreground">
            {clerkConfigError}
          </p>
          <div className="mt-6 rounded-2xl bg-muted/70 p-4 font-mono text-sm text-foreground">
            <p>frontend/.env.local</p>
            <p className="mt-2">VITE_CLERK_PUBLISHABLE_KEY=pk_test_...</p>
            <p>VITE_API_URL=http://localhost:8000</p>
          </div>
          <ol className="mt-6 list-decimal space-y-2 pl-5 text-sm text-muted-foreground">
            <li>Copy the real publishable key from the Clerk dashboard.</li>
            <li>Replace the placeholder value in frontend/.env.local.</li>
            <li>
              Restart the Vite dev server so the new env value is picked up.
            </li>
          </ol>
        </div>
      </div>
    );
  }

  return (
    <ClerkProvider publishableKey={publishableKey} afterSignOutUrl="/sign-in">
      <AccountWorkspace />
    </ClerkProvider>
  );
}

export default App;
