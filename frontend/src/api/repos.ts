import { API_URL } from "@/config/constants";
import { apiClient } from "@/api/client";
import { adaptRepo, adaptRule } from "@/lib/adapters";
import { getClerkToken } from "@/lib/clerk";
import type {
  ArchRule,
  ArchRuleCreate,
  GitHubAppAccessibleReposResponse,
  GitHubAppInstallComplete,
  GitHubAppInstallStart,
  GitHubAppInstallStartResponse,
  GitHubAppInstallSync,
  GitHubAppInstallSyncResponse,
  Repo,
} from "@/types";

export const reposApi = {
  async startGitHubInstall(
    data: GitHubAppInstallStart,
  ): Promise<GitHubAppInstallStartResponse> {
    const response = await apiClient.post("/api/auth/github/start", {
      repo_id: data.repoId,
    });
    return {
      installUrl: response.data.install_url,
      existingInstallationId: response.data.existing_installation_id,
      existingInstallationManageUrl:
        response.data.existing_installation_manage_url,
    };
  },

  async listGitHubInstallRepos(
    installationId: number,
    state: string,
  ): Promise<GitHubAppAccessibleReposResponse> {
    const response = await apiClient.get("/api/auth/github/repositories", {
      params: {
        installation_id: installationId,
        state,
      },
    });
    return {
      installationId: response.data.installation_id,
      repositories: response.data.repositories,
    };
  },

  async syncGitHubInstallRepos(
    data: GitHubAppInstallSync,
  ): Promise<GitHubAppInstallSyncResponse> {
    const response = await apiClient.post("/api/auth/github/sync", {
      installation_id: data.installationId,
      state: data.state,
    });
    return {
      installationId: response.data.installation_id,
      repositories: response.data.repositories.map(adaptRepo),
      importedCount: response.data.imported_count,
    };
  },

  async completeGitHubInstall(data: GitHubAppInstallComplete): Promise<Repo> {
    const response = await apiClient.post("/api/auth/github/complete", {
      installation_id: data.installationId,
      state: data.state,
      owner: data.owner,
      name: data.name,
    });
    return adaptRepo(response.data);
  },

  async list(): Promise<Repo[]> {
    const response = await apiClient.get("/api/repos");
    return response.data.map(adaptRepo);
  },

  async getRules(repoId: string): Promise<ArchRule[]> {
    const response = await apiClient.get(`/api/repos/${repoId}/rules`);
    return response.data.map(adaptRule);
  },

  async addRule(repoId: string, data: ArchRuleCreate): Promise<ArchRule> {
    const response = await apiClient.post(`/api/repos/${repoId}/rules`, data);
    return adaptRule(response.data);
  },

  async streamChat(
    repoId: string,
    message: string,
    onChunk: (chunk: string) => void,
    signal?: AbortSignal,
  ) {
    const token = await getClerkToken();
    const response = await fetch(`${API_URL}/api/repos/${repoId}/chat`, {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message }),
    });

    if (!response.ok) {
      throw new Error(`Chat request failed with status ${response.status}`);
    }

    if (!response.body) {
      throw new Error("Chat response did not include a readable stream");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      onChunk(decoder.decode(value, { stream: true }));
    }
  },
};
