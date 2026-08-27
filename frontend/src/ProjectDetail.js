import { Fragment, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { BarChart, Bar, CartesianGrid, LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, ArrowRight, CheckCircle2, FileText, Settings as SettingsIcon, Share2, UploadCloud, X, Info, Save } from "lucide-react";
import axios from "axios";
import { useLanguage, translateAssessment, translateWarning } from "@/i18n";
import { formatWithUnit, UNIT_LABELS } from "@/units";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const api = axios.create({ baseURL: API, withCredentials: true });
const fmt = (value, unit = "") => value === null || value === undefined || value === "" ? "—" : `${value} ${unit}`.trim();

const FIELD_LABEL_KEYS = {
  en: {
    record_number: "Record No.",
    sample_code: "Sample Code (Kode)",
    casting_date: "Casting Date (Tanggal Cor)",
    test_date: "Test Date (Tanggal Uji)",
    age_days: "Age / Umur (days)",
    cross_section_area: "Cross-section Area (Luas Penampang)",
    weight: "Weight (Berat)",
    load: "Load (Beban)",
    compressive_strength: "Compressive Strength (Kuat Tekan)",
    planned_strength: "Design / Planned Strength",
    actual_slump: "Actual Slump",
    target_slump: "Target Slump",
    supplier: "Supplier",
    location: "Element / Location",
    concrete_grade: "Concrete Grade / Mutu",
    crack_pattern: "Crack Pattern (Pola Retak)",
    notes: "Notes / Keterangan",
  },
  id: {
    record_number: "No. Catatan",
    sample_code: "Kode Sampel",
    casting_date: "Tanggal Cor",
    test_date: "Tanggal Uji",
    age_days: "Umur (hari)",
    cross_section_area: "Luas Penampang",
    weight: "Berat",
    load: "Beban",
    compressive_strength: "Kuat Tekan",
    planned_strength: "Kuat Tekan Rencana",
    actual_slump: "Slump Aktual",
    target_slump: "Slump Rencana",
    supplier: "Pemasok",
    location: "Elemen / Lokasi",
    concrete_grade: "Mutu Beton",
    crack_pattern: "Pola Retak",
    notes: "Keterangan",
  },
};

function useFieldLabels() {
  const { lang } = useLanguage();
  const dict = FIELD_LABEL_KEYS[lang] || FIELD_LABEL_KEYS.en;
  return (field) => dict[field] || field;
}

function Status({ assessment }) {
  const { t } = useLanguage();
  const status = assessment?.status || "UNASSESSED";
  const label = t(`status.${status}`);
  return <span className={`status status-${status.toLowerCase().replaceAll(" ", "-")}`} data-testid={`insight-status-${status.toLowerCase().replaceAll(" ", "-")}`}>{status === "COMPLIANT" ? <CheckCircle2 size={13} /> : label}</span>;
}

function AssessmentDetail({ assessment }) {
  const { t } = useLanguage();
  if (!assessment) return null;
  const info = translateAssessment(t, assessment);
  return (
    <div className="assessment-detail" data-testid="assessment-detail">
      <strong>{info.status}</strong>
      {info.reason && <p>{info.reason}</p>}
      {info.recommendation && <p className="muted">{info.recommendation}</p>}
    </div>
  );
}

function SharePanel({ projectId }) {
  const { t } = useLanguage();
  const [permission, setPermission] = useState("VIEWER");
  const [expiresAt, setExpiresAt] = useState("");
  const [created, setCreated] = useState(null);
  const [links, setLinks] = useState([]);
  const load = () => api.get(`/projects/${projectId}/shares`).then((res) => setLinks(res.data)).catch(() => {});
  useEffect(() => { load(); }, [projectId]);
  const create = async (event) => { event.preventDefault(); const res = await api.post(`/projects/${projectId}/shares`, { permission, expires_at: expiresAt ? new Date(expiresAt).toISOString() : null }); setCreated(res.data); load(); };
  const disable = async (id) => { await api.delete(`/projects/${projectId}/shares/${id}`); load(); };
  return (
    <section className="panel share-panel" data-testid="share-panel">
      <div className="panel-head"><div><span className="eyebrow">{t("share.eyebrow")}</span><h3>{t("share.title")}</h3></div><Share2 className="orange-icon" size={21} /></div>
      <p className="muted">{t("share.subtitle")}</p>
      <form className="share-form" onSubmit={create}>
        <label>{t("share.permission")}<select value={permission} onChange={(e) => setPermission(e.target.value)} data-testid="share-permission-select"><option value="VIEWER">{t("share.viewer")}</option><option value="EDITOR">{t("share.editor")}</option></select></label>
        <label>{t("share.optionalExpiry")}<input type="datetime-local" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} data-testid="share-expiry-input" /></label>
        <button className="button button-primary" data-testid="create-share-button">{t("share.create")} <ArrowRight size={16} /></button>
      </form>
      {created && <div className="share-created" data-testid="share-created-message"><strong>{created.permission} {t("share.linkReady")}</strong><input readOnly value={`${window.location.origin}${created.share_path}`} data-testid="share-link-input" onFocus={(e) => e.target.select()} /></div>}
      <div className="share-list">{links.map((link) => <div className="share-row" key={link.id}><span><strong>{link.permission}</strong><small>{link.expires_at ? `${t("share.expires")} ${new Date(link.expires_at).toLocaleString()}` : t("share.noExpiry")}</small></span><button className="icon-button" onClick={() => disable(link.id)} data-testid={`disable-share-${link.id}`} title="Disable link"><X size={16} /></button></div>)}</div>
    </section>
  );
}

