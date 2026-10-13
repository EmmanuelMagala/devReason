import axios from "axios";
import { API_URL } from "@/config/constants";
import { getClerkToken } from "@/lib/clerk";

export const apiClient = axios.create({
  baseURL: API_URL,
  timeout: 20_000,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use(async (config) => {
  const token = await getClerkToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (
      error.response?.status === 401 &&
      typeof window !== "undefined" &&
      !window.location.pathname.startsWith("/sign-in")
    ) {
      window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(window.location.pathname + window.location.search)}`);
    }

    return Promise.reject(error);
  },
);
