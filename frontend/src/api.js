// Single source of truth for backend calls. Base URL is proxied via Vite in dev
// (/api -> :8000). In production set VITE_API_BASE to the deployed API origin.
const BASE = import.meta.env.VITE_API_BASE ?? "/api";
const TOKEN_KEY = "cbp_token";

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

async function request(path, { method = "GET", body, form, auth = true } = {}) {
  const headers = {};
  const token = tokenStore.get();
  if (auth && token) headers["Authorization"] = `Bearer ${token}`;

  let payload = body;
  if (body !== undefined && !form) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (form) payload = form; // FormData: let the browser set the boundary

  const res = await fetch(`${BASE}${path}`, { method, headers, body: payload });

  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail;
    const msg = Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : detail;
    throw new Error(msg || `Request failed (${res.status})`);
  }
  return data;
}

export const api = {
  // auth
  register: (email, password) =>
    request("/auth/register", { method: "POST", body: { email, password }, auth: false }),
  login: async (email, password) => {
    // OAuth2 password flow expects form-encoded username/password.
    const form = new URLSearchParams({ username: email, password });
    const res = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data?.detail || "Login failed");
    return data; // { access_token, token_type }
  },
  me: () => request("/auth/me"),

  // projects
  listProjects: () => request("/projects"),
  createProject: (p) => request("/projects", { method: "POST", body: p }),
  getProject: (id) => request(`/projects/${id}`),
  updateProject: (id, p) => request(`/projects/${id}`, { method: "PATCH", body: p }),
  deleteProject: (id) => request(`/projects/${id}`, { method: "DELETE" }),

  // prompts
  listPrompts: (pid) => request(`/projects/${pid}/prompts`),
  createPrompt: (pid, p) => request(`/projects/${pid}/prompts`, { method: "POST", body: p }),
  deletePrompt: (pid, id) => request(`/projects/${pid}/prompts/${id}`, { method: "DELETE" }),

  // conversations & chat
  listConversations: (pid) => request(`/projects/${pid}/conversations`),
  getConversationMessages: (pid, convId) =>
    request(`/projects/${pid}/conversations/${convId}/messages`),
  sendMessage: (pid, convId, content, promptIds = []) =>
    request(`/projects/${pid}/conversations/${convId}/messages`, {
      method: "POST",
      body: { content, prompt_ids: promptIds },
    }),
  deleteConversation: (pid, convId) =>
    request(`/projects/${pid}/conversations/${convId}`, { method: "DELETE" }),

  // files

  listFiles: (pid) => request(`/projects/${pid}/files`),
  uploadFile: (pid, file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/projects/${pid}/files`, { method: "POST", form: fd });
  },
  deleteFile: (pid, id) => request(`/projects/${pid}/files/${id}`, { method: "DELETE" }),
};
