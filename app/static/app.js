// Fallback field config. The authoritative list is fetched from GET /fields at
// startup (loadFieldConfig); this hardcoded copy only keeps the UI working if
// that request fails. The backend (fields.py) is the single source of truth.
let FIELD_CONFIG = [
  { key: "brand_name", label: "Brand name", type: "input" },
  { key: "fanciful_name", label: "Fanciful name", type: "input" },
  { key: "class_type", label: "Class/type designation", type: "input" },
  { key: "domestic_name_address", label: "Domestic name/address", type: "textarea" },
  { key: "importer_name_address", label: "Importer name/address", type: "textarea" },
  { key: "country_of_origin", label: "Country of origin", type: "input" },
  { key: "grape_varietal", label: "Grape varietal", type: "input" },
  { key: "appellation_of_origin", label: "Appellation of origin", type: "input" },
  { key: "net_contents", label: "Net contents", type: "input" },
  { key: "alcohol_content", label: "Alcohol content", type: "input" },
  { key: "government_warning", label: "Government warning", type: "textarea" },
  { key: "sulfite_declaration", label: "Sulfite declaration", type: "input" },
  { key: "vintage_date", label: "Vintage date", type: "input" },
  { key: "percentage_of_foreign_wine", label: "Percentage of foreign wine", type: "input" },
  { key: "fdc_yellow_5_declaration", label: "FD&C Yellow #5 declaration", type: "input" },
  { key: "cochineal_carmine_declaration", label: "Cochineal/Carmine declaration", type: "input" },
  { key: "aspartame_declaration", label: "Aspartame declaration", type: "input" },
  { key: "statement_of_age", label: "Statement of age", type: "input" },
  { key: "commodity_statement", label: "Commodity statement", type: "input" },
  { key: "coloring_materials", label: "Coloring materials", type: "input" },
  { key: "wood_treatment", label: "Wood treatment", type: "input" },
  { key: "state_of_distillation", label: "State of distillation", type: "input" },
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
// Process up to this many batch files at once. A pool of 10 clears a typical
// batch in a single parallel wave (~2-3s, one extraction's time) and sits well
// under the server's per-IP rate limit (see security.py, default 120/min); when
// a big batch does hit 429, runBatchConcurrently pauses on the server's
// Retry-After instead of failing rows.
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
const PRODUCT_CATEGORY_LABELS = Object.fromEntries(PRODUCT_CATEGORY_OPTIONS.map((o) => [o.value, o.label]));
const ORIGIN_LABELS = Object.fromEntries(ORIGIN_OPTIONS.map((o) => [o.value, o.label]));
// Batch rows default to "Auto": the server reads the label and detects the
// category/origin at processing time; the dropdown then shows the detection.
const AUTO_OPTION = { value: "auto", label: "Auto" };
const BATCH_CATEGORY_OPTIONS = [AUTO_OPTION].concat(PRODUCT_CATEGORY_OPTIONS);
const BATCH_ORIGIN_OPTIONS = [AUTO_OPTION].concat(ORIGIN_OPTIONS);

const state = {
  requirements: { required: [], conditional: [], optional: [] },
  extracted: {},
  extractedKey: null,
  // The file key whose extraction last seeded the Expected side wholesale; a
  // re-read of the same label (category/origin change) must not clobber the
  // reviewer's typed corrections.
  seededKey: null,
  // True right after a wholesale re-seed: the form still shows the previous
  // label, so refreshRequirements must not fold it back into expectedValues.
  expectedValuesReseeded: false,
  detectedCategory: null,
  detectedOrigin: null,
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
const THEMES = ["light", "dark"];
const themeToggle = document.querySelector("#themeToggle");
const uploadModeGroup = document.getElementById("uploadModeGroup");
const singleCategory = document.getElementById("singleCategory");
const singleOrigin = document.getElementById("singleOrigin");

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

// Resolved category/origin for the single-label flow. The selects default to
// "auto" (the server detects from the label); once detected, the resolved value
// lives in state so requirements/validation always get a concrete value.
function currentCategory() {
  const v = singleCategory ? singleCategory.value : "auto";
  return v !== "auto" ? v : (state.detectedCategory || "malt_beverage");
}
function currentOrigin() {
  const v = singleOrigin ? singleOrigin.value : "auto";
  return v !== "auto" ? v : (state.detectedOrigin || "domestic");
}

// Detection never moves the Category/Origin dropdowns off "Auto" — a concrete
// value there reads as a manual pick and would be posted back as a hard
// constraint on the next label. The Auto option's own text shows what was
// detected instead, and the hint under the dropdowns flips once a detection
// exists.
function setAutoOptionText(select, detectedLabel) {
  if (!select) return;
  const auto = select.querySelector('option[value="auto"]');
  if (auto) auto.textContent = detectedLabel ? "Auto — detected: " + detectedLabel : "Auto";
}

function updateDetectionUI() {
  setAutoOptionText(singleCategory, state.detectedCategory ? PRODUCT_CATEGORY_LABELS[state.detectedCategory] : "");
  setAutoOptionText(singleOrigin, state.detectedOrigin ? ORIGIN_LABELS[state.detectedOrigin] : "");
}

// A new label means a new product: any earlier detection or pick no longer
// applies, so every file change in single mode puts both dropdowns back on Auto.
function resetDetection() {
  state.detectedCategory = null;
  state.detectedOrigin = null;
  if (singleCategory) singleCategory.value = "auto";
  if (singleOrigin) singleOrigin.value = "auto";
  updateDetectionUI();
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
const resultsThumb = document.getElementById("resultsThumb");
const recheckBar = document.getElementById("recheckBar");
const recheckButton = document.getElementById("recheckButton");
const busySpinner = document.getElementById("busySpinner");
const singleUploadPanel = document.getElementById("singleUploadPanel");
const batchPanel = document.getElementById("batchPanel");
const batchFiles = document.getElementById("batchFiles");
const batchBrowse = document.getElementById("batchBrowse");
const batchDropZone = document.getElementById("batchDropZone");
const batchBody = document.getElementById("batchBody");
const processBatchButton = document.getElementById("processBatchButton");
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
  // The preview belongs to the single-label flow — batch rows have their own
  // thumbnails, and a leftover single-label preview under the batch table reads
  // as part of the batch. setUploadMode re-renders on every mode switch, so the
  // preview comes back when the reviewer returns to single mode.
  if (!present.length || radioValue("uploadMode") === "batch") {
    if (panel) panel.hidden = true;
    return;
  }
  if (panel) panel.hidden = false;

  for (const [slot, file] of present) {
    const item = document.createElement("figure");
    item.className = "label-preview-item";

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

// Small clickable label thumbnail shown in the results panel — same Quick Look
// overlay as the top preview, just smaller. Images only (PDFs use the top viewer).
function renderResultsThumb() {
  if (!resultsThumb) return;
  if (state.resultsThumbUrl) {
    URL.revokeObjectURL(state.resultsThumbUrl);
    state.resultsThumbUrl = null;
  }
  resultsThumb.innerHTML = "";
  const file = state.files.front || state.files.back;
  if (!file || !(file.type && file.type.indexOf("image/") === 0)) {
    resultsThumb.hidden = true;
    resultsThumb.onclick = null;
    return;
  }
  const url = URL.createObjectURL(file);
  state.resultsThumbUrl = url;
  const img = document.createElement("img");
  img.src = url;
  img.alt = "";
  resultsThumb.appendChild(img);
  resultsThumb.hidden = false;
  resultsThumb.title = "Click to preview the label";
  resultsThumb.onclick = function() { openLightbox(url, "Label artwork"); };
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
    return;
  }
  // Focus trap: the dialog's only focusable control is the Close button, so
  // Tab must stay on it instead of escaping into the obscured page behind.
  // (If more controls are ever added, cycle between them here.)
  if (event.key === "Tab") {
    event.preventDefault();
    const box = document.getElementById("lightbox");
    const close = box && box.querySelector(".lightbox-close");
    if (close) close.focus();
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

// The batch flow gets the same numbered guidance: add files -> Process all ->
// read the results.
const BATCH_STEP_CALLOUTS = {
  upload: { num: 1, text: "Add your label files to begin." },
  process: { num: 2, text: "Click Process all to check every label." },
  processing: { num: 2, text: "Checking your labels…" },
  done: { num: 3, text: "Here are your results." },
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

function updateBatchStepCallout() {
  if (!batchPanel) return;
  // Drop the single-flow spotlight — batch is one panel, so only the callout
  // moves; a permanent glow would just be noise.
  for (const selector of [".setup-panel", ".fields-panel", ".results-panel"]) {
    const panel = document.querySelector(selector);
    if (panel) panel.classList.remove("step-active");
  }
  const items = state.batch.items;
  const step = !items.length
    ? "upload"
    : state.batch.processing
      ? "processing"
      : items.some(isBatchItemVerified)
        ? "done"
        : "process";
  const info = BATCH_STEP_CALLOUTS[step];
  const callout = getStepCallout();
  callout.querySelector(".step-num").textContent = info.num;
  callout.querySelector(".step-text").textContent = info.text;
  if (callout.parentElement !== batchPanel) batchPanel.prepend(callout);
}

function updateStepHighlight() {
  // Batch mode shows its own three steps inside the batch panel.
  if (radioValue("uploadMode") === "batch") {
    updateBatchStepCallout();
    return;
  }
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

// Big phone photos are the main cause of slow reads (a 40-megapixel label
// takes Gemini far longer than the same label at 2000px — observed in
// production as a deadline timeout). Downscale large images in the browser
// before upload: smaller, much faster, and label text at 2000px is still
// perfectly legible. PDFs, small images, and anything that fails to decode
// pass through unchanged.
const DOWNSCALE_THRESHOLD_BYTES = 2.5 * 1024 * 1024;
const DOWNSCALE_MAX_DIMENSION = 2000;
const DOWNSCALE_JPEG_QUALITY = 0.85;

async function prepareUploadFile(file) {
  if (!file || !file.type || file.type.indexOf("image/") !== 0) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const longest = Math.max(bitmap.width, bitmap.height);
    if (longest <= DOWNSCALE_MAX_DIMENSION && file.size <= DOWNSCALE_THRESHOLD_BYTES) {
      bitmap.close();
      return file;
    }
    const scale = Math.min(1, DOWNSCALE_MAX_DIMENSION / longest);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", DOWNSCALE_JPEG_QUALITY));
    if (!blob || blob.size >= file.size) return file;
    // Keep the base name (the batch _front/_back pairing keys off it) but the
    // re-encode is a JPEG now.
    return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;
  }
}

async function setSelectedFile(slot, file) {
  file = await prepareUploadFile(file);
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
  resetDetection();
  setStatus(FILE_LABELS[slot] + " selected");
  maybeAutoExtractLabel();
  updateStepHighlight();
  return true;
}

function clearSelectedFile(slot) {
  state.files[slot] = null;
  syncInputFiles(slot, null);
  renderFileState(slot);
  resetDetection();
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

let busyDepth = 0;

function setBusy(busy) {
  // Lock the inputs that would race a rebuild of the field stacks (category /
  // origin) and the action buttons while a request is in flight, and show a
  // spinner / announce busy state to assistive tech. Counter-based so two
  // overlapping requests (a fast re-check finishing under a slow extraction)
  // can't unlock the UI while one is still pending.
  busyDepth = Math.max(0, busyDepth + (busy ? 1 : -1));
  const active = busyDepth > 0;
  state.inFlight = active;
  const controls = [singleCategory, singleOrigin, uploadModeGroup, verifyButton, recheckButton, themeToggle];
  for (const control of controls) {
    if (control) control.disabled = active;
  }
  for (const input of uploadInputs) {
    input.disabled = active;
  }
  if (busySpinner) busySpinner.hidden = !active;
  const workspace = document.querySelector(".workspace");
  if (workspace) workspace.setAttribute("aria-busy", active ? "true" : "false");
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
  if (resultsThumb) { resultsThumb.hidden = true; resultsThumb.onclick = null; }
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
  "DEEMED_FROM_BOTTLER": "Brand = bottler",
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

// An editable cell on a flagged results row. side is "expected" (application) or
// "reviewed" (label). Enter triggers a re-check.
function makeEditInput(key, side, value) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "cell-edit";
  input.value = value || "";
  input.setAttribute("data-edit-field", key);
  input.setAttribute("data-edit-side", side);
  input.setAttribute("autocomplete", "off");
  input.setAttribute("aria-label", (side === "expected" ? "Application" : "Label") + " value for this field");
  input.addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      recheckFromResults();
    }
  });
  return input;
}

// Re-validate after inline edits: start from the last snapshot, override only the
// cells the reviewer changed, keep the form + stored extraction in sync, and
// re-run validation server-side (no Gemini call).
async function recheckFromResults() {
  if (state.inFlight) {
    setStatus("Still working — please wait a moment");
    return;
  }
  const expected = Object.assign({}, state.lastExpected || {});
  const reviewed = Object.assign({}, state.lastReviewed || {});
  for (const input of document.querySelectorAll("#resultsBody .cell-edit")) {
    const key = input.getAttribute("data-edit-field");
    const value = input.value.trim();
    if (input.getAttribute("data-edit-side") === "expected") expected[key] = value;
    else reviewed[key] = value;
  }
  setExpectedValues(expected);
  state.extracted = reviewed;
  clearError();
  setBusy(true);
  try {
    setStatus("Re-checking");
    const response = await fetchWithTimeout("/verify-reviewed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_category: currentCategory(),
        origin_type: currentOrigin(),
        expected: expected,
        reviewed: reviewed,
      }),
    });
    const body = await parseApiResponse(response);
    renderResults(body);
    setStatus("");
  } catch (error) {
    showError(error.message);
    setStatus("Re-check failed");
  } finally {
    setBusy(false);
  }
}

function renderResults(response) {
  state.lastResult = response;
  updateStepHighlight();
  renderResultsThumb();
  const expected = response.expected || formValues(expectedFields);
  const reviewed = response.reviewed || response.extracted || state.extracted || {};
  const validation = response.validation || {};
  const requirements = response.field_requirements || {};
  // Keep the full snapshots so an inline Re-check can start from them and only
  // override the cells the reviewer corrected.
  state.lastExpected = expected;
  state.lastReviewed = reviewed;
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
  let editableFlagged = 0;

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
      if (isFlaggedStatus(status)) {
        // Flagged row: let the reviewer correct either side (an AI misread of
        // the label, or a typo on the application side) and re-check inline.
        row.className = "is-flagged";
        expectedCell.appendChild(makeEditInput(key, "expected", expected[key]));
        reviewedCell.appendChild(makeEditInput(key, "reviewed", reviewed[key]));
        editableFlagged += 1;
      } else {
        expectedCell.textContent = expected[key] || "";
        reviewedCell.textContent = reviewed[key] || "";
        // Rows are one line and truncate, so expose the full value on hover.
        expectedCell.title = expected[key] || "";
        reviewedCell.title = reviewed[key] || "";
      }
    }
    fieldCell.title = config.label;

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
  if (recheckBar) recheckBar.hidden = editableFlagged === 0;

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
    ? "PASS — all checks cleared"
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

  const intro = document.createElement("p");
  intro.className = "compliance-intro";
  intro.textContent =
    "These check the label itself — container size, units, and origin — not the application fields.";
  container.appendChild(intro);

  const list = document.createElement("ul");
  for (const check of checks) {
    const item = document.createElement("li");
    const badge = document.createElement("span");
    badge.className = "status-badge " + complianceStatusClass(check.status);
    badge.textContent = statusLabel(check.status);
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
    const err = new Error(error.message || error.code || "Request failed");
    // Carry the machine-readable parts so callers can react to specific
    // failures — the batch runner pauses on 429 + Retry-After instead of
    // failing the row.
    err.status = response.status;
    err.code = error.code || "";
    const retryAfter = Number(response.headers.get("Retry-After"));
    if (Number.isFinite(retryAfter) && retryAfter > 0) err.retryAfterSeconds = retryAfter;
    throw err;
  }
  return body;
}

