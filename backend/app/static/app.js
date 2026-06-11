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
const BATCH_CONCURRENCY = 5;      // process batch files in parallel (~10 files in ~10s)
const ACCEPTED_EXTENSIONS = new Set(["pdf", "png", "jpg", "jpeg", "webp"]);
const ACCEPTED_MIME_TYPES = new Set(["application/pdf", "image/png", "image/jpeg", "image/webp"]);
const FILE_LABELS = {
  front: "Front label",
  back: "Back label",
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
  workflowMode: "cola",
  colaLoaded: false,
  colaFile: null,
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
const THEMES = ["light", "dark", "government", "corporate", "airbnb", "vimeo", "grammarly", "eventbrite"];
const themeSelect = document.querySelector("#themeSelect");
const productCategory = document.querySelector("#productCategory");
const originType = document.querySelector("#originType");
const frontImage = document.querySelector("#frontImage");
const backImage = document.querySelector("#backImage");
const expectedFields = document.querySelector("#expectedFields");
const requirementChips = document.querySelector("#requirementChips");
const extractButton = document.querySelector("#extractButton");
const verifyButton = document.querySelector("#verifyButton");
const colaFile = document.getElementById("colaFile");
const colaSummary = document.getElementById("colaSummary");
const colaFileName = document.getElementById("colaFileName");
const colaRemove = document.getElementById("colaRemove");
const colaChooseBtn = document.getElementById("colaChooseBtn");
const colaDropZone = document.getElementById("colaDropZone");
const colaProgress = document.getElementById("colaProgress");
const labelProgress = document.getElementById("labelProgress");
const colaUploadBlock = document.querySelector(".cola-upload");
const fieldsHelp = document.querySelector(".fields-help");
const modeColaWorkflow = document.getElementById("modeColaWorkflow");
const modeLabelWorkflow = document.getElementById("modeLabelWorkflow");
const statusText = document.querySelector("#statusText");
const errorBox = document.querySelector("#errorBox");
const resultsBody = document.querySelector("#resultsBody");
const resultsSummary = document.getElementById("resultsSummary");
const busySpinner = document.getElementById("busySpinner");
const exportButton = document.getElementById("exportButton");
const printButton = document.getElementById("printButton");
const modeChooseFile = document.getElementById("modeChooseFile");
const modeDragDrop = document.getElementById("modeDragDrop");
const modeBatch = document.getElementById("modeBatch");
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
  if (themeSelect) themeSelect.value = normalizedTheme;
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
      item.appendChild(img);
    } else {
      const note = document.createElement("span");
      note.className = "label-preview-note";
      note.textContent = file.name + " — PDF, not previewed inline";
      item.appendChild(note);
    }

    container.appendChild(item);
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
  return true;
}

