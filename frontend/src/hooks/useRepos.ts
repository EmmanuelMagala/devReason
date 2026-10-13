import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { reposApi } from "@/api/repos";
import { useRepoStore } from "@/stores/repoStore";
import type { ArchRuleCreate } from "@/types";

export function useReposList() {
  const setRepos = useRepoStore((state) => state.setRepos);
  const query = useQuery({
    queryKey: ["repos"],
    queryFn: reposApi.list,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (query.data) {
      setRepos(query.data);
    }
  }, [query.data, setRepos]);

  return query;
}

export function useArchRules(repoId: string | null) {
  return useQuery({
    queryKey: ["repos", repoId, "rules"],
    queryFn: () => reposApi.getRules(repoId!),
    enabled: Boolean(repoId),
  });
}

export function useAddRule(repoId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: ArchRuleCreate) => reposApi.addRule(repoId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["repos", repoId, "rules"],
      });
    },
  });
}