// Fold the live Expected form back into state so a field-stack rebuild keeps
// what the reviewer typed. Only rendered fields are read; values for fields
// hidden under the current category keep their stored value.
function captureExpectedForm() {
  if (!expectedFields) return;
  const live = {};
  for (const control of expectedFields.querySelectorAll("[name]")) {
    live[control.name] = control.value.trim();
  }
  if (Object.keys(live).length) {
    state.expectedValues = Object.assign({}, state.expectedValues, live);
  }
}

let requirementsToken = 0;

async function refreshRequirements() {
  // Carry the reviewer's typed corrections through the rebuild — unless the
  // values were just re-seeded from a new label, in which case the form on
  // screen still belongs to the previous label and must not leak into it.
  if (!state.expectedValuesReseeded) captureExpectedForm();
  state.expectedValuesReseeded = false;
  clearError();
  setStatus("Loading requirements");
  // Two quick category/origin changes can answer out of order; only the
  // newest request may repaint the form.
  const token = ++requirementsToken;
  const params = new URLSearchParams({
    product_category: currentCategory(),
    origin_type: currentOrigin(),
  });
  const response = await fetch("/field-requirements?" + params.toString());
  const body = await parseApiResponse(response);
  if (token !== requirementsToken) return;
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
  // Snapshot the file set now: if the reviewer swaps files while this request
  // is in flight, the result belongs to the old files and must not be stamped
  // as "already read" for the new ones.
  const key = labelFileKey();
  const postedCategory = singleCategory ? singleCategory.value : "auto";
  const postedOrigin = singleOrigin ? singleOrigin.value : "auto";
  const formData = new FormData();
  // "auto" lets the server detect the category/origin from the label itself;
  // a manual pick in the dropdowns sends the chosen value instead.
  formData.append("product_category", postedCategory);
  formData.append("origin_type", postedOrigin);
  formData.append("front_image", files[0]);
  if (files[1]) formData.append("back_image", files[1]);
  const response = await fetchWithTimeout("/extract", { method: "POST", body: formData });
  const body = await parseApiResponse(response);
  const stale = labelFileKey() !== key;
  state.extracted = body.extracted || {};
  state.extractedKey = stale ? null : key;
  if (!stale) {
    // Record the server's resolution as detection only for the sides we asked
    // it to detect — the dropdowns themselves stay on "Auto" so the next label
    // is detected too (see updateDetectionUI).
    if (postedCategory === "auto") {
      state.detectedCategory = body.product_category || body.detected_category || state.detectedCategory;
    }
    if (postedOrigin === "auto") {
      state.detectedOrigin = body.origin_type || body.detected_origin || state.detectedOrigin;
    }
    updateDetectionUI();
  }
  return { key: key, stale: stale };
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
  if (state.inFlight) {
    setStatus("Still working — please wait a moment");
    return;
  }
  clearError();

  if (!state.files.front && !state.files.back) {
    showError("Add at least one label.");
    setStatus("File selection needs attention");
    return;
  }

  const keyAtStart = labelFileKey();
  setBusy(true);
  if (labelProgress) labelProgress.hidden = false;
  setStatus("Extracting fields");
  try {
    const read = await runLabelExtraction();
    // Re-seed the Expected side wholesale only for a genuinely new label; a
    // re-read of the same label (category/origin change) keeps the reviewer's
    // typed corrections.
    if (!read.stale && state.seededKey !== read.key) {
      state.expectedValues = Object.assign({}, state.extracted);
      state.seededKey = read.key;
      state.expectedValuesReseeded = true;
    }
    // The detected category/origin decide which fields apply, so re-render the
    // field list (refreshRequirements re-applies state.expectedValues). The step
    // callout already tells the reviewer what to do next — no status line needed.
    await refreshRequirements();
    setStatus("");
  } catch (error) {
    showError(friendlyExtractionError(error));
    setStatus("Extraction failed");
  } finally {
    if (labelProgress) labelProgress.hidden = true;
    setBusy(false);
    // Files swapped while the request was in flight: read the new set now.
    if (labelFileKey() !== keyAtStart) maybeAutoExtractLabel();
  }
}

