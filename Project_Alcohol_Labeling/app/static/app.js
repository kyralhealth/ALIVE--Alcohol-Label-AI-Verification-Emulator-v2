/* TTB Label Verifier — vanilla JS, no build step. */
"use strict";

const $ = (id) => document.getElementById(id);

const FIELD_NAMES = {
  brand_name: "Brand name",
  class_type: "Class / type",
  alcohol_content: "Alcohol content",
  net_contents: "Net contents",
  government_warning: "Government warning — text",
  warning_capitalization: "Government warning — capitalization",
  warning_bold: "Government warning — bold type",
};
const STATUS_LABELS = { match: "✓ Match", review: "⚠ Review", mismatch: "✕ Mismatch", missing: "✕ Missing" };
const VERDICTS = {
  pass:   { title: "✓ PASS", sub: "Everything on the label matches the application." },
  review: { title: "⚠ NEEDS REVIEW", sub: "No hard mismatches, but a human should look at the flagged items." },
  fail:   { title: "✕ ISSUES FOUND", sub: "At least one required item is wrong or missing." },
};

/* ------------------------------------------------------------- utilities */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function show(el, yes = true) { el.hidden = !yes; }
function setStatus(el, msg) { el.innerHTML = msg ? `<span class="spinner"></span>${esc(msg)}` : ""; show(el, !!msg); }
function setError(el, msg) { el.textContent = msg || ""; show(el, !!msg); }

function fieldsTable(fields) {
  const rows = fields.map((f) => `
    <tr>
      <td><strong>${esc(FIELD_NAMES[f.field] || f.field)}</strong></td>
      <td><span class="chip ${esc(f.status)}">${STATUS_LABELS[f.status] || esc(f.status)}</span></td>
      <td class="value">${esc(f.label_value ?? "—")}</td>
      <td class="value">${esc(f.application_value ?? "—")}</td>
      <td class="note">${esc(f.note ?? "")}</td>
    </tr>`).join("");
  return `<table class="fields">
    <thead><tr><th>Item</th><th>Result</th><th>On the label</th><th>In the application</th><th>Notes</th></tr></thead>
    <tbody>${rows}</tbody></table>`;
}

function verdictBanner(result) {
  const v = VERDICTS[result.overall];
  const time = result.elapsed_seconds != null ? ` Checked in ${result.elapsed_seconds}s.` : "";
  const legibility = result.image_legibility === "poor"
    ? ` ⚠ Image quality was poor${result.legibility_notes ? " — " + esc(result.legibility_notes) : ""}.`
    : "";
  return `<div class="verdict ${esc(result.overall)}">${v.title}<small>${v.sub}${time}${legibility}</small></div>`;
}

async function postForm(url, formData) {
  const resp = await fetch(url, { method: "POST", body: formData });
  let body = null;
  try { body = await resp.json(); } catch { /* non-JSON error */ }
  if (!resp.ok) {
    throw new Error((body && body.detail) ? body.detail : `Server error (${resp.status}).`);
  }
  return body;
}

/* ----------------------------------------------------------------- tabs */
function selectTab(which) {
  const single = which === "single";
  $("tab-single").classList.toggle("active", single);
  $("tab-batch").classList.toggle("active", !single);
  $("tab-single").setAttribute("aria-selected", single);
  $("tab-batch").setAttribute("aria-selected", !single);
  show($("panel-single"), single);
  show($("panel-batch"), !single);
}
$("tab-single").addEventListener("click", () => selectTab("single"));
$("tab-batch").addEventListener("click", () => selectTab("batch"));

/* ---------------------------------------------------------- dropzones */
function wireDropzone(zone, input, onFiles) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
  input.addEventListener("change", () => onFiles(input.files));
  ["dragover", "dragenter"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((t) => zone.addEventListener(t, (e) => { e.preventDefault(); zone.classList.remove("dragover"); }));
  zone.addEventListener("drop", (e) => onFiles(e.dataTransfer.files));
}

/* ---------------------------------------------------------------- single */
let singleFile = null;
wireDropzone($("drop-single"), $("file-single"), (files) => {
  if (!files || !files.length) return;
  singleFile = files[0];
  show($("drop-single-empty"), false);
  const img = $("preview-single");
  img.src = URL.createObjectURL(singleFile);
  show(img);
  $("filename-single").textContent = singleFile.name;
  show($("filename-single"));
});

