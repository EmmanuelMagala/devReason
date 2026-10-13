import { apiClient } from "./client";
import { adaptRepo, adaptReview, adaptRule } from "@/lib/adapters";
import type { GitHubStatus, Page, Repo, Review, PullRequest, ScopePreview, ChatMessage } from "@/types";
import { currentGitHubReturn, githubReturnPath } from '@/lib/githubReturn';

export const workspaceApi = {
  async status(): Promise<GitHubStatus> { return (await apiClient.get('/api/auth/github/status')).data; },
  async connect(returnTo = currentGitHubReturn()): Promise<string> { const path = githubReturnPath(returnTo); const r = await apiClient.post('/api/auth/github/start', {return_to: path}, {timeout: 20_000}); return r.data.authorize_url; },
  async refresh(): Promise<{accounts: {account: string; connection_id: string; installation_id: number; status: string; manage_url?: string}[]; notices: string[]}> { return (await apiClient.post('/api/auth/github/refresh', null, {timeout: 50_000})).data; },
  async grant(connectionId: string, returnTo = currentGitHubReturn(), installationId?: number): Promise<string> { const path = githubReturnPath(returnTo); const r = await apiClient.post('/api/auth/github/install', null, {params: {connection_id: connectionId, return_to: path, installation_id: installationId}, withCredentials: true, timeout: 20_000}); return r.data.install_url; },
  async disconnect(id: string) { await apiClient.delete(`/api/auth/github/connections/${id}`); },
  async repositories(params: {q?: string; account?: string; page?: number; sort?: string}): Promise<Page<Repo> & {branch_reviews_enabled: boolean}> { const r = await apiClient.get('/api/repos/browse', {params}); return {...r.data, items: r.data.items.map(adaptRepo)}; },
  async repo(id: string): Promise<Repo> { return adaptRepo((await apiClient.get(`/api/repos/${id}`)).data); },
  async pulls(id: string, page: number, state: string): Promise<{items: PullRequest[]; has_next: boolean}> { return (await apiClient.get(`/api/repos/${id}/pulls`, {params: {page, state}})).data; },
  async branches(id: string, page = 1): Promise<{items: {name: string; commit_sha: string}[]; page: number; has_next: boolean}> { return (await apiClient.get(`/api/repos/${id}/branches`, {params: {page}})).data; },
  async scope(id: string, branch: string, offset: number, commit?: string): Promise<ScopePreview> { return (await apiClient.get(`/api/repos/${id}/scope`, {params: {branch, offset, commit_sha: commit || undefined}})).data; },
  async history(params: {repo_id?: string; status?: string; q?: string; page?: number}): Promise<Page<Review>> { const r = await apiClient.get('/api/reviews', {params: {...params, summary: true}}); return {...r.data, items: r.data.items.map(adaptReview)}; },
  async cancel(id: string) { return (await apiClient.post(`/api/reviews/${id}/cancel`)).data; },
  async rerun(id: string): Promise<{id: string}> { return (await apiClient.post(`/api/reviews/${id}/rerun`, null, {headers: {'Idempotency-Key': crypto.randomUUID()}})).data; },
  async comparison(id: string): Promise<{previous_review_id: string | null; new: number; recurring: number; resolved: number | null; coverage_comparable: boolean}> { return (await apiClient.get(`/api/reviews/${id}/comparison`)).data; },
  async preview(id: string): Promise<{body: string; target_url: string}> { return (await apiClient.get(`/api/reviews/${id}/posting-preview`)).data; },
  async post(id: string): Promise<{status: string; url: string}> { return (await apiClient.post(`/api/reviews/${id}/post`)).data; },
  async conversation(id: string, before?: string): Promise<{items: ChatMessage[]; has_more: boolean; next_cursor: string | null}> { return (await apiClient.get(`/api/repos/${id}/conversation`, {params: {before}})).data; },
  async suggest(id: string) { return (await apiClient.post(`/api/repos/${id}/rules/suggest`, {}, {timeout: 120_000})).data.map(adaptRule); },
  async updateRule(repo: string, id: string, data: {content?: string; status?: string}) { return adaptRule((await apiClient.patch(`/api/repos/${repo}/rules/${id}`, data, {timeout: 60_000})).data); },
  async deleteRule(repo: string, id: string) { await apiClient.delete(`/api/repos/${repo}/rules/${id}`); },
};