// Tell apart the two AI-reader failure modes: GEMINI_CLIENT_ERROR means the
// reader rejected THIS file (too large, unreadable format) — retrying the same
// file cannot help, so say that. Anything else Gemini-shaped is a temporary
// busy spike worth retrying. Neither message names the vendor — reviewers
// don't care which model is behind the reader.
function friendlyExtractionError(error) {
  if (error.code === "GEMINI_CLIENT_ERROR") {
    return "This file couldn't be read — it may be too large or in an unsupported format. Try a smaller image or a different file.";
  }
  return /gemini/i.test(error.message || "")
    ? "The label reader was busy for a moment — please try again."
    : error.message;
}

async function verifyReviewedFields() {
  if (state.inFlight) {
    setStatus("Still working — please wait a moment");
    return;
  }
  clearError();
  if (!state.files.front && !state.files.back) {
    showError("Add at least one label to verify against.");
    setStatus("File selection needs attention");
    return;
  }
  const keyAtStart = labelFileKey();
  setBusy(true);
  try {
    // Read the label if these exact files haven't been read yet, so Verify works
    // on its own; re-verifying after editing fields stays instant (no extra call).
    if (state.extractedKey !== labelFileKey()) {
      setStatus("Reading the label");
      const read = await runLabelExtraction();
      // First read on this file: seed the form and render the field set for the
      // detected category/origin before validating.
      if (!read.stale && state.seededKey !== read.key) {
        state.expectedValues = Object.assign({}, state.extracted);
        state.seededKey = read.key;
        state.expectedValuesReseeded = true;
      }
      await refreshRequirements();
    }
    setStatus("Verifying fields");
    const response = await fetchWithTimeout("/verify-reviewed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_category: currentCategory(),
        origin_type: currentOrigin(),
        expected: formValues(expectedFields),
        reviewed: state.extracted,
      }),
    });
    const body = await parseApiResponse(response);
    renderResults(body);
    setStatus("");
  } catch (error) {
    showError(friendlyExtractionError(error));
    setStatus("Verification failed");
  } finally {
    setBusy(false);
    // Files swapped while the request was in flight: read the new set now.
    if (labelFileKey() !== keyAtStart) maybeAutoExtractLabel();
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
    // Skip keys the UI doesn't know (same filter as buildBatchDetail), so the
    // row verdict can never disagree with its own detail view.
    if (!FIELD_LOOKUP[key]) continue;
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
  // Every row's selects read identically to a screen reader without the file
  // name in the accessible name.
  select.setAttribute(
    "aria-label",
    (key === "productCategory" ? "Category for " : "Origin for ") + item.file.name
  );

  for (const option of options) {
    const optionElement = document.createElement("option");
    optionElement.value = option.value;
    optionElement.textContent = option.label;
    optionElement.selected = item[key] === option.value;
    select.appendChild(optionElement);
  }

  return select;
}

