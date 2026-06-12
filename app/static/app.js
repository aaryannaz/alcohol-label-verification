// Fallback field config. The authoritative list is fetched from GET /fields at
// startup (loadFieldConfig); this hardcoded copy only keeps the UI working if
// that request fails. The backend (fields.py) is the single source of truth.
let FIELD_CONFIG = [
  { key: "brand_name", label: "Brand name", type: "input" },
  { key: "class_type", label: "Class/type designation", type: "input" },
  { key: "alcohol_content", label: "Alcohol content", type: "input" },
  { key: "net_contents", label: "Net contents", type: "input" },
  { key: "government_warning", label: "Government warning", type: "textarea" },
  { key: "domestic_name_address", label: "Domestic name/address", type: "textarea" },
  { key: "importer_name_address", label: "Importer name/address", type: "textarea" },
  { key: "country_of_origin", label: "Country of origin", type: "input" },
  { key: "sulfite_declaration", label: "Sulfite declaration", type: "input" },
  { key: "appellation_of_origin", label: "Appellation of origin", type: "input" },
  { key: "fanciful_name", label: "Fanciful name", type: "input" },
];

let FIELD_LOOKUP = Object.fromEntries(FIELD_CONFIG.map((field) => [field.key, field]));

function setFieldConfig(specs) {
  FIELD_CONFIG = specs.map((spec) => ({
    key: spec.key,
    label: spec.label,
    type: spec.control === "textarea" ? "textarea" : "input",
  }));
  FIELD_LOOKUP = Object.fromEntries(FIELD_CONFIG.map((field) => [field.key, field]));
}

async function loadFieldConfig() {
  try {
    const response = await fetch("/fields");
    if (!response.ok) return;
    const body = await response.json();
    if (Array.isArray(body.fields) && body.fields.length) setFieldConfig(body.fields);
  } catch (error) {
    // Network/parse failure — keep the fallback config so the UI still works.
  }
}
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
// Process up to this many batch files at once. The expected batch is ~10 files,
// so a pool of 10 clears a full batch in a single parallel wave (~2-3s, one
// extraction's time). Kept at/below the per-IP rate limit (see security.py) so a
// single batch never throttles itself.
const BATCH_CONCURRENCY = 10;
const ACCEPTED_EXTENSIONS = new Set(["pdf", "png", "jpg", "jpeg", "webp"]);
const ACCEPTED_MIME_TYPES = new Set(["application/pdf", "image/png", "image/jpeg", "image/webp"]);
const FILE_LABELS = {
  front: "First file",
  back: "Second file",
};
const PRODUCT_CATEGORY_OPTIONS = [
  { value: "malt_beverage", label: "Malt beverage" },
  { value: "distilled_spirits", label: "Distilled spirits" },
  { value: "wine", label: "Wine" },
];
const ORIGIN_OPTIONS = [
  { value: "domestic", label: "Domestic" },
  { value: "imported", label: "Imported" },
];

const state = {
  requirements: { required: [], conditional: [], optional: [] },
  extracted: {},
  extractedKey: null,
  expectedValues: {},
  validation: {},
  lastResult: null,
  inFlight: false,
  files: {
    front: null,
    back: null,
  },
  batch: {
    items: [],
    nextId: 1,
    processing: false,
  },
};

const THEME_STORAGE_KEY = "alcohol-label-theme";
const LAYOUT_STORAGE_KEY = "alcohol-label-layout";
const THEMES = ["light", "dark"];
const LAYOUTS = ["standard", "government"];
const themeToggle = document.querySelector("#themeToggle");
const layoutSelect = document.querySelector("#layoutSelect");
const categoryGroup = document.getElementById("categoryGroup");
const originGroup = document.getElementById("originGroup");
const uploadModeGroup = document.getElementById("uploadModeGroup");

// Product category, origin, and upload mode are radio groups (visible options,
// friendlier than dropdowns). Read/write the selected value by radio name.
function radioValue(name) {
  const el = document.querySelector('input[name="' + name + '"]:checked');
  return el ? el.value : "";
}
function setRadioValue(name, val) {
  const el = document.querySelector('input[name="' + name + '"][value="' + val + '"]');
  if (el) el.checked = true;
}

const frontImage = document.querySelector("#frontImage");
const backImage = document.querySelector("#backImage");
const expectedFields = document.querySelector("#expectedFields");
const verifyButton = document.querySelector("#verifyButton");
const labelProgress = document.getElementById("labelProgress");
const statusText = document.querySelector("#statusText");
const errorBox = document.querySelector("#errorBox");
const resultsBody = document.querySelector("#resultsBody");
const resultsSummary = document.getElementById("resultsSummary");
const busySpinner = document.getElementById("busySpinner");
const chooseFileInputs = document.getElementById("chooseFileInputs");
const dropZoneInputs = document.getElementById("dropZoneInputs");
const batchPanel = document.getElementById("batchPanel");
const batchFiles = document.getElementById("batchFiles");
const batchDropZone = document.getElementById("batchDropZone");
const batchBody = document.getElementById("batchBody");
const processBatchButton = document.getElementById("processBatchButton");
const clearBatchButton = document.getElementById("clearBatchButton");
const uploadInputs = Array.from(document.querySelectorAll("[data-file-slot]"));
const dropZones = Array.from(document.querySelectorAll("[data-drop-slot]"));

function currentTheme() {
  const theme = document.documentElement.dataset.theme;
  return THEMES.includes(theme) ? theme : "light";
}

function setTheme(theme) {
  const normalizedTheme = THEMES.includes(theme) ? theme : "light";
  document.documentElement.dataset.theme = normalizedTheme;
  if (themeToggle) themeToggle.checked = normalizedTheme === "dark";
  try {
    localStorage.setItem(THEME_STORAGE_KEY, normalizedTheme);
  } catch {
    return;
  }
}

function currentLayout() {
  const layout = document.documentElement.dataset.layout;
  return LAYOUTS.includes(layout) ? layout : "standard";
}

function setLayout(layout) {
  const normalizedLayout = LAYOUTS.includes(layout) ? layout : "standard";
  document.documentElement.dataset.layout = normalizedLayout;
  if (layoutSelect) layoutSelect.value = normalizedLayout;
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, normalizedLayout);
  } catch {
    return;
  }
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
  return bytes + " B";
}

