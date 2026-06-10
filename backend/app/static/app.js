const FIELD_CONFIG = [
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

const FIELD_LOOKUP = Object.fromEntries(FIELD_CONFIG.map((field) => [field.key, field]));
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = new Set(["pdf", "png", "jpg", "jpeg", "webp"]);
const ACCEPTED_MIME_TYPES = new Set(["application/pdf", "image/png", "image/jpeg", "image/webp"]);
const FILE_LABELS = {
  front: "Front label",
  back: "Back label",
};

const state = {
  requirements: { required: [], conditional: [], optional: [] },
  extracted: {},
  validation: {},
  files: {
    front: null,
    back: null,
  },
};

const THEME_STORAGE_KEY = "alcohol-label-theme";
const themeToggle = document.querySelector("#themeToggle");
const productCategory = document.querySelector("#productCategory");
const originType = document.querySelector("#originType");
const frontImage = document.querySelector("#frontImage");
const backImage = document.querySelector("#backImage");
const expectedFields = document.querySelector("#expectedFields");
const reviewedFields = document.querySelector("#reviewedFields");
const requirementChips = document.querySelector("#requirementChips");
const extractButton = document.querySelector("#extractButton");
const verifyButton = document.querySelector("#verifyButton");
const statusText = document.querySelector("#statusText");
const errorBox = document.querySelector("#errorBox");
const resultsBody = document.querySelector("#resultsBody");
const modeChooseFile = document.getElementById("modeChooseFile");
const modeDragDrop = document.getElementById("modeDragDrop");
const chooseFileInputs = document.getElementById("chooseFileInputs");
const dropZoneInputs = document.getElementById("dropZoneInputs");
const uploadInputs = Array.from(document.querySelectorAll("[data-file-slot]"));
const dropZones = Array.from(document.querySelectorAll("[data-drop-slot]"));

function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function setTheme(theme) {
  const normalizedTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = normalizedTheme;
  themeToggle.checked = normalizedTheme === "dark";
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

  row.appendChild(label);
  row.appendChild(control);
  return row;
}

function renderFieldStack(container, prefix) {
  const heading = container.querySelector("h3").outerHTML;
  container.innerHTML = heading;

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

function formValues(container) {
  const values = {};
  for (const field of FIELD_CONFIG) {
    const control = container.querySelector("[name=" + JSON.stringify(field.key) + "]");
    values[field.key] = control ? control.value.trim() : "";
  }
  return values;
}

function setReviewedValues(values) {
  for (const [key, value] of Object.entries(values || {})) {
    const control = reviewedFields.querySelector("[name=" + JSON.stringify(key) + "]");
    if (control) control.value = value || "";
  }
}

function setExpectedValues(values) {
  for (const [key, value] of Object.entries(values || {})) {
    const control = expectedFields.querySelector("[name=" + JSON.stringify(key) + "]");
    if (control) control.value = value || "";
  }
}

function statusClass(status) {
  if (status === "PASS") return "status-pass";
  if (status === "NOT REQUIRED") return "status-neutral";
  if (status === "MISSING" || status === "EXPECTED VALUE MISSING") return "status-missing";
  return "status-fail";
}

function renderResults(response) {
  const expected = response.expected || formValues(expectedFields);
  const reviewed = response.reviewed || response.extracted || formValues(reviewedFields);
  const validation = response.validation || {};
  resultsBody.innerHTML = "";

  for (const key of FIELD_CONFIG.map((field) => field.key)) {
    const row = document.createElement("tr");
    const fieldCell = document.createElement("td");
    const statusCell = document.createElement("td");
    const expectedCell = document.createElement("td");
    const reviewedCell = document.createElement("td");
    const badge = document.createElement("span");
    const status = validation[key] || "NOT REVIEWED";

    fieldCell.textContent = FIELD_LOOKUP[key].label;
    badge.className = "status-badge " + statusClass(status);
    badge.textContent = status;
    statusCell.appendChild(badge);
    expectedCell.textContent = expected[key] || "";
    reviewedCell.textContent = reviewed[key] || "";

    row.appendChild(fieldCell);
    row.appendChild(statusCell);
    row.appendChild(expectedCell);
    row.appendChild(reviewedCell);
    resultsBody.appendChild(row);
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
  renderFieldStack(reviewedFields, "reviewed");
  setReviewedValues(state.extracted);
  setExpectedValues(state.extracted);
  setStatus("Ready");
}

async function extractFields() {
  clearError();

  if (!state.files.front) {
    showError("Front label is required.");
    setStatus("File selection needs attention");
    return;
  }

  const formData = new FormData();
  formData.append("product_category", productCategory.value);
  formData.append("origin_type", originType.value);
  formData.append("front_image", state.files.front);
  if (state.files.back) formData.append("back_image", state.files.back);

  extractButton.disabled = true;
  setStatus("Extracting fields");
  try {
    const response = await fetch("/extract", { method: "POST", body: formData });
    const body = await parseApiResponse(response);
    state.extracted = body.extracted || {};
    setReviewedValues(state.extracted);
    setExpectedValues(state.extracted);
    setStatus("Fields extracted — review Expected COLA fields and adjust if needed, then click Verify");
  } catch (error) {
    showError(error.message);
    setStatus("Extraction failed");
  } finally {
    extractButton.disabled = false;
  }
}

async function verifyReviewedFields() {
  clearError();
  verifyButton.disabled = true;
  setStatus("Verifying fields");
  try {
    const response = await fetch("/verify-reviewed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product_category: productCategory.value,
        origin_type: originType.value,
        expected: formValues(expectedFields),
        reviewed: formValues(reviewedFields),
      }),
    });
    const body = await parseApiResponse(response);
    renderResults(body);
    setStatus("Verification complete");
  } catch (error) {
    showError(error.message);
    setStatus("Verification failed");
  } finally {
    verifyButton.disabled = false;
  }
}