// The expandable per-product detail shown inline under a verified batch row:
// a field-by-field breakdown (name / status / label value) plus the compliance
// checks, so a reviewer can read a product's result without leaving the batch.
function buildBatchDetail(item) {
  const wrap = document.createElement("div");
  wrap.className = "batch-detail";
  const v = item.verification;
  if (!v) {
    wrap.textContent = "Process this item to see its details.";
    return wrap;
  }

  const validation = v.validation || {};
  const reviewed = v.reviewed || v.extracted || {};
  const req = v.field_requirements || {};
  const keys = [].concat(req.required || [], req.conditional || [], req.optional || []);

  const verdict = computeBatchVerdict(v);
  const summary = document.createElement("div");
  summary.className = "batch-detail-summary " + (verdict.flagged ? "is-attention" : "is-pass");
  summary.textContent = verdict.flagged
    ? `${verdict.flagged} ${verdict.flagged === 1 ? "item needs" : "items need"} attention · ${verdict.checked} fields checked`
    : `No issues found · ${verdict.checked} fields checked`;
  wrap.appendChild(summary);

  // A field table, mirroring the single-label results output (Field / Status /
  // Label), one line per field.
  const tableWrap = document.createElement("div");
  tableWrap.className = "table-wrap";
  const table = document.createElement("table");
  // results-table: the shared skin used by the single-label results table, so
  // the two outputs stay visually identical (see styles.css).
  table.className = "batch-detail-table results-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr><th>Field</th><th>Status</th><th>Label</th></tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const key of keys) {
    const cfg = FIELD_LOOKUP[key];
    if (!cfg) continue;
    const raw = validation[key];
    const status = raw && typeof raw === "object"
      ? (raw.expected === "PASS" && raw.label === "PASS" ? "PASS" : "FAIL")
      : (raw || "NOT REVIEWED");
    const tr = document.createElement("tr");
    if (isFlaggedStatus(status) || status === "FAIL") tr.className = "is-flagged";
    const fieldTd = document.createElement("td");
    fieldTd.textContent = cfg.label;
    fieldTd.title = cfg.label;
    const statusTd = document.createElement("td");
    statusTd.appendChild(makeBadge(status));
    const valueTd = document.createElement("td");
    valueTd.textContent = reviewed[key] || "—";
    valueTd.title = reviewed[key] || "";
    tr.appendChild(fieldTd);
    tr.appendChild(statusTd);
    tr.appendChild(valueTd);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  tableWrap.appendChild(table);
  wrap.appendChild(tableWrap);

  const checks = v.compliance_checks || [];
  if (checks.length) {
    const cwrap = document.createElement("div");
    cwrap.className = "batch-detail-checks";
    const h = document.createElement("div");
    h.className = "batch-detail-checks-title";
    h.textContent = "Label compliance checks";
    cwrap.appendChild(h);
    const intro = document.createElement("p");
    intro.className = "compliance-intro";
    intro.textContent =
      "These check the label itself — container size, units, and origin — not the application fields.";
    cwrap.appendChild(intro);
    for (const c of checks) {
      const line = document.createElement("div");
      line.className = "batch-detail-check";
      const cb = document.createElement("span");
      cb.className = "status-badge " + complianceStatusClass(c.status);
      cb.textContent = statusLabel(c.status);
      line.appendChild(cb);
      line.appendChild(document.createTextNode(" " + c.label + " — " + c.detail));
      cwrap.appendChild(line);
    }
    wrap.appendChild(cwrap);
  }

  const editLink = document.createElement("button");
  editLink.type = "button";
  editLink.className = "link-button batch-detail-edit";
  editLink.dataset.reviewBatch = String(item.id);
  editLink.textContent = "Edit";
  editLink.setAttribute("aria-label", "Open in the editor to correct fields");
  wrap.appendChild(editLink);

  return wrap;
}

