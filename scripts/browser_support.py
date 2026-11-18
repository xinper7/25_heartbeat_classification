"""Prefer installed Chrome; otherwise use project Playwright Chromium."""
from pathlib import Path
import os

def launch_chromium(playwright):
 downloads=Path(__file__).resolve().parents[1]/'runtime/qa/browser-downloads'
 downloads.mkdir(parents=True,exist_ok=True)
 options=dict(headless=True,downloads_path=str(downloads))
 if os.getenv('QA_BROWSER')=='chromium':return playwright.chromium.launch(**options)
 for base in (os.getenv('LOCALAPPDATA',''),os.getenv('PROGRAMFILES',''),os.getenv('PROGRAMFILES(X86)','')):
  candidate=Path(base)/'Google/Chrome/Application/chrome.exe'
  if candidate.is_file():return playwright.chromium.launch(executable_path=str(candidate),**options)
 for base in (os.getenv('PROGRAMFILES(X86)',''),os.getenv('PROGRAMFILES','')):
  candidate=Path(base)/'Microsoft/Edge/Application/msedge.exe'
  if candidate.is_file():return playwright.chromium.launch(executable_path=str(candidate),**options)
 return playwright.chromium.launch(**options)
