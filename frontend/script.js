/**
 * script.js
 * ----------
 * Frontend logic for CodeLens.
 *
 * Flow:
 *  1. User pastes/uploads code and picks a language.
 *  2. We POST { code, language } to our Flask backend at /analyze.
 *  3. Backend returns structured JSON (summary, bugs, complexity_analysis,
 *     suggestions, optimized_code, code_statistics).
 *  4. We render each field into its own panel, using:
 *      - marked.js to render the plain-language summary as markdown
 *      - highlight.js to syntax-highlight the optimized code block
 */

const API_BASE_URL = "http://127.0.0.1:5000";

// ---- DOM references -------------------------------------------------
const codeInput      = document.getElementById("codeInput");
const languageSelect = document.getElementById("languageSelect");
const fileInput      = document.getElementById("fileInput");
const analyzeBtn     = document.getElementById("analyzeBtn");
const btnLabel       = analyzeBtn.querySelector(".btn-label");
const btnSpinner     = analyzeBtn.querySelector(".btn-spinner");

const titlebarFile   = document.getElementById("titlebarFile");
const titlebarStatus = document.getElementById("titlebarStatus");

const emptyState     = document.getElementById("emptyState");
const errorState     = document.getElementById("errorState");
const resultsContent = document.getElementById("resultsContent");

const summaryText       = document.getElementById("summaryText");
const statsGrid          = document.getElementById("statsGrid");
const bugsList           = document.getElementById("bugsList");
const bugCount           = document.getElementById("bugCount");
const complexityList     = document.getElementById("complexityList");
const suggestionsList    = document.getElementById("suggestionsList");
const optimizedCode      = document.getElementById("optimizedCode");
const copyBtn             = document.getElementById("copyBtn");

// Map our language values to highlight.js language classes
const HLJS_LANG = {
  python: "python",
  javascript: "javascript",
  java: "java",
  "auto-detect": "plaintext",
};

// ---- File upload: read file into the textarea ------------------------
fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    codeInput.value = e.target.result;
    titlebarFile.textContent = file.name;

    // Auto-select language based on extension
    if (file.name.endsWith(".py")) languageSelect.value = "python";
    else if (file.name.endsWith(".js")) languageSelect.value = "javascript";
    else if (file.name.endsWith(".java")) languageSelect.value = "java";
  };
  reader.readAsText(file);
});

// ---- Status indicator helper ------------------------------------------
function setStatus(state, label) {
  const dot = titlebarStatus.querySelector(".status-dot");
  const text = titlebarStatus.querySelector(".status-text");
  dot.className = `status-dot ${state}`;
  text.textContent = label;
}

