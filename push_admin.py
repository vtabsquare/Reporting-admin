#!/usr/bin/env python3
"""
Push script for VTAB-Admin-Console.
Invokes root push_to_github.py for 'admin' app.
"""
import sys
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
push_script = ROOT_DIR / "push_to_github.py"

if not push_script.is_file():
    print(f"Error: Could not locate push_to_github.py at {push_script}")
    sys.exit(1)

cmd = [sys.executable, str(push_script), "--app", "admin"] + sys.argv[1:]
sys.exit(subprocess.call(cmd))