// Small clickable thumbnail of the row's label photo (images only — PDFs have
// no inline thumbnail here). The object URL lives on the item so row rebuilds
// don't leak URLs; removeBatchItem revokes it.
function buildBatchThumb(item) {
  if (!(item.file && item.file.type && item.file.type.indexOf("image/") === 0)) return null;
  if (!item.thumbUrl) item.thumbUrl = URL.createObjectURL(item.file);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "batch-thumb";
  button.title = "Click to preview the label";
  button.setAttribute("aria-label", "Preview " + item.file.name);
  const img = document.createElement("img");
  img.src = item.thumbUrl;
  img.alt = "";
  img.loading = "lazy";
  button.appendChild(img);
  button.addEventListener("click", function() {
    openLightbox(item.thumbUrl, (item.productName || item.file.name) + " label artwork");
  });
  return button;
}

function buildBatchRow(item) {
  const row = document.createElement("tr");
  row.dataset.itemId = String(item.id);

  const caseCell = document.createElement("td");
  const thumb = buildBatchThumb(item);
  if (thumb) caseCell.appendChild(thumb);
  const productName = document.createElement("span");
  productName.className = "batch-product-name";
  productName.textContent = item.productName || ("#" + item.id);
  productName.title = item.productName || "";
  caseCell.appendChild(productName);

  const fileCell = document.createElement("td");
  const fileName = document.createElement("span");
  fileName.className = "batch-file-name";
  fileName.textContent = item.file.name;
  fileName.title = item.file.name;
  fileCell.appendChild(fileName);
  if (item.backFile) {
    const backName = document.createElement("span");
    backName.className = "batch-file-name batch-file-back";
    backName.textContent = "+ " + item.backFile.name;
    backName.title = item.backFile.name;
    fileCell.appendChild(backName);
    const fileMeta = document.createElement("span");
    fileMeta.className = "batch-file-meta";
    fileMeta.textContent = "2 images";
    fileCell.appendChild(fileMeta);
  }
  if (item.message) {
    const message = document.createElement("span");
    message.className = "batch-row-message" + (item.status === "Error" ? " error" : "");
    message.textContent = item.message;
    fileCell.appendChild(message);
  }

  const categoryCell = document.createElement("td");
  categoryCell.appendChild(createBatchSelect(item, "productCategory", BATCH_CATEGORY_OPTIONS));

  const originCell = document.createElement("td");
  originCell.appendChild(createBatchSelect(item, "originType", BATCH_ORIGIN_OPTIONS));

  const statusCell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "status-badge " + batchStatusClass(item.status);
  badge.textContent = batchStatusText(item);
  statusCell.appendChild(badge);
  if (item.status === "Processing") {
    const bar = document.createElement("div");
    bar.className = "batch-progress";
    bar.setAttribute("aria-hidden", "true");
    bar.innerHTML = '<div class="batch-progress-fill"></div>';
    statusCell.appendChild(bar);
  }

  const actionCell = document.createElement("td");
  const actions = document.createElement("div");
  actions.className = "batch-row-actions";

  // The visible button text is identical on every row; the accessible names
  // carry the file name so a screen-reader user knows which row each acts on.
  // updateBatchRow rebuilds the whole row through here, so they stay in sync.
  if (isBatchItemVerified(item)) {
    const toggle = document.createElement("button");
    toggle.className = "small-button";
    toggle.dataset.toggleBatch = String(item.id);
    toggle.disabled = state.batch.processing;
    toggle.type = "button";
    toggle.textContent = item.expanded ? "Hide" : "Details";
    toggle.setAttribute("aria-label", (item.expanded ? "Hide details for " : "Show details for ") + item.file.name);
    actions.appendChild(toggle);
  }

  if (item.status === "Error" && !item.clientError) {
    const retryButton = document.createElement("button");
    retryButton.className = "small-button";
    retryButton.dataset.retryBatch = String(item.id);
    retryButton.disabled = state.batch.processing;
    retryButton.type = "button";
    retryButton.textContent = "Retry";
    retryButton.setAttribute("aria-label", "Retry " + item.file.name);
    actions.appendChild(retryButton);
  }

  const removeButton = document.createElement("button");
  removeButton.className = "small-button danger";
  removeButton.dataset.removeBatch = String(item.id);
  removeButton.disabled = state.batch.processing;
  removeButton.type = "button";
  removeButton.textContent = "Remove";
  removeButton.setAttribute("aria-label", "Remove " + item.file.name + " from the list");
  actions.appendChild(removeButton);

  actionCell.appendChild(actions);

  row.appendChild(caseCell);
  row.appendChild(fileCell);
  row.appendChild(categoryCell);
  row.appendChild(originCell);
  row.appendChild(statusCell);
  row.appendChild(actionCell);
  return row;
}

function buildBatchDetailRow(item) {
  const detailRow = document.createElement("tr");
  detailRow.className = "batch-detail-row";
  detailRow.dataset.detailFor = String(item.id);
  const detailCell = document.createElement("td");
  detailCell.colSpan = 6;
  detailCell.appendChild(buildBatchDetail(item));
  detailRow.appendChild(detailCell);
  return detailRow;
}

function renderBatchQueue() {
  batchBody.innerHTML = "";

  // The whole table stays hidden until there is something to list — the step
  // callout above it already tells the reviewer to add files.
  const tableWrap = batchPanel ? batchPanel.querySelector(".batch-table-wrap") : null;
  if (tableWrap) tableWrap.hidden = !state.batch.items.length;

  for (const item of state.batch.items) {
    batchBody.appendChild(buildBatchRow(item));
    if (item.expanded && isBatchItemVerified(item)) {
      batchBody.appendChild(buildBatchDetailRow(item));
    }
  }

  updateBatchControls();
  updateStepHighlight();
}

