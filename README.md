# CodeLens — Intelligent Code Reviewer & Explainer

A developer utility that analyzes Python, JavaScript, or Java code, finds
bugs, explains what the code does in plain language, and outputs an
optimized version — all rendered with syntax highlighting in a web UI.

## Architecture

```
code-reviewer/
├── backend/
│   ├── app.py            Flask server, exposes POST /analyze
│   ├── analyzer.py       Prompt engineering + Gemini API call + JSON parsing
│   ├── requirements.txt
│   └── .env              Your GEMINI_API_KEY (do not commit this)
└── frontend/
    ├── index.html        Two-panel UI (input / results)
    ├── style.css          Dark, IDE-inspired theme
    └── script.js          Calls the API, renders structured results
```

## Setup (one-time)

1. **Get a free Gemini API key**: https://aistudio.google.com/app/apikey
   (no credit card required, 1,500 requests/day free tier as of mid-2026)

2. **Add your key**: open `backend/.env` and set:
   ```
   GEMINI_API_KEY=your_actual_key_here
   ```

3. **Install backend dependencies** (already done if you ran the setup
   commands below once):
   ```bash
   cd backend
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

## Running the app

You need TWO things running at once: the backend API and the frontend page.

**Terminal 1 — start the backend:**
```bash
cd backend
./venv/bin/python app.py
```
You should see Flask start on `http://127.0.0.1:5000`.

**Terminal 2 — serve the frontend:**
```bash
cd frontend
python3 -m http.server 8000
```
Then open **http://localhost:8000** in your browser.

## Using it

1. Paste code into the left panel, or click "Upload file" to load a
   `.py`, `.js`, or `.java` file.
2. Pick the language (or leave on Auto-detect).
3. Click "Analyze code".
4. The right panel fills in with:
   - A plain-language explanation of what the code does
   - A bug report (severity-tagged: critical/high/medium/low)
   - Style/performance suggestions
   - A syntax-highlighted, optimized version of the code (with a Copy button)

## How the structured output works

`analyzer.py` sends Gemini a strict system prompt defining an exact JSON
schema (summary, bugs[], suggestions[], optimized_code) and sets
`response_mime_type: "application/json"` in the generation config. This
forces the model to return parseable JSON instead of free-form prose, so
the frontend can reliably split "bug report" from "optimized code" into
separate, distinctly-rendered panels — which was the core requirement of
this project.

## Troubleshooting

- **"GEMINI_API_KEY not found"** — you haven't edited `.env` yet, or you're
  running `app.py` from the wrong directory (must run from `backend/`).
- **CORS error in browser console** — make sure the backend is running on
  port 5000; `flask-cors` is already configured to allow the frontend's
  origin.
- **"Failed to reach the analysis server"** — backend isn't running, or
  crashed. Check Terminal 1 for the actual Python error.
- **Model output missing required keys** — rare, but can happen if Gemini's
  free tier rate-limits mid-response. Just retry the analysis.