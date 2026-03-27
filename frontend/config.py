import streamlit as st
import os

def get_api_base():
    """
    Returns the backend API base URL.
    Checks Streamlit secrets first (for Cloud deployment),
    then environment variables, falling back to localhost.
    """
    try:
        # Streamlit Cloud deployment
        return st.secrets["BACKEND_URL"]
    except Exception:
        # Local or Render deployment
        return os.getenv("BACKEND_URL", os.getenv("API_BASE", "http://127.0.0.1:8000"))

API_BASE = get_api_base()
