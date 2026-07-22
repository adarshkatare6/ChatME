import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { user, login } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function submit() {
    setErr("");
    setBusy(true);
    try {
      await login(email, password);
      nav("/");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-card">
      <h1>Sign in</h1>
      {err && <div className="error">{err}</div>}
      <label>Email</label>
      <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="you@example.com" />
      <label>Password</label>
      <input
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        type="password"
        placeholder="••••••••"
        onKeyDown={(e) => e.key === "Enter" && submit()}
      />
      <button className="btn primary full" disabled={busy} onClick={submit}>
        {busy ? "Signing in…" : "Sign in"}
      </button>
      <p className="muted center">No account? <Link to="/register">Register</Link></p>
    </div>
  );
}
