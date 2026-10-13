import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { workspaceApi } from '@/api/workspace';
import { reviewsApi } from '@/api/reviews';
import { QueryState, errorText } from '@/components/shared/QueryState';
import { ReviewRows } from './ReviewsPage';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { GitPullRequest, FolderGit2, ArrowRight } from 'lucide-react';

export function OverviewPage() {
  const navigate = useNavigate(); const [url, setUrl] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const recent = useQuery({queryKey: ['review-history', 'overview'], queryFn: () => workspaceApi.history({})});
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('');
    try {
      const parsed = new URL(url); const match = parsed.pathname.match(/^\/([^/]+)\/([^/]+)\/pull\/(\d+)(?:\/(files|commits|checks))?\/?$/);
      if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || !match) throw new Error('Enter a GitHub pull request URL.');
      const repos = await workspaceApi.repositories({q: match[2]});
      let repo = repos.items.find(r => r.owner.toLowerCase() === match[1].toLowerCase() && r.name.toLowerCase() === match[2].toLowerCase());
      for (let page = 2; !repo && (page - 1) * 20 < repos.total; page++) { const more = await workspaceApi.repositories({q: match[2], page}); repo = more.items.find(r => r.owner.toLowerCase() === match[1].toLowerCase() && r.name.toLowerCase() === match[2].toLowerCase()); }
      if (!repo) throw new Error('Connect GitHub and grant access to this repository in Settings.');
      const result = await reviewsApi.create({repoId: repo.id, prUrl: url, postToGithub: false}); navigate(`/reviews/${result.id}`);
    } catch(e) { setError(errorText(e)); } finally { setBusy(false); }
  }
  return <div className="page-stack"><div className="page-heading"><div><p className="eyebrow">Welcome to DevReason</p><h1>Understand your code. Ship with confidence.</h1><p>Review changes, keep architecture consistent, and return to every result.</p></div></div>
    <section className="hero-panel"><div><FolderGit2 size={30} aria-hidden="true" /><h2>Start with a repository</h2><p>Connect GitHub, choose a pull request or branch, and get actionable findings.</p><Button asChild><Link to="/repositories">Browse repositories <ArrowRight size={16} /></Link></Button></div><form onSubmit={submit} className="quick-review"><label htmlFor="pr-shortcut"><GitPullRequest size={18} aria-hidden="true" />Already have a PR link?</label><Input id="pr-shortcut" type="url" required placeholder="https://github.com/owner/repo/pull/42" value={url} onChange={e => setUrl(e.target.value)} /><Button variant="outline" disabled={busy}>{busy ? 'Starting…' : 'Review pull request'}</Button>{error && <p role="alert" className="text-sm text-destructive">{error}</p>}</form></section>
    <section className="panel"><div className="flex items-center justify-between gap-3"><h2>Recent reviews</h2><Link to="/reviews" className="text-sm text-primary">View all →</Link></div><QueryState loading={recent.isPending} error={recent.error} retry={() => void recent.refetch()} />{recent.data?.items.length === 0 && <p className="py-8 text-sm text-muted-foreground">Your first review starts with a repository. Saved results will appear here.</p>}<ReviewRows items={recent.data?.items.slice(0, 5) ?? []} /></section>
  </div>;
}