// Patch one row in place. A full renderBatchQueue per status change is O(n^2)
// DOM work across a 300-file run and yanks focus from a select the reviewer is
// using in another row — so per-row status updates go through here; the full
// rebuild stays for add/remove/clear/pairing changes.
function updateBatchRow(item) {
  const existing = batchBody.querySelector('tr[data-item-id="' + item.id + '"]');
  if (!existing) {
    renderBatchQueue();
    return;
  }
  // If focus is inside this row (its select or Details button), put it back on
  // the equivalent control after the patch.
  const focused = document.activeElement;
  let refocus = "";
  if (focused && existing.contains(focused) && focused.dataset) {
    if (focused.dataset.batchCategory) refocus = "[data-batch-category]";
    else if (focused.dataset.batchOrigin) refocus = "[data-batch-origin]";
    else if (focused.dataset.toggleBatch) refocus = "[data-toggle-batch]";
  }
  const fresh = buildBatchRow(item);
  existing.replaceWith(fresh);
  const oldDetail = batchBody.querySelector('tr[data-detail-for="' + item.id + '"]');
  if (oldDetail) oldDetail.remove();
  if (item.expanded && isBatchItemVerified(item)) {
    fresh.after(buildBatchDetailRow(item));
  }
  if (refocus) {
    const control = fresh.querySelector(refocus);
    if (control && !control.disabled) control.focus();
  }
  updateBatchControls();
  updateStepHighlight();
}

function updateBatchControls() {
  const hasProcessableItems = state.batch.items.some(canProcessBatchItem);
  processBatchButton.disabled = state.batch.processing || !hasProcessableItems;
  renderBatchVerdict();
}

// One prominent overall banner for a finished batch, mirroring the single-label
// verdict: solid green PASS when every label cleared, amber when any row needs
// review (or errored). Hidden while the batch is running or any row is still
// waiting — adding a new file to a finished batch hides it again.
function renderBatchVerdict() {
  const banner = document.getElementById("batchVerdict");
  if (!banner) return;
  const items = state.batch.items;
  const settled = items.length > 0 && !state.batch.processing &&
    items.every((item) => isBatchItemVerified(item) || item.status === "Error");
  if (!settled || !items.some(isBatchItemVerified)) {
    banner.hidden = true;
    return;
  }
  const flagged = items.filter((item) => item.status !== "Pass").length;
  const pass = flagged === 0;
  const noun = items.length === 1 ? "label" : "labels";
  banner.hidden = false;
  banner.className = "results-verdict batch-verdict " + (pass ? "verdict-pass" : "verdict-attention");
  banner.querySelector(".results-verdict-icon").textContent = pass ? "✓" : "!";
  banner.querySelector(".results-verdict-text").textContent = pass
    ? (items.length === 1 ? "PASS — label cleared" : "PASS — all " + items.length + " labels cleared")
    : "Needs attention — " + flagged + " of " + items.length + " " + noun + " to review";
}

// Split a trailing front/back marker off a filename: "airlie_front.jpg" ->
// {base:"airlie", side:"front"}; "IMG_1234.jpg" -> {base:"IMG_1234", side:null}.
function parseBatchFileName(name) {
  const noExt = (name || "").replace(/\.[^.]+$/, "");
  const match = noExt.match(/^(.+?)[ _-]+(front|back)$/i);
  if (match) return { base: match[1], side: match[2].toLowerCase() };
  return { base: noExt, side: null };
}

// Pair files that share a base name with _front/_back markers into one product;
// unmarked files (and any extra duplicates) become their own single product.
function groupBatchFiles(files) {
  const groups = new Map();
  const order = [];
  const singles = [];
  for (const file of files) {
    const { base, side } = parseBatchFileName(file.name);
    if (!side) { singles.push({ file, name: base }); continue; }
    const key = base.toLowerCase();
    if (!groups.has(key)) { groups.set(key, { name: base, front: null, back: null }); order.push(key); }
    const group = groups.get(key);
    if (side === "front" && !group.front) { group.front = file; continue; }
    if (side === "back" && !group.back) { group.back = file; continue; }
    singles.push({ file, name: base });  // duplicate marker → standalone
  }
  const result = [];
  for (const key of order) {
    const group = groups.get(key);
    result.push({ front: group.front || group.back, back: (group.front && group.back) ? group.back : null, name: group.name });
  }
  for (const single of singles) result.push({ front: single.file, back: null, name: single.name });
  return result;
}

function makeBatchItem(frontFile, backFile, productName) {
  const clientError = validateClientFile(frontFile) || (backFile ? validateClientFile(backFile) : "");
  const item = {
    id: state.batch.nextId,
    file: frontFile,
    backFile: backFile || null,
    productName: productName || frontFile.name,
    // "auto": the server detects these from the label when the row is processed;
    // the dropdown then shows the detected value. A manual pick overrides.
    productCategory: "auto",
    originType: "auto",
    status: clientError ? "Error" : "Ready",
    // The Status column already says "Ready" — no per-row message until
    // something needs saying (an error, a retry, a verdict summary).
    message: clientError || "",
    clientError,
    extracted: null,
    verification: null,
    expanded: true,  // show the per-product detail automatically once verified
  };
  state.batch.nextId += 1;
  return item;
}

async function addBatchFiles(files) {
  const incomingFiles = Array.from(files || []);
  if (!incomingFiles.length) return;

  clearError();
  setStatus("Preparing files…");
  const prepared = await Promise.all(incomingFiles.map(prepareUploadFile));
  const groups = groupBatchFiles(prepared);

  let invalidCount = 0;
  for (const group of groups) {
    const item = makeBatchItem(group.front, group.back, group.name);
    if (item.clientError) invalidCount += 1;
    state.batch.items.push(item);
  }

  renderBatchQueue();
  setStatus(groups.length === 1 ? "1 product added" : groups.length + " products added");

  if (invalidCount) {
    showError(invalidCount + " batch file" + (invalidCount === 1 ? " needs" : "s need") + " attention before processing.");
  }
}

// Returns null when the row landed on a verdict or a real error, or
// { rateLimited: true, retryAfterSeconds } when the server answered 429 — the
// batch runner re-queues those instead of failing the row.
async function processBatchItem(item) {
  const clientError = validateClientFile(item.file);
  if (clientError) {
    item.clientError = clientError;
    item.status = "Error";
    item.message = clientError;
    item.extracted = null;
    item.verification = null;
    updateBatchRow(item);
    return null;
  }

  const backError = item.backFile ? validateClientFile(item.backFile) : "";
  if (backError) {
    item.clientError = backError;
    item.status = "Error";
    item.message = "Second image: " + backError;
    item.extracted = null;
    item.verification = null;
    updateBatchRow(item);
    return null;
  }

  item.clientError = "";
  item.status = "Processing";
  item.message = "Extracting and verifying";
  item.extracted = null;
  item.verification = null;
  updateBatchRow(item);

  const formData = new FormData();
  // "auto" tells the server to read the label and infer the category/origin
  // itself; a manual pick sends the chosen value instead.
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
    // Reflect the resolved (detected or chosen) category/origin back into the
    // row's dropdowns.
    if (item.productCategory === "auto" && body.product_category) item.productCategory = body.product_category;
    if (item.originType === "auto" && body.origin_type) item.originType = body.origin_type;
    const { verdict, flagged, checked } = computeBatchVerdict(body);
    item.status = verdict;
    item.message = verdict === "Pass"
      ? checked + " field" + (checked === 1 ? "" : "s") + " checked, all clear"
      : flagged + " item" + (flagged === 1 ? "" : "s") + " need attention";
  } catch (error) {
    if (error.status === 429 || error.code === "RATE_LIMITED") {
      // Not this row's fault — the server asked us to slow down. Hand it back
      // to the batch runner, which pauses every worker for Retry-After.
      item.status = "Ready";
      item.message = "Waiting — the server asked us to slow down";
      item.verification = null;
      updateBatchRow(item);
      return { rateLimited: true, retryAfterSeconds: error.retryAfterSeconds || 0 };
    }
    if (isTransientBatchError(error)) {
      // A Gemini busy spike or timeout — hand it back to the runner, which
      // retries the row automatically before bothering the reviewer.
      item.verification = null;
      return { transient: true };
    }
    item.status = "Error";
    item.message = error.code === "GEMINI_CLIENT_ERROR"
      ? "This file couldn't be read — try a smaller image or a different format."
      : error.message;
    item.verification = null;
  }

  updateBatchRow(item);
  return null;
}

