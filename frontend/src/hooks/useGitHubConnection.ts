import { useEffect, useRef } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { workspaceApi } from '@/api/workspace';
import { apiClient } from '@/api/client';
import { takeGitHubReturn } from '@/lib/githubReturn';

export function useGitHubConnection(finalize = false, syncRepositories = false) {
  const [params, setParams] = useSearchParams(); const ticket = params.get('github_ticket'); const qc = useQueryClient();
  const navigate = useNavigate(); const restoreReturn = params.has('github_return');
  const restored = useRef(false);
  const restoredAfterBack = useRef(false);
  const complete = useQuery({queryKey: ['github-complete', ticket], queryFn: () => apiClient.post('/api/auth/github/complete', {ticket}), enabled: Boolean(ticket), retry: false, staleTime: Infinity});
  useEffect(() => {
    if (finalize && ticket && complete.isSuccess && !restoreReturn) {
      takeGitHubReturn();
      setParams(prev => { const next = new URLSearchParams(prev); next.delete('github_ticket'); next.set('github_connected', '1'); return next; }, {replace: true});
      void qc.invalidateQueries({queryKey: ['github-status']});
      void apiClient.post('/api/metrics', {event: 'connection_completed'}).catch(() => {});
    }
  }, [finalize, ticket, complete.isSuccess, restoreReturn, qc, setParams]);
  useEffect(() => {
    if (!finalize) return;
    if (restoreReturn) {
      if (restored.current) return;
      restored.current = true;
      const returnTo = takeGitHubReturn();
      if (returnTo) {
        const url = new URL(returnTo, window.location.origin);
        for (const name of ['github_ticket', 'github_connected', 'github_notice', 'github_error']) {
          const value = params.get(name); if (value) url.searchParams.set(name, value);
        }
        navigate(url.pathname + url.search + url.hash, {replace: true});
      } else setParams(previous => { const next = new URLSearchParams(previous); next.delete('github_return'); return next; }, {replace: true});
    } else {
      restored.current = false;
      if (!ticket && (params.has('github_connected') || params.has('github_notice') || params.has('github_error'))) takeGitHubReturn();
    }
  }, [finalize, restoreReturn, ticket, params, navigate, setParams]);
  useEffect(() => {
    if (!finalize) return;
    const hasResult = ticket || restoreReturn || params.has('github_connected') || params.has('github_notice') || params.has('github_error');
    const returnAfterBack = () => {
      if (hasResult) return;
      const path = takeGitHubReturn();
      if (!path) return;
      navigate(path, {replace: true});
      // A return or cancellation is not proof of a grant. Recheck signed-in access.
      for (const queryKey of [['github-status'], ['github-refresh'], ['repo-browse']]) void qc.invalidateQueries({queryKey});
    };
    const onPageShow = (event: PageTransitionEvent) => { if (event.persisted) returnAfterBack(); };
    window.addEventListener('pageshow', onPageShow);
    const navigation = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined;
    if (navigation?.type === 'back_forward' && !restoredAfterBack.current) {
      restoredAfterBack.current = true;
      returnAfterBack();
    }
    return () => window.removeEventListener('pageshow', onPageShow);
  }, [finalize, ticket, restoreReturn, params, navigate, qc]);
  const status = useQuery({queryKey: ['github-status'], queryFn: workspaceApi.status, enabled: !ticket || complete.isSuccess, staleTime: 60_000, refetchOnWindowFocus: false});
  const refresh = useQuery({
    queryKey: ['github-refresh', status.data?.connections.map(c => c.id + c.status).join(',')],
    queryFn: workspaceApi.refresh,
    // Saved reports never need a GitHub network call. Discovery refreshes in
    // the background; an explicit return from GitHub still forces a refresh.
    enabled: syncRepositories && Boolean(status.data?.connections.some(c => c.status === 'connected')),
    staleTime: 300_000, refetchOnWindowFocus: false, retry: false,
  });
  useEffect(() => {
    if (syncRepositories && refresh.isSuccess) void qc.invalidateQueries({queryKey: ['repo-browse']});
  }, [syncRepositories, refresh.isSuccess, refresh.dataUpdatedAt, qc]);
  return {status, refresh, complete, ready: !ticket || complete.isSuccess};
}