function fileExtension(file) {
  const parts = file.name.toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function validateClientFile(file) {
  if (!file) return "Select a file first.";
  if (!ACCEPTED_EXTENSIONS.has(fileExtension(file))) {
    return "Unsupported file extension. Use PDF, PNG, JPEG, or WebP.";
  }
  if (file.type && !ACCEPTED_MIME_TYPES.has(file.type)) {
    return "Unsupported file type. Use PDF, PNG, JPEG, or WebP.";
  }
  if (file.size === 0) {
    return "This file is empty. Choose a different file.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return "File is larger than 10 MB. Choose a smaller file.";
  }
  return "";
}

function inputsForSlot(slot) {
  return uploadInputs.filter((input) => input.dataset.fileSlot === slot);
}

function syncInputFiles(slot, file) {
  for (const input of inputsForSlot(slot)) {
    if (!file) {
      input.value = "";
      continue;
    }

    try {
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
    } catch {
      if (input.files.length && input.files[0] !== file) input.value = "";
    }
  }
}

function renderFileState(slot) {
  const file = state.files[slot];
  const fileText = file ? file.name + " · " + formatBytes(file.size) : "";

  for (const summary of document.querySelectorAll("[data-file-summary=" + JSON.stringify(slot) + "]")) {
    summary.classList.toggle("has-file", Boolean(file));
  }

  for (const name of document.querySelectorAll("[data-file-name=" + JSON.stringify(slot) + "]")) {
    name.textContent = fileText;
  }

  for (const button of document.querySelectorAll("[data-remove-file=" + JSON.stringify(slot) + "]")) {
    button.hidden = !file;
  }

  for (const zone of document.querySelectorAll("[data-drop-slot=" + JSON.stringify(slot) + "]")) {
    zone.classList.toggle("has-file", Boolean(file));
  }

  renderLabelPreview();
}

function renderLabelPreview() {
  const container = document.getElementById("labelPreview");
  const panel = document.getElementById("labelPreviewPanel");
  if (!container) return;

  // Release any previous object URLs before re-rendering.
  (state.previewUrls || []).forEach((url) => URL.revokeObjectURL(url));
  state.previewUrls = [];
  container.innerHTML = "";

  const present = [["front", state.files.front], ["back", state.files.back]].filter(function(entry) { return entry[1]; });
  if (!present.length) {
    if (panel) panel.hidden = true;
    return;
  }
  if (panel) panel.hidden = false;

  for (const [slot, file] of present) {
    const item = document.createElement("figure");
    item.className = "label-preview-item";

    const caption = document.createElement("figcaption");
    caption.className = "label-preview-label";
    caption.textContent = FILE_LABELS[slot];
    item.appendChild(caption);

    if (file.type && file.type.indexOf("image/") === 0) {
      const url = URL.createObjectURL(file);
      state.previewUrls.push(url);
      const img = document.createElement("img");
      img.src = url;
      img.alt = FILE_LABELS[slot] + " label artwork";
      img.className = "label-preview-img";
      img.tabIndex = 0;
      img.setAttribute("role", "button");
      img.title = "Click to preview";
      img.setAttribute("aria-label", "Preview " + FILE_LABELS[slot] + " label (opens a larger view)");
      const openThis = function() { openLightbox(url, img.alt); };
      img.addEventListener("click", openThis);
      img.addEventListener("keydown", function(event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openThis();
        }
      });
      item.appendChild(img);
    } else if (file.type === "application/pdf" || /\.pdf$/i.test(file.name || "")) {
      // Render PDFs in the browser's built-in viewer (scrollable, all pages).
      const url = URL.createObjectURL(file);
      state.previewUrls.push(url);
      const frame = document.createElement("iframe");
      frame.src = url;
      frame.className = "label-preview-pdf";
      frame.title = FILE_LABELS[slot] + " label PDF preview";
      frame.setAttribute("loading", "lazy");
      item.appendChild(frame);

      const open = document.createElement("a");
      open.href = url;
      open.target = "_blank";
      open.rel = "noopener";
      open.className = "label-preview-open";
      open.textContent = "Open PDF in a new tab";
      item.appendChild(open);
    } else {
      const note = document.createElement("span");
      note.className = "label-preview-note";
      note.textContent = file.name + " — preview not available";
      item.appendChild(note);
    }

    container.appendChild(item);
  }
}

// Quick Look–style preview: click a label thumbnail to see it large on a dim
// backdrop. Close by clicking the backdrop, the close button, or pressing Escape.
let lightboxLastFocus = null;

function getLightbox() {
  let el = document.getElementById("lightbox");
  if (!el) {
    el = document.createElement("div");
    el.id = "lightbox";
    el.className = "lightbox";
    el.hidden = true;
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", "Label preview");
    el.innerHTML =
      '<button type="button" class="lightbox-close" aria-label="Close preview">&times;</button>' +
      '<img class="lightbox-img" alt="" />';
    el.addEventListener("click", function(event) {
      if (event.target === el || event.target.classList.contains("lightbox-close")) {
        closeLightbox();
      }
    });
    document.body.appendChild(el);
  }
  return el;
}

function openLightbox(src, alt) {
  const box = getLightbox();
  const img = box.querySelector(".lightbox-img");
  img.src = src;
  img.alt = alt || "";
  lightboxLastFocus = document.activeElement;
  box.hidden = false;
  document.body.classList.add("lightbox-open");
  box.querySelector(".lightbox-close").focus();
  document.addEventListener("keydown", onLightboxKey);
}

function closeLightbox() {
  const box = document.getElementById("lightbox");
  if (!box || box.hidden) return;
  box.hidden = true;
  document.body.classList.remove("lightbox-open");
  document.removeEventListener("keydown", onLightboxKey);
  if (lightboxLastFocus && lightboxLastFocus.focus) lightboxLastFocus.focus();
  lightboxLastFocus = null;
}

function onLightboxKey(event) {
  if (event.key === "Escape") {
    event.preventDefault();
    closeLightbox();
  }
}

