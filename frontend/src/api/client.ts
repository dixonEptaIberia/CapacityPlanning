import axios, { AxiosError } from "axios";
import type { ApiError } from "../types";

// In dev, the selected user is stored locally and sent as X-User (dev auth).
// In production this would be replaced by a Cognito bearer token.
const USER_KEY = "cpp.devUser";

export function getDevUser(): string {
  return localStorage.getItem(USER_KEY) ?? "admin";
}

export function setDevUser(username: string): void {
  localStorage.setItem(USER_KEY, username);
}

export const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  config.headers.set("X-User", getDevUser());
  return config;
});

/** Extract a user-friendly message from a backend error envelope (R4.3). */
export function errorMessage(err: unknown): string {
  const axiosErr = err as AxiosError<ApiError>;
  if (axiosErr.response?.data?.error?.message) {
    return axiosErr.response.data.error.message;
  }
  if (axiosErr.message) return axiosErr.message;
  return "An unexpected error occurred.";
}
