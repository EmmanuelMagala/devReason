import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { GitBranch, CheckCircle2, ExternalLink, Loader2 } from 'lucide-react';
import { workspaceApi } from '@/api/workspace';
import { useGitHubConnection } from '@/hooks/useGitHubConnection';
import { QueryState, errorText } from '@/components/shared/QueryState';
import { Button } from '@/components/ui/button';
import { currentGitHubReturn, githubReturnPath } from '@/lib/githubReturn';
import { useGitHubAction } from '@/hooks/useGitHubAction';

export function IntegrationsPage() {
  const {status, refresh} = useGitHubConnection(false, true); const [params] = useSearchParams(); const github = useGitHubAction(); const qc = useQueryClient();
  const returnTo = params.has('return_to') ? githubReturnPath(params.get('return_to')) : currentGitHubReturn();
  const disconnect = useMutation({mutationFn: workspaceApi.disconnect, onSuccess: () => { void qc.invalidateQueries({queryKey: ['github-status']}); void qc.invalidateQueries({queryKey: ['repo-browse']}); }});
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">Settings</p><h1>GitHub integration</h1><p>Connect accounts and choose which repositories DevReason can review.</p></div></div>
    {params.has('return_to') && <Link className="text-sm text-primary" to={returnTo}>← Back to your workspace</Link>}
    <section className="panel page-stack"><div className="flex items-center gap-3"><GitBranch size={28} /><div><h2>GitHub</h2><p className="text-sm text-muted-foreground">Your account access and the App’s repository permissions are verified together.</p></div></div><QueryState loading={status.isPending} error={status.error || refresh.error} retry={() => { void status.refetch(); void refresh.refetch(); }} />
      {status.data && !status.data.configured && <div role="status" className="notice">GitHub connection is awaiting administrator configuration. Your existing reports remain available.</div>}
      <p className="text-sm text-muted-foreground">GitHub opens in a new tab. Save your changes there, then close that tab or switch back here. DevReason refreshes repository access automatically and keeps your current page.</p>
      {status.data?.connections.map(c => <div key={c.id} className="connection-row"><div className="flex-1"><h3 className="flex items-center gap-2">{c.status === 'connected' && <CheckCircle2 size={17} className="text-emerald-700" />}@{c.login}</h3><p className="text-sm text-muted-foreground">{c.status === 'connected' ? 'Connected' : 'Access expired or revoked. Reconnect to continue.'}</p></div><Button variant="outline" disabled={github.busy || disconnect.isPending || c.status !== 'connected'} aria-busy={github.pending === `grant:${c.id}`} onClick={() => void github.run(`grant:${c.id}`, path => workspaceApi.grant(c.id, path), returnTo)}>{github.pending === `grant:${c.id}` ? <><Loader2 size={16} className="animate-spin" aria-hidden="true" />Opening GitHub…</> : github.waiting && github.activeKey === `grant:${c.id}` ? 'GitHub tab open' : 'Grant repository access'}</Button><Button variant="ghost" disabled={github.busy || disconnect.isPending} onClick={() => disconnect.mutate(c.id)}>Disconnect</Button></div>)}
      {disconnect.error && <p role="alert">{errorText(disconnect.error)}</p>}
      {refresh.data?.accounts.map(a => <div className="connection-row" key={`${a.connection_id}-${a.installation_id}`}><div className="flex-1"><h3>{a.account}</h3><p className="text-sm text-muted-foreground">{a.status}</p></div>{a.manage_url && <Button variant="outline" disabled={github.busy || disconnect.isPending || a.status !== 'connected'} aria-busy={github.pending === `manage:${a.installation_id}`} onClick={() => void github.run(`manage:${a.installation_id}`, path => workspaceApi.grant(a.connection_id, path, a.installation_id), returnTo)}>{github.pending === `manage:${a.installation_id}` ? <><Loader2 size={16} className="animate-spin" aria-hidden="true" />Opening GitHub…</> : github.waiting && github.activeKey === `manage:${a.installation_id}` ? 'GitHub tab open' : <>Manage access <ExternalLink size={14} aria-hidden="true" /></>}</Button>}</div>)}
      {refresh.data?.notices.map(n => <p key={n} role="status" className="notice">{n}</p>)}
      <Button className="self-start" disabled={status.isPending || status.isError || status.data?.configured === false || github.busy || disconnect.isPending} aria-busy={github.pending === 'connect'} onClick={() => void github.run('connect', path => workspaceApi.connect(path), returnTo)}>{github.pending === 'connect' ? <><Loader2 size={16} className="animate-spin" aria-hidden="true" />Opening GitHub…</> : github.waiting && github.activeKey === 'connect' ? 'GitHub tab open' : 'Connect GitHub account'}</Button>
    </section><section className="panel"><h2>Organization approval</h2><p className="mt-2 text-sm text-muted-foreground">If your organization requires approval, request access on GitHub and ask its administrator to approve the App. Repositories appear automatically when you return here. If one is missing, use Grant repository access to add it to the installation.</p></section>
  </div>;
}
