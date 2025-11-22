#!/usr/bin/env python3
"""
Wrapper script to run audio_router with proper Python path
"""

import sys
import os
import subprocess

# Add venv site-packages to path
venv_path = os.path.expanduser("~/.config/pipewire-router/venv")
site_packages = os.path.join(venv_path, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages")

if site_packages not in sys.path:
    sys.path.insert(0, site_packages)

# Import and run the main router
router_dir = os.path.join(venv_path, "..", "src")
sys.path.insert(0, router_dir)

from audio_router import main

if __name__ == '__main__':
    sys.exit(main())