// Progressive step highlight: spotlight the one section the reviewer is on now —
// set up & upload (no label yet) -> review the fields (label loaded) -> results
// (verified). Guides the eye start-to-finish without blocking. Called on every
// state transition (file change, extraction, verify).
const STEP_CALLOUTS = {
  upload: { num: 1, text: "Upload the label artwork to begin." },
  review: { num: 2, text: "Review these fields, then click Verify Against Label." },
  done: { num: 3, text: "Here are your verification results." },
};

function getStepCallout() {
  let el = document.getElementById("stepCallout");
  if (!el) {
    el = document.createElement("div");
    el.id = "stepCallout";
    el.className = "step-callout";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.innerHTML = '<span class="step-num" aria-hidden="true"></span><span class="step-text"></span>';
  }
  return el;
}

function updateStepHighlight() {
  const setup = document.querySelector(".setup-panel");
  const fields = document.querySelector(".fields-panel");
  const results = document.querySelector(".results-panel");
  const hasLabel = Boolean(state.files.front || state.files.back);
  const hasResult = Boolean(state.lastResult);
  const step = !hasLabel ? "upload" : !hasResult ? "review" : "done";

  if (setup) setup.classList.toggle("step-active", step === "upload");
  if (fields) fields.classList.toggle("step-active", step === "review");
  if (results) results.classList.toggle("step-active", step === "done");
  if (verifyButton) verifyButton.classList.toggle("is-ready", step === "review");

  // Move the callout box to the active section and update its text.
  const target = step === "upload" ? setup : step === "review" ? fields : results;
  const info = STEP_CALLOUTS[step];
  if (target && info) {
    const callout = getStepCallout();
    callout.querySelector(".step-num").textContent = info.num;
    callout.querySelector(".step-text").textContent = info.text;
    if (callout.parentElement !== target) target.prepend(callout);
  }
}

function setSelectedFile(slot, file) {
  const error = validateClientFile(file);
  if (error) {
    showError(error);
    setStatus("File selection needs attention");
    syncInputFiles(slot, state.files[slot]);
    renderFileState(slot);
    return false;
  }

  clearError();
  state.files[slot] = file;
  syncInputFiles(slot, file);
  renderFileState(slot);
  setStatus(FILE_LABELS[slot] + " selected");
  maybeAutoExtractLabel();
  updateStepHighlight();
  return true;
}

function clearSelectedFile(slot) {
  state.files[slot] = null;
  syncInputFiles(slot, null);
  renderFileState(slot);
  clearError();
  setStatus("");
  updateStepHighlight();
}

function draggedFiles(event) {
  return Array.from(event.dataTransfer?.types || []).includes("Files");
}

function orderedVisibleFields() {
  const visible = [
    ...state.requirements.required,
    ...state.requirements.conditional,
    ...state.requirements.optional,
  ];
  return FIELD_CONFIG.map((field) => field.key).filter((key) => visible.includes(key));
}

function fieldRequirement(key) {
  if (state.requirements.required.includes(key)) return "required";
  if (state.requirements.conditional.includes(key)) return "conditional";
  return "optional";
}

function inputName(prefix, key) {
  return prefix + "_" + key;
}

function createField(prefix, key) {
  const field = FIELD_LOOKUP[key];
  const row = document.createElement("div");
  row.className = "field-row";
  row.dataset.field = key;

  const label = document.createElement("label");
  label.setAttribute("for", inputName(prefix, key));

  const name = document.createElement("span");
  name.className = "field-name";
  name.textContent = field.label;

  const requirement = fieldRequirement(key);
  if (requirement === "required") {
    const star = document.createElement("span");
    star.className = "req-mark";
    star.textContent = "*";
    star.title = "Required";
    star.setAttribute("aria-hidden", "true");
    name.appendChild(star);
    const sr = document.createElement("span");
    sr.className = "sr-only";
    sr.textContent = " required";
    name.appendChild(sr);
  }
  label.appendChild(name);

  const control = document.createElement(field.type === "textarea" ? "textarea" : "input");
  control.id = inputName(prefix, key);
  control.name = key;
  control.autocomplete = "off";

  // Textareas grow to fit their content (no scrollbar, no drag handle).
  if (field.type === "textarea") {
    control.addEventListener("input", function() { autosizeTextarea(control); });
  }

  // The government warning is editable and checked against the statutory text on
  // both sides; it auto-fills from the label extraction.

  row.appendChild(label);
  row.appendChild(control);
  return row;
}

function renderFieldStack(container, prefix) {
  const headingEl = container.querySelector("h3");
  container.innerHTML = headingEl ? headingEl.outerHTML : "";

  // Fields render in COLA-form order (see fields.py); required fields are marked
  // with an asterisk rather than grouped, so there is no requirement divider.
  for (const key of orderedVisibleFields()) {
    container.appendChild(createField(prefix, key));
  }
}

function showError(message) {
  errorBox.hidden = false;
  errorBox.textContent = message;
}

function clearError() {
  errorBox.hidden = true;
  errorBox.textContent = "";
}

function setStatus(message) {
  statusText.textContent = message;
}

function setBusy(busy) {
  // Lock the inputs that would race a rebuild of the field stacks (category /
  // origin) and the action buttons while a request is in flight, and show a
  // spinner / announce busy state to assistive tech.
  state.inFlight = busy;
  const controls = [categoryGroup, originGroup, uploadModeGroup, verifyButton, themeToggle, layoutSelect];
  for (const control of controls) {
    if (control) control.disabled = busy;
  }
  for (const input of uploadInputs) {
    input.disabled = busy;
  }
  if (busySpinner) busySpinner.hidden = !busy;
  const workspace = document.querySelector(".workspace");
  if (workspace) workspace.setAttribute("aria-busy", busy ? "true" : "false");
}

function renderEmptyResults(message) {
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  resultsBody.innerHTML = "";
  cell.colSpan = 4;
  cell.className = "empty-row";
  cell.textContent = message || "No verification results yet.";
  row.appendChild(cell);
  resultsBody.appendChild(row);
  const compliance = document.getElementById("complianceChecks");
  if (compliance) compliance.innerHTML = "";
  state.lastResult = null;
  if (resultsSummary) resultsSummary.textContent = "";
  const verdict = document.getElementById("resultsVerdict");
  if (verdict) verdict.hidden = true;
  updateStepHighlight();
}

