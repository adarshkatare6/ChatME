import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";

export default function Chat() {
  const { id } = useParams();
  const pid = Number(id);

  const [project, setProject] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState("new");
  const [messages, setMessages] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState(new Set()); // prompt_ids folded into next turn

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const scrollRef = useRef(null);

  async function loadAll() {
    try {
      const [p, convs, pr, f] = await Promise.all([
        api.getProject(pid),
        api.listConversations(pid),
        api.listPrompts(pid),
        api.listFiles(pid),
      ]);
      setProject(p);
      setConversations(convs);
      setPrompts(pr);
      setFiles(f);

      if (convs.length > 0) {
        const firstConvId = convs[0].id;
        setActiveConvId(firstConvId);
        const msgs = await api.getConversationMessages(pid, firstConvId);
        setMessages(msgs);
      } else {
        setActiveConvId("new");
        setMessages([]);
      }
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    loadAll();
    /* eslint-disable-next-line */
  }, [pid]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  async function selectConversation(convId) {
    if (convId === activeConvId) return;
    setActiveConvId(convId);
    setErr("");
    if (convId === "new") {
      setMessages([]);
    } else {
      try {
        const msgs = await api.getConversationMessages(pid, convId);
        setMessages(msgs);
      } catch (e) {
        setErr(e.message);
      }
    }
  }

  async function send() {
    const content = input.trim();
    if (!content || sending) return;
    setErr("");
    setSending(true);

    const optimistic = { id: `tmp-${Date.now()}`, role: "user", content };
    setMessages((ms) => [...ms, optimistic]);
    setInput("");

    try {
      const res = await api.sendMessage(pid, activeConvId, content, [...selected]);
      setMessages((ms) => [
        ...ms.filter((x) => x.id !== optimistic.id),
        res.user_message,
        res.assistant_message,
      ]);

      if (activeConvId === "new") {
        setActiveConvId(res.conversation_id);
      }

      // Refresh conversations sidebar list
      const updatedConvs = await api.listConversations(pid);
      setConversations(updatedConvs);
    } catch (e) {
      setMessages((ms) => ms.filter((x) => x.id !== optimistic.id));
      setErr(e.message);
      setInput(content);
    } finally {
      setSending(false);
    }
  }

  async function delConversation(e, convId) {
    e.stopPropagation();
    if (!confirm("Delete this conversation?")) return;
    try {
      await api.deleteConversation(pid, convId);
      const updated = conversations.filter((c) => c.id !== convId);
      setConversations(updated);

      if (activeConvId === convId) {
        if (updated.length > 0) {
          selectConversation(updated[0].id);
        } else {
          selectConversation("new");
        }
      }
    } catch (e2) {
      setErr(e2.message);
    }
  }

  function toggle(promptId) {
    setSelected((s) => {
      const n = new Set(s);
      n.has(promptId) ? n.delete(promptId) : n.add(promptId);
      return n;
    });
  }

  async function addPrompt() {
    const name = prompt("Prompt name?");
    if (!name) return;
    const content = prompt("Prompt content?");
    if (!content) return;
    const created = await api.createPrompt(pid, { name, content });
    setPrompts((ps) => [...ps, created]);
  }

  async function delPrompt(pmid) {
    await api.deletePrompt(pid, pmid);
    setPrompts((ps) => ps.filter((p) => p.id !== pmid));
    setSelected((s) => {
      const n = new Set(s);
      n.delete(pmid);
      return n;
    });
  }

  async function onUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const rec = await api.uploadFile(pid, file);
      setFiles((fs) => [...fs, rec]);
    } catch (e2) {
      setErr(e2.message);
    } finally {
      e.target.value = "";
    }
  }

  async function delFile(fid) {
    await api.deleteFile(pid, fid);
    setFiles((fs) => fs.filter((f) => f.id !== fid));
  }

  if (!project) return <div className="muted">{err || "Loading…"}</div>;

  return (
    <div className="chat-layout">
      <aside className="sidebar">
        <Link to="/" className="muted">
          ← All agents
        </Link>
        <h3>{project.name}</h3>
        <code className="chip">{project.model || "default model"}</code>

        {/* Conversations History Section */}
        <div className="side-section">
          <div className="side-head">
            <span>Conversations</span>
            <button
              className="btn ghost sm"
              onClick={() => selectConversation("new")}
            >
              + New Chat
            </button>
          </div>
          {conversations.length === 0 && (
            <p className="muted sm">No conversations yet.</p>
          )}
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`conv-row ${c.id === activeConvId ? "active" : ""}`}
              onClick={() => selectConversation(c.id)}
            >
              <span title={c.title} className="conv-title">
                {c.title}
              </span>
              <button
                className="btn ghost danger sm"
                onClick={(e) => delConversation(e, c.id)}
                title="Delete thread"
              >
                ×
              </button>
            </div>
          ))}
        </div>

        {/* Prompt Templates Section */}
        <div className="side-section">
          <div className="side-head">
            <span>Prompt templates</span>
            <button className="btn ghost sm" onClick={addPrompt}>
              + Add
            </button>
          </div>
          {prompts.length === 0 && (
            <p className="muted sm">
              None. Selected templates are injected as system context.
            </p>
          )}
          {prompts.map((p) => (
            <label key={p.id} className="prompt-row">
              <input
                type="checkbox"
                checked={selected.has(p.id)}
                onChange={() => toggle(p.id)}
              />
              <span title={p.content}>{p.name}</span>
              <button
                className="btn ghost danger sm"
                onClick={() => delPrompt(p.id)}
              >
                ×
              </button>
            </label>
          ))}
        </div>

        {/* Files Section */}
        <div className="side-section">
          <div className="side-head">
            <span>Files</span>
            <label className="btn ghost sm file-btn">
              + Upload
              <input type="file" hidden onChange={onUpload} />
            </label>
          </div>
          {files.length === 0 && <p className="muted sm">No files uploaded.</p>}
          {files.map((f) => (
            <div key={f.id} className="file-row">
              <span title={f.filename}>{f.filename}</span>
              <button
                className="btn ghost danger sm"
                onClick={() => delFile(f.id)}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="chat-main">
        <div className="messages" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="muted center">Start the conversation.</div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={`bubble ${m.role}`}>
              <div className="role">{m.role}</div>
              <div className="content">{m.content}</div>
            </div>
          ))}
          {sending && (
            <div className="bubble assistant">
              <div className="role">assistant</div>
              <div className="content muted">…</div>
            </div>
          )}
        </div>

        {err && <div className="error">{err}</div>}

        <div className="composer">
          <textarea
            rows={2}
            value={input}
            placeholder="Message the agent…  (Enter to send, Shift+Enter for newline)"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button
            className="btn primary"
            disabled={sending || !input.trim()}
            onClick={send}
          >
            Send
          </button>
        </div>
      </section>
    </div>
  );
}
