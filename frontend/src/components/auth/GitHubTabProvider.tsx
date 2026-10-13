import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { useQueryClient } from '@tanstack/react-query';
import { workspaceApi } from '@/api/workspace';
import { errorText } from '@/components/shared/QueryState';
import { currentGitHubReturn, githubReturnPath, rememberGitHubReturn } from '@/lib/githubReturn';
import { GitHubTabContext, githubTabChannel, githubTabAckKey, githubTabResultKey, parseGitHubTabResult, readGitHubTabFlow, readGitHubTabResult, saveGitHubTabFlow, type GitHubTabFlow, type GitHubTabResult } from '@/lib/githubTab';

export function GitHubTabProvider({children}: {children: ReactNode}) {
  const {userId} = useAuth(); const qc = useQueryClient();
  const [flow, setFlow] = useState<GitHubTabFlow | null>(() => readGitHubTabFlow(userId));
  const [pending, setPending] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(Boolean(flow));
  const [error, setError] = useState(''); const [message, setMessage] = useState('');
  const popup = useRef<Window | null>(null); const opening = useRef(false);
  const syncing = useRef<Promise<void> | null>(null);
  const lastResult = useRef<string | null>(null);
  function store(next: GitHubTabFlow | null) { saveGitHubTabFlow(next); setFlow(next); }
  function dismiss() { store(null); popup.current = null; setWaiting(false); setMessage(''); setError(''); }

  async function refreshWorkspace() {
    if (syncing.current) {
      await syncing.current;
      // One follow-up sees changes made while the earlier request was running.
      if (syncing.current) return syncing.current;
    }
    const work = (async () => {
      setError(''); setMessage('Refreshing GitHub repository access…');
      try {
        const status = await qc.fetchQuery({queryKey: ['github-status'], queryFn: workspaceApi.status, staleTime: 0, retry: false});
        if (status.connections.some(c => c.status === 'connected')) {
          const signature = status.connections.map(c => c.id + c.status).join(',');
          await qc.fetchQuery({queryKey: ['github-refresh', signature], queryFn: workspaceApi.refresh, staleTime: 0, retry: false});
          // Refresh can mark a connection revoked or expired on the server.
          await qc.invalidateQueries({queryKey: ['github-status']});
        }
        await qc.invalidateQueries({predicate: query => ['repo-browse', 'repo', 'pulls', 'branches', 'scope'].includes(String(query.queryKey[0]))});
        setMessage('GitHub repository access refreshed.');
      } catch (cause) { setError(errorText(cause)); setMessage(''); }
    })();
    syncing.current = work;
    try { await work; } finally { syncing.current = null; }
  }

  async function run(key: string, action: (callbackPath: string) => Promise<string>, returnTo = currentGitHubReturn()) {
    if (opening.current || waiting || !userId) return;
    // Open synchronously inside the click, before the token/API request awaits.
    const tab = window.open('about:blank', '_blank');
    if (!tab) { setError('Your browser blocked the GitHub tab. Allow new tabs for DevReason, then try again.'); return; }
    tab.opener = null; // GitHub cannot navigate or inspect the original workspace.
    tab.document.title = 'Opening GitHub';
    tab.document.body.textContent = 'Opening GitHub… Keep DevReason open in the original tab.';
    popup.current = tab; opening.current = true; setPending(key); setWaiting(true); setError(''); setMessage('');
    const next = {id: crypto.randomUUID(), accountId: userId, key, returnTo: githubReturnPath(returnTo), expires: Date.now() + 1_200_000};
    const callbackPath = '/github/return?github_flow=' + next.id + '&workspace_return=' + encodeURIComponent(next.returnTo);
    store(next);
    try {
      // The server cookie normally restores state. This also covers callbacks
      // without state, without exposing a token to the original tab.
      saveGitHubTabFlow(null, tab.sessionStorage);
      rememberGitHubReturn(callbackPath, tab.sessionStorage);
      const value = await action(callbackPath);
      if (!value || typeof value !== 'string') throw new Error('GitHub did not return a connection link. Please try again.');
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin && (url.protocol !== 'https:' || url.hostname !== 'github.com')) throw new Error('GitHub returned an invalid connection link. Please try again.');
      if (tab.closed) throw new Error('The GitHub tab was closed before it opened. Please try again.');
      tab.location.replace(url.href);
    } catch (cause) {
      tab.close(); popup.current = null; store(null); setWaiting(false); setError(errorText(cause));
    } finally { opening.current = false; setPending(null); }
  }

  useEffect(() => {
    if (!flow || flow.accountId !== userId) return;
    let disposed = false; let wasAway = !document.hasFocus() || document.visibilityState === 'hidden'; let focusTimer: number | undefined;
    const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(githubTabChannel(flow.id));
    const receive = async (result: GitHubTabResult) => {
      if (disposed || lastResult.current === flow.id) return;
      lastResult.current = flow.id;
      // Signals only ask for a refresh. Signed-in API calls verify all access.
      await refreshWorkspace();
      if (disposed) return;
      if (result.error) { setError(result.error); setMessage(''); }
      else if (result.notice) setMessage(result.notice);
      channel?.postMessage({kind: 'ack', flowId: flow.id});
      try { localStorage.setItem(githubTabAckKey(flow.id), flow.id); localStorage.removeItem(githubTabResultKey(flow.id)); } catch { /* BroadcastChannel handles the normal path. */ }
      store(null); popup.current = null; setWaiting(false);
    };
    if (channel) channel.onmessage = event => { const result = parseGitHubTabResult(event.data, flow.id); if (result) void receive(result); };
    const onStorage = (event: StorageEvent) => {
      if (event.key !== githubTabResultKey(flow.id) || !event.newValue) return;
      try { const result = parseGitHubTabResult(JSON.parse(event.newValue), flow.id); if (result) void receive(result); } catch { /* Ignore malformed or unrelated messages. */ }
    };
    const onReturn = () => {
      if (document.visibilityState !== 'visible' || opening.current || !wasAway || lastResult.current === flow.id) return;
      wasAway = false; window.clearTimeout(focusTimer);
      focusTimer = window.setTimeout(() => {
        const result = readGitHubTabResult(flow.id);
        if (result) { void receive(result); return; }
        void refreshWorkspace();
        // COOP can sever a window reference. Retain correlation for a late
        // callback even when its proxy reports closed; a refresh proves no grant.
        if (popup.current?.closed) { popup.current = null; setWaiting(false); }
      }, 150);
    };
    const onAway = () => { wasAway = true; };
    const onVisibility = () => { if (document.visibilityState === 'hidden') onAway(); else onReturn(); };
    window.addEventListener('storage', onStorage); window.addEventListener('focus', onReturn); window.addEventListener('blur', onAway);
    document.addEventListener('visibilitychange', onVisibility);
    const saved = readGitHubTabResult(flow.id); if (saved) void receive(saved);
    const timer = window.setInterval(() => {
      if (Date.now() > flow.expires) { dismiss(); return; }
      if (!opening.current && lastResult.current !== flow.id && popup.current?.closed && document.visibilityState === 'visible') { popup.current = null; setWaiting(false); void refreshWorkspace(); }
    }, 750);
    return () => {
      disposed = true; channel?.close(); window.clearInterval(timer); window.clearTimeout(focusTimer);
      window.removeEventListener('storage', onStorage); window.removeEventListener('focus', onReturn); window.removeEventListener('blur', onAway);
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // The flow owns these listeners; the query client is scoped to the account.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flow, userId, qc]);

  return <GitHubTabContext.Provider value={{pending, waiting, busy: Boolean(pending) || waiting, activeKey: flow?.key || null, error, message, run, dismiss, retry: () => { void refreshWorkspace(); }}}>{children}</GitHubTabContext.Provider>;
}
