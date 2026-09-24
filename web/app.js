// SanadAI frontend (vanilla ES modules, no build step).
import { t, setLang, lang, initialLang } from "./i18n.js";
import { renderGraph, finalWording } from "./graph.js";

// Example posts. Sacred texts are verbatim from the DB (Tanzil 112:1-4; Sahih al-Bukhari 6138). The weak and
// fabricated examples are circulating phrasings whose gradings the app quotes from Dorar.net.
const EXAMPLES = {
  fabricated: "The Prophet ﷺ said: Seek knowledge even if you have to go as far as China",
  weak: "قال رسول الله ﷺ: «كما تكونوا يولى عليكم» — انشرها ليعلم الجميع",
  authentic: "قال النبي ﷺ: «مَنْ كَانَ يُؤْمِنُ بِاللَّهِ وَالْيَوْمِ الآخِرِ فَلْيُكْرِمْ ضَيْفَهُ»",
  quran: "قال تعالى: ﴿قل هو الله أحد الله الصمد لم يلد ولم يولد ولم يكن له كفوا أحد﴾",
};

const $ = (id) => document.getElementById(id);
const state = { image: null, result: null, outLang: "ar", busy: false };

// ---------------- helpers ----------------

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function show(id, on = true) { $(id).hidden = !on; }

