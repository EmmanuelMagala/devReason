type ClerkSession = {
  getToken: () => Promise<string | null>;
};

type ClerkWindow = Window & {
  Clerk?: {
    session?: ClerkSession;
  };
};

let tokenProvider: (() => Promise<string | null>) | null = null;
export function setTokenProvider(provider: typeof tokenProvider) { tokenProvider = provider; }

export async function getClerkToken() {
  if (typeof window === "undefined") {
    return null;
  }
  const clerk = window as ClerkWindow;
  const provider = tokenProvider ?? clerk.Clerk?.session?.getToken?.bind(clerk.Clerk.session);
  if (!provider) return null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      provider(),
      new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error('Sign-in verification took too long. Please retry.')), 10_000); }),
    ]);
  } finally { clearTimeout(timer); }
}
