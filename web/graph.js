// Evidence Graph: Claim → Source → Original → Verification → Final wording (inline SVG, RTL-aware).
import { t, lang } from "./i18n.js";

const SVGNS = "http://www.w3.org/2000/svg";

function el(name, attrs = {}, text) {
  const n = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
}

function clip(s, n = 34) {
  s = (s || "").replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// Mirrors app/core/prepare.py: keep the verified original verbatim unless fabricated / not found (spec 6.8).
export function finalWording(c) {
  if (c.match_type !== "not_found" && c.grade_class !== "mawdu" && (c.ayah || c.source)) {
    const hadith = c.match_type === "partial" && c.source?.excerpt_ar ? c.source.excerpt_ar : c.source?.text_ar;
    return { kind: "keep", text: c.ayah ? c.ayah.text_uthmani : hadith };
  }
  if (c.alternatives?.length) return { kind: "replace", text: c.alternatives[0].text_ar };
  return { kind: "remove", text: "" };
}

function sourceLabel(c) {
  if (c.ayah) return `${c.ayah.surah_name_ar} ${c.ayah.ref}`;
  if (c.source) return `${c.source.collection || ""} ${c.source.number || ""}`.trim();
  return t("mt_not_found");
}

export function buildNodes(c) {
  const fw = finalWording(c);
  const statusCls = c.status;
  return [
    { key: "claim", label: t("node_claim"), value: clip(c.claim_text), cls: "neutral" },
    { key: "source", label: t("node_source"), value: clip(sourceLabel(c), 28),
      cls: c.match_type === "not_found" ? "red" : "neutral" },
    { key: "original", label: t("node_original"),
      value: clip(c.ayah?.text_clean || c.source?.text_ar || "—"), cls: c.match_type === "not_found" ? "red" : "neutral" },
    { key: "verify", label: t("node_verify"), value: `${t("status_" + c.status)} · ${c.sanad_score}`, cls: statusCls },
    { key: "final", label: t("node_final"), value: clip(t("final_" + fw.kind), 30), cls: statusCls },
  ];
}

/**
 * Render the graph into `container`. `details(key)` returns an HTML string for the detail panel.
 */
export function renderGraph(container, c, details) {
  container.innerHTML = "";
  const nodes = buildNodes(c);
  const rtl = lang() === "ar";
  const vertical = container.clientWidth < 640;
  const W = vertical ? 340 : 1000;
  const nw = vertical ? 300 : 176, nh = 66, gap = vertical ? 26 : (W - 24 - 5 * 176) / 4;
  const H = vertical ? nodes.length * nh + (nodes.length - 1) * gap + 20 : nh + 24;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "group", "aria-label": t("evidence_graph") });
  const defs = el("defs");
  const marker = el("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "8", refY: "5", markerWidth: "7",
    markerHeight: "7", orient: "auto-start-reverse" });
  marker.appendChild(el("path", { d: "M0,0 L10,5 L0,10 z", fill: "#14655F" }));
  defs.appendChild(marker);
  svg.appendChild(defs);

  const pos = nodes.map((_, i) => {
    if (vertical) return { x: (W - nw) / 2, y: 10 + i * (nh + gap) };
    const x = 12 + i * (176 + gap);
    return { x: rtl ? W - x - 176 : x, y: 12 };
  });

  const edges = [];
  for (let i = 0; i < nodes.length - 1; i++) {
    const a = pos[i], b = pos[i + 1];
    let d;
    if (vertical) d = `M${W / 2},${a.y + nh} L${W / 2},${b.y - 2}`;
    else if (rtl) d = `M${a.x},${a.y + nh / 2} L${b.x + 176 + 2},${b.y + nh / 2}`;
    else d = `M${a.x + 176},${a.y + nh / 2} L${b.x - 2},${b.y + nh / 2}`;
    const e = el("path", { d, class: "gedge", "marker-end": "url(#arrow)" });
    svg.appendChild(e);
    edges.push(e);
  }

  const panel = document.createElement("div");
  panel.className = "graph-detail";
  panel.setAttribute("aria-live", "polite");
  panel.innerHTML = `<p class="muted small">${t("graph_hint")}</p>`;

  const gs = nodes.map((n, i) => {
    // Outer <g> positions (SVG attribute); inner <g> animates (CSS transform would override the attribute).
    const holder = el("g", { transform: `translate(${pos[i].x},${pos[i].y})` });
    const g = el("g", { class: `gnode ${n.cls}`, tabindex: "0", role: "button", "aria-label": `${n.label}: ${n.value}` });
    holder.appendChild(g);
    g.appendChild(el("rect", { width: vertical ? nw : 176, height: nh, rx: 14 }));
    const tx = rtl ? (vertical ? nw : 176) - 14 : 14;
    const anchor = "start"; // SVG inherits the page direction: "start" is the right edge in RTL
    g.appendChild(el("circle", { class: "dot", cx: rtl ? 14 : (vertical ? nw : 176) - 14, cy: 16, r: 5 }));
    g.appendChild(el("text", { class: "gl", x: tx, y: 24, "text-anchor": anchor }, n.label));
    g.appendChild(el("text", { class: "gv", x: tx, y: 48, "text-anchor": anchor }, n.value));
    const select = () => {
      gs.forEach((x) => x.classList.remove("sel"));
      g.classList.add("sel");
      panel.innerHTML = `<h4>${n.label}</h4>${details(n.key)}`;
    };
    g.addEventListener("click", select);
    g.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(); }
    });
    svg.appendChild(holder);
    return g;
  });

  container.appendChild(svg);
  container.appendChild(panel);

  // Reveal step by step, paced by the evidence trace (at least 180 ms per node).
  const steps = c.evidence_trace?.length || 5;
  const delay = Math.max(180, Math.min(420, 1400 / steps));
  gs.forEach((g, i) => {
    setTimeout(() => {
      g.classList.add("on");
      if (i > 0) edges[i - 1].classList.add("on");
      if (i === gs.length - 1) g.dispatchEvent(new Event("click"));
    }, 120 + i * delay);
  });
}