async function api(path, body) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg).join("; ") : `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return data;
}

// ---------------- image input ----------------

function setImage(file) {
  if (!file || !file.type.startsWith("image/")) return;
  if (file.size > 5_000_000) { formError(t("error") + ": > 5 MB"); return; }
  const reader = new FileReader();
  reader.onload = () => {
    state.image = reader.result;           // data URL
    $("previewImg").src = reader.result;
    show("imagePreview");
  };
  reader.readAsDataURL(file);
}

function clearImage() {
  state.image = null;
  $("previewImg").removeAttribute("src");
  $("fileInput").value = "";
  show("imagePreview", false);
}

function formError(msg) {
  $("formError").textContent = msg;
  show("formError", !!msg);
}

// ---------------- loading animation ----------------

let loadingTimer = null;
function startLoading() {
  const ol = $("loadingSteps");
  ol.innerHTML = t("steps").map((s) => `<li>${esc(s)}</li>`).join("");
  const items = [...ol.children];
  let i = 0;
  items[0].classList.add("active");
  loadingTimer = setInterval(() => {
    if (i < items.length - 1) {
      items[i].classList.replace("active", "done");
      items[++i].classList.add("active");
    }
  }, 900);
  show("loading");
}
function stopLoading() {
  clearInterval(loadingTimer);
  show("loading", false);
}

// ---------------- verify ----------------

async function verify() {
  if (state.busy) return;
  const text = $("postText").value.trim();
  if (!text && !state.image) { formError(t("empty_input")); return; }
  formError("");
  state.busy = true;
  $("verifyBtn").disabled = true;
  show("results", false); show("error", false);
  startLoading();
  try {
    const body = { text: text || null, image_base64: state.image };
    state.result = await api("/api/verify", body);
    renderResults(state.result);
  } catch (e) {
    $("errorDetail").textContent = e.message;
    show("error");
  } finally {
    stopLoading();
    state.busy = false;
    $("verifyBtn").disabled = false;
  }
}

// ---------------- rendering ----------------

function gauge(score, status) {
  const r = 38, c = 2 * Math.PI * r, frac = Math.max(0, Math.min(100, score)) / 100;
  const color = { green: "#1E8E5A", amber: "#B7791F", red: "#C0392B" }[status];
  return `<div class="gauge" title="${esc(t("score_hint"))}">
    <svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true">
      <circle cx="48" cy="48" r="${r}" fill="none" stroke="#E6F2EF" stroke-width="9"/>
      <circle cx="48" cy="48" r="${r}" fill="none" stroke="${color}" stroke-width="9" stroke-linecap="round"
        stroke-dasharray="${(c * frac).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 48 48)"/>
      <text x="48" y="55" text-anchor="middle" font-size="24" font-weight="700" fill="#16302F">${score}</text>
    </svg>
    <div class="cap"><strong>${esc(t("score"))}</strong><br>${esc(t("score_hint"))}</div>
  </div>`;
}

function srcLabel(src) {
  const v = t("src." + String(src).replace(/[^a-z0-9_]/gi, "_"));
  return v.startsWith("src.") ? src : v;
}

const STATUS_ICON = { green: "🟢", amber: "🟡", red: "🔴" };

function diffHtml(diff) {
  return diff.map((d) => {
    if (d.op === "equal") return `<span>${esc(d.text)}</span>`;
    if (d.op === "insert") return `<span class="d-ins">${esc(d.text)}</span>`;
    if (d.op === "delete") return `<span class="d-del">${esc(d.text)}</span>`;
    return `<span class="d-rep-old">${esc(d.source)}</span> <span class="d-rep-new">${esc(d.text)}</span>`;
  }).join(" ");
}

function gradingsHtml(gs) {
  if (!gs.length) return `<p class="muted">${esc(t("no_gradings"))}</p>`;
  return `<div class="grades">${gs.map((g) => `
    <div class="grade">
      <span class="gclass ${esc(g.grade_class)}">${esc(t("gc." + g.grade_class))}</span>
      <span class="gtext">${esc(g.grade_ar || g.grade_en)}${g.grade_ar && g.grade_en ? ` <span class="muted">(${esc(g.grade_en)})</span>` : ""}</span>
      <span class="gmeta">${esc(t("grader"))}: ${esc(g.grader)}${g.reference ? " — " + esc(g.reference) : ""} · ${esc(srcLabel(g.source))}</span>
    </div>`).join("")}</div>`;
}

function sourceHtml(c) {
  if (c.match_type === "not_found") {
    return `<div class="not-found">${esc(t("not_found_msg"))}</div>`;
  }
  if (c.ayah) {
    const a = c.ayah;
    const occ = a.other_occurrences?.length ? `<p class="muted small">${esc(t("other_occ"))}: ${a.other_occurrences.map(esc).join("، ")}</p>` : "";
    return `
      <div class="source-line"><strong>${esc(a.surah_name_ar)} (${esc(a.surah_name_en)}) ${esc(a.ref)}</strong>
        <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(t("open_source"))} ↗</a></div>
      <blockquote class="sacred quran" dir="rtl" lang="ar">﴿${esc(a.text_uthmani)}﴾</blockquote>
      <p class="muted small">${esc(a.source)}</p>
      ${a.text_en ? `<details><summary>${esc(t("translation"))}</summary><p class="translation" lang="en">${esc(a.text_en)}</p></details>` : ""}
      ${occ}`;
  }
  const s = c.source;
  if (!s) return "";
  const link = s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(t("open_source"))} ↗</a>` : "";
  return `
    <div class="source-line"><strong>${esc(s.collection || "")} ${s.number ? "— " + esc(s.number) : ""}</strong>
      ${s.collection_en ? `<span class="muted">${esc(s.collection_en)}</span>` : ""} ${link}</div>
    ${s.narrator ? `<p class="muted small">${esc(s.narrator)}</p>` : ""}
    <blockquote class="sacred" dir="rtl" lang="ar">${esc(s.text_ar)}</blockquote>
    <p class="muted small">${esc(srcLabel(s.provider))}</p>
    ${s.text_ar_full && s.text_ar_full !== s.text_ar ? `<details><summary>${esc(t("full_text"))}</summary><p class="sacred" dir="rtl" lang="ar">${esc(s.text_ar_full)}</p></details>` : ""}
    ${s.text_en ? `<details><summary>${esc(t("translation_hadith"))}</summary><p class="translation" lang="en">${esc(s.text_en)}</p></details>` : ""}`;
}