function setUploadMode(mode) {
  if (mode === "choose") {
    chooseFileInputs.hidden = false;
    dropZoneInputs.hidden = true;
    modeChooseFile.classList.add("active");
    modeDragDrop.classList.remove("active");
    modeChooseFile.setAttribute("aria-pressed", "true");
    modeDragDrop.setAttribute("aria-pressed", "false");
  } else {
    chooseFileInputs.hidden = true;
    dropZoneInputs.hidden = false;
    modeDragDrop.classList.add("active");
    modeChooseFile.classList.remove("active");
    modeDragDrop.setAttribute("aria-pressed", "true");
    modeChooseFile.setAttribute("aria-pressed", "false");
  }
}

function inputForDropSlot(slot) {
  return document.querySelector("#" + slot + "ImageDrop");
}

function initDropZone(zone) {
  const slot = zone.dataset.dropSlot;
  const input = inputForDropSlot(slot);

  zone.addEventListener("click", function(event) {
    if (!event.target.closest("button")) input.click();
  });

  zone.addEventListener("keydown", function(event) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      input.click();
    }
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
      showError("Drop one file per label slot. Batch uploads are coming next.");
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

for (const button of document.querySelectorAll("[data-browse-file]")) {
  button.addEventListener("click", function() {
    const input = inputForDropSlot(button.dataset.browseFile);
    input.click();
  });
}

for (const button of document.querySelectorAll("[data-remove-file]")) {
  button.addEventListener("click", function() {
    clearSelectedFile(button.dataset.removeFile);
  });
}

setUploadMode("choose");
renderFileState("front");
renderFileState("back");

document.addEventListener("dragover", function(event) {
  if (draggedFiles(event)) event.preventDefault();
});

document.addEventListener("drop", function(event) {
  if (!draggedFiles(event)) return;
  event.preventDefault();
  if (!event.target.closest("[data-drop-slot]")) {
    showError("Drop files into the Front label or Back label upload area.");
    setStatus("File selection needs attention");
  }
});

themeToggle.checked = currentTheme() === "dark";
themeToggle.addEventListener("change", function() {
  setTheme(themeToggle.checked ? "dark" : "light");
});

modeChooseFile.addEventListener("click", function() { setUploadMode("choose"); });
modeDragDrop.addEventListener("click", function() { setUploadMode("drop"); });

productCategory.addEventListener("change", refreshRequirements);
originType.addEventListener("change", refreshRequirements);
extractButton.addEventListener("click", extractFields);
verifyButton.addEventListener("click", verifyReviewedFields);

refreshRequirements().catch(function(error) {
  showError(error.message);
  setStatus("Unable to load requirements");
});
