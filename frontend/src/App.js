import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate, useParams, Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { Activity, AlertTriangle, ArrowRight, BarChart3, Beaker, ChevronRight, ClipboardList, FileText, FolderKanban, Globe, LogOut, Menu, Moon, Plus, ShieldCheck, Sun, X } from "lucide-react";
import axios from "axios";
import "@/App.css";
import ProjectDetailView, { SharedProject } from "@/ProjectDetail";
import { LanguageProvider, useLanguage } from "@/i18n";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const api = axios.create({ baseURL: API, withCredentials: true });

function Brand({ compact = false }) {
  const { t } = useLanguage();
  return <Link to="/dashboard" className={`brand ${compact ? "brand-compact" : ""}`} data-testid="brand-home-link"><img src="/assets/logo.svg" alt="CQAS logo" data-testid="brand-logo" /><span>{compact ? t("brand.short") : t("brand.long")}</span></Link>;
}

function useTheme() {
  const [dark, setDark] = useState(localStorage.getItem("cqas-theme") === "dark");
  useEffect(() => { document.documentElement.dataset.theme = dark ? "dark" : "light"; localStorage.setItem("cqas-theme", dark ? "dark" : "light"); }, [dark]);
  return [dark, () => setDark((value) => !value)];
}

function AuthPage({ register = false, onAuth }) {
  const { t } = useLanguage();
  const [form, setForm] = useState({ email: "admin@cqas.local", password: "admin123", name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await api.post(`/auth/${register ? "register" : "login"}`, form);
      onAuth(response.data);
      navigate("/dashboard");
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((item) => item.msg).join(" ") : detail || t("auth.genericError"));
    } finally { setBusy(false); }
  };
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const google = () => {
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };
  return (
    <main className="auth-shell">
      <LanguageBadge />
      <div className="auth-art">
        <Brand />
        <div className="art-copy">
          <span className="eyebrow">{t("auth.artEyebrow")}</span>
          <h1>{t("auth.artTitle1")} <em>{t("auth.artTitle2")}</em></h1>
          <p>{t("auth.artSub")}</p>
        </div>
        <div className="art-foot">{t("auth.artFoot")}</div>
      </div>
      <section className="auth-panel">
        <div className="auth-panel-inner">
          <span className="eyebrow">{register ? t("auth.eyebrowRegister") : t("auth.eyebrowLogin")}</span>
          <h2>{register ? t("auth.create") : t("auth.welcome")}</h2>
          <p className="muted">{register ? t("auth.subRegister") : t("auth.subLogin")}</p>
          <form onSubmit={submit} data-testid="auth-form">
            {register && <label>{t("auth.name")}<input data-testid="auth-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("auth.namePlaceholder")} /></label>}
            <label>{t("auth.email")}<input data-testid="auth-email-input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
            <label>{t("auth.password")}<input data-testid="auth-password-input" type="password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
            {error && <div className="error-box" data-testid="auth-error-message">{error}</div>}
            <button className="button button-primary button-wide" disabled={busy} data-testid="auth-submit-button">{busy ? t("auth.checking") : register ? t("auth.linkRegister") : t("auth.signIn")} <ArrowRight size={17} /></button>
          </form>
          <div className="auth-divider"><span>{t("auth.or")}</span></div>
          <button type="button" className="button button-outline button-wide" onClick={google} data-testid="google-signin-button"><svg width="17" height="17" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.3 2 30 0 24 0 14.7 0 6.7 5.4 2.7 13.3l7.8 6C12.4 13.3 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.2-.4-4.7H24v9h12.7c-.5 3-2.2 5.5-4.7 7.2l7.3 5.7c4.3-3.9 6.7-9.7 6.7-17.2z"/><path fill="#FBBC05" d="M10.5 28.7c-.5-1.5-.8-3.1-.8-4.7s.3-3.2.8-4.7l-7.8-6C.9 16.6 0 20.2 0 24s.9 7.4 2.7 10.7l7.8-6z"/><path fill="#34A853" d="M24 48c6 0 11-2 14.7-5.3l-7.3-5.7c-2 1.4-4.6 2.2-7.4 2.2-6.3 0-11.6-3.8-13.5-9.5l-7.8 6C6.7 42.6 14.7 48 24 48z"/></svg> {t("auth.google")}</button>
          <div className="auth-switch">{register ? t("auth.switchToLogin") : t("auth.switchToRegister")} <Link to={register ? "/login" : "/register"} data-testid="auth-switch-link">{register ? t("auth.linkLogin") : t("auth.linkRegister")}</Link></div>
          <div className="auth-note"><ShieldCheck size={16} /> {t("auth.noteBoth")}</div>
        </div>
      </section>
    </main>
  );
}

