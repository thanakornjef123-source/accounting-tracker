"""Visual theme: deep purple with an orange accent, in the style of a retail-bank app.

Colours come from .streamlit/config.toml (Streamlit's own theme) plus the CSS
below for the parts the config cannot reach: cards, tabs, buttons, fonts.
"""

from __future__ import annotations

import streamlit as st

PURPLE = "#4E2E7F"
PURPLE_DEEP = "#3A2160"
PURPLE_MID = "#9C7BD0"
PURPLE_SOFT = "#CBB9E6"
PURPLE_TINT = "#ECE6F5"
ORANGE = "#F58220"
INK = "#1E1830"
MUTED = "#6B6580"
LINE = "#E4DCF0"
BG = "#F6F4FA"

# Task stages, light to dark. Review is orange because that is where work waits for the owner.
STATUS_COLORS = {
    "todo": PURPLE_SOFT,
    "doing": PURPLE_MID,
    "review": ORANGE,
    "approved": PURPLE,
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap');

html, body, .stApp, .stApp p, .stApp label, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button, .stApp input, .stApp textarea,
[data-testid="stMetricLabel"], [data-testid="stMetricValue"], [data-testid="stMetricDelta"] {{
  font-family: "IBM Plex Sans Thai", "Noto Sans Thai", "Leelawadee UI", Tahoma, sans-serif;
}}

.stApp {{ background: {BG}; color: {INK}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.4rem; padding-bottom: 4rem; max-width: 1280px; }}

/* Headings */
.stApp h1 {{ color: {PURPLE}; font-weight: 700; letter-spacing: -0.01em; }}
.stApp h2, .stApp h3 {{ color: {PURPLE_DEEP}; font-weight: 600; }}
.stApp h5 {{ color: {PURPLE_DEEP}; font-weight: 600; }}
[data-testid="stCaptionContainer"] {{ color: {MUTED}; }}

/* Metric cards */
[data-testid="stMetric"] {{
  background: #FFFFFF; border: 1px solid {LINE}; border-radius: 16px;
  padding: 16px 18px; box-shadow: 0 1px 2px rgba(78, 46, 127, 0.07);
}}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.85rem; font-weight: 500; }}
[data-testid="stMetricValue"] {{ color: {PURPLE}; font-weight: 700; font-size: 1.9rem; }}
[data-testid="stMetricDelta"] {{ color: {MUTED}; }}

/* Buttons */
[data-testid^="stBaseButton-"] {{
  border-radius: 12px; font-weight: 600; transition: box-shadow .15s ease, background-color .15s ease;
}}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {PURPLE}; border-color: {PURPLE}; color: #FFFFFF;
}}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: {PURPLE_DEEP}; border-color: {PURPLE_DEEP}; box-shadow: 0 4px 12px rgba(78, 46, 127, 0.28);
}}
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-secondaryFormSubmit"] {{
  background: #FFFFFF; color: {PURPLE}; border: 1px solid {PURPLE_SOFT};
}}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover {{
  border-color: {PURPLE}; color: {PURPLE_DEEP}; background: {PURPLE_TINT};
}}
[data-testid^="stBaseButton-"]:focus-visible {{ outline: 3px solid {ORANGE}; outline-offset: 2px; }}

/* Tabs */
button[data-baseweb="tab"] {{ font-weight: 600; color: {MUTED}; }}
button[data-baseweb="tab"][aria-selected="true"] {{ color: {PURPLE}; }}
[data-baseweb="tab-highlight"] {{ background-color: {PURPLE}; height: 3px; border-radius: 3px; }}
[data-baseweb="tab-border"] {{ background-color: {LINE}; }}

/* Tables, bordered containers, expanders, alerts */
[data-testid="stDataFrame"] {{
  border: 1px solid {LINE}; border-radius: 14px; overflow: hidden; background: #FFFFFF;
}}
[data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"] [data-testid="stBaseButton-primary"]) {{
  border-color: {LINE}; border-radius: 16px; background: #FFFFFF;
}}
[data-testid="stExpander"] details {{ border: 1px solid {LINE}; border-radius: 14px; background: #FFFFFF; }}
[data-testid="stAlert"] {{ border-radius: 14px; }}
hr {{ border-color: {LINE}; }}

/* Inputs */
[data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-baseweb="textarea"] {{
  border-radius: 12px; border-color: {LINE};
}}
[data-baseweb="select"] > div:focus-within, [data-baseweb="input"] > div:focus-within,
[data-baseweb="textarea"]:focus-within {{ border-color: {PURPLE}; box-shadow: 0 0 0 1px {PURPLE}; }}

/* Sidebar */
[data-testid="stSidebar"] {{ border-right: 0; }}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {{ color: #CDBFE6; }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: #FFFFFF; }}
[data-testid="stSidebarNavSeparator"] {{ display: none; }}
[data-testid="stSidebarNavLink"] {{ border-radius: 12px; font-weight: 500; }}
[data-testid="stSidebarNavLink"][aria-current="page"] {{
  background: rgba(255, 255, 255, 0.16); font-weight: 600; box-shadow: inset 3px 0 0 {ORANGE};
}}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{
  background: rgba(255, 255, 255, 0.08); border-color: rgba(255, 255, 255, 0.18);
}}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {{
  background: rgba(255, 255, 255, 0.10); color: #FFFFFF; border-color: rgba(255, 255, 255, 0.28);
}}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {{
  background: rgba(255, 255, 255, 0.22); border-color: #FFFFFF; color: #FFFFFF;
}}
</style>
"""


def inject() -> None:
    """Add the brand logo and CSS. Call once per run, before any page content."""
    try:
        st.logo("assets/logo.svg", icon_image="assets/mark.svg", size="large")
    except Exception:  # an older Streamlit or a missing asset must not break the app
        pass
    st.markdown(CSS, unsafe_allow_html=True)
