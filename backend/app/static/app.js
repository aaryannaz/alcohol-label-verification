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

const state = {
  requirements: { required: [], conditional: [], optional: [] },
  extracted: {},
  validation: {},
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
  return `${prefix}_${key}`;
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
  note.className = `field-note ${fieldRequirement(key)}`;
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
    chip.textContent = `${FIELD_LOOKUP[key].label}: required`;
    requirementChips.appendChild(chip);
  }
  for (const key of state.requirements.conditional) {
    const chip = document.createElement("span");
    chip.className = "chip conditional";
    chip.textContent = `${FIELD_LOOKUP[key].label}: conditional`;
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
    const control = container.querySelector(`[name="${field.key}"]`);
    values[field.key] = control ? control.value.trim() : "";
  }
  return values;
}

function setReviewedValues(values) {
  for (const [key, value] of Object.entries(values || {})) {
    const control = reviewedFields.querySelector(`[name="${key}"]`);
    if (control) control.value = value ?? "";
  }
}

function setExpectedValues(values) {
  for (const [key, value] of Object.entries(values || {})) {
    const control = expectedFields.querySelector(`[name="${key}"]`);
    if (control) control.value = value ?? "";
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
    badge.className = `status-badge ${statusClass(status)}`;
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
  const response = await fetch(`/field-requirements?${params.toString()}`);
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
  const isDropMode = dropZoneInputs && dropZoneInputs.style.display !== "none";
  const activeFront = isDropMode ? document.getElementById("frontImageDrop") : frontImage;
  if (!activeFront.files.length) {
    showError("Front label is required.");
    return;
  }

  const isDropMode = dropZoneInputs.style.display !== "none";
  const activeFront = isDropMode ? document.getElementById("frontImageDrop") : frontImage;
  const activeBack = isDropMode ? document.getElementById("backImageDrop") : backImage;

  const formData = new FormData();
  formData.append("product_category", productCategory.value);
  formData.append("origin_type", originType.value);
  formData.append("front_image", activeFront.files[0]);
  if (activeBack.files.length) formData.append("back_image", activeBack.files[0]);

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

themeToggle.checked = currentTheme() === "dark";
themeToggle.addEventListener("change", () => {
  setTheme(themeToggle.checked ? "dark" : "light");
});

productCategory.addEventListener("change", refreshRequirements);
originType.addEventListener("change", refreshRequirements);
extractButton.addEventListener("click", extractFields);
verifyButton.addEventListener("click", verifyReviewedFields);

refreshRequirements().catch((error) => {
  showError(error.message);
  setStatus("Unable to load requirements");
});

const modeChooseFile = document.getElementById("modeChooseFile");
const modeDragDrop = document.getElementById("modeDragDrop");
const chooseFileInputs = document.getElementById("chooseFileInputs");
const dropZoneInputs = document.getElementById("dropZoneInputs");

function setUploadMode(mode) {
  if (mode === "choose") {
    chooseFileInputs.style.display = "";
    dropZoneInputs.style.display = "none";
    modeChooseFile.classList.add("active");
    modeDragDrop.classList.remove("active");
  } else {
    chooseFileInputs.style.display = "none";
    dropZoneInputs.style.display = "grid";
    modeDragDrop.classList.add("active");
    modeChooseFile.classList.remove("active");
  }
}

function initDropZone(dropZoneId, inputId, hintId) {
  const zone = document.getElementById(dropZoneId);
  const input = document.getElementById(inputId);
  const hint = document.getElementById(hintId);

  function setFile(file) {
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    hint.innerHTML = '<span class="drop-file-name">' + file.name + '</span>';
    zone.classList.add("has-file");
  }

  zone.addEventListener("click", (e) => {
    if (!e.target.closest("label")) input.click();
  });

  input.addEventListener("change", () => {
    if (input.files.length) setFile(input.files[0]);
  });

  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });

  zone.addEventListener("dragleave", () => {
    zone.classList.remove("drag-over");
  });

  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
  });
}

initDropZone("frontDropZone", "frontImageDrop", "frontDropHint");
initDropZone("backDropZone", "backImageDrop", "backDropHint");

modeChooseFile.addEventListener("click", () => setUploadMode("choose"));
modeDragDrop.addEventListener("click", () => setUploadMode("drop"));