function InsightsPanel({ projectId }) {
  const { t } = useLanguage();
  const [filters, setFilters] = useState({ status: "", age: "", supplier: "", location: "", date_from: "", date_to: "" });
  const [data, setData] = useState(null);
  const load = async () => { const params = Object.fromEntries(Object.entries(filters).filter(([, value]) => value)); const res = await api.get(`/projects/${projectId}/insights`, { params }); setData(res.data); };
  useEffect(() => { load(); }, [projectId]);
  const update = (key, value) => setFilters((current) => ({ ...current, [key]: value }));
  return (
    <section className="panel insights-panel" id="analysis" data-testid="engineering-insights-panel">
      <div className="panel-head"><div><span className="eyebrow">{t("insights.eyebrow")}</span><h3>{t("insights.title")}</h3></div><button className="button button-outline" onClick={load} data-testid="apply-insight-filters-button"><Activity size={16} /> {t("insights.refresh")}</button></div>
      <div className="insight-filters">
        <select value={filters.status} onChange={(e) => update("status", e.target.value)} data-testid="insight-status-filter">
          <option value="">{t("insights.filterStatus.all")}</option>
          <option value="COMPLIANT">{t("status.COMPLIANT")}</option>
          <option value="WARNING">{t("status.WARNING")}</option>
          <option value="NON-COMPLIANT">{t("status.NON-COMPLIANT")}</option>
          <option value="INSUFFICIENT DATA">{t("status.INSUFFICIENT DATA")}</option>
        </select>
        <input type="number" placeholder={t("insights.filterAge")} value={filters.age} onChange={(e) => update("age", e.target.value)} data-testid="insight-age-filter" />
        <input type="text" placeholder={t("insights.filterSupplier")} value={filters.supplier} onChange={(e) => update("supplier", e.target.value)} data-testid="insight-supplier-filter" />
        <input type="text" placeholder={t("insights.filterLocation")} value={filters.location} onChange={(e) => update("location", e.target.value)} data-testid="insight-location-filter" />
        <input type="date" value={filters.date_from} onChange={(e) => update("date_from", e.target.value)} data-testid="insight-date-from-filter" />
        <input type="date" value={filters.date_to} onChange={(e) => update("date_to", e.target.value)} data-testid="insight-date-to-filter" />
      </div>
      {data && (
        <>
          <div className="insight-summary"><strong data-testid="insight-total-count">{data.total} {t("insights.total")}</strong><span>{t("insights.recommendation")}</span></div>
          <div className="insight-charts">
            <div><h4>{t("insights.chartStrength")}</h4><ResponsiveContainer width="100%" height={220}><LineChart data={data.strength_by_age}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="age" tick={{ fill: "var(--muted)", fontSize: 11 }} unit=" d" /><YAxis tick={{ fill: "var(--muted)", fontSize: 11 }} unit=" MPa" /><Tooltip /><Line type="monotone" dataKey="actual" stroke="var(--orange)" strokeWidth={3} dot={{ r: 3 }} /><Line type="monotone" dataKey="planned" stroke="var(--muted)" strokeDasharray="4 4" /></LineChart></ResponsiveContainer></div>
            <div><h4>{t("insights.chartSupplier")}</h4><ResponsiveContainer width="100%" height={220}><BarChart data={data.supplier_comparison}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="supplier" tick={{ fill: "var(--muted)", fontSize: 10 }} /><YAxis allowDecimals={false} tick={{ fill: "var(--muted)", fontSize: 11 }} /><Tooltip /><Bar dataKey="compliant" fill="var(--green)" /><Bar dataKey="warning" fill="var(--orange)" /><Bar dataKey="non_compliant" fill="var(--red)" /></BarChart></ResponsiveContainer></div>
          </div>
          <div className="anomaly-strip"><strong>{t("insights.verificationTrend")}</strong>{data.anomaly_trends.length ? data.anomaly_trends.slice(0, 4).map((item, index) => <span key={index}>{item.date || t("insights.undated")} · {translateWarning(t, item)}</span>) : <span>{t("insights.noAnomalies")}</span>}</div>
        </>
      )}
    </section>
  );
}