function formValues(container) {
  const values = {};
  for (const field of FIELD_CONFIG) {
    const control = container.querySelector("[name=" + JSON.stringify(field.key) + "]");
    values[field.key] = control ? control.value.trim() : "";
  }
  return values;
}

// Grow a textarea to fit its content so the full text shows with no scrollbar.
function autosizeTextarea(el) {
  if (!el || el.tagName !== "TEXTAREA") return;
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function setExpectedValues(values) {
  for (const [key, value] of Object.entries(values || {})) {
    const control = expectedFields.querySelector("[name=" + JSON.stringify(key) + "]");
    if (control) {
      control.value = value || "";
      autosizeTextarea(control);
    }
  }
}

const STATUS_LABELS = {
  "PASS": "Pass",
  "FAIL": "Fail",
  "MISSING": "Missing",
  "NOT REQUIRED": "Not required",
  "NOT REVIEWED": "Not reviewed",
  "EXPECTED VALUE MISSING": "No expected value",
  "FAIL_MISSING_HEADING": "Heading missing",
  "FAIL_HEADING_FORMAT": "Heading format",
  "FAIL_TEXT_MISMATCH": "Wording mismatch",
  "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY": "On label — confirm",
  "DEEMED_FROM_BOTTLER": "Brand = bottler — confirm",
  "EXEMPT_TABLE_WINE": "Exempt (table wine)",
  "FAIL_APPELLATION_REQUIRED_BY_TRIGGER": "Appellation required",
  "FAIL_NOT_ALLCAPS": "Not all-caps",
};

function statusClass(status) {
  if (status === "PASS" || status === "EXEMPT_TABLE_WINE") return "status-pass";
  if (status === "NOT REQUIRED") return "status-neutral";
  if (status === "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY" || status === "DEEMED_FROM_BOTTLER") return "status-processing";
  if (status === "MISSING" || status === "EXPECTED VALUE MISSING") return "status-missing";
  return "status-fail";
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function makeBadge(status) {
  const badge = document.createElement("span");
  badge.className = "status-badge " + statusClass(status);
  badge.textContent = statusLabel(status);
  badge.title = status;
  return badge;
}

// A field's value shown beneath its per-side badge (used for the government
// warning, where each column carries both a status and the compared text).
function makeValueText(value) {
  const span = document.createElement("span");
  span.className = "cell-value";
  span.textContent = value || "";
  return span;
}

function isFlaggedStatus(status) {
  const cls = statusClass(status);
  return cls === "status-fail" || cls === "status-missing";
}

function renderResults(response) {
  state.lastResult = response;
  updateStepHighlight();
  const expected = response.expected || formValues(expectedFields);
  const reviewed = response.reviewed || response.extracted || state.extracted || {};
  const validation = response.validation || {};
  const requirements = response.field_requirements || {};
  resultsBody.innerHTML = "";

  // Show only the fields applicable to this product category, in requirement
  // order (required, then conditional, then optional). Falls back to all fields.
  const applicable = [].concat(
    requirements.required || [],
    requirements.conditional || [],
    requirements.optional || [],
  );
  const keys = applicable.length ? applicable : FIELD_CONFIG.map((field) => field.key);

  let passed = 0;
  let attention = 0;

  for (const key of keys) {
    const config = FIELD_LOOKUP[key];
    if (!config) continue;
    const row = document.createElement("tr");
    const fieldCell = document.createElement("td");
    const statusCell = document.createElement("td");
    const expectedCell = document.createElement("td");
    const reviewedCell = document.createElement("td");
    fieldCell.textContent = config.label;

    const raw = validation[key];
    if (raw && typeof raw === "object") {
      // government_warning is checked against the statutory text on both sides
      // and returns {expected, label}: a badge in each value column, plus a
      // combined STATUS that passes only when both sides match the statute.
      const combined =
        raw.expected === "PASS" && raw.label === "PASS" ? "PASS" : "FAIL";
      statusCell.appendChild(makeBadge(combined));
      expectedCell.appendChild(makeBadge(raw.expected));
      expectedCell.appendChild(makeValueText(expected[key]));
      reviewedCell.appendChild(makeBadge(raw.label));
      reviewedCell.appendChild(makeValueText(reviewed[key]));
      if (combined === "PASS") {
        passed += 1;
      } else {
        attention += 1;
        row.className = "is-flagged";
      }
    } else {
      const status = raw || "NOT REVIEWED";
      if (status === "PASS" || status === "EXEMPT_TABLE_WINE") passed += 1;
      else if (isFlaggedStatus(status)) attention += 1;
      statusCell.appendChild(makeBadge(status));
      expectedCell.textContent = expected[key] || "";
      reviewedCell.textContent = reviewed[key] || "";
      if (isFlaggedStatus(status)) row.className = "is-flagged";
    }

    row.appendChild(fieldCell);
    row.appendChild(statusCell);
    row.appendChild(expectedCell);
    row.appendChild(reviewedCell);
    resultsBody.appendChild(row);
  }

  const checked = keys.filter((key) => FIELD_LOOKUP[key]).length;
  if (resultsSummary) {
    resultsSummary.textContent = `${checked} fields checked · ${passed} passed · ${attention} need attention`;
  }

  const complianceFails = (response.compliance_checks || []).filter((c) => c.status === "FAIL").length;
  renderVerdict(checked, attention + complianceFails);

  renderComplianceChecks(response.compliance_checks || []);
}

// One prominent overall pass/attention banner above the per-field table, so a
// clean result reads at a glance instead of only as small green words.
function renderVerdict(checked, flagged) {
  const banner = document.getElementById("resultsVerdict");
  if (!banner) return;
  if (!checked) {
    banner.hidden = true;
    return;
  }
  const pass = flagged === 0;
  banner.hidden = false;
  banner.className = "results-verdict " + (pass ? "verdict-pass" : "verdict-attention");
  banner.querySelector(".results-verdict-icon").textContent = pass ? "✓" : "!";
  banner.querySelector(".results-verdict-text").textContent = pass
    ? "Passed — all checks cleared"
    : `Needs attention — ${flagged} ${flagged === 1 ? "item" : "items"} to review`;
}

function complianceStatusClass(status) {
  if (status === "PASS") return "status-pass";
  if (status === "FAIL") return "status-missing";
  return "status-neutral";
}

function renderComplianceChecks(checks) {
  const container = document.getElementById("complianceChecks");
  if (!container) return;
  container.innerHTML = "";
  if (!checks.length) return;

  const heading = document.createElement("h3");
  heading.textContent = "Label compliance checks";
  container.appendChild(heading);

  const list = document.createElement("ul");
  for (const check of checks) {
    const item = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = "status-badge " + complianceStatusClass(check.status);
    badge.textContent = check.status;
    item.appendChild(badge);
    item.appendChild(document.createTextNode(" " + check.label + " — " + check.detail));
    list.appendChild(item);
  }
  container.appendChild(list);
}

const REQUEST_TIMEOUT_MS = 90000;

async function fetchWithTimeout(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, Object.assign({}, options, { signal: controller.signal }));
  } catch (error) {
    if (error && error.name === "AbortError") {
      throw new Error("The request timed out. Please try again.");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function parseApiResponse(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = body.error || body.detail || {};
    throw new Error(error.message || error.code || "Request failed");
  }
  return body;
}

async function refreshRequirements() {
  clearError();
  setStatus("Loading requirements");
  const params = new URLSearchParams({
    product_category: radioValue("productCategory"),
    origin_type: radioValue("originType"),
  });
  const response = await fetch("/field-requirements?" + params.toString());
  const body = await parseApiResponse(response);
  state.requirements = body.field_requirements;
  renderFieldStack(expectedFields, "expected");
  setExpectedValues(state.expectedValues);
  setStatus("");
}

function labelFileKey() {
  const f = state.files.front;
  const b = state.files.back;
  return [f ? f.name + ":" + f.size : "", b ? b.name + ":" + b.size : ""].join("|");
}

async function runLabelExtraction() {
  // POST the label artwork and store the reviewed snapshot. Throws on failure;
  // the caller manages busy state and error display.
  // Order-agnostic: send whichever label slot(s) have a file, first one as the
  // primary image — so it doesn't matter which slot the reviewer used.
  const files = [state.files.front, state.files.back].filter(Boolean);
  const formData = new FormData();
  formData.append("product_category", radioValue("productCategory"));
  formData.append("origin_type", radioValue("originType"));
  formData.append("front_image", files[0]);
  if (files[1]) formData.append("back_image", files[1]);
  const response = await fetchWithTimeout("/extract", { method: "POST", body: formData });
  const body = await parseApiResponse(response);
  state.extracted = body.extracted || {};
  state.extractedKey = labelFileKey();
}

function maybeAutoExtractLabel() {
  // Reading the label IS what fills the form, so do it automatically — on upload,
  // and again on a category/origin change (the extraction is category-scoped, so
  // that caller invalidates extractedKey first). Skip when no label is uploaded
  // yet, while a request is in flight, and when these exact files were already read.
  if (!state.files.front && !state.files.back) return;
  if (state.inFlight) return;
  if (state.extractedKey === labelFileKey()) return;
  extractFields();
}

async function extractFields() {
  clearError();

  if (!state.files.front && !state.files.back) {
    showError("Add at least one label.");
    setStatus("File selection needs attention");
    return;
  }

  setBusy(true);
  if (labelProgress) labelProgress.hidden = false;
  setStatus("Extracting fields");
  try {
    await runLabelExtraction();
    state.expectedValues = state.extracted;
    setExpectedValues(state.expectedValues);
    setStatus("Fields extracted from the label — edit each field to match the COLA application, then Verify");
  } catch (error) {
    showError(error.message);
    setStatus("Extraction failed");
  } finally {
    if (labelProgress) labelProgress.hidden = true;
    setBusy(false);
  }
}

async function verifyReviewedFields() {
  clearError();
  if (!state.files.front && !state.files.back) {
    showError("Add at least one label to verify against.");
    setStatus("File selection needs attention");
    return;
  }
  setBusy(true);
  try {
    // Read the label if these exact files haven't been read yet, so Verify works
    // on its own; re-verifying after editing fields stays instant (no extra call).
    if (state.extractedKey !== labelFileKey()) {
      setStatus("Reading the label");
      await runLabelExtraction();
    }
    setStatus("Verifying fields");
    const response = await fetchWithTimeout("/verify-reviewed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_category: radioValue("productCategory"),
        origin_type: radioValue("originType"),
        expected: formValues(expectedFields),
        reviewed: state.extracted,
      }),
    });
    const body = await parseApiResponse(response);
    renderResults(body);
    setStatus("Verification complete");
  } catch (error) {
    showError(error.message);
    setStatus("Verification failed");
  } finally {
    setBusy(false);
  }
}

