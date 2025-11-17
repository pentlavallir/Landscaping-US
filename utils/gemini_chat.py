
import os
from typing import Optional

def get_gemini_answer(prompt: str, context: Optional[str] = None) -> str:
    """Return an answer from Gemini if configured; otherwise a friendly placeholder.

    Looks for GEMINI_API_KEY in:
    1. st.secrets (if Streamlit and secrets configured)
    2. environment variable GEMINI_API_KEY

    If google-generativeai isn't installed or no key is present,
    returns a simple echo-style response instead of raising.
    """
    api_key = None

    # Try Streamlit secrets if available
    try:
        import streamlit as st  # type: ignore
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

    # Fallback to environment variable
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return (
            "Gemini API key is not configured yet.\n\n"
            "To enable AI responses, set GEMINI_API_KEY in `.streamlit/secrets.toml` or "
            "as an environment variable, then reload the app.\n\n"
            f"(Your question was: '{prompt[:200]}...')"
        )

    # Try calling Gemini, but fail gracefully if library is missing
    try:
        import google.generativeai as genai  # type: ignore

        genai.configure(api_key=api_key)

        # Use a lightweight model for Q&A
        model = genai.GenerativeModel("gemini-pro")

        full_prompt = prompt
        if context:
            full_prompt = f"Context: {context}\n\nQuestion: {prompt}"

        resp = model.generate_content(full_prompt)
        if hasattr(resp, "text") and resp.text:
            return resp.text.strip()
        else:
            return "Gemini did not return any text. Please try rephrasing your question."
    except Exception as e:
        return (
            "Gemini call failed (perhaps the library is not installed or the key is invalid). "
            "Please check configuration.\n\n"
            f"Details: {e}"
        )