// A failure worth retrying automatically: Gemini busy spikes (surfaced as 5xx
// or a "Gemini …" message) and request timeouts. GEMINI_CLIENT_ERROR means
// Gemini rejected this specific file — deterministic, so retrying is pointless;
// validation problems and other 4xx responses are likewise not retried.
function isTransientBatchError(error) {
  if (error.code === "GEMINI_CLIENT_ERROR") return false;
  if (error.status >= 500) return true;
  return /gemini|timed out/i.test(error.message || "");
}

// A rate-limited row goes back in the queue this many times before it lands on
// Error.
const RATE_LIMIT_MAX_ATTEMPTS = 5;

// A row that hits a transient Gemini failure (busy spike, timeout) is retried
// automatically this many times — with an escalating shared pause, since a
// slow spell is usually global and can outlast a quick retry (a real one
// observed in production lasted ~2 minutes) — before it lands on Error with a
// Retry button.
const TRANSIENT_MAX_ATTEMPTS = 3;
const TRANSIENT_RETRY_DELAYS_MS = [2000, 8000];

// Run the batch items through a small pool of parallel workers so a full batch
// of 10 finishes in ~10s instead of ~20s sequentially. When the server answers
// 429 (rate limited, default 120 requests/min — see security.py), the row is
// re-queued and every worker waits on ONE shared gate for the server's
// Retry-After, so a 200-300 file batch paces itself instead of mass-failing.
async function runBatchConcurrently(items, limit) {
  const pending = items.slice();
  const total = items.length;
  let done = 0;
  let pauseUntil = 0;
  for (const item of items) {
    item.rateLimitAttempts = 0;
    item.transientAttempts = 0;
  }

  async function waitForGate() {
    if (Date.now() >= pauseUntil) return;
    while (Date.now() < pauseUntil) {
      const remaining = pauseUntil - Date.now();
      setStatus("Pausing " + Math.ceil(remaining / 1000) + " s so the server can catch up — " + done + " of " + total + " checked");
      await new Promise((resolve) => setTimeout(resolve, Math.min(1000, remaining)));
    }
    setStatus("Resuming — " + done + " of " + total + " checked");
  }

  async function worker() {
    while (pending.length) {
      await waitForGate();
      const item = pending.shift();
      if (!item) break;
      const outcome = await processBatchItem(item);
      if (outcome && outcome.rateLimited) {
        item.rateLimitAttempts += 1;
        if (item.rateLimitAttempts < RATE_LIMIT_MAX_ATTEMPTS) {
          pending.push(item);
          const waitMs = Math.max(outcome.retryAfterSeconds || 5, 1) * 1000;
          pauseUntil = Math.max(pauseUntil, Date.now() + waitMs);
          continue;
        }
        item.status = "Error";
        item.message = "The server stayed busy — wait a minute, then click Retry.";
        updateBatchRow(item);
      } else if (outcome && outcome.transient) {
        item.transientAttempts += 1;
        if (item.transientAttempts < TRANSIENT_MAX_ATTEMPTS) {
          item.status = "Processing";
          item.message = "Busy moment — retrying automatically";
          updateBatchRow(item);
          pending.push(item);
          const delay = TRANSIENT_RETRY_DELAYS_MS[
            Math.min(item.transientAttempts - 1, TRANSIENT_RETRY_DELAYS_MS.length - 1)
          ];
          pauseUntil = Math.max(pauseUntil, Date.now() + delay);
          continue;
        }
        item.status = "Error";
        item.message = "This label couldn't be checked just now — click Retry.";
        updateBatchRow(item);
      }
      done += 1;
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
    showError("Add valid files in Multiple labels before processing.");
    setStatus("Batch needs files");
    return;
  }

  state.batch.processing = true;
  renderBatchQueue();
  setStatus("Processing " + queue.length + " file" + (queue.length === 1 ? "" : "s") + "…");

  // Transient Gemini failures are retried per-row inside the runner (up to
  // TRANSIENT_MAX_ATTEMPTS), so no separate second pass is needed here.
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
  renderBatchQueue();
  // Route through the batch runner so a 429 on the retry waits for the
  // server's Retry-After instead of failing the row again.
  await runBatchConcurrently([item], 1);
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
  try {
    // The verification response carries the resolved (detected or chosen)
    // category/origin — load those as the DETECTION for the single-label
    // editor. The dropdowns stay on "Auto" (with the detection shown in the
    // Auto option's text) so the next fresh upload is still auto-detected.
    const v = item.verification || {};
    const category = v.product_category || (item.productCategory !== "auto" ? item.productCategory : null);
    const origin = v.origin_type || (item.originType !== "auto" ? item.originType : null);
    if (singleCategory) singleCategory.value = "auto";
    if (singleOrigin) singleOrigin.value = "auto";
    state.detectedCategory = category || null;
    state.detectedOrigin = origin || null;
    updateDetectionUI();
    state.extracted = item.extracted;
    state.expectedValues = item.extracted;
    state.files.front = item.file;
    state.files.back = item.backFile || null;
    // The batch item is already extracted; mark the label as read (and the form
    // as seeded from it) so Verify doesn't needlessly re-extract or re-seed.
    state.extractedKey = labelFileKey();
    state.seededKey = state.extractedKey;
    // The form on screen still shows the previous label — don't fold it back in.
    state.expectedValuesReseeded = true;
    syncInputFiles("front", item.file);
    syncInputFiles("back", item.backFile || null);
    renderFileState("front");
    renderFileState("back");
    setUploadMode("single");
    await refreshRequirements();
    setExpectedValues(item.extracted);
    // Show the auto-verdict immediately so the reviewer lands on the flagged
    // fields; they can correct the COLA side and re-Verify from here.
    if (item.verification) {
      renderResults(item.verification);
    } else {
      renderEmptyResults("No verification results for this batch item yet.");
    }
    setStatus("Loaded batch item #" + item.id + " — edit fields to match the approved application, then Verify");
    // The batch panel — including the button that was just clicked — is now
    // hidden, so move focus to the editor's heading (tabindex="-1" in the
    // markup) or a keyboard user is stranded on a hidden element.
    const fieldsTitle = document.querySelector("#fields-title");
    fieldsTitle.scrollIntoView({ block: "start" });
    fieldsTitle.focus({ preventScroll: true });
  } catch (error) {
    // A failed /field-requirements load must not strand the UI on "Loading
    // requirements" forever.
    showError(error.message);
    setStatus("");
  }
}

function removeBatchItem(id) {
  if (state.batch.processing) return;
  const removed = state.batch.items.find((item) => item.id === id);
  if (removed && removed.thumbUrl) URL.revokeObjectURL(removed.thumbUrl);
  state.batch.items = state.batch.items.filter((item) => item.id !== id);
  renderBatchQueue();
  setStatus(state.batch.items.length ? "Batch item removed" : "Batch cleared");
}

// The row's inputs changed, so any verdict it already holds is stale — send it
// back to the queue to be re-processed.
function resetBatchItemVerdict(item) {
  if (isBatchItemVerified(item)) {
    item.status = "Ready";
    item.message = "";
    item.extracted = null;
    item.verification = null;
  }
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
  // Two modes: "single" (the drop-or-browse zones) and "batch" (multiple labels).
  // Keep the radio in sync for programmatic calls (init, batch review).
  setRadioValue("uploadMode", mode);
  const batch = mode === "batch";
  singleUploadPanel.hidden = batch;
  batchPanel.hidden = !batch;
  // Batch has its own per-product output, so hide the single-label review
  // surface (fields + results) in batch mode. Opening a batch item in the
  // editor switches back to single mode and shows them again.
  const fieldsPanel = document.querySelector(".fields-panel");
  const resultsPanel = document.querySelector(".results-panel");
  if (fieldsPanel) fieldsPanel.hidden = batch;
  if (resultsPanel) resultsPanel.hidden = batch;
  // Hide the single-label preview in batch mode (and bring it back in single).
  renderLabelPreview();
  updateStepHighlight();
}

function initDropZone(zone) {
  const slot = zone.dataset.dropSlot;

  // Click anywhere in the zone (except the Remove button) to browse for a file —
  // so the same control does "drop here or browse".
  zone.addEventListener("click", function(event) {
    if (event.target.closest(".remove-file-button")) return;
    const input = slot === "back" ? backImage : frontImage;
    if (input) input.click();
  });

  // The zone is a div acting as a button (role="button" + tabindex in the
  // markup), so Enter/Space must open the same file picker the click does.
  // The inner Remove button is a real button — its own Enter must not also
  // open the picker.
  zone.addEventListener("keydown", function(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest(".remove-file-button")) return;
    event.preventDefault();
    const input = slot === "back" ? backImage : frontImage;
    if (input) input.click();
  });

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
      showError("Drop one file per label slot. Switch to Multiple labels for several files.");
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

setUploadMode("single");
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
    showError("Drop files into a label slot or the Multiple labels area.");
    setStatus("File selection needs attention");
  }
});