function batchStatusClass(status) {
  if (status === "Pass") return "status-pass";
  if (status === "Needs attention") return "status-missing";
  if (status === "Processing") return "status-processing";
  if (status === "Error") return "status-fail";
  return "status-ready";
}

function batchStatusText(item) {
  return item.status;
}

// True once a row carries a verdict and can be opened in the editor.
function isBatchItemVerified(item) {
  return item.status === "Pass" || item.status === "Needs attention";
}

function canProcessBatchItem(item) {
  return Boolean(item.file) && !item.clientError && item.status !== "Processing" && !isBatchItemVerified(item);
}

// Derive a row's triage verdict from a full /verify response. A label needs
// attention when any applicable field is flagged (missing/failed), the
// government warning is non-compliant, or a label-level compliance check fails.
// Mirrors the per-field flagging in renderResults so the badge and the editor
// agree. Returns the counts so the row message can be specific.
function computeBatchVerdict(body) {
  const validation = body.validation || {};
  const requirements = body.field_requirements || {};
  const keys = [].concat(
    requirements.required || [],
    requirements.conditional || [],
    requirements.optional || [],
  );
  const checkKeys = keys.length ? keys : Object.keys(validation);
  let attention = 0;
  let checked = 0;

  for (const key of checkKeys) {
    const raw = validation[key];
    if (raw === undefined) continue;
    checked += 1;
    if (raw && typeof raw === "object") {
      if (!(raw.expected === "PASS" && raw.label === "PASS")) attention += 1;
    } else if (isFlaggedStatus(raw)) {
      attention += 1;
    }
  }

  let failedChecks = 0;
  for (const check of (body.compliance_checks || [])) {
    if (check.status === "FAIL") failedChecks += 1;
  }

  const flagged = attention + failedChecks;
  return { verdict: flagged ? "Needs attention" : "Pass", flagged, checked };
}