function ImportReview({ projectId, document, fields, onClose, onImported }) {
  const { t } = useLanguage();
  const fieldLabel = useFieldLabels();
  const [data, setData] = useState(document.extraction);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const updateMapping = async (tableIndex, columnIndex, field) => {
    setBusy(true);
    try {
      const res = await api.post(`/projects/${projectId}/documents/${document.id}/mapping`, { overrides: [{ table_index: tableIndex, column_index: columnIndex, field: field || null }] });
      setData(res.data);
      setMessage(field ? `${t("review.mappedTo")} ${fieldLabel(field)}.` : t("review.mappingCleared"));
    } catch (err) { setMessage(err.response?.data?.detail || t("review.mappingError")); }
    finally { setBusy(false); }
  };
  const changeType = async (tableIndex, testType) => {
    setBusy(true);
    try {
      const res = await api.post(`/projects/${projectId}/documents/${document.id}/mapping`, { overrides: [{ table_index: tableIndex, test_type: testType }] });
      setData(res.data);
      const typeLabel = { strength: t("review.typeStrength"), slump: t("review.typeSlump"), unknown: t("review.typeUnknown") }[testType] || testType;
      setMessage(`${t("review.typeClassified")} ${typeLabel}.`);
    } finally { setBusy(false); }
  };
  const saveTemplate = async (table) => {
    const name = window.prompt(t("template.namePrompt"), document.filename?.replace(/\.[^.]+$/, "") || "Template");
    if (!name) return;
    setBusy(true);
    try {
      const mappings = Object.fromEntries(table.used_columns.map((col) => [col.header, col.field]));
      await api.post("/mapping-templates", { name, signature: table.source_headers, mappings, test_type: table.test_type });
      setMessage(t("template.saved"));
    } finally { setBusy(false); }
  };
  const finalize = async () => {
    setBusy(true);
    try {
      const res = await api.post(`/projects/${projectId}/import/${document.id}`);
      onImported(res.data.inserted);
    } finally { setBusy(false); }
  };
  const tables = data?.tables || [];
  return (
    <div className="modal-backdrop">
      <div className="modal review-modal" data-testid="import-review-modal">
        <button type="button" className="modal-close" onClick={onClose} data-testid="review-close-button"><X size={18} /></button>
        <span className="eyebrow">{t("review.eyebrow")} · {document.filename}</span>
        <h2>{data?.detected || 0} {t("review.readyPrefix")}</h2>
        <p className="muted">{t("review.subtitle")}</p>
        {data?.applied_templates?.length ? <div className="notice" data-testid="auto-template-banner"><Info size={16} /><span>{t("template.autoApplied")} {data.applied_templates.join(", ")}</span></div> : null}
        {message && <div className="success-box" data-testid="review-message">{message}</div>}
        {tables.map((table) => (
          <section className="review-table" key={table.table_index} data-testid={`review-table-${table.table_index}`}>
            <header>
              <div><strong>{t("review.table")} {table.table_index + 1}</strong><small>{table.records.length} {t("review.rows")} {table.header_row}</small></div>
              <div className="review-header-actions">
                <label>{t("review.testType")}
                  <select value={table.test_type} onChange={(e) => changeType(table.table_index, e.target.value)} data-testid={`review-type-${table.table_index}`} disabled={busy}>
                    <option value="strength">{t("review.typeStrength")}</option>
                    <option value="slump">{t("review.typeSlump")}</option>
                    <option value="unknown">{t("review.typeUnknown")}</option>
                  </select>
                </label>
                <button type="button" className="button button-outline" onClick={() => saveTemplate(table)} disabled={busy || !table.used_columns.length} data-testid={`save-template-${table.table_index}`}><Save size={15} /> {t("template.saveAs")}</button>
              </div>
            </header>
            <div className="mapping-grid">
              {table.used_columns.map((column) => (
                <div className="mapping-row" key={column.column_index} data-testid={`mapping-used-${table.table_index}-${column.column_index}`}>
                  <span className="mapping-header"><strong>{column.header}</strong><small>{t("review.column")} {column.column_index + 1} · {column.manual ? t("review.manual") : `${t("review.auto")} ${(column.confidence * 100).toFixed(0)}%`}</small></span>
                  <select value={column.field} onChange={(e) => updateMapping(table.table_index, column.column_index, e.target.value)} disabled={busy} data-testid={`mapping-field-${table.table_index}-${column.column_index}`}>
                    {fields.map((field) => <option key={field} value={field}>{fieldLabel(field)}</option>)}
                  </select>
                  <button type="button" className="icon-button" onClick={() => updateMapping(table.table_index, column.column_index, null)} title="Unmap column" disabled={busy} data-testid={`mapping-remove-${table.table_index}-${column.column_index}`}><X size={15} /></button>
                </div>
              ))}
              {table.unused_columns.map((column) => (
                <div className="mapping-row muted-row" key={`u-${column.column_index}`} data-testid={`mapping-unused-${table.table_index}-${column.column_index}`}>
                  <span className="mapping-header"><strong>{column.header || `${t("review.column")} ${column.column_index + 1}`}</strong><small>{t("review.unmapped")} {column.suggestion ? fieldLabel(column.suggestion) : t("review.noMatch")}</small></span>
                  <select defaultValue="" onChange={(e) => e.target.value && updateMapping(table.table_index, column.column_index, e.target.value)} disabled={busy} data-testid={`mapping-add-${table.table_index}-${column.column_index}`}>
                    <option value="">{t("review.mapTo")}</option>
                    {fields.map((field) => <option key={field} value={field}>{fieldLabel(field)}</option>)}
                  </select>
                </div>
              ))}
            </div>
            <div className="review-preview">
              <table>
                <thead><tr>{table.used_columns.map((column) => <th key={column.column_index}>{fieldLabel(column.field)}</th>)}</tr></thead>
                <tbody>{table.records.slice(0, 4).map((record, rowIndex) => (
                  <tr key={rowIndex}>{table.used_columns.map((column) => <td key={column.column_index}>{fmt(record[column.field])}</td>)}</tr>
                ))}</tbody>
              </table>
              {table.records.length > 4 && <small className="muted">{t("review.showing")} {table.records.length} {t("review.rowsSuffix")}</small>}
            </div>
          </section>
        ))}
        {data?.warnings?.length ? <div className="notice"><Info size={16} /><span>{data.warnings.join(" ")}</span></div> : null}
        <div className="review-actions">
          <button type="button" className="button button-outline" onClick={onClose} data-testid="review-cancel-button">{t("review.cancel")}</button>
          <button type="button" className="button button-primary" onClick={finalize} disabled={busy || !data?.detected} data-testid="review-save-button">{t("review.save")} {data?.detected || 0} {t("review.saveSuffix")} <ArrowRight size={17} /></button>
        </div>
      </div>
    </div>
  );
}