if (themeToggle) {
  themeToggle.checked = currentTheme() === "dark";
  themeToggle.addEventListener("change", function() {
    setTheme(themeToggle.checked ? "dark" : "light");
  });
}
uploadModeGroup.addEventListener("change", function() { setUploadMode(radioValue("uploadMode")); });

batchFiles.addEventListener("change", function() {
  addBatchFiles(batchFiles.files);
  batchFiles.value = "";
});

if (batchBrowse) {
  batchBrowse.addEventListener("click", function(event) {
    event.stopPropagation();
    batchFiles.click();
  });
}

processBatchButton.addEventListener("click", processBatchQueue);

batchBody.addEventListener("change", function(event) {
  const categoryControl = event.target.closest("[data-batch-category]");
  const originControl = event.target.closest("[data-batch-origin]");
  const control = categoryControl || originControl;
  if (!control) return;

  const id = Number(categoryControl ? categoryControl.dataset.batchCategory : originControl.dataset.batchOrigin);
  const item = state.batch.items.find((candidate) => candidate.id === id);
  if (!item) return;

  if (categoryControl) item.productCategory = categoryControl.value;  // picking "Auto" re-enables detection
  if (originControl) item.originType = originControl.value;

  // A different category/origin makes the row's verdict stale — send it back
  // to Ready so "Process all" picks it up again (it skips verified rows).
  if (isBatchItemVerified(item)) {
    resetBatchItemVerdict(item);
    updateBatchRow(item);
  }
});

batchBody.addEventListener("click", function(event) {
  const reviewButton = event.target.closest("[data-review-batch]");
  const retryButton = event.target.closest("[data-retry-batch]");
  const removeButton = event.target.closest("[data-remove-batch]");
  const toggleButton = event.target.closest("[data-toggle-batch]");

  if (reviewButton) reviewBatchItem(Number(reviewButton.dataset.reviewBatch));
  if (retryButton) retryBatchItem(Number(retryButton.dataset.retryBatch));
  if (removeButton) removeBatchItem(Number(removeButton.dataset.removeBatch));
  if (toggleButton) {
    const item = state.batch.items.find((candidate) => candidate.id === Number(toggleButton.dataset.toggleBatch));
    if (item) { item.expanded = !item.expanded; updateBatchRow(item); }
  }
});

// A category/origin change rebuilds the field list AND re-extracts from the
// loaded label, since extraction is scoped to the product category. Invalidating
// extractedKey forces maybeAutoExtractLabel to re-run (it no-ops with no label).
async function onCategoryOrOriginChange() {
  try {
    await refreshRequirements();
    state.extractedKey = null;
    maybeAutoExtractLabel();
  } catch (error) {
    // A failed /field-requirements load must not strand the UI on "Loading
    // requirements" forever.
    showError(error.message);
    setStatus("");
  }
}
if (singleCategory) singleCategory.addEventListener("change", onCategoryOrOriginChange);
if (singleOrigin) singleOrigin.addEventListener("change", onCategoryOrOriginChange);
verifyButton.addEventListener("click", verifyReviewedFields);
if (recheckButton) recheckButton.addEventListener("click", recheckFromResults);

loadFieldConfig().then(refreshRequirements).catch(function(error) {
  showError(error.message);
  setStatus("Unable to load requirements");
});
