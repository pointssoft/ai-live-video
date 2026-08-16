import type { AuthResponse, User } from "@/types/api";
import { apiRequest, clearCsrf, refreshCsrf } from "./api-client";

export async function register(email: string, password: string): Promise<User> {
  await refreshCsrf();
  const result = await apiRequest<AuthResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  clearCsrf();
  return result.user;
}

export async function login(email: string, password: string): Promise<User> {
  await refreshCsrf();
  const result = await apiRequest<AuthResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  clearCsrf();
  return result.user;
}

export async function logout(): Promise<void> {
  await refreshCsrf();
  await apiRequest<void>("/api/v1/auth/logout", { method: "POST" });
  clearCsrf();
}

export async function currentUser(): Promise<User> {
  return apiRequest<User>("/api/v1/me");
}
