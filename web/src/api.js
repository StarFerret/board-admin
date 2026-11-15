const DEFAULT_TIMEOUT_MS = 15000;

export async function api(path, options = {}) {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options;
  const headers = { ...(fetchOptions.headers || {}) };
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const body =
    fetchOptions.body && typeof fetchOptions.body === "object" && !(fetchOptions.body instanceof FormData)
      ? JSON.stringify(fetchOptions.body)
      : fetchOptions.body;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(path, {
      ...fetchOptions,
      headers,
      body,
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("The server took too long to answer. Try again.");
    }
    throw new Error(
      `Network error talking to ${window.location.host}. On other devices, use this PC's LAN IP and the same port shown in the address bar.`
    );
  } finally {
    clearTimeout(timer);
  }

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || res.statusText || "Request failed");
  }
  return data;
}

export const getHost = () => api("/api/settings/host");
export const setBoardName = (name) => api("/api/settings/board", { method: "POST", body: { name } });
export const getOllama = () => api("/api/settings/ollama");
export const setOllama = (base_url) => api("/api/settings/ollama", { method: "POST", body: { base_url } });
export const setOllamaModel = (model) =>
  api("/api/settings/ollama", { method: "POST", body: { model } });

/** Control site URL from the address the visitor came in on. */
export function controlUrl(path = "", controlPort) {
  const port = controlPort || 7411;
  const base =
    typeof window === "undefined"
      ? `http://127.0.0.1:${port}`
      : `${window.location.protocol}//${window.location.hostname}:${port}`;
  const suffix = path ? (path.startsWith("/") ? path : `/${path}`) : "/";
  return `${base}${suffix}`;
}

export async function getControlUrl(path = "") {
  try {
    const host = await getHost();
    return controlUrl(path, host.control_port);
  } catch {
    return controlUrl(path);
  }
}
export const listWorkspaces = () => api("/api/workspaces");
export const createWorkspace = (name) => api("/api/workspaces", { method: "POST", body: { name } });
export const getWorkspace = (id) => api(`/api/workspaces/${id}`);
export const renameWorkspace = (id, name) =>
  api(`/api/workspaces/${id}`, { method: "PATCH", body: { name } });
export const patchWorkspace = (id, body) =>
  api(`/api/workspaces/${id}`, { method: "PATCH", body });
export const deleteWorkspace = (id) => api(`/api/workspaces/${id}`, { method: "DELETE" });
export const browseWorkspace = (id, path = "") =>
  api(`/api/workspaces/${id}/browse?path=${encodeURIComponent(path || "")}`);
export const mkdirWorkspace = (id, path) =>
  api(`/api/workspaces/${id}/mkdir`, { method: "POST", body: { path } });
export const listTools = () => api("/api/tools");
export const addWorkspaceTool = (id, packId) =>
  api(`/api/workspaces/${id}/tools`, { method: "POST", body: { id: packId } });
export const removeWorkspaceTool = (id, packId) =>
  api(`/api/workspaces/${id}/tools/${packId}`, { method: "DELETE" });
export const listMcpServers = () => api("/api/mcp/servers");
export const importMcpServers = (json) =>
  api("/api/mcp/servers/import", { method: "POST", body: { json } });
export const createMcpServer = (body) =>
  api("/api/mcp/servers", { method: "POST", body });
export const patchMcpServer = (id, body) =>
  api(`/api/mcp/servers/${id}`, { method: "PATCH", body });
export const setMcpWorkspaces = (id, workspaces) =>
  api(`/api/mcp/servers/${id}/workspaces`, { method: "PUT", body: { workspaces } });
export const probeMcpServer = (id) =>
  api(`/api/mcp/servers/${id}/probe`, { method: "POST" });
export const deleteMcpServer = (id) =>
  api(`/api/mcp/servers/${id}`, { method: "DELETE" });
export const shareWorkspace = (id) =>
  api(`/api/workspaces/${id}/share`, { method: "POST" });
export const uploadWorkspaceFiles = (id, files, folder = "") => {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  if (folder) form.append("folder", folder);
  return api(`/api/workspaces/${id}/files`, { method: "POST", body: form });
};
export const deleteWorkspaceFile = (id, path) =>
  api(`/api/workspaces/${id}/files/${encodeURIComponent(path)}`, { method: "DELETE" });
export const moveAgent = (id, workspace_id) =>
  api(`/api/agents/${id}/move`, { method: "POST", body: { workspace_id } });
export const listAgents = (archived = false) =>
  api(archived ? "/api/agents?archived=1" : "/api/agents");
export const archiveAgent = (id) => api(`/api/agents/${id}/archive`, { method: "POST" });
export const restoreAgent = (id) => api(`/api/agents/${id}/restore`, { method: "POST" });
export const deleteAgent = (id) => api(`/api/agents/${id}`, { method: "DELETE" });
export const createAgent = (name, workspace = {}) =>
  api("/api/agents", { method: "POST", body: { name, ...workspace } });
export const getAgent = (id) => api(`/api/agents/${id}`);
export const patchAgent = (id, fields) => api(`/api/agents/${id}`, { method: "PATCH", body: fields });
export const sendMessage = (id, content, author = "", mode = "send") =>
  api(`/api/agents/${id}/messages`, {
    method: "POST",
    body: { content, author, mode },
  });
export const stopAgent = (id) => api(`/api/agents/${id}/stop`, { method: "POST", body: {} });
export const uploadFiles = (agentId, files, folder = "") => {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  if (folder) form.append("folder", folder);
  return api(`/api/agents/${agentId}/files`, { method: "POST", body: form });
};
export const deleteFile = (agentId, path) =>
  api(`/api/agents/${agentId}/files/${encodeURIComponent(path)}`, { method: "DELETE" });
export const createSchedule = (agentId, body) =>
  api(`/api/agents/${agentId}/schedules`, { method: "POST", body });
export const deleteSchedule = (agentId, scheduleId) =>
  api(`/api/agents/${agentId}/schedules/${scheduleId}`, { method: "DELETE" });
export const listSchedules = (agentId) => api(`/api/agents/${agentId}/schedules`);
