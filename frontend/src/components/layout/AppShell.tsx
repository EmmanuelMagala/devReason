import { useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { UserButton, useAuth } from '@clerk/clerk-react';
import { Menu, X, GitBranch } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { Button } from '@/components/ui/button';
import { useRepoStore } from '@/stores/repoStore';
import { useReviewStore } from '@/stores/reviewStore';
import { setTokenProvider } from '@/lib/clerk';
import { useGitHubConnection } from '@/hooks/useGitHubConnection';
import { QueryState } from '@/components/shared/QueryState';
import { useGitHubAction } from '@/hooks/useGitHubAction';

export function AppShell({children}: {children: ReactNode}) {
  const [open, setOpen] = useState(false);
  const {userId, getToken} = useAuth();
  const location = useLocation();
  const [params, setParams] = useSearchParams();
  const connection = useGitHubConnection(true);
  const github = useGitHubAction();
  useEffect(() => { setTokenProvider(getToken); return () => setTokenProvider(null); }, [getToken]);
  useEffect(() => { useRepoStore.setState({repos: [], selectedRepoId: null}); useReviewStore.getState().reset(); }, [userId]);
  useEffect(() => { const main = document.getElementById('main-content'); main?.focus(); }, [location.pathname]);
  return <div className="app-layout">
    <a href="#main-content" className="skip-link">Skip to content</a>
    <aside className="desktop-sidebar"><Link to="/" className="brand"><GitBranch size={25} aria-hidden="true" />DevReason</Link><Sidebar /><p className="sidebar-note">A clearer view of your code.</p></aside>
    <div className="min-w-0">
      <header className="app-header"><div className="flex items-center gap-3"><Button variant="ghost" size="icon" className="lg:hidden" aria-label={open ? 'Close navigation' : 'Open navigation'} aria-expanded={open} aria-controls="mobile-navigation" onClick={() => setOpen(!open)}>{open ? <X size={20} /> : <Menu size={20} />}</Button><Link to="/" className="font-semibold lg:hidden">DevReason</Link><span className="hidden text-sm text-muted-foreground lg:block">Code review workspace</span></div><UserButton afterSignOutUrl="/sign-in" /></header>
      {open && <div id="mobile-navigation" className="border-b bg-white p-4 lg:hidden"><Sidebar onNavigate={() => setOpen(false)} /></div>}
      <main id="main-content" tabIndex={-1} className="main-content"><QueryState error={connection.complete.error} />{(params.get('github_notice') || params.get('github_error')) && <div role={params.has('github_error') ? 'alert' : 'status'} className="notice flex items-start justify-between gap-3"><p>{params.get('github_error') || params.get('github_notice')}</p><Button variant="ghost" size="icon" aria-label="Dismiss GitHub message" onClick={() => setParams(previous => {const next = new URLSearchParams(previous); next.delete('github_notice'); next.delete('github_error'); return next;}, {replace: true})}><X size={16} /></Button></div>}
        {(github.busy || github.message || github.error) && <div role={github.error ? 'alert' : 'status'} className="notice mb-6 flex items-start justify-between gap-3"><p>{github.error || (github.pending ? 'Opening GitHub in a new tab…' : github.message || 'GitHub is open in another tab. Save your changes there. Repository access refreshes when you return.')}</p><div className="flex gap-2">{github.error && <Button variant="outline" onClick={github.retry}>Retry access refresh</Button>}{!github.pending && <Button variant="ghost" size="icon" aria-label="Dismiss GitHub tab status" onClick={github.dismiss}><X size={16} /></Button>}</div></div>}
        {children}</main>
    </div>
  </div>;
}
