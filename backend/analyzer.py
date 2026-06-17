"""
analyzer.py
------------
Core "code analysis pipeline" for the Intelligent Code Reviewer.

Responsibilities:
1. Take raw code (as a string) + its language.
2. Send it to the Gemini API with strict SYSTEM instructions that force
   a structured, predictable output (JSON) containing:
      - a plain-language explanation
      - a list of discovered bugs/issues
      - a per-function time/space complexity analysis
      - an optimized / corrected version of the code
3. Deterministically compute code statistics (lines, functions, loops,
   imports, bug count) via lightweight static analysis — these are exact,
   mechanical counts, so we don't ask the model to guess them.
4. Parse and validate the model's JSON so the rest of the app can trust its shape.

This is the "Code-as-context management" + "structured outputs" part of
the project: we treat the user's code as an opaque string we inject into
a prompt template, and we constrain the model's output format rather than
hoping it free-forms something parseable.
"""

import os
import json
import re
import google.generativeai as genai
from dotenv import load_dotenv

# Load GEMINI_API_KEY from a local .env file (never hardcode keys in code)
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY not found. Create a .env file in backend/ with:\n"
        "GEMINI_API_KEY=your_key_here"
    )

genai.configure(api_key=API_KEY)

# Gemini 2.5 Flash: free tier, fast, strong at code tasks.
MODEL_NAME = "gemini-2.5-flash"

# ---------------------------------------------------------------------------
# SYSTEM INSTRUCTIONS
# ---------------------------------------------------------------------------
# This is the "force structured output" mechanism the project asks for.
# We:
#   1. Define a strict role/persona.
#   2. Define the EXACT JSON schema the model must return.
#   3. Forbid any prose outside that JSON.
# Gemini's `response_mime_type="application/json"` (set below in
# generation_config) reinforces this at the API level, not just via prompt
# wording — that's the most reliable way to get structured output.
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTIONS = """You are an expert senior software engineer acting as an automated code
reviewer. You review code in Python, JavaScript, and Java.

You will be given a single raw code file as a string. You must analyze it and
respond with ONLY a single JSON object — no markdown fences, no commentary
before or after it. The JSON object must exactly match this schema:

{
  "language_detected": string,          // the language you identified
  "summary": string,                     // 2-4 sentence plain-language explanation of what the code does, for a non-expert
  "bugs": [
    {
      "severity": "critical" | "high" | "medium" | "low",
      "line_reference": string,          // e.g. "line 12" or "function calculate_total"
      "issue": string,                   // short title of the problem
      "explanation": string              // why it's a problem, in plain language
    }
  ],
  "complexity_analysis": [
    {
      "function_name": string,          // name of the function/method, no parentheses
      "time_complexity": string,        // Big-O notation, e.g. "O(n)", "O(1)", "O(n log n)"
      "space_complexity": string        // Big-O notation, e.g. "O(1)", "O(n)"
    }
  ],
  "suggestions": [string],               // style/performance/readability improvements that are NOT bugs
  "optimized_code": string                // the full corrected, optimized version of the code
}

Rules:
- If there are no bugs, return an empty array for "bugs" — do not invent issues.
- "complexity_analysis" must contain exactly one entry per top-level function or
  method defined in the code. Reason about the function's actual logic (loops,
  recursion, data structures used) to determine complexity — do not default to
  O(n) without justification.
- "optimized_code" must be complete and runnable, not a diff or snippet.
- Preserve the original code's intent; do not change its purpose.
- Never include the markdown code fence characters (```) inside "optimized_code" — just the raw code itself.
- Be precise and concise. Do not pad explanations with filler.
- Output must be valid, parseable JSON. Escape special characters properly.
"""

PROMPT_TEMPLATE = """Analyze the following {language} code. Identify bugs, explain what it does
in plain language, determine the time and space complexity of each function,
and provide an optimized/corrected version.

--- BEGIN CODE ---
{code}
--- END CODE ---
"""


def _strip_code_fences(text: str) -> str:
    """
    Safety net: even with response_mime_type=application/json, models
    occasionally wrap output in ```json ... ``` fences. Strip them before
    parsing so json.loads doesn't blow up.
    """
    text = text.strip()
    fence_pattern = r"^```(?:json)?\s*|\s*```$"
    text = re.sub(fence_pattern, "", text, flags=re.IGNORECASE)
    return text.strip()


