import type { ApiErrorBody } from "@/types/api";
import { ApiClientError } from "./errors";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
let csrfToken: string | null = null;

function apiUrl(path: string): string {
  if (!API_BASE_URL) throw new Error("NEXT_PUBLIC_API_BASE_URL is not configured");
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function refreshCsrf(): Promise<string> {
  const response = await fetch(apiUrl("/api/v1/auth/csrf"), {
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) await throwApiError(response);
  const body = (await response.json()) as { csrf_token: string };
  csrfToken = body.csrf_token;
  return csrfToken;
}

async function throwApiError(response: Response): Promise<never> {
  let body: ApiErrorBody | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // Keep a safe fallback when an intermediary returns a non-JSON response.
  }
  throw new ApiClientError(
    body?.error.message ?? "The service could not complete the request.",
    body?.error.code ?? "REQUEST_FAILED",
    body?.error.request_id ?? response.headers.get("X-Request-ID"),
    response.status,
  );
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 15_000,
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const unsafe = !["GET", "HEAD", "OPTIONS"].includes(method);
  if (unsafe && !csrfToken) await refreshCsrf();

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body) headers.set("Content-Type", "application/json");
    if (unsafe && csrfToken) headers.set("X-CSRF-Token", csrfToken);
    const response = await fetch(apiUrl(path), {
      ...init,
      headers,
      credentials: "include",
      signal: init.signal ?? controller.signal,
      cache: "no-store",
    });
    if (!response.ok) await throwApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export function clearCsrf(): void {
  csrfToken = null;
}
