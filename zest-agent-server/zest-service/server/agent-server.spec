# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Zest Agent Server with PEP 420 (implicit namespace) layout.
"""

from pathlib import Path
import os
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    copy_metadata,
)

# Get the project root directory (current working directory when running PyInstaller)
project_root = Path.cwd()
# Namespace roots must be in pathex so PyInstaller can find 'Zest/...'
PATHEX = [
    project_root / "Zest-agent-server",
    project_root / "Zest-sdk",
    project_root / "Zest-tools",
    project_root / "Zest-workspace",
]

# Entry script for the agent server package (namespace: Zest/agent_server/__main__.py)
ENTRY = str(project_root / "Zest-agent-server" / "Zest" / "agent_server" / "__main__.py")

a = Analysis(
    [ENTRY],
    pathex=PATHEX,
    binaries=[],
    datas=[
        # Third-party packages that ship data
        *collect_data_files("tiktoken"),
        *collect_data_files("tiktoken_ext"),
        *collect_data_files("litellm"),
        *collect_data_files("fastmcp"),
        *collect_data_files("mcp"),

        # Zest SDK prompt templates (adjusted for shallow namespace layout)
        *collect_data_files("sdk.agent", includes=["prompts/*.j2"]),
        *collect_data_files("sdk.context.condenser", includes=["prompts/*.j2"]),
        *collect_data_files("sdk.context.prompts", includes=["templates/*.j2"]),

        # Package metadata for importlib.metadata
        *copy_metadata("fastmcp"),
        *copy_metadata("litellm"),
    ],
    hiddenimports=[
        # Pull all Zest modules from the namespace (PEP 420 safe once pathex is correct)
        *collect_submodules("sdk"),
        *collect_submodules("tools"),
        *collect_submodules("Zest.workspace"),
        *collect_submodules("server"),

        # Third-party dynamic imports
        *collect_submodules("tiktoken"),
        *collect_submodules("tiktoken_ext"),
        *collect_submodules("litellm"),
        *collect_submodules("fastmcp"),

        # mcp subpackages used at runtime (avoid CLI)
        "mcp.types",
        "mcp.client",
        "mcp.server",
        "mcp.shared",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim size
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
        # Exclude mcp CLI parts that pull in typer/extra deps
        "mcp.cli",
        "mcp.cli.cli",
    ],
    noarchive=False,
    # IMPORTANT: don't use optimize=2 (-OO); it strips docstrings needed by parsers (e.g., PLY/bashlex)
    optimize=0,
)

# Remove problematic system libraries that should use host versions
# This prevents bundling incompatible libgcc_s.so.1 that lacks GCC_14.0 symbols
a.binaries = [x for x in a.binaries if not x[0].startswith('libgcc_s.so')]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Zest-agent-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