function altsHtml(alts) {
  return alts.map((a) => {
    const g = a.gradings[0];
    const src = a.source || {};
    return `<div class="alt">
      <p class="sacred" dir="rtl" lang="ar">${esc(a.text_ar)}</p>
      <p class="meta">${esc(src.collection || "")} ${src.number ? "— " + esc(src.number) : ""}
        ${g ? ` · ${esc(g.grader)}: <strong>${esc(g.grade_ar || g.grade_en)}</strong>` : ""}
        · ${esc(a.origin.startsWith("dorar") ? t("alt_from_dorar") : t("alt_from_local"))}
        ${src.url ? ` · <a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(t("open_source"))} ↗</a>` : ""}</p>
    </div>`;
  }).join("");
}

function nodeDetails(c) {
  return (key) => {
    switch (key) {
      case "claim":
        return `<p>${esc(c.claim_text)}</p><p class="muted small">${esc(t("type_" + c.claim_type))}${c.attributed_to ? " · " + esc(t("attributed")) + ": " + esc(c.attributed_to) : ""}</p>`;
      case "source":
        return c.match_type === "not_found" ? `<p>${esc(t("not_found_msg"))}</p>` : sourceHtml(c);
      case "original":
        return c.ayah ? `<p class="sacred quran">﴿${esc(c.ayah.text_uthmani)}﴾</p>`
          : c.source ? `<p class="sacred">${esc(c.source.text_ar)}</p>` : `<p>${esc(t("not_found_msg"))}</p>`;
      case "verify":
        return `<p><strong>${esc(t("mt_" + c.match_type))}</strong> · ${esc(t("score"))} ${c.sanad_score} · ${(c.match_confidence * 100).toFixed(0)}%</p>
          ${c.reasons.map((r) => `<span class="reason">${esc(t("reasons." + r))}</span>`).join(" ")}
          <ul class="trace">${c.evidence_trace.map((s) => `<li class="st-${esc(s.status)}"><span>${esc(lang() === "ar" ? s.label_ar : s.label_en)}${s.status !== "ok" ? " (" + esc(s.status) + ")" : ""}</span><span>${Math.round(s.ms)} ${esc(t("ms"))}</span></li>`).join("")}</ul>`;
      case "final": {
        const fw = finalWording(c);
        return `<p><strong>${esc(t("final_" + fw.kind))}</strong></p>${fw.text ? `<p class="sacred">${esc(fw.text)}</p>` : ""}`;
      }
      default: return "";
    }
  };
}

function claimCard(c) {
  const card = document.createElement("article");
  card.className = `card ${c.status}`;
  card.setAttribute("aria-label", `${t("status_" + c.status)} — ${c.claim_text}`);
  const notes = c.notes.map((n) => t("notes." + n)).filter((x) => x && !x.startsWith("notes.")).join(" ");
  card.innerHTML = `
    <div class="card-head">
      <div>
        <div class="pills">
          <span class="pill ${c.status}">${STATUS_ICON[c.status]} ${esc(t("status_" + c.status))}</span>
          <span class="tag">${esc(t("type_" + c.claim_type))}</span>
          <span class="tag">${esc(t("match"))}: ${esc(t("mt_" + c.match_type))}</span>
        </div>
        <p class="claim-text" dir="auto">«${esc(c.claim_text)}»</p>
        <p class="summary">${esc(lang() === "ar" ? c.summary_ar : c.summary_en)}</p>
        <div class="reasons">${c.reasons.map((r) => `<span class="reason">${esc(t("reasons." + r))}</span>`).join("")}</div>
      </div>
      ${gauge(c.sanad_score, c.status)}
    </div>
    <div class="card-body">
      <section class="block"><h3>${esc(t("source"))} · ${esc(t("original"))}</h3>${sourceHtml(c)}</section>
      ${c.match_type === "altered" && c.diff.length ? `<section class="block"><h3>${esc(t("diff"))}</h3><p class="diff" dir="rtl">${diffHtml(c.diff)}</p><p class="muted small">${esc(t("diff_legend"))}</p></section>` : ""}
      ${c.claim_type !== "quran" && c.match_type !== "not_found" ? `<section class="block"><h3>${esc(t("gradings"))}</h3>${gradingsHtml(c.gradings)}</section>` : ""}
      ${c.alternatives.length ? `<section class="block"><h3>${esc(t("alternatives"))}</h3>${altsHtml(c.alternatives)}</section>` : ""}
      <section class="block"><h3>${esc(t("evidence_graph"))}</h3><div class="graph-wrap"></div></section>
      ${notes ? `<p class="notes">${esc(notes)}</p>` : ""}
    </div>`;
  return card;
}