function createBatchSelect(item, key, options) {
  const select = document.createElement("select");
  select.dataset[key === "productCategory" ? "batchCategory" : "batchOrigin"] = String(item.id);
  select.disabled = state.batch.processing || item.status === "Processing";

  for (const option of options) {
    const optionElement = document.createElement("option");
    optionElement.value = option.value;
    optionElement.textContent = option.label;
    optionElement.selected = item[key] === option.value;
    select.appendChild(optionElement);
  }

  return select;
}

// A batch row is one label; this control lets a reviewer attach a second image
// (e.g. the back panel) so the row is verified as a single item, mirroring the
// First/Second slots in single-upload mode.
function buildBatchSecondImage(item) {
  const wrap = document.createElement("div");
  wrap.className = "batch-second";
  const locked = state.batch.processing || item.status === "Processing";

  if (item.backFile) {
    const name = document.createElement("span");
    name.className = "batch-second-name";
    name.textContent = "+ second image: " + item.backFile.name + " (" + formatBytes(item.backFile.size) + ")";
    wrap.appendChild(name);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "batch-second-button";
    remove.dataset.removeBatchSecond = String(item.id);
    remove.disabled = locked;
    remove.textContent = "Remove";
    wrap.appendChild(remove);
  } else {
    const label = document.createElement("label");
    label.className = "batch-second-button";
    label.textContent = "+ Add second image";
    const input = document.createElement("input");
    input.type = "file";
    input.className = "native-file-input";
    input.accept = ".pdf,.png,.jpg,.jpeg,.webp,application/pdf,image/png,image/jpeg,image/webp";
    input.dataset.addBatchSecond = String(item.id);
    input.disabled = locked;
    label.appendChild(input);
    wrap.appendChild(label);
  }
  return wrap;
}

function renderBatchQueue() {
  batchBody.innerHTML = "";

  if (!state.batch.items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty-row";
    cell.textContent = "No batch files added.";
    row.appendChild(cell);
    batchBody.appendChild(row);
    updateBatchControls();
    return;
  }

  for (const item of state.batch.items) {
    const row = document.createElement("tr");

    const caseCell = document.createElement("td");
    caseCell.textContent = "#" + item.id;

    const fileCell = document.createElement("td");
    const fileName = document.createElement("span");
    const fileMeta = document.createElement("span");
    fileName.className = "batch-file-name";
    fileName.textContent = item.file.name;
    fileMeta.className = "batch-file-meta";
    fileMeta.textContent = formatBytes(item.file.size);
    fileCell.appendChild(fileName);
    fileCell.appendChild(fileMeta);
    if (item.message) {
      const message = document.createElement("span");
      message.className = "batch-row-message" + (item.status === "Error" ? " error" : "");
      message.textContent = item.message;
      fileCell.appendChild(message);
    }
    fileCell.appendChild(buildBatchSecondImage(item));

    const categoryCell = document.createElement("td");
    categoryCell.appendChild(createBatchSelect(item, "productCategory", PRODUCT_CATEGORY_OPTIONS));

    const originCell = document.createElement("td");
    originCell.appendChild(createBatchSelect(item, "originType", ORIGIN_OPTIONS));

    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "status-badge " + batchStatusClass(item.status);
    badge.textContent = batchStatusText(item);
    statusCell.appendChild(badge);

    const actionCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "batch-row-actions";

    if (isBatchItemVerified(item)) {
      const reviewButton = document.createElement("button");
      reviewButton.className = "small-button";
      reviewButton.dataset.reviewBatch = String(item.id);
      reviewButton.disabled = state.batch.processing;
      reviewButton.type = "button";
      reviewButton.textContent = item.status === "Needs attention" ? "Review" : "Open";
      actions.appendChild(reviewButton);
    }

    if (item.status === "Error" && !item.clientError) {
      const retryButton = document.createElement("button");
      retryButton.className = "small-button";
      retryButton.dataset.retryBatch = String(item.id);
      retryButton.disabled = state.batch.processing;
      retryButton.type = "button";
      retryButton.textContent = "Retry";
      actions.appendChild(retryButton);
    }

    const removeButton = document.createElement("button");
    removeButton.className = "small-button danger";
    removeButton.dataset.removeBatch = String(item.id);
    removeButton.disabled = state.batch.processing;
    removeButton.type = "button";
    removeButton.textContent = "Remove";
    actions.appendChild(removeButton);

    actionCell.appendChild(actions);

    row.appendChild(caseCell);
    row.appendChild(fileCell);
    row.appendChild(categoryCell);
    row.appendChild(originCell);
    row.appendChild(statusCell);
    row.appendChild(actionCell);
    batchBody.appendChild(row);
  }

  updateBatchControls();
}

function updateBatchControls() {
  const hasProcessableItems = state.batch.items.some(canProcessBatchItem);
  processBatchButton.disabled = state.batch.processing || !hasProcessableItems;
  clearBatchButton.disabled = state.batch.processing || !state.batch.items.length;
}

function addBatchFiles(files) {
  const incomingFiles = Array.from(files || []);
  if (!incomingFiles.length) return;

  clearError();
  let invalidCount = 0;

  for (const file of incomingFiles) {
    const clientError = validateClientFile(file);
    if (clientError) invalidCount += 1;

    state.batch.items.push({
      id: state.batch.nextId,
      file,
      productCategory: radioValue("productCategory"),
      originType: radioValue("originType"),
      status: clientError ? "Error" : "Ready",
      message: clientError || "Ready to process",
      clientError,
      backFile: null,
      extracted: null,
      verification: null,
    });
    state.batch.nextId += 1;
  }

  renderBatchQueue();
  setStatus(incomingFiles.length === 1 ? "Batch file added" : incomingFiles.length + " batch files added");

  if (invalidCount) {
    showError(invalidCount + " batch file" + (invalidCount === 1 ? " needs" : "s need") + " attention before processing.");
  }
}

