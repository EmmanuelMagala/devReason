// Navigation intent only. Authorization remains bound and verified on the server.
const storageKey = 'devreason:github-return';
const transient = ['github_ticket', 'github_connected', 'github_notice', 'github_error', 'github_return', 'return_to'];

export function githubReturnPath(value?: string | null): string {
  const fallback = '/repositories';
  if (!value || !value.startsWith('/') || value.startsWith('//') || [...value].some(char => char === '\\' || char.charCodeAt(0) < 33)) return fallback;
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin) return fallback;
    for (const name of transient) url.searchParams.delete(name);
    return url.pathname + url.search + url.hash;
  } catch { return fallback; }
}

export function currentGitHubReturn(): string {
  return githubReturnPath(window.location.pathname + window.location.search + window.location.hash);
}

export function githubSettingsLink(): string {
  return '/settings/integrations?return_to=' + encodeURIComponent(currentGitHubReturn());
}

export function rememberGitHubReturn(path: string, storage?: Storage) {
  try { (storage ?? sessionStorage).setItem(storageKey, JSON.stringify({path: githubReturnPath(path), expires: Date.now() + 600_000})); } catch { /* Storage may be disabled. Server state still preserves the return path. */ }
}

export function takeGitHubReturn(): string | null {
  try {
    const raw = sessionStorage.getItem(storageKey); sessionStorage.removeItem(storageKey);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    return saved.expires > Date.now() && typeof saved.path === 'string' ? githubReturnPath(saved.path) : null;
  } catch { return null; }
}
