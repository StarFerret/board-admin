const DEFAULT_TIMEOUT_MS = 60000;
const TOKEN_KEY = "starferret_control_token";

export function getControlToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setControlToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export async function controlApi(path, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;
  const headers = { ...(fetchOptions.headers || {}) };
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const token = getControlToken();
  if (token && !headers.Authorization) {
    headers.Authorization = `Bearer ${token}`;
  }
  const body =
    fetchOptions.body && typeof fetchOptions.body === "object" && !(fetchOptions.body instanceof FormData)
      ? JSON.stringify(fetchOptions.body)
      : fetchOptions.body;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`/api/control${path}`, {
      ...fetchOptions,
      headers,
      body,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Control took too long to answer.");
    }
    throw new Error("Network error talking to Control.");
  } finally {
    clearTimeout(timer);
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) setControlToken("");
    const error = new Error(data.error || res.statusText || "Request failed");
    error.status = res.status;
    error.data = data;
    throw error;
  }
  return data;
}

export const getControlMeta = () => controlApi("/meta");
export const getControlHealth = () => controlApi("/health");
export async function bootstrapAdmin(body) {
  const data = await controlApi("/bootstrap", { method: "POST", body });
  if (data.token) setControlToken(data.token);
  return data;
}
export async function loginControl(body) {
  const data = await controlApi("/login", { method: "POST", body });
  if (data.token) setControlToken(data.token);
  return data;
}
export async function logoutControl() {
  try {
    await controlApi("/logout", { method: "POST", body: {} });
  } finally {
    setControlToken("");
  }
}
export const resetControlAdmin = (body) => controlApi("/reset-admin", { method: "POST", body });
export const getControlMe = () => controlApi("/me");
export const listControlUsers = () => controlApi("/users");
export const createControlUser = (body) => controlApi("/users", { method: "POST", body });
export const patchControlUser = (id, body) => controlApi(`/users/${id}`, { method: "PATCH", body });
export const deleteControlUser = (id) => controlApi(`/users/${id}`, { method: "DELETE" });
export const getControlUsage = (days = 30) => controlApi(`/usage?days=${days}`);
export const listControlApps = () => controlApi("/apps");
export const startControlApp = (id) => controlApi(`/apps/${id}/start`, { method: "POST", body: {} });
export const stopControlApp = (id) => controlApi(`/apps/${id}/stop`, { method: "POST", body: {} });
export const updateControlApp = (id) => controlApi(`/apps/${id}/update`, { method: "POST", body: {}, timeoutMs: 600000 });
export const listControlModels = () => controlApi("/models");
// Starts a background download and returns at once. Progress comes from listControlPulls.
export const pullControlModel = (name) => controlApi("/models/pull", { method: "POST", body: { name } });
export const listControlPulls = () => controlApi("/models/pulls");
export const deleteControlModel = (name) =>
  controlApi("/models/delete", { method: "POST", body: { name } });
export const setBoardDefaultModel = (name) =>
  controlApi("/models/default", { method: "POST", body: { name } });
export const getBoardOllama = () => controlApi("/board/ollama");
export const setBoardOllama = (body) => controlApi("/board/ollama", { method: "POST", body });
export const setBoardOllamaModel = (model) =>
  controlApi("/board/ollama", { method: "POST", body: { model } });
export const getControlMachine = () => controlApi("/machine");
export const getControlMetrics = () => controlApi("/metrics", { timeoutMs: 15000 });
export const getControlCapacity = () => controlApi("/capacity", { timeoutMs: 15000 });
export const measureControlCapacity = (models = "default") =>
  controlApi("/capacity/measure", { method: "POST", body: { models }, timeoutMs: 15000 });
export const getControlPeople = () => controlApi("/people");
export const getControlUpdates = () => controlApi("/updates", { timeoutMs: 8000 });
export const checkControlUpdates = () => controlApi("/updates/check", { method: "POST", body: {}, timeoutMs: 20000 });
export const applyControlUpdate = () => controlApi("/updates/apply", { method: "POST", body: {} });
export const undoControlUpdate = () => controlApi("/updates/back", { method: "POST", body: {} });
export const startBoardProcess = () => controlApi("/board/start", { method: "POST", body: {} });
export const stopBoardProcess = () => controlApi("/board/stop", { method: "POST", body: {} });
export const getBoardLogs = () => controlApi("/board/logs");