async function processBatchItem(item) {
  const clientError = validateClientFile(item.file);
  if (clientError) {
    item.clientError = clientError;
    item.status = "Error";
    item.message = clientError;
    item.extracted = null;
    item.verification = null;
    renderBatchQueue();
    return;
  }

  const backError = item.backFile ? validateClientFile(item.backFile) : "";
  if (backError) {
    item.clientError = backError;
    item.status = "Error";
    item.message = "Second image: " + backError;
    item.extracted = null;
    item.verification = null;
    renderBatchQueue();
    return;
  }

  item.clientError = "";
  item.status = "Processing";
  item.message = "Extracting and verifying";
  item.extracted = null;
  item.verification = null;
  renderBatchQueue();

  const formData = new FormData();
  formData.append("product_category", item.productCategory);
  formData.append("origin_type", item.originType);
  formData.append("front_image", item.file);
  if (item.backFile) formData.append("back_image", item.backFile);

  try {
    // One /verify call extracts and validates the label, so each row lands on a
    // real Pass / Needs-attention verdict instead of an unreviewed "extracted".
    const response = await fetchWithTimeout("/verify", { method: "POST", body: formData });
    const body = await parseApiResponse(response);
    item.extracted = body.reviewed || body.extracted || {};
    item.verification = body;
    const { verdict, flagged, checked } = computeBatchVerdict(body);
    item.status = verdict;
    item.message = verdict === "Pass"
      ? checked + " field" + (checked === 1 ? "" : "s") + " checked, all clear"
      : flagged + " item" + (flagged === 1 ? "" : "s") + " need attention";
  } catch (error) {
    item.status = "Error";
    item.message = error.message;
    item.verification = null;
  }

  renderBatchQueue();
}

// Run the batch items through a small pool of parallel workers so a full batch
// of 10 finishes in ~10s instead of ~20s sequentially.
async function runBatchConcurrently(items, limit) {
  const pending = items.slice();
  async function worker() {
    while (pending.length) {
      await processBatchItem(pending.shift());
    }
  }
  const workers = [];
  for (let i = 0; i < Math.min(limit, items.length); i += 1) {
    workers.push(worker());
  }
  await Promise.all(workers);
}

async function processBatchQueue() {
  clearError();
  const queue = state.batch.items.filter(canProcessBatchItem);

  if (!queue.length) {
    showError("Add valid batch files before processing.");
    setStatus("Batch needs files");
    return;
  }

  state.batch.processing = true;
  renderBatchQueue();
  setStatus("Processing " + queue.length + " file" + (queue.length === 1 ? "" : "s") + "…");

  await runBatchConcurrently(queue, BATCH_CONCURRENCY);

  state.batch.processing = false;
  renderBatchQueue();

  const passCount = state.batch.items.filter((item) => item.status === "Pass").length;
  const attentionCount = state.batch.items.filter((item) => item.status === "Needs attention").length;
  const errorCount = state.batch.items.filter((item) => item.status === "Error").length;
  const parts = [passCount + " passed"];
  if (attentionCount) parts.push(attentionCount + " need attention");
  if (errorCount) parts.push(errorCount + " errored");
  setStatus("Batch complete: " + parts.join(", "));
}

async function retryBatchItem(id) {
  const item = state.batch.items.find((candidate) => candidate.id === id);
  if (!item || state.batch.processing) return;

  state.batch.processing = true;
  clearError();
  setStatus("Retrying batch item");
  await processBatchItem(item);
  state.batch.processing = false;
  renderBatchQueue();
  const retryMessage = {
    "Pass": "Batch item passed",
    "Needs attention": "Batch item needs attention",
    "Error": "Batch item errored",
  };
  setStatus(retryMessage[item.status] || "Batch item processed");
}

async function reviewBatchItem(id) {
  const item = state.batch.items.find((candidate) => candidate.id === id);
  if (!item || !isBatchItemVerified(item) || !item.extracted) {
    showError("Process this batch item before reviewing it.");
    setStatus("Batch item needs extraction");
    return;
  }

  clearError();
  setRadioValue("productCategory", item.productCategory);
  setRadioValue("originType", item.originType);
  state.extracted = item.extracted;
  state.expectedValues = item.extracted;
  state.files.front = item.file;
  state.files.back = item.backFile || null;
  // The batch item is already extracted; mark the label as read so Verify
  // doesn't needlessly re-extract it.
  state.extractedKey = labelFileKey();
  syncInputFiles("front", item.file);
  syncInputFiles("back", item.backFile || null);
  renderFileState("front");
  renderFileState("back");
  setUploadMode("choose");
  await refreshRequirements();
  setExpectedValues(item.extracted);
  // Show the auto-verdict immediately so the reviewer lands on the flagged
  // fields; they can correct the COLA side and re-Verify from here.
  if (item.verification) {
    renderResults(item.verification);
  } else {
    renderEmptyResults("No verification results for this batch item yet.");
  }
  setStatus("Loaded batch item #" + item.id + " — edit fields to match the COLA application, then Verify");
  document.querySelector("#fields-title").scrollIntoView({ block: "start" });
}

function removeBatchItem(id) {
  if (state.batch.processing) return;
  state.batch.items = state.batch.items.filter((item) => item.id !== id);
  renderBatchQueue();
  setStatus(state.batch.items.length ? "Batch item removed" : "Batch cleared");
}

// The row's inputs changed, so any verdict it already holds is stale — send it
// back to the queue to be re-processed.
function resetBatchItemVerdict(item) {
  if (isBatchItemVerified(item)) {
    item.status = "Ready";
    item.message = "Ready to process";
    item.extracted = null;
    item.verification = null;
  }
}

function attachBatchSecondImage(id, file) {
  const item = state.batch.items.find((candidate) => candidate.id === id);
  if (!item || state.batch.processing) return;

  const clientError = validateClientFile(file);
  if (clientError) {
    showError("Second image: " + clientError);
    return;
  }
  clearError();
  item.backFile = file;
  resetBatchItemVerdict(item);
  renderBatchQueue();
  setStatus("Second image added to item #" + id);
}