function clearSelectedFile(slot) {
  state.files[slot] = null;
  syncInputFiles(slot, null);
  renderFileState(slot);
  clearError();
  setStatus("Ready");
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

function fieldNote(key) {
  const type = fieldRequirement(key);
  if (type === "required") return "Required";
  if (type === "conditional") return "Conditional";
  return "Optional";
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
  label.textContent = field.label;
  label.setAttribute("for", inputName(prefix, key));

  const note = document.createElement("span");
  note.className = "field-note " + fieldRequirement(key);
  note.textContent = fieldNote(key);
  label.appendChild(note);

  const control = document.createElement(field.type === "textarea" ? "textarea" : "input");
  control.id = inputName(prefix, key);
  control.name = key;
  control.autocomplete = "off";

  // The government warning is always checked against the fixed statutory text,
  // so the Expected-column box is read-only (editing it would do nothing).
  if (prefix === "expected" && key === "government_warning") {
    control.readOnly = true;
    control.placeholder = "Checked against the statutory wording — no entry needed.";
    control.classList.add("readonly-field");
  }

  row.appendChild(label);
  row.appendChild(control);
  return row;
}

function renderFieldStack(container, prefix) {
  const headingEl = container.querySelector("h3");
  container.innerHTML = headingEl ? headingEl.outerHTML : "";

  let optionalHeaderAdded = false;
  for (const key of orderedVisibleFields()) {
    if (fieldRequirement(key) === "optional" && !optionalHeaderAdded) {
      const divider = document.createElement("p");
      divider.className = "optional-divider";
      divider.textContent = "Additional fields";
      container.appendChild(divider);
      optionalHeaderAdded = true;
    }
    container.appendChild(createField(prefix, key));
  }
}

function renderRequirementChips() {
  requirementChips.innerHTML = "";
  for (const key of state.requirements.required) {
    const chip = document.createElement("span");
    chip.className = "chip required";
    chip.textContent = FIELD_LOOKUP[key].label + ": required";
    requirementChips.appendChild(chip);
  }
  for (const key of state.requirements.conditional) {
    const chip = document.createElement("span");
    chip.className = "chip conditional";
    chip.textContent = FIELD_LOOKUP[key].label + ": conditional";
    requirementChips.appendChild(chip);
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
  const controls = [productCategory, originType, extractButton, verifyButton, modeChooseFile, modeDragDrop, modeBatch, colaFile, colaRemove, modeColaWorkflow, modeLabelWorkflow];
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

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  return /[",\n\r]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
}

function buildResultsCsv(result) {
  const rows = [];
  rows.push(["Product category", result.product_category || ""]);
  rows.push(["Origin", result.origin_type || ""]);
  if (result.wine_path) rows.push(["Wine path", result.wine_path]);
  rows.push([]);
  rows.push(["Field", "Status", "Expected", "Reviewed"]);
  const expected = result.expected || {};
  const reviewed = result.reviewed || {};
  const validation = result.validation || {};
  const requirements = result.field_requirements || {};
  const keys = [].concat(requirements.required || [], requirements.conditional || [], requirements.optional || []);
  for (const key of (keys.length ? keys : Object.keys(validation))) {
    const config = FIELD_LOOKUP[key];
    rows.push([config ? config.label : key, validation[key] || "", expected[key] || "", reviewed[key] || ""]);
  }
  const checks = result.compliance_checks || [];
  if (checks.length) {
    rows.push([]);
    rows.push(["Label compliance check", "Status", "Detail"]);
    for (const check of checks) rows.push([check.label, check.status, check.detail]);
  }
  return rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
}

function downloadTextFile(filename, text, mimeType) {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function exportResults() {
  if (!state.lastResult) {
    showError("Run a verification first, then export.");
    return;
  }
  clearError();
  downloadTextFile("label-verification.csv", buildResultsCsv(state.lastResult), "text/csv;charset=utf-8");
}

function printResults() {
  if (!state.lastResult) {
    showError("Run a verification first, then print.");
    return;
  }
  clearError();
  window.print();
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
}

function formValues(container) {
  const values = {};
  for (const field of FIELD_CONFIG) {
    const control = container.querySelector("[name=" + JSON.stringify(field.key) + "]");
    values[field.key] = control ? control.value.trim() : "";
  }
  return values;
}

function setExpectedValues(values) {
  for (const [key, value] of Object.entries(values || {})) {
    const control = expectedFields.querySelector("[name=" + JSON.stringify(key) + "]");
    if (control) control.value = value || "";
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
  "EXEMPT_TABLE_WINE": "Exempt (table wine)",
  "FAIL_APPELLATION_REQUIRED_BY_TRIGGER": "Appellation required",
  "FAIL_NOT_ALLCAPS": "Not all-caps",
};

function statusClass(status) {
  if (status === "PASS" || status === "EXEMPT_TABLE_WINE") return "status-pass";
  if (status === "NOT REQUIRED") return "status-neutral";
  if (status === "PRESENT_ON_LABEL_CONFIRM_APPLICABILITY") return "status-processing";
  if (status === "MISSING" || status === "EXPECTED VALUE MISSING") return "status-missing";
  return "status-fail";
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function isFlaggedStatus(status) {
  const cls = statusClass(status);
  return cls === "status-fail" || cls === "status-missing";
}

function renderResults(response) {
  state.lastResult = response;
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
    const badge = document.createElement("span");
    const status = validation[key] || "NOT REVIEWED";

    if (status === "PASS" || status === "EXEMPT_TABLE_WINE") passed += 1;
    else if (isFlaggedStatus(status)) attention += 1;

    fieldCell.textContent = config.label;
    badge.className = "status-badge " + statusClass(status);
    badge.textContent = statusLabel(status);
    badge.title = status;
    statusCell.appendChild(badge);
    expectedCell.textContent = expected[key] || "";
    reviewedCell.textContent = reviewed[key] || "";

    if (isFlaggedStatus(status)) row.className = "is-flagged";

    row.appendChild(fieldCell);
    row.appendChild(statusCell);
    row.appendChild(expectedCell);
    row.appendChild(reviewedCell);
    resultsBody.appendChild(row);
  }

  if (resultsSummary) {
    const checked = keys.filter((key) => FIELD_LOOKUP[key]).length;
    resultsSummary.textContent = `${checked} fields checked · ${passed} passed · ${attention} need attention`;
  }

  renderComplianceChecks(response.compliance_checks || []);
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
    product_category: productCategory.value,
    origin_type: originType.value,
  });
  const response = await fetch("/field-requirements?" + params.toString());
  const body = await parseApiResponse(response);
  state.requirements = body.field_requirements;
  renderRequirementChips();
  renderFieldStack(expectedFields, "expected");
  setExpectedValues(state.expectedValues);
  setStatus("Ready");
}

function renderColaSummary() {
  if (!colaSummary) return;
  const has = Boolean(state.colaFile);
  colaSummary.classList.toggle("has-file", has);
  if (colaFileName) {
    colaFileName.textContent = has
      ? state.colaFile.name + (state.colaLoaded ? " — fields loaded" : "")
      : "";
  }
  if (colaRemove) colaRemove.hidden = !has;
}

async function extractCola(file) {
  const error = validateClientFile(file);
  if (error) {
    showError(error);
    setStatus("File selection needs attention");
    if (colaFile) colaFile.value = "";
    return;
  }
  clearError();
  state.colaFile = file;
  renderColaSummary();

  const formData = new FormData();
  formData.append("cola_file", file);

  setBusy(true);
  if (colaProgress) colaProgress.hidden = false;
  setStatus("Reading the COLA application");
  try {
    const response = await fetchWithTimeout("/extract-cola", { method: "POST", body: formData });
    const body = await parseApiResponse(response);
    if (body.product_category) productCategory.value = body.product_category;
    if (body.origin_type) originType.value = body.origin_type;
    state.expectedValues = body.extracted || {};
    state.colaLoaded = true;
    await refreshRequirements();
    renderColaSummary();
    setStatus("COLA fields loaded — upload the label artwork, then Verify against it");
  } catch (error) {
    showError(error.message);
    setStatus("COLA extraction failed");
  } finally {
    if (colaProgress) colaProgress.hidden = true;
    setBusy(false);
  }
}

function clearExpectedFields() {
  for (const control of expectedFields.querySelectorAll("input, textarea")) {
    control.value = "";
  }
}

function clearCola() {
  state.colaFile = null;
  state.colaLoaded = false;
  state.expectedValues = state.extracted || {};
  if (colaFile) colaFile.value = "";
  renderColaSummary();
  // Blank the form first so COLA-derived values don't linger; then re-apply
  // whatever the label extraction left (empty until the reviewer extracts).
  clearExpectedFields();
  setExpectedValues(state.expectedValues);
  clearError();
  setStatus("COLA removed");
}

const COLA_HELP = "These auto-fill from the uploaded COLA application. Upload the label artwork, then Verify to compare the label against the COLA.";
const LABEL_HELP = "These auto-fill from the label. Edit each field to match the approved COLA application, then Verify to compare it against the label.";

function setWorkflowMode(mode) {
  const isCola = mode === "cola";
  state.workflowMode = isCola ? "cola" : "label";
  if (colaUploadBlock) colaUploadBlock.hidden = !isCola;
  if (modeColaWorkflow) {
    modeColaWorkflow.classList.toggle("active", isCola);
    modeColaWorkflow.setAttribute("aria-pressed", String(isCola));
  }
  if (modeLabelWorkflow) {
    modeLabelWorkflow.classList.toggle("active", !isCola);
    modeLabelWorkflow.setAttribute("aria-pressed", String(!isCola));
  }
  // In COLA mode there's no separate Extract step: Verify reads the label itself.
  if (extractButton) extractButton.hidden = isCola;
  // Leaving COLA mode drops any loaded COLA so the form reverts to label-driven.
  if (!isCola && state.colaLoaded) clearCola();
  if (fieldsHelp) fieldsHelp.textContent = isCola ? COLA_HELP : LABEL_HELP;
}

function labelFileKey() {
  const f = state.files.front;
  const b = state.files.back;
  return [f ? f.name + ":" + f.size : "", b ? b.name + ":" + b.size : ""].join("|");
}

async function runLabelExtraction() {
  // POST the label artwork and store the reviewed snapshot. Throws on failure;
  // the caller manages busy state and error display.
  const formData = new FormData();
  formData.append("product_category", productCategory.value);
  formData.append("origin_type", originType.value);
  formData.append("front_image", state.files.front);
  if (state.files.back) formData.append("back_image", state.files.back);
  const response = await fetchWithTimeout("/extract", { method: "POST", body: formData });
  const body = await parseApiResponse(response);
  state.extracted = body.extracted || {};
  state.extractedKey = labelFileKey();
}

function maybeAutoExtractLabel() {
  // In the label-only workflow, reading the label IS what fills the form, so do
  // it automatically on upload (mirroring the COLA auto-fill). The "Extract from
  // Label" button stays as an explicit re-run (e.g. after changing category or
  // adding a back label). Skip in COLA mode (Verify reads the label there), when
  // there's no front label yet, while a request is in flight, and when these
  // exact files were already read.
  if (state.workflowMode !== "label") return;
  if (!state.files.front) return;
  if (state.inFlight) return;
  if (state.extractedKey === labelFileKey()) return;
  extractFields();
}

async function extractFields() {
  clearError();

  if (!state.files.front) {
    showError("Front label is required.");
    setStatus("File selection needs attention");
    return;
  }

  setBusy(true);
  if (labelProgress) labelProgress.hidden = false;
  setStatus("Extracting fields");
  try {
    await runLabelExtraction();
    if (state.colaLoaded) {
      // The COLA already populated the expected fields; the label only supplies
      // the values being checked. Don't overwrite the reviewer's COLA values.
      setStatus("Label read — now Verify it against the COLA application fields");
    } else {
      state.expectedValues = state.extracted;
      setExpectedValues(state.expectedValues);
      setStatus("Fields extracted from the label — edit each field to match the COLA application, then Verify");
    }
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
  if (state.workflowMode === "cola" && !state.files.front) {
    showError("Upload the label artwork to verify against the COLA.");
    setStatus("File selection needs attention");
    return;
  }
  setBusy(true);
  try {
    // COLA mode has no separate Extract button, so read the label here — but
    // only when the label file has changed since the last read, so re-verifying
    // after editing fields stays instant (no extra Gemini call).
    if (state.workflowMode === "cola" && state.extractedKey !== labelFileKey()) {
      setStatus("Reading the label");
      await runLabelExtraction();
    }
    setStatus("Verifying fields");
    const response = await fetchWithTimeout("/verify-reviewed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_category: productCategory.value,
        origin_type: originType.value,
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
  if (status === "Needs review") return "status-neutral";
  if (status === "Processing") return "status-processing";
  if (status === "Error") return "status-fail";
  return "status-ready";
}

function batchStatusText(item) {
  if (item.status === "Needs review") return "Needs review";
  return item.status;
}

function canProcessBatchItem(item) {
  return Boolean(item.file) && !item.clientError && item.status !== "Needs review" && item.status !== "Processing";
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

    if (item.status === "Needs review") {
      const reviewButton = document.createElement("button");
      reviewButton.className = "small-button";
      reviewButton.dataset.reviewBatch = String(item.id);
      reviewButton.disabled = state.batch.processing;
      reviewButton.type = "button";
      reviewButton.textContent = "Review";
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
      productCategory: productCategory.value,
      originType: originType.value,
      status: clientError ? "Error" : "Ready",
      message: clientError || "Ready to process",
      clientError,
      extracted: null,
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
    renderBatchQueue();
    return;
  }

  item.clientError = "";
  item.status = "Processing";
  item.message = "Extracting fields";
  item.extracted = null;
  renderBatchQueue();

  const formData = new FormData();
  formData.append("product_category", item.productCategory);
  formData.append("origin_type", item.originType);
  formData.append("front_image", item.file);

  try {
    const response = await fetchWithTimeout("/extract", { method: "POST", body: formData });
    const body = await parseApiResponse(response);
    item.extracted = body.extracted || {};
    item.status = "Needs review";
    item.message = "Open in editor to verify";
  } catch (error) {
    item.status = "Error";
    item.message = error.message;
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

  const readyCount = state.batch.items.filter((item) => item.status === "Needs review").length;
  const errorCount = state.batch.items.filter((item) => item.status === "Error").length;
  setStatus("Batch complete: " + readyCount + " ready to review" + (errorCount ? ", " + errorCount + " need attention" : ""));
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
  setStatus(item.status === "Needs review" ? "Batch item ready to review" : "Batch item needs attention");
}

async function reviewBatchItem(id) {
  const item = state.batch.items.find((candidate) => candidate.id === id);
  if (!item || item.status !== "Needs review" || !item.extracted) {
    showError("Process this batch item before reviewing it.");
    setStatus("Batch item needs extraction");
    return;
  }

  clearError();
  productCategory.value = item.productCategory;
  originType.value = item.originType;
  state.extracted = item.extracted;
  state.expectedValues = item.extracted;
  state.colaLoaded = false;
  state.colaFile = null;
  if (colaFile) colaFile.value = "";
  renderColaSummary();
  state.files.front = item.file;
  state.files.back = null;
  // The batch item is already extracted; mark the label as read so a COLA-mode
  // Verify doesn't needlessly re-extract it.
  state.extractedKey = labelFileKey();
  syncInputFiles("front", item.file);
  syncInputFiles("back", null);
  renderFileState("front");
  renderFileState("back");
  setUploadMode("choose");
  renderEmptyResults("No verification results for this batch item yet.");
  await refreshRequirements();
  setExpectedValues(item.extracted);
  setStatus("Loaded batch item #" + item.id + " — edit fields to match the COLA application, then Verify");
  document.querySelector("#fields-title").scrollIntoView({ block: "start" });
}

function removeBatchItem(id) {
  if (state.batch.processing) return;
  state.batch.items = state.batch.items.filter((item) => item.id !== id);
  renderBatchQueue();
  setStatus(state.batch.items.length ? "Batch item removed" : "Batch cleared");
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

function setColaMode(mode) {
  // The COLA upload mirrors the label upload: a drop zone in Drag & Drop mode,
  // a file picker otherwise.
  const dropMode = mode === "drop";
  if (colaChooseBtn) colaChooseBtn.hidden = dropMode;
  if (colaDropZone) colaDropZone.hidden = !dropMode;
}

function setUploadMode(mode) {
  setColaMode(mode);
  if (mode === "choose") {
    chooseFileInputs.hidden = false;
    dropZoneInputs.hidden = true;
    batchPanel.hidden = true;
    modeChooseFile.classList.add("active");
    modeDragDrop.classList.remove("active");
    modeBatch.classList.remove("active");
    modeChooseFile.setAttribute("aria-pressed", "true");
    modeDragDrop.setAttribute("aria-pressed", "false");
    modeBatch.setAttribute("aria-pressed", "false");
  } else if (mode === "batch") {
    chooseFileInputs.hidden = true;
    dropZoneInputs.hidden = true;
    batchPanel.hidden = false;
    modeBatch.classList.add("active");
    modeChooseFile.classList.remove("active");
    modeDragDrop.classList.remove("active");
    modeBatch.setAttribute("aria-pressed", "true");
    modeChooseFile.setAttribute("aria-pressed", "false");
    modeDragDrop.setAttribute("aria-pressed", "false");
  } else {
    chooseFileInputs.hidden = true;
    dropZoneInputs.hidden = false;
    batchPanel.hidden = true;
    modeDragDrop.classList.add("active");
    modeChooseFile.classList.remove("active");
    modeBatch.classList.remove("active");
    modeDragDrop.setAttribute("aria-pressed", "true");
    modeChooseFile.setAttribute("aria-pressed", "false");
    modeBatch.setAttribute("aria-pressed", "false");
  }
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

function initColaDropZone(zone) {
  if (!zone) return;
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
      showError("Drop a single COLA application file.");
      setStatus("File selection needs attention");
      return;
    }
    if (files[0]) extractCola(files[0]);
  });
}

initColaDropZone(colaDropZone);

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
renderColaSummary();
renderBatchQueue();

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

if (themeSelect) {
  themeSelect.value = currentTheme();
  themeSelect.addEventListener("change", function() {
    setTheme(themeSelect.value);
  });
}

modeChooseFile.addEventListener("click", function() { setUploadMode("choose"); });
modeDragDrop.addEventListener("click", function() { setUploadMode("drop"); });
modeBatch.addEventListener("click", function() { setUploadMode("batch"); });

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
});

batchBody.addEventListener("click", function(event) {
  const reviewButton = event.target.closest("[data-review-batch]");
  const retryButton = event.target.closest("[data-retry-batch]");
  const removeButton = event.target.closest("[data-remove-batch]");

  if (reviewButton) reviewBatchItem(Number(reviewButton.dataset.reviewBatch));
  if (retryButton) retryBatchItem(Number(retryButton.dataset.retryBatch));
  if (removeButton) removeBatchItem(Number(removeButton.dataset.removeBatch));
});

productCategory.addEventListener("change", refreshRequirements);
originType.addEventListener("change", refreshRequirements);
extractButton.addEventListener("click", extractFields);
verifyButton.addEventListener("click", verifyReviewedFields);
if (colaFile) {
  colaFile.addEventListener("change", function() {
    if (colaFile.files.length) extractCola(colaFile.files[0]);
  });
}
if (colaRemove) colaRemove.addEventListener("click", clearCola);
if (modeColaWorkflow) modeColaWorkflow.addEventListener("click", function() { setWorkflowMode("cola"); });
if (modeLabelWorkflow) modeLabelWorkflow.addEventListener("click", function() { setWorkflowMode("label"); });
setWorkflowMode(state.workflowMode);
if (exportButton) exportButton.addEventListener("click", exportResults);
if (printButton) printButton.addEventListener("click", printResults);

loadFieldConfig().then(refreshRequirements).catch(function(error) {
  showError(error.message);
  setStatus("Unable to load requirements");
});
