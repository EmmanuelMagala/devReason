import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { FolderGit2, ArrowUpRight, Search, Lock, Loader2 } from 'lucide-react';
import { workspaceApi } from '@/api/workspace';
import { useGitHubConnection } from '@/hooks/useGitHubConnection';
import { useDebounce } from '@/hooks/useDebounce';
import { QueryState } from '@/components/shared/QueryState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { githubSettingsLink } from '@/lib/githubReturn';
import { useGitHubAction } from '@/hooks/useGitHubAction';

export function RepositoriesPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get('q') ?? '');
  const github = useGitHubAction();
  const query = useDebounce(search);
  const page = Number(params.get('page') || 1);
  const account = params.get('account') || '';
  const connection = useGitHubConnection(false, true);
  const repos = useQuery({queryKey: ['repo-browse', query, account, page], queryFn: () => workspaceApi.repositories({q: query, account: account || undefined, page}), enabled: connection.ready, staleTime: 60_000});
  function connect() { void github.run('connect', path => workspaceApi.connect(path)); }
  const connecting = Boolean(github.pending);
  const connectDisabled = github.busy || connection.status.isPending || connection.status.isError || connection.status.data?.configured === false;
  const connectProgress = <><Loader2 size={16} className="animate-spin" aria-hidden="true" />Opening GitHub…</>;
  function change(key: string, value: string) { setParams(prev => { const next = new URLSearchParams(prev); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.delete('page'); return next; }); }
  const accounts = [...new Set(connection.refresh.data?.accounts.map(a => a.account) ?? [])];
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">Your workspace</p><h1>Repositories</h1><p>Choose a repository to review a pull request or a branch.</p></div><Button onClick={connect} disabled={connectDisabled} aria-busy={connecting}>{connecting ? connectProgress : 'Connect GitHub account'}</Button></div>
    <QueryState error={connection.status.error || connection.refresh.error} retry={() => { void connection.status.refetch(); void connection.refresh.refetch(); }} />
    {connection.refresh.isFetching && <p role="status" className="text-sm text-muted-foreground">Checking GitHub access in the background. Your saved repositories are available below.</p>}
    {connection.refresh.data?.notices.map(notice => <div key={notice} role="status" className="notice">{notice} <Link to={githubSettingsLink()}>Manage access →</Link></div>)}
    {connection.status.data?.connections.some(c => c.status !== 'connected') && <div className="notice">GitHub access needs to be renewed. <Button variant="outline" onClick={connect} disabled={connectDisabled} aria-busy={connecting}>{connecting ? connectProgress : 'Reconnect GitHub'}</Button></div>}
    <div className="toolbar"><label className="search-field"><Search size={18} aria-hidden="true" /><span className="sr-only">Search repositories</span><Input placeholder="Search repositories…" value={search} onChange={e => { setSearch(e.target.value); change('q', e.target.value); }} /></label><label><span className="sr-only">Account or organization</span><select value={account} onChange={e => change('account', e.target.value)}><option value="">All accounts</option>{accounts.map(a => <option key={a}>{a}</option>)}</select></label><Link className="text-sm text-primary" to={githubSettingsLink()}>Missing a repository? Grant access</Link></div>
    <QueryState loading={repos.isPending && connection.ready} error={repos.error} retry={() => void repos.refetch()} />
    {repos.data?.items.length === 0 && Boolean(connection.status.data?.connections.length) && !connection.refresh.isFetching && !connection.refresh.isError && <div className="empty-panel"><FolderGit2 size={32} aria-hidden="true" /><h2>{search ? 'No repositories match your search' : 'Your repositories will appear here'}</h2><p>{search ? 'Try another name or account.' : 'Connect GitHub, then grant the App access to the repositories you want to review.'}</p><Button asChild variant="outline"><Link to={githubSettingsLink()}>Manage GitHub access</Link></Button></div>}
    {connection.status.isSuccess && !connection.status.data?.connections.length && <div className="empty-panel"><FolderGit2 size={32} /><h2>Start with GitHub</h2><p>Connect your account once. Your accessible repositories stay available here.</p><Button onClick={connect} disabled={connectDisabled} aria-busy={connecting}>{connecting ? connectProgress : 'Connect GitHub'}</Button></div>}
    <div className="repo-grid">{repos.data?.items.map(repo => <Link className="repo-card" key={repo.id} to={`/repos/${repo.id}`}><div className="flex items-center justify-between"><FolderGit2 size={23} /><ArrowUpRight size={17} /></div><p className="text-xs text-muted-foreground">{repo.owner}</p><h2>{repo.name}</h2><p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">{repo.details?.description || 'Open repository workspace'}</p><div className="flex gap-3 text-xs text-muted-foreground">{repo.details?.language && <span>{repo.details.language}</span>}{repo.details?.private && <span className="flex gap-1"><Lock size={12} />Private</span>}</div></Link>)}</div>
    {repos.data && repos.data.total > 20 && <div className="pagination"><span>{repos.data.total} repositories · Page {page}</span><Button variant="outline" disabled={page <= 1} onClick={() => change('page', String(page - 1))}>Previous</Button><Button variant="outline" disabled={page * 20 >= repos.data.total} onClick={() => change('page', String(page + 1))}>Next</Button></div>}
  </div>;
}