function LanguageBadge() {
  const { lang, setLang, t } = useLanguage();
  return (
    <button type="button" className="lang-badge" onClick={() => setLang(lang === "en" ? "id" : "en")} data-testid="language-badge" title={t("shell.language")}>
      <Globe size={14} /> {lang === "en" ? "EN" : "ID"}
    </button>
  );
}

function LanguageToggle() {
  const { lang, setLang } = useLanguage();
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      <button type="button" className={lang === "en" ? "active" : ""} onClick={() => setLang("en")} data-testid="language-set-en">EN</button>
      <button type="button" className={lang === "id" ? "active" : ""} onClick={() => setLang("id")} data-testid="language-set-id">ID</button>
    </div>
  );
}

function GoogleCallback({ onAuth }) {
  const { t } = useLanguage();
  const location = useLocation();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  useEffect(() => {
    const params = new URLSearchParams(location.hash.replace(/^#/, ""));
    const sessionId = params.get("session_id");
    if (!sessionId) { navigate("/login"); return; }
    window.history.replaceState({}, "", location.pathname);
    api.post("/auth/google/session", null, { headers: { "X-Session-ID": sessionId } })
      .then((response) => { onAuth(response.data); navigate("/dashboard"); })
      .catch(() => setError(t("auth.googleError")));
  }, [location, navigate, onAuth, t]);
  return <main className="shared-shell"><h1>{error || t("auth.googleCompleting")}</h1></main>;
}

function Sidebar({ open, close, user, onLogout }) {
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [dark, toggleTheme] = useTheme();
  const items = [["/dashboard", t("nav.overview"), Activity], ["/projects", t("nav.projects"), FolderKanban], ["/about", t("nav.about"), ClipboardList]];
  return (
    <>
      <div className={`sidebar-overlay ${open ? "show" : ""}`} onClick={close} />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="side-top"><Brand compact /><button className="icon-button mobile-only" onClick={close} data-testid="sidebar-close-button"><X size={19} /></button></div>
        <nav>{items.map(([path, label, Icon]) => <Link key={path} to={path} onClick={close} className="nav-item" data-testid={`nav-${path.replace("/", "")}`}><Icon size={18} />{label}</Link>)}</nav>
        <div className="side-bottom">
          <div className="side-controls">
            <button className="theme-button" onClick={toggleTheme} data-testid="theme-toggle-button">{dark ? <Sun size={17} /> : <Moon size={17} />}{dark ? t("shell.themeLight") : t("shell.themeDark")}</button>
            <LanguageToggle />
          </div>
          <div className="user-chip"><span className="avatar">{(user?.name || "A").slice(0, 1).toUpperCase()}</span><div><strong data-testid="current-user-name">{user?.name}</strong><small>{user?.email}</small></div><button className="logout-button" onClick={async () => { await api.post("/auth/logout"); onLogout(); navigate("/login"); }} data-testid="logout-button"><LogOut size={16} /></button></div>
        </div>
      </aside>
    </>
  );
}

function Shell({ user, onLogout, children }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  return (
    <div className="app-shell">
      <Sidebar open={open} close={() => setOpen(false)} user={user} onLogout={onLogout} />
      <div className="main-area">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setOpen(true)} data-testid="mobile-menu-button"><Menu size={20} /></button>
          <div className="breadcrumb">CQAS <ChevronRight size={14} /> <span>{t("shell.workspace")}</span></div>
          <div className="topbar-tag"><span className="status-dot" /> {t("shell.systemReady")}</div>
        </header>
        {children}
      </div>
    </div>
  );
}

function Dashboard() {
  const { t } = useLanguage();
  const [data, setData] = useState(null);
  const navigate = useNavigate();
  useEffect(() => { api.get("/dashboard").then((res) => setData(res.data)).catch(() => setData({ counts: {}, statuses: {}, projects: [] })); }, []);
  const cards = data ? [["projects", "dash.stat.projects", FolderKanban, "01"], ["documents", "dash.stat.documents", FileText, "02"], ["slump", "dash.stat.slump", Beaker, "03"], ["strength", "dash.stat.strength", BarChart3, "04"]] : [];
  const bars = data ? Object.entries(data.statuses || {}).map(([name, value]) => ({ name: t(`status.${name}`), value })) : [];
  return (
    <main className="page">
      <div className="page-heading">
        <div><span className="eyebrow">{t("dash.eyebrow")}</span><h1>{t("dash.greeting")} <em>{data?.projects?.[0]?.name?.split(" ")[0] || "engineer"}.</em></h1><p className="muted">{t("dash.subtitle")}</p></div>
        <button className="button button-primary" onClick={() => navigate("/projects/new")} data-testid="new-project-button"><Plus size={18} /> {t("dash.newProject")}</button>
      </div>
      <div className="stat-grid">{cards.map(([key, labelKey, Icon, number]) => <div className="stat-card" key={key} data-testid={`dashboard-stat-${key}`}><div className="stat-index">{number}</div><Icon size={21} /><strong>{data?.counts?.[key] ?? "—"}</strong><span>{t(labelKey)}</span></div>)}</div>
      <div className="dashboard-grid">
        <section className="panel chart-panel">
          <div className="panel-head"><div><span className="eyebrow">{t("dash.status.eyebrow")}</span><h3>{t("dash.status.title")}</h3></div><Link to="/projects" className="text-link" data-testid="dashboard-projects-link">{t("dash.viewProjects")} <ArrowRight size={15} /></Link></div>
          <div className="chart-wrap">{data && <ResponsiveContainer width="100%" height="100%"><BarChart data={bars} layout="vertical" margin={{ left: 18, right: 20 }}><XAxis type="number" hide /><YAxis type="category" dataKey="name" width={140} tick={{ fill: "var(--muted)", fontSize: 11 }} /><Tooltip cursor={{ fill: "var(--wash)" }} /><Bar dataKey="value" fill="var(--orange)" radius={[0, 2, 2, 0]} barSize={24} /></BarChart></ResponsiveContainer>}</div>
        </section>
        <section className="panel activity-panel">
          <div className="panel-head"><div><span className="eyebrow">{t("dash.active.eyebrow")}</span><h3>{t("dash.active.title")}</h3></div></div>
          {(data?.projects || []).slice(0, 3).map((project) => <Link className="project-row" to={`/projects/${project.id}`} key={project.id} data-testid={`project-row-${project.id}`}><span className="project-mark">{project.name.slice(0, 1)}</span><span><strong>{project.name}</strong><small>{project.code || t("projects.uncoded")} · {project.location || t("projects.locationPending")}</small></span><ChevronRight size={17} /></Link>)}
          {!data?.projects?.length && <div className="empty-state">{t("dash.emptyProjects")}</div>}
        </section>
      </div>
      <div className="notice"><AlertTriangle size={18} /><span><strong>{t("dash.engineeringNote")}</strong> {t("dash.disclaimer")}</span></div>
    </main>
  );
}

function Projects({ user }) {
  const { t } = useLanguage();
  const [projects, setProjects] = useState([]);
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", location: "", description: "" });
  const navigate = useNavigate();
  useEffect(() => { api.get("/projects").then((res) => setProjects(res.data)); }, []);
  const create = async (e) => { e.preventDefault(); const res = await api.post("/projects", form); navigate(`/projects/${res.data.id}`); };
  return (
    <main className="page">
      <div className="page-heading">
        <div><span className="eyebrow">{t("projects.eyebrow")}</span><h1>{t("projects.title1")} <em>{t("projects.title2")}</em></h1><p className="muted">{t("projects.subtitle")}</p></div>
        <button className="button button-primary" onClick={() => setShow(true)} data-testid="projects-new-button"><Plus size={18} /> {t("projects.new")}</button>
      </div>
      <div className="project-list">
        {projects.map((project) => (
          <button className="project-card" key={project.id} onClick={() => navigate(`/projects/${project.id}`)} data-testid={`project-card-${project.id}`}>
            <div className="project-card-top"><span className="project-mark large">{project.name.slice(0, 1)}</span><span className="project-code">{project.code || t("projects.uncoded")}</span></div>
            <h3>{project.name}</h3>
            <p>{project.description || t("projects.noDescription")}</p>
            <div className="project-meta"><span>{project.location || t("projects.locationPending")}</span><span>{project.members?.length || 1} {t("projects.memberSingular")}</span></div>
          </button>
        ))}
        {!projects.length && <div className="empty-state">{t("projects.empty")}</div>}
      </div>
      {show && (
        <div className="modal-backdrop">
          <form className="modal" onSubmit={create}>
            <button type="button" className="modal-close" onClick={() => setShow(false)} data-testid="new-project-close-button"><X size={18} /></button>
            <span className="eyebrow">{t("projects.new")}</span><h2>{t("projects.newTitle")}</h2>
            <label>{t("projects.name")}<input required data-testid="project-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("projects.namePlaceholder")} /></label>
            <div className="form-row">
              <label>{t("projects.code")}<input data-testid="project-code-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="NBS-01" /></label>
              <label>{t("projects.location")}<input data-testid="project-location-input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder={t("projects.locationPlaceholder")} /></label>
            </div>
            <label>{t("projects.description")}<textarea data-testid="project-description-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder={t("projects.descriptionPlaceholder")} /></label>
            <button className="button button-primary button-wide" data-testid="create-project-submit-button">{t("projects.create")} <ArrowRight size={17} /></button>
          </form>
        </div>
      )}
    </main>
  );
}

function About() {
  const { t } = useLanguage();
  return (
    <main className="page about-page">
      <span className="eyebrow">{t("about.eyebrow")}</span>
      <h1>{t("about.title1")} <em>{t("about.title2")}</em> {t("about.title3")}</h1>
      <p className="lead">{t("about.lead")}</p>
      <div className="about-grid">
        <div className="panel"><ShieldCheck size={24} className="orange-icon" /><h3>{t("about.disclaimerTitle")}</h3><p className="muted">{t("about.disclaimer")}</p></div>
        <div className="panel"><h3>{t("about.developedBy")}</h3><p className="contact-name">Nathan</p><p className="muted">{t("about.program")}</p><a href="mailto:nathannnforsomeone@gmail.com" data-testid="contact-email-link">nathannnforsomeone@gmail.com</a><a href="https://www.instagram.com/hendy._nathan/" data-testid="contact-instagram-link">@hendy._nathan</a></div>
      </div>
    </main>
  );
}

function AppRoutes({ user, setUser }) {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) {
    return <GoogleCallback onAuth={setUser} />;
  }
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/dashboard" /> : <AuthPage onAuth={setUser} />} />
      <Route path="/register" element={user ? <Navigate to="/dashboard" /> : <AuthPage register onAuth={setUser} />} />
      <Route path="/share/:token" element={<SharedProject />} />
      <Route path="*" element={user ? (
        <Shell user={user} onLogout={() => setUser(null)}>
          <Routes>
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/projects" element={<Projects user={user} />} />
            <Route path="/projects/new" element={<Projects user={user} />} />
            <Route path="/projects/:id" element={<ProjectDetailView />} />
            <Route path="/about" element={<About />} />
            <Route path="*" element={<Navigate to="/dashboard" />} />
          </Routes>
        </Shell>
      ) : <Navigate to="/login" />} />
    </Routes>
  );
}

function AppInner() {
  const { t } = useLanguage();
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    if (window.location.hash?.includes("session_id=")) { setChecking(false); return; }
    api.get("/auth/me").then((res) => setUser(res.data)).catch(() => setUser(null)).finally(() => setChecking(false));
  }, []);
  if (checking) return <div className="loading-screen">{t("loading")}</div>;
  return <BrowserRouter><AppRoutes user={user} setUser={setUser} /></BrowserRouter>;
}

function App() {
  return <LanguageProvider><AppInner /></LanguageProvider>;
}

export default App;
