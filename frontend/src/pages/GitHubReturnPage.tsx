import { useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { apiClient } from '@/api/client';
import { Button } from '@/components/ui/button';
import { errorText } from '@/components/shared/QueryState';
import { githubReturnPath } from '@/lib/githubReturn';
import { githubTabAckKey, githubTabChannel, githubTabResultKey, validGitHubFlowId, type GitHubTabResult } from '@/lib/githubTab';

export function GitHubReturnPage() {
  const [params] = useSearchParams(); const {getToken} = useAuth();
  const id = params.get('github_flow'); const ticket = params.get('github_ticket');
  const returnTo = githubReturnPath(params.get('workspace_return'));
  const complete = useQuery({queryKey: ['github-complete', ticket], enabled: Boolean(ticket), retry: false, staleTime: Infinity,
    queryFn: async () => { const token = await getToken(); return apiClient.post('/api/auth/github/complete', {ticket}, {headers: token ? {Authorization: `Bearer ${token}`} : {}}); }});
  const pending = Boolean(ticket && complete.isPending);
  const error = params.get('github_error') || (complete.error ? errorText(complete.error) : '');
  const notice = params.get('github_notice') || '';
  const hasResult = Boolean(ticket || error || notice || params.has('github_connected'));
  const sent = useRef(false);
  useEffect(() => {
    if (!validGitHubFlowId(id) || pending || !hasResult) return;
    let channel: BroadcastChannel | null = null;
    const close = () => {
      try { localStorage.removeItem(githubTabResultKey(id)); localStorage.removeItem(githubTabAckKey(id)); } catch { /* Optional fallback storage. */ }
      window.close();
    };
    const onStorage = (event: StorageEvent) => { if (event.key === githubTabAckKey(id) && event.newValue === id) close(); };
    window.addEventListener('storage', onStorage);
    if (typeof BroadcastChannel !== 'undefined') {
      channel = new BroadcastChannel(githubTabChannel(id));
      channel.onmessage = event => { if (event.data?.kind === 'ack' && event.data.flowId === id) close(); };
    }
    const result: GitHubTabResult = {kind: 'result', flowId: id, error: error || undefined, notice: notice || undefined, expires: Date.now() + 1_200_000};
    channel?.postMessage(result);
    try { localStorage.setItem(githubTabResultKey(id), JSON.stringify(result)); } catch { /* The channel does not need localStorage. */ }
    if (ticket && complete.isSuccess && !sent.current) {
      sent.current = true; void apiClient.post('/api/metrics', {event: 'connection_completed'}).catch(() => {});
    }
    return () => { channel?.close(); window.removeEventListener('storage', onStorage); };
  }, [id, pending, hasResult, error, notice, ticket, complete.isSuccess]);
  return <main className="mx-auto flex min-h-screen max-w-xl items-center p-6"><section className="panel page-stack w-full">
    <div className="flex items-center gap-3">{pending ? <Loader2 className="animate-spin" aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}<h1>{pending ? 'Completing GitHub connection…' : error ? 'GitHub needs attention' : hasResult ? 'GitHub setup finished' : 'Return to your workspace'}</h1></div>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <p>{pending ? 'Keep this tab open while DevReason verifies your account.' : 'Your original DevReason tab refreshes repository access automatically. You can close this tab.'}</p>
    <div className="flex flex-wrap gap-3"><Button disabled={pending} onClick={() => window.close()}>Close this tab</Button><Button asChild variant="outline"><Link to={returnTo}>Open workspace here</Link></Button></div>
  </section></main>;
}
