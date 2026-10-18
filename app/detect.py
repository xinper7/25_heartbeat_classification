"""Alternate entry point for digital 12-lead data inspection."""

import streamlit as st

from page_modules.page_ptbxl import render


st.set_page_config(page_title="PTB-XL 12 导联数据查看", page_icon="❤️", layout="wide")
render()