function renderResults(r, scroll = true) {
  const box = $("claims");
  box.innerHTML = "";
  $("resultsMeta").textContent = `${t("claims_found", r.claims.length)} · ${t(r.extraction_method === "llm" ? "method_llm" : "method_rules")}`;
  show("prepareBtn", r.claims.length > 0);
  if (!r.claims.length) {
    box.innerHTML = `<div class="empty">${esc(t("no_claims"))}</div>`;
  }
  show("results");
  r.claims.forEach((c) => {
    const card = claimCard(c);
    box.appendChild(card);
    renderGraph(card.querySelector(".graph-wrap"), c, nodeDetails(c));
  });
  if (scroll) $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------- prepare modal ----------------

async function loadPrepared() {
  const ta = $("preparedText");
  ta.value = "…";
  try {
    const p = await api("/api/prepare", { check_id: state.result.check_id, output_lang: state.outLang });
    ta.value = p.text;
    show("prepareWarn", !p.validated);
    $("waBtn").href = "https://wa.me/?text=" + encodeURIComponent(p.text);
  } catch (e) {
    ta.value = `${t("error")}: ${e.message}`;
  }
}

function openPrepare() {
  if (!state.result) return;
  state.outLang = lang();
  document.querySelectorAll(".seg-btn").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.out === state.outLang)));
  $("prepareModal").showModal();
  loadPrepared();
}

// ---------------- health ----------------

async function loadHealth() {
  try {
    const h = await api("/api/health");
    const ok = h.status === "ok";
    $("health").className = "health " + (ok ? "ok" : "degraded");
    $("health").textContent = t(ok ? "health_ok" : "health_degraded");
  } catch {
    $("health").className = "health degraded";
  }
}

// ---------------- wiring ----------------

function rerender() {
  setLang(lang());
  if (state.result && !$("results").hidden) renderResults(state.result, false);
  loadHealth();
}

function init() {
  setLang(initialLang());
  loadHealth();

  $("verifyForm").addEventListener("submit", (e) => { e.preventDefault(); verify(); });
  $("postText").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); verify(); }
  });
  $("retryBtn").addEventListener("click", verify);
  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => {
    $("postText").value = EXAMPLES[b.dataset.example];
    clearImage();
    verify();
  }));
  $("langToggle").addEventListener("click", () => { setLang(lang() === "ar" ? "en" : "ar"); rerender(); });

  const dz = $("dropZone");
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => setImage(e.dataTransfer.files[0]));
  dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("fileInput").click(); } });
  $("fileInput").addEventListener("change", (e) => setImage(e.target.files[0]));
  $("removeImage").addEventListener("click", (e) => { e.stopPropagation(); clearImage(); });
  window.addEventListener("paste", (e) => {
    const item = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
    if (item) { setImage(item.getAsFile()); }
  });

  $("prepareBtn").addEventListener("click", openPrepare);
  document.querySelectorAll(".seg-btn").forEach((b) => b.addEventListener("click", () => {
    state.outLang = b.dataset.out;
    document.querySelectorAll(".seg-btn").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
    loadPrepared();
  }));
  $("copyBtn").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText($("preparedText").value);
    } catch {
      $("preparedText").select();
      document.execCommand("copy");
    }
    $("copyBtn").textContent = t("copied");
    setTimeout(() => { $("copyBtn").textContent = t("copy"); }, 1600);
  });

  // Re-render graphs only when the layout switches between horizontal and vertical.
  let resizeT, wasNarrow = window.innerWidth < 720;
  window.addEventListener("resize", () => {
    clearTimeout(resizeT);
    resizeT = setTimeout(() => {
      const narrow = window.innerWidth < 720;
      if (narrow !== wasNarrow && state.result && !$("results").hidden) renderResults(state.result, false);
      wasNarrow = narrow;
    }, 250);
  });
}

init();
