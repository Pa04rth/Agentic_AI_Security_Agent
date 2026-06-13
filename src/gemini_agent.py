"""
DEPRECATED — the AI core was switched from Gemini to the Claude API.
This shim only exists so any stray import keeps working. Use claude_agent.py.
"""

from claude_agent import ClaudeAgent as GeminiAgent  # noqa: F401
