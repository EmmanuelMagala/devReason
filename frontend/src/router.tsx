/* eslint-disable react-refresh/only-export-components */
import { createBrowserRouter, Link, Outlet, useParams } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/layout/ProtectedRoute';
import { SignInPage } from '@/pages/SignInPage';
import { SignUpPage } from '@/pages/SignUpPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { GitHubTabProvider } from '@/components/auth/GitHubTabProvider';

function RootLayout() { return <ProtectedRoute><GitHubTabProvider><AppShell><Outlet /></AppShell></GitHubTabProvider></ProtectedRoute>; }
function RouteError() { return <div role="alert" className="empty-panel"><h1>This page could not be loaded</h1><p>Check your connection and reload the page.</p><Link to="/">Return to overview</Link></div>; }
export const router = createBrowserRouter([
  {path: '/sign-in/*', element: <SignInPage />},
  {path: '/sign-up/*', element: <SignUpPage />},
  {path: '/github/return', hydrateFallbackElement: <p role="status" className="state-box">Completing GitHub setup…</p>, lazy: async () => { const {GitHubReturnPage} = await import('@/pages/GitHubReturnPage'); return {Component: () => <ProtectedRoute><GitHubReturnPage /></ProtectedRoute>}; }},
  {path: '/', element: <RootLayout />, hydrateFallbackElement: <p role="status" className="state-box">Loading workspace…</p>, errorElement: <RouteError />, children: [
    {index: true, lazy: async () => ({Component: (await import('@/pages/OverviewPage')).OverviewPage})},
    {path: 'repositories', lazy: async () => ({Component: (await import('@/pages/RepositoriesPage')).RepositoriesPage})},
    {path: 'reviews', lazy: async () => ({Component: (await import('@/pages/ReviewsPage')).ReviewsPage})},
    {path: 'reviews/:reviewId', lazy: async () => ({Component: (await import('@/pages/ReviewPage')).ReviewPage})},
    {path: 'repos/:repoId', lazy: async () => ({Component: (await import('@/pages/RepositoryPage')).RepositoryPage})},
    {path: 'repos/:repoId/reviews', lazy: async () => {
      const {ReviewsPage} = await import('@/pages/ReviewsPage');
      return {Component: function RepositoryHistory() { const {repoId} = useParams(); return <><nav className="breadcrumbs" aria-label="Breadcrumb"><Link to={`/repos/${repoId}`}>Repository</Link><span>/</span><span>Reviews</span></nav><ReviewsPage repoId={repoId} /></>; }};
    }},
    {path: 'repos/:repoId/settings', lazy: async () => ({Component: (await import('@/pages/RepoSettingsPage')).RepoSettingsPage})},
    {path: 'repos/:repoId/chat', lazy: async () => ({Component: (await import('@/pages/RepoChatPage')).RepoChatPage})},
    {path: 'settings/integrations', lazy: async () => ({Component: (await import('@/pages/IntegrationsPage')).IntegrationsPage})},
  ]},
  {path: '*', element: <NotFoundPage />},
]);
