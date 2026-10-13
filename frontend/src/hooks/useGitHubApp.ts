import { useMutation, useQueryClient } from "@tanstack/react-query";
import { reposApi } from "@/api/repos";
import type {
  GitHubAppInstallComplete,
  GitHubAppInstallStart,
  GitHubAppInstallSync,
} from "@/types";

export function useStartGitHubInstall() {
  return useMutation({
    mutationFn: (payload: GitHubAppInstallStart) =>
      reposApi.startGitHubInstall(payload),
  });
}

export function useListGitHubInstallRepos() {
  return useMutation({
    mutationFn: ({
      installationId,
      state,
    }: {
      installationId: number;
      state: string;
    }) => reposApi.listGitHubInstallRepos(installationId, state),
  });
}

export function useSyncGitHubInstallRepos() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: GitHubAppInstallSync) =>
      reposApi.syncGitHubInstallRepos(payload),
    onSuccess: (data) => {
      queryClient.setQueryData(["repos"], data.repositories);
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

export function useCompleteGitHubInstall() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: GitHubAppInstallComplete) =>
      reposApi.completeGitHubInstall(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}
