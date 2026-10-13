import { GitBranch, Loader2 } from 'lucide-react';
import { workspaceApi } from '@/api/workspace';
import { useGitHubAction } from '@/hooks/useGitHubAction';
import { Button } from '@/components/ui/button';

export function AddRepoForm() {
  const github = useGitHubAction();
  return <div className="space-y-3"><p className="text-sm text-muted-foreground">Connect your GitHub account in a new tab and choose which repositories DevReason can review.</p><Button onClick={()=>void github.run('connect', path => workspaceApi.connect(path))} disabled={github.busy}><span aria-hidden="true">{github.pending ? <Loader2 className="h-4 w-4 animate-spin"/> : <GitBranch className="h-4 w-4"/>}</span>{github.pending ? 'Opening GitHub…' : 'Connect GitHub'}</Button></div>;
}
