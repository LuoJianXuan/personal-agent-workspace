import type { User, Token } from "./contracts/models";
import { validate } from "./contracts/validate";
let token = sessionStorage.getItem("workspace.token");
export function setToken(value: string | null) {
  token = value;
  if (value) sessionStorage.setItem("workspace.token", value);
  else sessionStorage.removeItem("workspace.token");
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId: string,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch("/api" + path, {
      ...init,
      headers,
      signal: controller.signal,
    });
    const isJson = response.headers
      .get("content-type")
      ?.includes("application/json");
    if (!isJson)
      throw new ApiError(
        response.status,
        "SERVICE_UNAVAILABLE",
        "服务暂不可用，请稍后重试",
        response.headers.get("X-Request-ID") || "",
      );
    const data = await response.json().catch(() => {
      throw new ApiError(
        response.status,
        "INVALID_RESPONSE",
        "服务响应异常，请稍后重试",
        "",
      );
    });
    if (!response.ok) {
      if (response.status === 401 && path != "/auth/login") {
        setToken(null);
        window.dispatchEvent(new Event("workspace:unauthorized"));
      }
      throw new ApiError(
        response.status,
        data.code || "REQUEST_FAILED",
        data.message || "请求失败",
        data.request_id || "",
      );
    }
    return data as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError")
      throw new ApiError(
        0,
        "REQUEST_TIMEOUT",
        "请求超时，请检查连接后重试",
        "",
      );
    throw new ApiError(0, "NETWORK_ERROR", "连接失败，请检查网络后重试", "");
  } finally {
    clearTimeout(timer);
  }
}
export async function me() {
  return validate<User>("User", await api("/auth/me"));
}
export async function login(values: { username: string; password: string }) {
  return validate<Token>(
    "Token",
    await api("/auth/login", { method: "POST", body: JSON.stringify(values) }),
  );
}

export function authHeaders() {
  return token ? { Authorization: `Bearer ${token}` } : { Authorization: "" };
}

export async function downloadFile(id: string, name: string) {
  const response = await fetch(`/api/files/${id}/download`, { headers: authHeaders() });
  if (!response.ok) throw Error(`下载失败（${response.status}）`);
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
