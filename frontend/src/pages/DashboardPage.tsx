import { useEffect } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  Link2,
  MessageSquareText,
  Settings2,
  Sparkles,
} from "lucide-react";
import { AddRepoForm } from "@/components/repo/AddRepoForm";
import { SubmitForm } from "@/components/review/SubmitForm";
import { EmptyState } from "@/components/shared/EmptyState";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useReposList } from "@/hooks/useRepos";
import { useRepoStore } from "@/stores/repoStore";

export function DashboardPage() {
  const { data: repos = [], isLoading } = useReposList();
  const selectedRepoId = useRepoStore((state) => state.selectedRepoId);
  const setSelectedRepo = useRepoStore((state) => state.setSelectedRepo);
  const selectedRepo =
    repos.find((repo) => repo.id === selectedRepoId) ?? repos[0] ?? null;

  useEffect(() => {
    if (!repos.length) {
      if (selectedRepoId) {
        setSelectedRepo(null);
      }
      return;
    }

    const selectedRepoStillExists = repos.some(
      (repo) => repo.id === selectedRepoId,
    );
    if (!selectedRepoId || !selectedRepoStillExists) {
      setSelectedRepo(repos[0].id);
    }
  }, [repos, selectedRepoId, setSelectedRepo]);

  return (
    <div className="space-y-8">
      <section className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.9fr)]">
        <Card className="overflow-hidden border-transparent bg-devreason-ink text-white">
          <CardHeader className="relative overflow-hidden pb-3">
            <div className="absolute inset-y-0 right-0 w-1/2 bg-[radial-gradient(circle_at_top_right,rgba(29,158,117,0.35),transparent_45%),radial-gradient(circle_at_center,rgba(255,255,255,0.12),transparent_55%)]" />
            <Badge variant="secondary" className="w-fit bg-white/10 text-white">
              Backend-aligned build
            </Badge>
            <CardTitle className="max-w-xl text-3xl font-semibold leading-tight sm:text-4xl">
              Real-time review streaming, repo memory chat, and architecture
              rules in one workspace.
            </CardTitle>
            <CardDescription className="max-w-xl text-base text-white/72">
              Register a repo, choose a pull request, and stream the review
              graph as the backend emits state.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/70">
                Selected repo
              </p>
              {selectedRepo ? (
                <>
                  <p className="mt-3 text-lg font-semibold">
                    {selectedRepo.owner}/{selectedRepo.name}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      asChild
                      variant="secondary"
                      size="sm"
                      className="bg-white text-devreason-ink hover:bg-white/90"
                    >
                      <Link to={`/repos/${selectedRepo.id}/settings`}>
                        Rules
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                    <Button
                      asChild
                      variant="ghost"
                      size="sm"
                      className="text-white hover:bg-white/10 hover:text-white"
                    >
                      <Link to={`/repos/${selectedRepo.id}/chat`}>
                        Chat
                        <ArrowRight className="h-4 w-4" />
                      </Link>
                    </Button>
                  </div>
                </>
              ) : (
                <p className="mt-3 text-sm text-white/70">
                  Add a repository to unlock review submission and repo chat.
                </p>
              )}
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white/75">
              The backend currently exposes repo CRUD, rule CRUD, review
              submission, review detail, review SSE, and plain-text repo chat.
              Review history remains deferred until the backend adds a list
              route.
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Current status</CardTitle>
            <CardDescription>
              Local repo onboarding and review submission are live in this
              build. Server-backed review history is not yet available.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <div className="rounded-xl bg-muted/70 p-4">
              Review list remains intentionally deferred until the backend
              exposes a list route.
            </div>
            <div className="rounded-xl bg-muted/70 p-4">
              Repo chat will use chunked text streaming instead of SSE, matching
              the backend.
            </div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <Sparkles className="h-5 w-5 text-devreason-violet" />
            <CardTitle className="text-lg">Review orchestration</CardTitle>
            <CardDescription>
              Live agent progression, findings, and streamed report rendering.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <MessageSquareText className="h-5 w-5 text-devreason-teal" />
            <CardTitle className="text-lg">Repo chat</CardTitle>
            <CardDescription>
              Streaming answers over the repo's historical findings and project
              insight memory.
            </CardDescription>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <Settings2 className="h-5 w-5 text-devreason-amber" />
            <CardTitle className="text-lg">Architecture rules</CardTitle>
            <CardDescription>
              Repo-scoped rule authoring that feeds the architecture agent.
            </CardDescription>
          </CardHeader>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>Connect repository</CardTitle>
            <CardDescription>
              Connect a repository through the GitHub App install flow.
              DevReason stores installation metadata instead of asking you for a
              PAT.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AddRepoForm />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Submit review</CardTitle>
            <CardDescription>
              Choose a saved repo and a pull request URL. The review page will
              open the SSE stream immediately.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <p className="text-sm text-muted-foreground">
                Loading repositories...
              </p>
            ) : repos.length ? (
              <SubmitForm repos={repos} />
            ) : (
              <EmptyState
                icon={Link2}
                title="No repositories yet"
                description="Add a repository before you submit a pull request for review."
              />
            )}
          </CardContent>
        </Card>
      </section>

      {repos.length ? (
        <section>
          <Card>
            <CardHeader>
              <CardTitle>Registered repositories</CardTitle>
              <CardDescription>
                Selecting a repository updates the sidebar shortcuts and the
                default review target.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {repos.map((repo) => {
                const active = repo.id === selectedRepo?.id;
                return (
                  <button
                    key={repo.id}
                    type="button"
                    onClick={() => setSelectedRepo(repo.id)}
                    className={
                      active
                        ? "rounded-2xl border border-primary bg-primary/5 p-4 text-left"
                        : "rounded-2xl border p-4 text-left hover:bg-muted/60"
                    }
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-foreground">
                          {repo.owner}/{repo.name}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          Connected repository
                        </p>
                      </div>
                      {active ? <Badge>Active</Badge> : null}
                    </div>
                  </button>
                );
              })}
            </CardContent>
          </Card>
        </section>
      ) : null}
    </div>
  );
}
