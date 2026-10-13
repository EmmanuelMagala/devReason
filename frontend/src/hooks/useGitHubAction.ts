import { useContext } from 'react';
import { GitHubTabContext } from '@/lib/githubTab';

export function useGitHubAction() {
  const actions = useContext(GitHubTabContext);
  if (!actions) throw new Error('GitHub actions require the signed-in workspace.');
  return actions;
}
