import { Navigate, Link, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Projects from "./pages/Projects.jsx";
import Chat from "./pages/Chat.jsx";

function Protected({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <div className="center muted">Loading…</div>;
  return user ? children : <Navigate to="/login" replace />;
}

function TopBar() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user) return null;
  return (
    <header className="topbar">
      <Link to="/" className="brand">◆ Chatbot Platform</Link>
      <div className="topbar-right">
        <span className="muted">{user.email}</span>
        <button className="btn ghost" onClick={() => { logout(); nav("/login"); }}>Log out</button>
      </div>
    </header>
  );
}

export default function App() {
  return (
    <>
      <TopBar />
      <main className="container">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/" element={<Protected><Projects /></Protected>} />
          <Route path="/projects/:id" element={<Protected><Chat /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  );
}