function SettingsPanel({ project, onClose, onSaved }) {
  const { t } = useLanguage();
  const settings = project.settings || {};
  const [form, setForm] = useState({
    target_slump: settings.target_slump ?? "",
    min_slump: settings.min_slump ?? "",
    max_slump: settings.max_slump ?? "",
    design_strength: settings.design_strength ?? "",
    slump_unit: settings.slump_unit || "mm",
    strength_unit: settings.strength_unit || "MPa",
    area_unit: settings.area_unit || "cm2",
    load_unit: settings.load_unit || "kN",
  });
  const [busy, setBusy] = useState(false);
  const submit = async (event) => {
    event.preventDefault(); setBusy(true);
    const payload = {
      ...form,
      target_slump: form.target_slump === "" ? null : Number(form.target_slump),
      min_slump: form.min_slump === "" ? null : Number(form.min_slump),
      max_slump: form.max_slump === "" ? null : Number(form.max_slump),
      design_strength: form.design_strength === "" ? null : Number(form.design_strength),
    };
    try {
      const res = await api.patch(`/projects/${project.id}/settings`, payload);
      onSaved(res.data);
    } finally { setBusy(false); }
  };
  const update = (key, value) => setForm((state) => ({ ...state, [key]: value }));
  return (
    <div className="modal-backdrop">
      <form className="modal wide" onSubmit={submit} data-testid="settings-modal">
        <button type="button" className="modal-close" onClick={onClose} data-testid="settings-close-button"><X size={18} /></button>
        <span className="eyebrow">{t("settings.eyebrow")}</span>
        <h2>{t("settings.title")}</h2>
        <p className="muted">{t("settings.subtitle")}</p>
        <div className="form-grid">
          <label>{t("settings.targetSlump")} ({UNIT_LABELS[form.slump_unit]})<input type="number" value={form.target_slump} onChange={(e) => update("target_slump", e.target.value)} data-testid="settings-target-slump" /></label>
          <label>{t("settings.minSlump")} ({UNIT_LABELS[form.slump_unit]})<input type="number" value={form.min_slump} onChange={(e) => update("min_slump", e.target.value)} data-testid="settings-min-slump" /></label>
          <label>{t("settings.maxSlump")} ({UNIT_LABELS[form.slump_unit]})<input type="number" value={form.max_slump} onChange={(e) => update("max_slump", e.target.value)} data-testid="settings-max-slump" /></label>
          <label>{t("settings.designStrength")} ({UNIT_LABELS[form.strength_unit]})<input type="number" step="0.1" value={form.design_strength} onChange={(e) => update("design_strength", e.target.value)} data-testid="settings-design-strength" /></label>
        </div>
        <div className="eyebrow" style={{ marginTop: 22 }}>{t("settings.unitsGroup")}</div>
        <div className="form-grid">
          <label>{t("settings.slumpUnit")}<select value={form.slump_unit} onChange={(e) => update("slump_unit", e.target.value)} data-testid="settings-slump-unit"><option value="mm">mm</option><option value="cm">cm</option></select></label>
          <label>{t("settings.strengthUnit")}<select value={form.strength_unit} onChange={(e) => update("strength_unit", e.target.value)} data-testid="settings-strength-unit"><option value="MPa">MPa</option><option value="N/mm2">N/mm²</option><option value="kgf/cm2">kgf/cm²</option><option value="psi">psi</option></select></label>
          <label>{t("settings.areaUnit")}<select value={form.area_unit} onChange={(e) => update("area_unit", e.target.value)} data-testid="settings-area-unit"><option value="cm2">cm²</option><option value="mm2">mm²</option></select></label>
          <label>{t("settings.loadUnit")}<select value={form.load_unit} onChange={(e) => update("load_unit", e.target.value)} data-testid="settings-load-unit"><option value="kN">kN</option><option value="N">N</option></select></label>
        </div>
        <button className="button button-primary button-wide" disabled={busy} data-testid="settings-save-button">{t("settings.save")} <ArrowRight size={17} /></button>
      </form>
    </div>
  );
}

