import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function Projects() {
  const nav = useNavigate();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [form, setForm] = useState({ name: "", system_prompt: "", model: "" });
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setProjects(await api.listProjects());
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function create() {
    if (!form.name.trim()) return;
    setCreating(true);
    setErr("");
    try {
      const p = await api.createProject(form);
      setForm({ name: "", system_prompt: "", model: "" });
      nav(`/projects/${p.id}`);
    } catch (e) {
      setErr(e.message);
    } finally {
      setCreating(false);
    }
  }

  async function remove(id, e) {
    e.stopPropagation();
    if (!confirm("Delete this agent and its history?")) return;
    await api.deleteProject(id);
    setProjects((ps) => ps.filter((p) => p.id !== id));
  }

  return (
    <div className="grid-2">
      <section>
        <h2>Your agents</h2>
        {err && <div className="error">{err}</div>}
        {loading ? (
          <div className="muted">Loading…</div>
        ) : projects.length === 0 ? (
          <div className="muted">No agents yet. Create one to start chatting.</div>
        ) : (
          <ul className="cards">
            {projects.map((p) => (
              <li key={p.id} className="card clickable" onClick={() => nav(`/projects/${p.id}`)}>
                <div className="card-head">
                  <strong>{p.name}</strong>
                  <button className="btn ghost danger sm" onClick={(e) => remove(p.id, e)}>Delete</button>
                </div>
                {p.description && <p className="muted">{p.description}</p>}
                <code className="chip">{p.model || "default model"}</code>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <h2>New agent</h2>
        <label>Name</label>
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Support Bot" />
        <label>System prompt</label>
        <textarea
          rows={5}
          value={form.system_prompt}
          onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
          placeholder="You are a concise, helpful assistant…"
        />
        <label>Model override <span className="muted">(optional)</span></label>
        <input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="openai/gpt-4o-mini" />
        <button className="btn primary full" disabled={creating} onClick={create}>
          {creating ? "Creating…" : "Create agent"}
        </button>
      </section>
    </div>
  );
}
