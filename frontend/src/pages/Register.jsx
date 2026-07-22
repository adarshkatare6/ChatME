import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Register() {
  const { user, register } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function submit() {
    setErr("");
    if (password.length < 8) return setErr("Password must be at least 8 characters.");
    setBusy(true);
    try {
      await register(email, password);
      nav("/");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-card">
      <h1>Create account</h1>
      {err && <div className="error">{err}</div>}
      <label>Email</label>
      <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="you@example.com" />
      <label>Password</label>
      <input
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        type="password"
        placeholder="min 8 characters"
        onKeyDown={(e) => e.key === "Enter" && submit()}
      />
      <button className="btn primary full" disabled={busy} onClick={submit}>
        {busy ? "Creating…" : "Create account"}
      </button>
      <p className="muted center">Have an account? <Link to="/login">Sign in</Link></p>
    </div>
  );
}