# ---------------------------------------------------------------------------
# Deterministic code statistics ("📋 Code Statistics" panel)
# ---------------------------------------------------------------------------
# Lines of code / function count / loop count / import count are exact,
# mechanical facts about the source — we compute them ourselves via regex
# rather than asking the model, so these numbers can never drift or get
# hallucinated. Only "complexity_analysis" (which needs actual reasoning
# about the logic) comes from Gemini.
# ---------------------------------------------------------------------------
_LANG_PATTERNS = {
    "python": {
        "function": r"^\s*def\s+\w+\s*\(",
        "loop": r"^\s*(for|while)\s+.+:",
        "import": r"^\s*(import|from)\s+\w",
    },
    "javascript": {
        "function": r"\bfunction\s+\w*\s*\(|\b(const|let|var)\s+\w+\s*=\s*(\([^)]*\)|\w+)\s*=>|\b\w+\s*\([^)]*\)\s*\{",
        "loop": r"\b(for|while)\s*\(",
        "import": r"^\s*(import\s+.+from|const\s+\w+\s*=\s*require\()",
    },
    "java": {
        "function": r"\b(public|private|protected|static)[\w\s<>\[\],]*\s+\w+\s*\([^;{]*\)\s*\{",
        "loop": r"\b(for|while)\s*\(",
        "import": r"^\s*import\s+",
    },
}


def _guess_language(code: str) -> str:
    if re.search(r"^\s*def\s+\w+\s*\(", code, re.MULTILINE):
        return "python"
    if re.search(r"\bfunction\s+\w*\s*\(|=>", code):
        return "javascript"
    if re.search(r"\bpublic\s+(static\s+)?(class|void|int|String)\b", code):
        return "java"
    return "python"


def compute_code_statistics(code: str, language: str) -> dict:
    """
    Lightweight static analysis backing the "Code Statistics" panel.
    Returns exact counts for lines/functions/loops/imports — no LLM call.
    """
    non_blank_lines = [l for l in code.splitlines() if l.strip()]
    loc = len(non_blank_lines)

    lang = (language or "auto-detect").lower()
    if lang not in _LANG_PATTERNS:
        lang = _guess_language(code)

    patterns = _LANG_PATTERNS.get(lang, _LANG_PATTERNS["python"])

    functions = len(re.findall(patterns["function"], code, flags=re.MULTILINE))
    loops = len(re.findall(patterns["loop"], code, flags=re.MULTILINE))
    imports = len(re.findall(patterns["import"], code, flags=re.MULTILINE))

    return {
        "lines_of_code": loc,
        "functions": functions,
        "loops": loops,
        "imports": imports,
    }


def analyze_code(code: str, language: str = "auto-detect") -> dict:
    """
    Sends the given code to Gemini and returns a parsed, structured dict.

    Args:
        code: The raw source code as a string (this is the "ingest a raw
              code file as a string variable" requirement — the caller,
              e.g. our Flask route, is responsible for reading the file
              and decoding it into this string before calling here).
        language: One of "python", "javascript", "java", or "auto-detect".

    Returns:
        dict matching the schema described in SYSTEM_INSTRUCTIONS, plus a
        "code_statistics" key computed deterministically (not from the model).

    Raises:
        ValueError: if the model's output can't be parsed as valid JSON,
                    or doesn't contain the required keys.
    """
    if not code or not code.strip():
        raise ValueError("No code provided to analyze.")

    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=SYSTEM_INSTRUCTIONS,
        generation_config={
            "temperature": 0.2,          # low temperature = more deterministic, less "creative" bug reports
            "response_mime_type": "application/json",  # force JSON mode at the API level
        },
    )

    prompt = PROMPT_TEMPLATE.format(language=language, code=code)

    response = model.generate_content(prompt)
    raw_text = response.text

    cleaned = _strip_code_fences(raw_text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Model did not return valid JSON. Raw output:\n{raw_text}"
        ) from e

    required_keys = {
        "language_detected", "summary", "bugs",
        "complexity_analysis", "suggestions", "optimized_code",
    }
    missing = required_keys - data.keys()
    if missing:
        raise ValueError(f"Model output missing required keys: {missing}")

    # Attach deterministic code statistics. "potential_bugs" reuses the
    # bug count we already trust from the model's "bugs" array, instead of
    # asking it to count a second time.
    stats = compute_code_statistics(code, language)
    stats["potential_bugs"] = len(data.get("bugs", []))
    data["code_statistics"] = stats

    return data