// ---- Main analyze action ----------------------------------------------
analyzeBtn.addEventListener("click", async () => {
  const code = codeInput.value;
  const language = languageSelect.value;

  if (!code.trim()) {
    showError("Paste some code first, or upload a file.");
    return;
  }

  setLoading(true);
  setStatus("working", "analyzing");
  hideError();

  try {
    const response = await fetch(`${API_BASE_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, language }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Something went wrong on the server.");
    }

    renderResults(data);
    setStatus("done", "complete");
  } catch (err) {
    console.error(err);
    showError(err.message || "Failed to reach the analysis server. Is the Flask backend running?");
    setStatus("error", "failed");
  } finally {
    setLoading(false);
  }
});

function setLoading(isLoading) {
  analyzeBtn.disabled = isLoading;
  btnSpinner.hidden = !isLoading;
  btnLabel.textContent = isLoading ? "Analyzing…" : "Analyze code";
}

function showError(message) {
  emptyState.hidden = true;
  resultsContent.hidden = true;
  errorState.hidden = false;
  errorState.textContent = message;
}

function hideError() {
  errorState.hidden = true;
}

// ---- Render the structured response into the results panel -----------
function renderResults(data) {
  emptyState.hidden = true;
  errorState.hidden = true;
  resultsContent.hidden = false;

  // 1. Plain-language summary (rendered as markdown -> HTML)
  summaryText.innerHTML = marked.parse(data.summary || "No summary provided.");

  // 2. Code statistics
  renderCodeStatistics(data.code_statistics);

  // 3. Bug report
  const bugs = Array.isArray(data.bugs) ? data.bugs : [];
  bugCount.textContent = bugs.length;

  if (bugs.length === 0) {
    bugsList.innerHTML = `<div class="no-bugs">✓ No bugs detected.</div>`;
  } else {
    bugsList.innerHTML = bugs.map(bugCardHTML).join("");
  }

  // 4. Complexity analysis
  renderComplexityAnalysis(data.complexity_analysis);

  // 5. Suggestions
  const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
  if (suggestions.length === 0) {
    suggestionsList.innerHTML = `<p class="prose" style="color: var(--text-muted)">No additional suggestions.</p>`;
  } else {
    suggestionsList.innerHTML = `<ul class="suggestions-list">${suggestions
      .map((s) => `<li>${escapeHTML(s)}</li>`)
      .join("")}</ul>`;
  }

  // 6. Optimized code, syntax-highlighted
  const lang = HLJS_LANG[languageSelect.value] || "plaintext";
  const codeStr = data.optimized_code || "";
  optimizedCode.innerHTML = `<pre><code class="language-${lang}">${escapeHTML(codeStr)}</code></pre>`;
  hljs.highlightElement(optimizedCode.querySelector("code"));

  // Store for copy button
  copyBtn.dataset.code = codeStr;
}

// ---- 📋 Code statistics -------------------------------------------------
function renderCodeStatistics(stats) {
  if (!stats) {
    statsGrid.innerHTML = `<p class="prose" style="color: var(--text-muted)">No statistics available.</p>`;
    return;
  }

  const items = [
    { label: "Lines of Code", value: stats.lines_of_code },
    { label: "Functions", value: stats.functions },
    { label: "Loops", value: stats.loops },
    { label: "Imports", value: stats.imports },
    { label: "Potential Bugs", value: stats.potential_bugs },
  ];

  statsGrid.innerHTML = `
    <div class="stats-grid">
      ${items
        .map(
          (item) => `
        <div class="stat-card">
          <div class="stat-value">${item.value ?? 0}</div>
          <div class="stat-label">${escapeHTML(item.label)}</div>
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

// ---- 📈 Complexity analysis ----------------------------------------------
function renderComplexityAnalysis(list) {
  const items = Array.isArray(list) ? list : [];

  if (items.length === 0) {
    complexityList.innerHTML = `<p class="prose" style="color: var(--text-muted)">No functions found to analyze.</p>`;
    return;
  }

  complexityList.innerHTML = items.map(complexityCardHTML).join("");
}

function complexityCardHTML(item) {
  const name = escapeHTML(item.function_name || "function");
  const time = escapeHTML(item.time_complexity || "—");
  const space = escapeHTML(item.space_complexity || "—");

  return `
    <div class="complexity-card">
      <div class="complexity-head">${name}()</div>
      <div class="complexity-metrics">
        <span class="metric-badge">Time Complexity: ${time}</span>
        <span class="metric-badge">Space Complexity: ${space}</span>
      </div>
    </div>
  `;
}

function bugCardHTML(bug) {
  const severity = (bug.severity || "low").toLowerCase();
  const validSeverities = ["critical", "high", "medium", "low"];
  const sevClass = validSeverities.includes(severity) ? severity : "low";

  return `
    <div class="bug-card sev-${sevClass}">
      <div class="bug-head">
        <span class="bug-severity">${sevClass}</span>
        <span class="bug-title">${escapeHTML(bug.issue || "Issue")}</span>
        ${bug.line_reference ? `<span class="bug-loc">${escapeHTML(bug.line_reference)}</span>` : ""}
      </div>
      <div class="bug-explanation">${escapeHTML(bug.explanation || "")}</div>
    </div>
  `;
}

function escapeHTML(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ---- Copy optimized code to clipboard ----------------------------------
copyBtn.addEventListener("click", async () => {
  const code = copyBtn.dataset.code || "";
  if (!code) return;

  try {
    await navigator.clipboard.writeText(code);
    const original = copyBtn.textContent;
    copyBtn.textContent = "Copied!";
    setTimeout(() => (copyBtn.textContent = original), 1500);
  } catch (err) {
    console.error("Clipboard write failed", err);
  }
});

// ---- Keep titlebar filename in sync with language selection -----------
languageSelect.addEventListener("change", () => {
  const ext = { python: "py", javascript: "js", java: "java" }[languageSelect.value];
  if (ext && titlebarFile.textContent.startsWith("untitled")) {
    titlebarFile.textContent = `untitled.${ext}`;
  }
});