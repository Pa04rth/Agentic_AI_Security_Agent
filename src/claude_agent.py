"""
claude_agent.py
---------------
The Executive Summary engine, powered by Google Gemini (google-genai SDK).
Sends a paper abstract to Gemini and gets back a tight, 3-sentence "CTO
takeaway". Only abstracts of CURRENTLY selected papers are ever sent — we never
replay historical records — keeping token usage (and cost) minimal.

Set GEMINI_API_KEY in .env (get one at https://aistudio.google.com/apikey).
Pick any Gemini model via GEMINI_MODEL (default: gemini-2.0-flash, fast + cheap).
The class keeps its historical name (ClaudeAgent) so the rest of the pipeline
needs no changes.
"""

import os

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover
    genai = None
    types = None

# Persona + instruction (the PRD's exact directive) used as the system prompt.
CTO_SYSTEM = (
    "You are an Elite Enterprise AI Security CTO. Read the following foundational "
    "technical abstract. Translate the mathematics and architectural specifications "
    "into exactly 3 sentences focusing heavily on engineering impact, structural "
    "vulnerabilities, or technical paradigm shifts. Avoid fluff, filler text, or "
    "introductory remarks."
)


class ClaudeAgent:
    def __init__(self, api_key=None, model_name=None):
        # Accept GEMINI_API_KEY (preferred) or the generic GOOGLE_API_KEY.
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        # gemini-2.0-flash is fast + cheap and ideal for short summaries.
        # Override with GEMINI_MODEL (e.g. gemini-2.5-pro) for max quality.
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self._client = None
        if genai and self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    @property
    def enabled(self):
        return self._client is not None

    def summarize(self, abstract):
        """Return a 3-sentence CTO takeaway, or a graceful fallback string."""
        if not abstract or not abstract.strip():
            return "(No abstract available to summarize.)"
        if not self.enabled:
            return "(LLM disabled — set GEMINI_API_KEY to enable CTO takeaways.)"
        try:
            resp = self._client.models.generate_content(
                model=self.model_name,
                contents=abstract.strip(),
                config=types.GenerateContentConfig(
                    system_instruction=CTO_SYSTEM,
                    max_output_tokens=300,
                ),
            )
            text = (resp.text or "").strip()
            return text or "(LLM returned no text.)"
        except Exception as e:
            return f"(LLM error: {e})"

    def summarize_batch(self, papers):
        """
        Attach a 'cto_takeaway' to each paper dict in-place. Returns the list.
        Iterates one-by-one so a single bad abstract can't poison the batch.
        """
        for p in papers:
            p["cto_takeaway"] = self.summarize(p.get("abstract", ""))
        return papers
