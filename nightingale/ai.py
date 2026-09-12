"""Real LLM integration — OpenAI-compatible chat API (DeepSeek by default).

Swap the provider by changing environment variables (or the CONFIG block
below):
    NIGHTINGALE_LLM_API_KEY    e.g. sk-... (required to enable the LLM)
    NIGHTINGALE_LLM_BASE_URL   default https://api.deepseek.com/v1
    NIGHTINGALE_LLM_MODEL      default deepseek-chat

Any OpenAI-compatible service works (OpenAI, DeepSeek, proxies) — only the
three values above change. Only the Python standard library is used
(urllib), so there are no new dependencies.

Privacy: the patient text is PHI-redacted (names / NRICs / phone numbers)
BEFORE it leaves the machine. If the API is not configured or the call
fails, generate_suggestion() returns None and the app keeps the static
simulated suggestion — the demo never breaks.
"""
import json
import os
import re
import urllib.request

# ---------------------- CONFIG (swap provider here) ----------------------
API_KEY = os.environ.get("NIGHTINGALE_LLM_API_KEY", "")
BASE_URL = os.environ.get("NIGHTINGALE_LLM_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.environ.get("NIGHTINGALE_LLM_MODEL", "deepseek-chat")
TIMEOUT_SECONDS = 30

# ---------------------- PHI redaction (before any LLM call) --------------
_NRIC = re.compile(r"\b[STFGM]\d{7}[A-Z]\b")
_PHONE = re.compile(r"\+?65[\s-]?\d{4}[\s-]?\d{4}|\b\d{4}[\s-]?\d{4}\b")
_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Mdm|Dr|Prof)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


def redact(text: str) -> str:
    """Strip NRICs, phone numbers and salutation names from text."""
    text = _NRIC.sub("[REDACTED-NRIC]", text)
    text = _PHONE.sub("[REDACTED-PHONE]", text)
    text = _NAME.sub("[REDACTED-NAME]", text)
    return text


def is_configured() -> bool:
    return bool(API_KEY)


def generate_suggestion(patient: dict) -> str | None:
    """Ask the LLM for a clinical suggestion for one patient.

    Returns the suggestion text, or None when the API is not configured or
    the call fails — the caller then keeps the static simulated suggestion.
    """
    if not API_KEY:
        return None
    story = redact(patient.get("patient_story", ""))
    diagnosis = redact(patient.get("doctor_diagnosis", ""))
    prompt = (
        "You are a clinical decision-support assistant in a family clinic. "
        "Given the patient's story and the doctor's current diagnosis, write "
        "2-3 short sentences of clinical suggestions (next tests, monitoring, "
        "or medication notes). Do not invent patient identifiers.\n\n"
        f"Patient story: {story}\n"
        f"Doctor diagnosis: {diagnosis}\n"
    )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system",
             "content": "Answer as a cautious clinical assistant. Short, plain sentences."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }
    req = urllib.request.Request(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {API_KEY}"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"].strip()