function removeBatchSecondImage(id) {
  const item = state.batch.items.find((candidate) => candidate.id === id);
  if (!item || state.batch.processing) return;

  item.backFile = null;
  resetBatchItemVerdict(item);
  renderBatchQueue();
  setStatus("Second image removed from item #" + id);
}

function clearBatchQueue() {
  if (state.batch.processing) return;
  state.batch.items = [];
  renderBatchQueue();
  clearError();
  setStatus("Batch cleared");
}

function initBatchDropZone(zone) {
  zone.addEventListener("dragenter", function(event) {
    if (!draggedFiles(event)) return;
    event.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragover", function(event) {
    if (!draggedFiles(event)) return;
    event.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", function(event) {
    if (zone.contains(event.relatedTarget)) return;
    zone.classList.remove("drag-over");
  });

  zone.addEventListener("drop", function(event) {
    if (!draggedFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    zone.classList.remove("drag-over");
    addBatchFiles(event.dataTransfer.files);
  });
}

function setUploadMode(mode) {
  // Keep the radio in sync for programmatic calls (init, batch review), then
  // show the matching upload pane. The radio's checked state is the visual cue.
  setRadioValue("uploadMode", mode);
  chooseFileInputs.hidden = mode !== "choose";
  dropZoneInputs.hidden = mode !== "drop";
  batchPanel.hidden = mode !== "batch";
}

function initDropZone(zone) {
  const slot = zone.dataset.dropSlot;

  zone.addEventListener("dragenter", function(event) {
    if (!draggedFiles(event)) return;
    event.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragover", function(event) {
    if (!draggedFiles(event)) return;
    event.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", function(event) {
    if (zone.contains(event.relatedTarget)) return;
    zone.classList.remove("drag-over");
  });

  zone.addEventListener("drop", function(event) {
    if (!draggedFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    zone.classList.remove("drag-over");
    const files = Array.from(event.dataTransfer.files || []);

    if (files.length > 1) {
      showError("Drop one file per label slot. Use Batch for multiple files.");
      setStatus("File selection needs attention");
      return;
    }

    if (files[0]) setSelectedFile(slot, files[0]);
  });
}

for (const input of uploadInputs) {
  input.addEventListener("change", function() {
    const slot = input.dataset.fileSlot;
    if (input.files.length) {
      setSelectedFile(slot, input.files[0]);
    } else {
      clearSelectedFile(slot);
    }
  });
}

for (const zone of dropZones) {
  initDropZone(zone);
}

initBatchDropZone(batchDropZone);

for (const button of document.querySelectorAll("[data-remove-file]")) {
  button.addEventListener("click", function() {
    clearSelectedFile(button.dataset.removeFile);
  });
}

setUploadMode("choose");
renderFileState("front");
renderFileState("back");
renderBatchQueue();
updateStepHighlight();

document.addEventListener("dragover", function(event) {
  if (draggedFiles(event)) event.preventDefault();
});

document.addEventListener("drop", function(event) {
  if (!draggedFiles(event)) return;
  event.preventDefault();
  if (!event.target.closest("[data-drop-slot]") && !event.target.closest("[data-batch-drop-zone]")) {
    showError("Drop files into a label slot or the Batch area.");
    setStatus("File selection needs attention");
  }
});

if (themeToggle) {
  themeToggle.checked = currentTheme() === "dark";
  themeToggle.addEventListener("change", function() {
    setTheme(themeToggle.checked ? "dark" : "light");
  });
}
if (layoutSelect) {
  layoutSelect.value = currentLayout();
  layoutSelect.addEventListener("change", function() {
    setLayout(layoutSelect.value);
  });
}

uploadModeGroup.addEventListener("change", function() { setUploadMode(radioValue("uploadMode")); });

batchFiles.addEventListener("change", function() {
  addBatchFiles(batchFiles.files);
  batchFiles.value = "";
});

processBatchButton.addEventListener("click", processBatchQueue);
clearBatchButton.addEventListener("click", clearBatchQueue);

batchBody.addEventListener("change", function(event) {
  const categoryControl = event.target.closest("[data-batch-category]");
  const originControl = event.target.closest("[data-batch-origin]");

  if (categoryControl) {
    const item = state.batch.items.find((candidate) => candidate.id === Number(categoryControl.dataset.batchCategory));
    if (item) item.productCategory = categoryControl.value;
  }

  if (originControl) {
    const item = state.batch.items.find((candidate) => candidate.id === Number(originControl.dataset.batchOrigin));
    if (item) item.originType = originControl.value;
  }

  const addSecond = event.target.closest("[data-add-batch-second]");
  if (addSecond && addSecond.files && addSecond.files.length) {
    attachBatchSecondImage(Number(addSecond.dataset.addBatchSecond), addSecond.files[0]);
  }
});

batchBody.addEventListener("click", function(event) {
  const reviewButton = event.target.closest("[data-review-batch]");
  const retryButton = event.target.closest("[data-retry-batch]");
  const removeButton = event.target.closest("[data-remove-batch]");
  const removeSecondButton = event.target.closest("[data-remove-batch-second]");

  if (reviewButton) reviewBatchItem(Number(reviewButton.dataset.reviewBatch));
  if (retryButton) retryBatchItem(Number(retryButton.dataset.retryBatch));
  if (removeButton) removeBatchItem(Number(removeButton.dataset.removeBatch));
  if (removeSecondButton) removeBatchSecondImage(Number(removeSecondButton.dataset.removeBatchSecond));
});

// A category/origin change rebuilds the field list AND re-extracts from the
// loaded label, since extraction is scoped to the product category. Invalidating
// extractedKey forces maybeAutoExtractLabel to re-run (it no-ops with no label).
async function onCategoryOrOriginChange() {
  await refreshRequirements();
  state.extractedKey = null;
  maybeAutoExtractLabel();
}
categoryGroup.addEventListener("change", onCategoryOrOriginChange);
originGroup.addEventListener("change", onCategoryOrOriginChange);
verifyButton.addEventListener("click", verifyReviewedFields);

loadFieldConfig().then(refreshRequirements).catch(function(error) {
  showError(error.message);
  setStatus("Unable to load requirements");
});
