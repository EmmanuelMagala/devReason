import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useMutation, useQuery } from '@tanstack/react-query';
import { workspaceApi } from '@/api/workspace';
import { reviewsApi } from '@/api/reviews';
import { QueryState, errorText } from '@/components/shared/QueryState';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { GitPullRequest, GitBranch } from 'lucide-react';
import type { ReviewCreate } from '@/types';
import { useDebounce } from '@/hooks/useDebounce';
import { githubSettingsLink } from '@/lib/githubReturn';

export function RepositoryPage() { const {repoId = ''} = useParams(); return <RepositoryWorkspace key={repoId} repoId={repoId} />; }
function RepositoryWorkspace({repoId}: {repoId: string}) {
  const navigate = useNavigate(); const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'branches' ? 'branches' : 'pulls'; const page = Number(params.get('page') || 1); const prState = params.get('state') || 'open';
  const [search, setSearch] = useState(''); const query = useDebounce(search);
  const repo = useQuery({queryKey: ['repo', repoId], queryFn: () => workspaceApi.repo(repoId)});
  const pulls = useQuery({queryKey: ['pulls', repoId, page, prState], queryFn: () => workspaceApi.pulls(repoId, page, prState), enabled: tab === 'pulls'});
  const branches = useInfiniteQuery({queryKey: ['branches', repoId], queryFn: ({pageParam}) => workspaceApi.branches(repoId, pageParam), initialPageParam: 1, getNextPageParam: last => last.has_next ? last.page + 1 : undefined, enabled: tab === 'branches', staleTime: 30_000});
  const [pinnedCommit, setPinnedCommit] = useState(params.get('commit') || ''); const [branch, setBranch] = useState(params.get('branch') || ''); const [offset, setOffset] = useState(Number(params.get('offset') || 0)); const [selected, setSelected] = useState<string[] | null>(null);
  const preview = useQuery({queryKey: ['scope', repoId, branch, offset, pinnedCommit], queryFn: () => workspaceApi.scope(repoId, branch, offset, pinnedCommit), enabled: tab === 'branches' && Boolean(branch), staleTime: 10_000});
  const create = useMutation({mutationFn: (payload: ReviewCreate) => reviewsApi.create(payload), onSuccess: r => navigate(`/reviews/${r.id}`)});
  function change(key: string, value: string) { setParams(prev => { const next = new URLSearchParams(prev); next.set(key, value); if (key !== 'page') next.delete('page'); return next; }); }
  const paths = selected ?? preview.data?.paths ?? [];
  const filtered = pulls.data?.items.filter(p => `${p.title} ${p.number} ${p.author}`.toLowerCase().includes(query.toLowerCase())) ?? [];
  return <div className="page-stack"><nav aria-label="Breadcrumb" className="breadcrumbs"><Link to="/repositories">Repositories</Link><span>/</span><span>{repo.data ? `${repo.data.owner}/${repo.data.name}` : 'Repository'}</span></nav>
    <QueryState loading={repo.isPending} error={repo.error} retry={() => void repo.refetch()} />
    {repo.data && <><div className="page-heading"><div><p className="eyebrow">{repo.data.owner}</p><h1>{repo.data.name}</h1><p>{repo.data.details?.description || 'Choose changes or source code to review.'}</p></div><a className="text-sm text-primary" target="_blank" rel="noreferrer" href={`https://github.com/${repo.data.owner}/${repo.data.name}`}>View on GitHub ↗</a></div>
    <nav aria-label="Repository navigation" className="tabs"><Link aria-current={tab === 'pulls' ? 'page' : undefined} className={tab === 'pulls' ? 'active' : ''} to={`/repos/${repoId}`}>Pull requests</Link><Link aria-current={tab === 'branches' ? 'page' : undefined} className={tab === 'branches' ? 'active' : ''} to={`/repos/${repoId}?tab=branches`}>Branches</Link><Link to={`/repos/${repoId}/reviews`}>Reviews</Link><Link to={`/repos/${repoId}/chat`}>Chat</Link><Link to={`/repos/${repoId}/settings`}>Rules</Link></nav>
    {create.error && <div role="alert" className="notice">{errorText(create.error)} <Link to={githubSettingsLink()}>Manage GitHub access</Link></div>}
    {tab === 'pulls' ? <><div className="toolbar"><Input aria-label="Filter loaded pull requests" value={search} onChange={e => setSearch(e.target.value)} placeholder="Filter this page by title, number, or author…" /><select aria-label="Pull request state" value={prState} onChange={e => change('state', e.target.value)}><option value="open">Open</option><option value="closed">Closed</option><option value="all">All</option></select></div>
      <QueryState loading={pulls.isPending} error={pulls.error} retry={() => void pulls.refetch()} />
      {!pulls.isError && pulls.data?.items.length === 0 && <div className="empty-panel"><GitPullRequest size={30} /><h2>No {prState === 'all' ? '' : prState} pull requests</h2><p>You can review source code from a branch instead.</p><Button variant="outline" onClick={() => change('tab', 'branches')}>Review a branch</Button></div>}
      {pulls.data && pulls.data.items.length > 0 && filtered.length === 0 && <p role="status">No pull requests on this page match your filter.</p>}
      <div className="review-rows">{filtered.map(pr => <article key={pr.number} className="pr-row"><GitPullRequest size={19} className="text-emerald-700" aria-hidden="true" /><div className="min-w-0 flex-1"><h3>{pr.title} {pr.draft && <span className="badge">Draft</span>}</h3><p>#{pr.number} · {pr.author} · {pr.branch}</p></div><Button disabled={create.isPending} aria-label={`Review pull request ${pr.number}`} onClick={() => create.mutate({repoId, prNumber: pr.number, postToGithub: false})}>Review</Button></article>)}</div>
      <div className="pagination"><span>Page {page}</span><Button variant="outline" disabled={page <= 1} onClick={() => change('page', String(page - 1))}>Previous</Button><Button variant="outline" disabled={!pulls.data?.has_next} onClick={() => change('page', String(page + 1))}>Next</Button></div>
    </> : <><QueryState loading={branches.isPending} error={branches.error} retry={() => void branches.refetch()} /><section className="panel page-stack"><div className="flex items-center gap-2"><GitBranch size={20} /><h2>Review a branch snapshot</h2></div><p className="text-sm text-muted-foreground">The branch is pinned to a commit. Each run uses the file and character limits shown below. Generated and vendor files are excluded.</p><label className="field-label">Branch<select aria-label="Branch" value={branch} onChange={e => { setBranch(e.target.value); setPinnedCommit(''); setOffset(0); setSelected(null); }}><option value="">Choose a branch</option>{branches.data?.pages.flatMap(page => page.items).map(b => <option key={b.name}>{b.name}</option>)}</select></label>
      <Button variant="outline" disabled={!branches.hasNextPage || branches.isFetchingNextPage} onClick={() => void branches.fetchNextPage()}>Load more branches</Button><QueryState loading={preview.isFetching} error={preview.error} retry={() => void preview.refetch()} />
      {preview.data && !preview.isError && <><p className="text-sm">Commit <code>{preview.data.commit_sha.slice(0, 12)}</code> · {preview.data.eligible_files} eligible files · Batch {Math.floor(offset / (preview.data.file_limit || 50)) + 1}</p><fieldset className="scope-files"><legend>Files selected for this run</legend>{preview.data.paths.map(path => <label key={path}><input type="checkbox" checked={paths.includes(path)} onChange={e => setSelected(e.target.checked ? [...paths, path] : paths.filter(p => p !== path))} /><code>{path}</code></label>)}</fieldset><p className="text-xs text-muted-foreground">{paths.length} of {preview.data.file_limit || 50} files selected · {preview.data.character_limit.toLocaleString()} character limit. The saved result lists reviewed, skipped, and truncated files.</p><div className="flex flex-wrap gap-2"><Button disabled={create.isPending || preview.isFetching || paths.length === 0} onClick={() => create.mutate({repoId, mode: 'snapshot', branch, commitSha: preview.data.commit_sha, scope: selected ? {paths: selected, commit_sha: preview.data.commit_sha} : {offset, commit_sha: preview.data.commit_sha}, postToGithub: false})}>{create.isPending ? 'Starting…' : 'Review selected scope'}</Button><Button variant="outline" disabled={offset === 0} onClick={() => { setOffset(Math.max(0, offset - (preview.data.file_limit || 50))); setSelected(null); }}>Previous batch</Button><Button variant="outline" disabled={preview.data.next_offset === null} onClick={() => { setOffset(preview.data.next_offset ?? 0); setSelected(null); }}>Next batch</Button></div></>}
    </section></>}
    </>}
  </div>;
}