function ProjectDetail() {
  const { t, lang } = useLanguage();
  const { id } = useParams();
  const [project, setProject] = useState(null);
  const [type, setType] = useState("strength");
  const [showForm, setShowForm] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [record, setRecord] = useState({ sample_code: "", test_date: "", casting_date: "", age_days: "", compressive_strength: "", planned_strength: "", actual_slump: "", target_slump: "", notes: "" });
  const [upload, setUpload] = useState(null);
  const [job, setJob] = useState(null);
  const [message, setMessage] = useState("");
  const [reviewDoc, setReviewDoc] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [fields, setFields] = useState([]);
  const load = async () => { const res = await api.get(`/projects/${id}`); setProject(res.data); };
  useEffect(() => { load(); api.get("/config/field-synonyms").then((res) => setFields(res.data.fields)); }, [id]);
  const save = async (event) => { event.preventDefault(); await api.post(`/projects/${id}/records`, { test_type: type, record: { ...record, age_days: Number(record.age_days) || null, compressive_strength: Number(record.compressive_strength) || null, planned_strength: Number(record.planned_strength) || null, actual_slump: Number(record.actual_slump) || null, target_slump: Number(record.target_slump) || null } }); setShowForm(false); setMessage(t("project.messageSaved")); load(); };
  const processUpload = async (event) => {
    event.preventDefault();
    if (!upload) return;
    if (upload.size > 104857600) { setMessage(t("project.messageOverLimit")); return; }
    const form = new FormData(); form.append("file", upload);
    try {
      const response = await api.post(`/projects/${id}/upload`, form, { headers: { "Content-Type": "multipart/form-data" } });
      setJob(response.data);
      setMessage(t("project.messageUploaded"));
      const started = Date.now();
      const poll = async () => {
        try {
          const status = await api.get(`/projects/${id}/documents/${response.data.id}/status`);
          setJob(status.data);
          if (status.data.status === "completed") {
            setReviewDoc(status.data);
            setMessage(`${status.data.extraction?.detected || 0} ${t("project.messageReviewReady")}`);
          } else if (status.data.status === "failed") {
            setMessage(status.data.error || t("project.messageUploadFailed"));
          } else if (Date.now() - started < 300000) {
            window.setTimeout(poll, 1200);
          }
        } catch (err) { /* stop polling on transient errors */ }
      };
      poll();
    } catch (error) { setMessage(error.response?.data?.detail || t("project.messageUploadFailed")); }
  };
  const analyzeNow = async () => { await api.post(`/projects/${id}/analyze`); load(); setMessage(t("project.messageAnalyzed")); };
  if (!project) return <main className="page"><div className="loading">Loading…</div></main>;
  const strength = project.records?.filter((item) => item.test_type === "strength") || [];
  const slump = project.records?.filter((item) => item.test_type === "slump") || [];
  const shown = type === "strength" ? strength : slump;
  const strengthUnit = project.settings?.strength_unit || "MPa";
  const slumpUnit = project.settings?.slump_unit || "mm";
  return (
    <main className="page">
      <div className="project-hero">
        <div><Link className="back-link" to="/projects" data-testid="project-back-link">{t("project.back")}</Link><span className="eyebrow">{t("project.eyebrow")} / {project.code || t("projects.uncoded")}</span><h1>{project.name}</h1><p className="muted">{project.description || t("project.workspace")} · {project.location || t("projects.locationPending")}</p></div>
        <div className="hero-actions"><button className="button button-outline" onClick={() => setShowSettings(true)} data-testid="open-settings-button"><SettingsIcon size={17} /> {t("settings.open")}</button><button className="button button-outline" onClick={analyzeNow} data-testid="analyze-project-button"><Activity size={17} /> {t("project.reanalyze")}</button><a className="button button-primary" href={`${API}/projects/${id}/report?lang=${lang}`} target="_blank" rel="noreferrer" data-testid="download-report-button"><FileText size={17} /> {t("project.report")}</a></div>
      </div>
      {message && <div className="success-box" data-testid="project-message">{message}</div>}
      <div className="project-layout">
        <section className="panel" id="records">
          <div className="panel-head"><div><span className="eyebrow">{t("project.records")} / {project.records?.length || 0}</span><h3>{t("project.recordsTitle")}</h3></div><button className="button button-primary" onClick={() => setShowForm(true)} data-testid="add-record-button">{t("project.addRecord")} <ArrowRight size={16} /></button></div>
          <div className="segmented">
            <button className={type === "strength" ? "active" : ""} onClick={() => setType("strength")} data-testid="strength-filter-button">{t("project.strengthFilter")} ({strength.length})</button>
            <button className={type === "slump" ? "active" : ""} onClick={() => setType("slump")} data-testid="slump-filter-button">{t("project.slumpFilter")} ({slump.length})</button>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr><th>{t("project.thSample")}</th><th>{t("project.thDate")}</th><th>{t("project.thAge")}</th><th>{t("project.thResult")}</th><th>{t("project.thStatus")}</th></tr></thead>
              <tbody>{shown.map((item) => { const row = item.record; const isOpen = expanded === item.id; return (
                <Fragment key={item.id}>
                  <tr onClick={() => setExpanded(isOpen ? null : item.id)} className="clickable-row" data-testid={`record-row-${item.id}`}>
                    <td><strong>{row.sample_code || row.record_number || t("project.unidentified")}</strong><small>{row.source?.file ? `${t("project.sourceLabel")} ${row.source.file} · ${t("project.rowLabel")} ${row.source.row || "-"}` : row.notes || t("project.manualEntry")}</small></td>
                    <td>{row.test_date || "—"}</td>
                    <td>{type === "strength" ? fmt(row.age_days, "days") : "—"}</td>
                    <td className="mono">{type === "strength" ? formatWithUnit(row.compressive_strength ?? row.derived_strength, "MPa", strengthUnit) : formatWithUnit(row.actual_slump, "mm", slumpUnit)}</td>
                    <td><Status assessment={row.assessment} /></td>
                  </tr>
                  {isOpen && (row.assessment || row.warnings?.length) && (
                    <tr className="row-detail">
                      <td colSpan={5}>
                        <AssessmentDetail assessment={row.assessment} />
                        {row.warnings?.length ? <ul className="warning-list">{row.warnings.map((w, idx) => <li key={idx}>⚠ {translateWarning(t, w)}</li>)}</ul> : null}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ); })}</tbody>
            </table>
            {!shown.length && <div className="table-empty">{t("project.emptyRecords")}</div>}
          </div>
        </section>
        <section className="panel upload-panel" id="upload">
          <div className="panel-head"><div><span className="eyebrow">{t("project.pipeline")}</span><h3>{t("project.pipelineTitle")}</h3></div><UploadCloud className="orange-icon" size={21} /></div>
          <p className="muted">{t("project.pipelineSub")}</p>
          <form onSubmit={processUpload} className="upload-form">
            <label className="dropzone">
              <UploadCloud size={28} />
              <strong>{upload ? upload.name : t("project.dropzoneTitle")}</strong>
              <small>{upload ? `${(upload.size / 1024 / 1024).toFixed(1)} ${t("project.dropzoneSelected")}` : t("project.dropzoneHint")}</small>
              <input type="file" accept=".pdf,.xlsx,.xls" onChange={(event) => setUpload(event.target.files?.[0])} data-testid="document-file-input" />
            </label>
            <button className="button button-primary button-wide" disabled={!upload} data-testid="process-document-button">{t("project.startProcessing")} <ArrowRight size={17} /></button>
          </form>
          {job && (
            <div className="review-box" data-testid="import-progress-panel">
              <strong>{job.status === "completed" ? t("project.reviewReady") : job.status === "failed" ? t("project.processingFailed") : `${t("project.processing")} · ${job.progress || 0}%`}</strong>
              <div className="progress-track"><span style={{ width: `${job.progress || 0}%` }} /></div>
              {job.status === "completed" && <button className="button button-primary" onClick={() => setReviewDoc(job)} data-testid="open-review-button">{t("project.openReview")}</button>}
              {job.status === "failed" && <small className="muted">{job.error}</small>}
            </div>
          )}
          <div className="doc-history">
            {(project.documents || []).slice(0, 5).map((doc) => (
              <div key={doc.id} className="doc-row" data-testid={`document-row-${doc.id}`}>
                <div><strong>{doc.filename}</strong><small>{(doc.size / 1024 / 1024).toFixed(2)} MB · {doc.status} {doc.imported_count ? `· ${t("project.docHistoryImported")} ${doc.imported_count}` : ""}</small></div>
                {doc.status === "completed" && !doc.imported_at && <button className="text-link" onClick={() => setReviewDoc(doc)} data-testid={`review-doc-${doc.id}`}>{t("project.docReview")} <ArrowRight size={14} /></button>}
              </div>
            ))}
          </div>
        </section>
      </div>
      <InsightsPanel projectId={id} />
      <SharePanel projectId={id} />
      {showForm && <RecordForm type={type} record={record} setRecord={setRecord} onClose={() => setShowForm(false)} onSave={save} />}
      {showSettings && <SettingsPanel project={project} onClose={() => setShowSettings(false)} onSaved={(next) => { setProject((prev) => ({ ...prev, settings: next })); setShowSettings(false); setMessage(t("settings.saved")); }} />}
      {reviewDoc && <ImportReview projectId={id} document={reviewDoc} fields={fields} onClose={() => setReviewDoc(null)} onImported={(count) => { setReviewDoc(null); setMessage(`${count} ${t("project.messageImported")}`); load(); }} />}
    </main>
  );
}

function RecordForm({ type, record, setRecord, onClose, onSave }) {
  const { t } = useLanguage();
  const update = (key, value) => setRecord({ ...record, [key]: value });
  return (
    <div className="modal-backdrop">
      <form className="modal wide" onSubmit={onSave}>
        <button type="button" className="modal-close" onClick={onClose} data-testid="record-form-close-button"><X size={18} /></button>
        <span className="eyebrow">{type === "strength" ? t("record.eyebrowStrength") : t("record.eyebrowSlump")}</span>
        <h2>{t("record.formTitle")}</h2>
        <div className="form-grid">
          <label>{t("record.sampleCode")}<input required value={record.sample_code} onChange={(e) => update("sample_code", e.target.value)} data-testid="record-sample-input" /></label>
          <label>{t("record.testDate")}<input type="date" value={record.test_date} onChange={(e) => update("test_date", e.target.value)} data-testid="record-test-date-input" /></label>
          {type === "strength" ? (
            <>
              <label>{t("record.castingDate")}<input type="date" value={record.casting_date} onChange={(e) => update("casting_date", e.target.value)} /></label>
              <label>{t("record.age")}<input type="number" value={record.age_days} onChange={(e) => update("age_days", e.target.value)} /></label>
              <label>{t("record.compressive")}<input type="number" step="0.01" value={record.compressive_strength} onChange={(e) => update("compressive_strength", e.target.value)} /></label>
              <label>{t("record.designStrength")}<input type="number" step="0.01" value={record.planned_strength} onChange={(e) => update("planned_strength", e.target.value)} /></label>
            </>
          ) : (
            <>
              <label>{t("record.actualSlump")}<input type="number" value={record.actual_slump} onChange={(e) => update("actual_slump", e.target.value)} /></label>
              <label>{t("record.targetSlump")}<input type="number" value={record.target_slump} onChange={(e) => update("target_slump", e.target.value)} /></label>
            </>
          )}
          <label className="span-2">{t("record.notes")}<textarea value={record.notes} onChange={(e) => update("notes", e.target.value)} /></label>
        </div>
        <button className="button button-primary button-wide" data-testid="save-record-button">{t("record.save")} <ArrowRight size={17} /></button>
      </form>
    </div>
  );
}

export function SharedProject() {
  const { t } = useLanguage();
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.get(`/shared/${token}`).then((res) => setData(res.data)).catch((err) => setError(err.response?.data?.detail || t("shared.linkUnavailable"))); }, [token, t]);
  if (error) return <main className="shared-shell"><h1>{t("shared.linkUnavailable")}</h1><p>{error}</p></main>;
  if (!data) return <main className="shared-shell"><div className="loading">{t("shared.loading")}</div></main>;
  return (
    <main className="shared-shell">
      <span className="eyebrow">{t("shared.eyebrow")} / {data.permission}</span>
      <h1>{data.project.name}</h1>
      <p className="muted">{t("shared.subtitleWithExpiry")} {data.expires_at ? `${t("shared.expires")} ${new Date(data.expires_at).toLocaleString()}.` : t("shared.noExpiry")}</p>
      <div className="panel">
        <table>
          <thead><tr><th>{t("project.thSample")}</th><th>{t("project.thStatus")}</th><th>{t("project.thDate")}</th><th>{t("project.thResult")}</th><th>{t("project.thStatus")}</th></tr></thead>
          <tbody>{data.records.map((item) => (
            <tr key={item.id}>
              <td>{item.record.sample_code || item.record.record_number || t("project.unidentified")}</td>
              <td>{item.test_type}</td>
              <td>{item.record.test_date || "—"}</td>
              <td>{fmt(item.record.compressive_strength || item.record.actual_slump, item.test_type === "strength" ? "MPa" : "mm")}</td>
              <td><Status assessment={item.record.assessment} /></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </main>
  );
}

export default ProjectDetail;
