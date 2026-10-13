import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { workspaceApi } from '@/api/workspace';
import { useDebounce } from '@/hooks/useDebounce';
import { QueryState } from '@/components/shared/QueryState';
import { StatusPill } from '@/components/shared/StatusPill';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import type { Review } from '@/types';

export function ReviewRows({items}: {items: Review[]}) {
  return <div className="review-rows">{items.map(r => <Link key={r.id} to={`/reviews/${r.id}`} className="review-row"><div className="min-w-0"><h3 className="truncate">{r.title || (r.mode === 'snapshot' ? `Branch ${r.branch}` : `Pull request #${r.prNumber}`)}</h3><p className="text-xs text-muted-foreground">{r.mode === 'snapshot' ? 'Branch snapshot' : `PR #${r.prNumber}`} · {new Date(r.createdAt).toLocaleString()} · {r.findingCount ?? r.findings.length} findings</p></div><StatusPill status={r.status} /></Link>)}</div>;
}
export function ReviewsPage({repoId}: {repoId?: string}) {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get('q') || '');
  const query = useDebounce(search); const status = params.get('status') || ''; const page = Number(params.get('page') || 1);
  const history = useQuery({queryKey: ['review-history', repoId, status, query, page], queryFn: () => workspaceApi.history({repo_id: repoId, status: status || undefined, q: query, page}), refetchInterval: q => q.state.data?.items.some(r => ['pending', 'running'].includes(r.status)) ? 5000 : false});
  function change(key: string, value: string) { setParams(prev => { const next = new URLSearchParams(prev); if (value) next.set(key, value); else next.delete(key); if (key !== 'page') next.delete('page'); return next; }); }
  return <div className="page-stack">{!repoId && <div className="page-heading"><div><h1>Reviews</h1><p>Your saved results, ready whenever you return.</p></div><Button asChild><Link to="/repositories">Start a review</Link></Button></div>}
    <div className="toolbar"><Input aria-label="Search review titles" placeholder="Search reviews…" value={search} onChange={e => { setSearch(e.target.value); change('q', e.target.value); }} /><select aria-label="Review status" value={status} onChange={e => change('status', e.target.value)}><option value="">All statuses</option>{['pending', 'running', 'completed', 'partial', 'failed', 'cancelled'].map(s => <option key={s}>{s}</option>)}</select></div>
    <QueryState loading={history.isPending} error={history.error} retry={() => void history.refetch()} />
    {history.data?.items.length === 0 && <div className="empty-panel"><h2>No reviews found</h2><p>{status || search ? 'Change your filters to see more results.' : 'Choose a repository and start your first review.'}</p><Link to="/repositories">Browse repositories →</Link></div>}
    <ReviewRows items={history.data?.items ?? []} />
    {history.data && history.data.total > 20 && <div className="pagination"><span>{history.data.total} reviews · Page {page}</span><Button variant="outline" disabled={page <= 1} onClick={() => change('page', String(page - 1))}>Previous</Button><Button variant="outline" disabled={page * 20 >= history.data.total} onClick={() => change('page', String(page + 1))}>Next</Button></div>}
  </div>;
}
