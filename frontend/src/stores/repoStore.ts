import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Repo } from "@/types";

type RepoStoreState = {
  selectedRepoId: string | null;
  repos: Repo[];
  setSelectedRepo: (repoId: string | null) => void;
  setRepos: (repos: Repo[]) => void;
};

export const useRepoStore = create<RepoStoreState>()(
  persist(
    (set) => ({
      selectedRepoId: null,
      repos: [],
      setSelectedRepo: (repoId) => set({ selectedRepoId: repoId }),
      setRepos: (repos) => set({ repos }),
    }),
    { name: "devreason-selected-repo", partialize: (state) => ({selectedRepoId: state.selectedRepoId}) },
  ),
);
