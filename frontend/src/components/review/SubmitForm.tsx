import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { GitPullRequestArrow, Loader2 } from "lucide-react";
import { useCreateReview } from "@/hooks/useReviews";
import { useRepoStore } from "@/stores/repoStore";
import { useReviewStore } from "@/stores/reviewStore";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Repo } from "@/types";

export function SubmitForm({ repos }: { repos: Repo[] }) {
  const [prUrl, setPrUrl] = useState("");
  const [postToGithub, setPostToGithub] = useState(false);
  const navigate = useNavigate();
  const selectedRepoId = useRepoStore((state) => state.selectedRepoId);
  const setSelectedRepo = useRepoStore((state) => state.setSelectedRepo);
  const startReview = useReviewStore((state) => state.startReview);
  const createReview = useCreateReview();

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedRepoId || !prUrl.trim()) {
      return;
    }

    const result = await createReview.mutateAsync({
      prUrl: prUrl.trim(),
      repoId: selectedRepoId,
      postToGithub,
    });

    startReview(result.id);
    navigate(`/reviews/${result.id}`);
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="space-y-2">
        <Label htmlFor="repoId">Repository</Label>
        <select
          id="repoId"
          value={selectedRepoId ?? ""}
          onChange={(event) => setSelectedRepo(event.target.value || null)}
          className="flex h-10 w-full rounded-md border bg-background/80 px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <option value="">Select a repository</option>
          {repos.map((repo) => (
            <option key={repo.id} value={repo.id}>
              {repo.owner}/{repo.name}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="prUrl">GitHub PR URL</Label>
        <Input
          id="prUrl"
          placeholder="https://github.com/owner/repo/pull/42"
          value={prUrl}
          onChange={(event) => setPrUrl(event.target.value)}
        />
      </div>
      <label className="flex items-center gap-3 rounded-xl border bg-background/70 px-3 py-3 text-sm">
        <input
          type="checkbox"
          checked={postToGithub}
          onChange={(event) => setPostToGithub(event.target.checked)}
          className="h-4 w-4 rounded border-border"
        />
        Post the final report back to GitHub.
      </label>
      <Button
        type="submit"
        className="w-full"
        disabled={!selectedRepoId || !prUrl.trim() || createReview.isPending}
      >
        {createReview.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <GitPullRequestArrow className="h-4 w-4" />
        )}
        Start review
      </Button>
    </form>
  );
}