$("form-single").addEventListener("submit", async (e) => {
  e.preventDefault();
  setError($("error-single"), "");
  show($("result-single"), false);
  if (!singleFile) { setError($("error-single"), "Please choose a label image first."); return; }

  const fd = new FormData($("form-single"));
  fd.append("image", singleFile, singleFile.name);
  $("btn-single").disabled = true;
  setStatus($("status-single"), "Reading the label…");
  try {
    const result = await postForm("/api/verify", fd);
    $("result-single").innerHTML = verdictBanner(result) + fieldsTable(result.fields);
    show($("result-single"));
  } catch (err) {
    setError($("error-single"), err.message);
  } finally {
    $("btn-single").disabled = false;
    setStatus($("status-single"), "");
  }
});

/* ----------------------------------------------------------------- batch */
let batchFiles = [];
wireDropzone($("drop-batch"), $("file-batch"), (files) => {
  if (!files || !files.length) return;
  batchFiles = Array.from(files);
  $("filenames-batch").textContent =
    `${batchFiles.length} image${batchFiles.length === 1 ? "" : "s"} selected: ` +
    batchFiles.slice(0, 8).map((f) => f.name).join(", ") + (batchFiles.length > 8 ? ", …" : "");
  show($("filenames-batch"));
});

$("btn-batch").addEventListener("click", async () => {
  setError($("error-batch"), "");
  show($("result-batch"), false);
  show($("summary-batch"), false);
  const csv = $("file-csv").files[0];
  if (!batchFiles.length) { setError($("error-batch"), "Please choose the label images first."); return; }
  if (!csv) { setError($("error-batch"), "Please choose the applications CSV file."); return; }

  const fd = new FormData();
  batchFiles.forEach((f) => fd.append("images", f, f.name));
  fd.append("applications", csv, csv.name);
  $("btn-batch").disabled = true;
  setStatus($("status-batch"), `Checking ${batchFiles.length} labels…`);
  try {
    const data = await postForm("/api/verify-batch", fd);
    renderBatch(data);
  } catch (err) {
    setError($("error-batch"), err.message);
  } finally {
    $("btn-batch").disabled = false;
    setStatus($("status-batch"), "");
  }
});

function renderBatch(data) {
  const s = data.summary || {};
  $("summary-batch").innerHTML = `
    <div class="sum-card pass"><span class="n">${s.pass || 0}</span>Pass</div>
    <div class="sum-card review"><span class="n">${s.review || 0}</span>Needs review</div>
    <div class="sum-card fail"><span class="n">${s.fail || 0}</span>Issues found</div>
    <div class="sum-card error"><span class="n">${s.error || 0}</span>Couldn't check</div>`;
  show($("summary-batch"));

  const order = { fail: 0, error: 1, review: 2, pass: 3 };
  const items = [...data.items].sort((a, b) => {
    const ka = a.error ? "error" : (a.result ? a.result.overall : "error");
    const kb = b.error ? "error" : (b.result ? b.result.overall : "error");
    return order[ka] - order[kb] || a.filename.localeCompare(b.filename);
  });

  $("result-batch").innerHTML = items.map((item) => {
    if (item.error) {
      return `<details class="batch-item"><summary>
          <span class="chip error">✕ Couldn't check</span> ${esc(item.filename)}</summary>
        <div class="body"><p class="note">${esc(item.error)}</p></div></details>`;
    }
    const r = item.result;
    const chipClass = r.overall === "pass" ? "match" : r.overall === "review" ? "review" : "mismatch";
    const label = r.overall === "pass" ? "✓ Pass" : r.overall === "review" ? "⚠ Review" : "✕ Issues";
    return `<details class="batch-item"><summary>
        <span class="chip ${chipClass}">${label}</span> ${esc(item.filename)}</summary>
      <div class="body">${verdictBanner(r)}${fieldsTable(r.fields)}</div></details>`;
  }).join("");
  show($("result-batch"));
}

/* ----------------------------------------------------------------- boot */
fetch("/api/health").then((r) => r.json()).then((h) => {
  const badge = $("mode-badge");
  badge.textContent = h.mode === "demo" ? "Demo mode — sample labels only" : `Live — ${h.model}`;
  show(badge);
}).catch(() => {});
