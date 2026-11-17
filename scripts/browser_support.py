"""Prefer installed Chrome; otherwise use project Playwright Chromium."""
from pathlib import Path
import os

def launch_chromium(playwright):
 for base in (os.getenv('LOCALAPPDATA',''),os.getenv('PROGRAMFILES',''),os.getenv('PROGRAMFILES(X86)','')):
  candidate=Path(base)/'Google/Chrome/Application/chrome.exe'
  if candidate.is_file():return playwright.chromium.launch(executable_path=str(candidate),headless=True)
 for base in (os.getenv('PROGRAMFILES(X86)',''),os.getenv('PROGRAMFILES','')):
  candidate=Path(base)/'Microsoft/Edge/Application/msedge.exe'
  if candidate.is_file():return playwright.chromium.launch(executable_path=str(candidate),headless=True)
 return playwright.chromium.launch(headless=True)
