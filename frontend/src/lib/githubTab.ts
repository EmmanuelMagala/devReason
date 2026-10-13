import { createContext } from 'react';
import { githubReturnPath } from './githubReturn';

const flowKey = 'devreason:github-tab';
const resultPrefix = 'devreason:github-tab-result:';
export interface GitHubTabFlow {id: string; accountId: string; key: string; returnTo: string; expires: number}
export interface GitHubTabResult {kind: 'result'; flowId: string; error?: string; notice?: string; expires: number}
export interface GitHubTabActions {
  pending: string | null; waiting: boolean; busy: boolean; activeKey: string | null; error: string; message: string;
  run: (key: string, action: (callbackPath: string) => Promise<string>, returnTo?: string) => Promise<void>;
  dismiss: () => void; retry: () => void;
}
export const GitHubTabContext = createContext<GitHubTabActions | null>(null);
export const githubTabChannel = (id: string) => 'devreason:github-tab:' + id;
export const githubTabResultKey = (id: string) => resultPrefix + id;
export const githubTabAckKey = (id: string) => resultPrefix + id + ':ack';
export const validGitHubFlowId = (id: string | null): id is string => Boolean(id && /^[a-f0-9-]{36}$/.test(id));

export function saveGitHubTabFlow(flow: GitHubTabFlow | null, target?: Storage) {
  try { const storage = target ?? sessionStorage; if (flow) storage.setItem(flowKey, JSON.stringify(flow)); else storage.removeItem(flowKey); } catch { /* Cross-tab messages still work without storage. */ }
}
export function readGitHubTabFlow(accountId: string | null | undefined): GitHubTabFlow | null {
  try {
    const flow = JSON.parse(sessionStorage.getItem(flowKey) || 'null');
    if (!flow || flow.accountId !== accountId || !validGitHubFlowId(flow.id) || flow.expires < Date.now()) return null;
    return {...flow, returnTo: githubReturnPath(flow.returnTo)};
  } catch { return null; }
}
export function parseGitHubTabResult(value: unknown, flowId: string): GitHubTabResult | null {
  if (!value || typeof value !== 'object') return null;
  const result = value as Record<string, unknown>;
  if (result.kind !== 'result' || result.flowId !== flowId || typeof result.expires !== 'number' || result.expires < Date.now()) return null;
  return {kind: 'result', flowId, expires: result.expires,
    error: typeof result.error === 'string' ? result.error.slice(0, 500) : undefined,
    notice: typeof result.notice === 'string' ? result.notice.slice(0, 500) : undefined};
}
export function readGitHubTabResult(id: string) {
  try { return parseGitHubTabResult(JSON.parse(localStorage.getItem(githubTabResultKey(id)) || 'null'), id); } catch { return null; }
}
