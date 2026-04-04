# PyInstaller spec for SinkSwitch
# Onefile:  pyinstaller run_app.spec   (or ./build.sh)
# Onedir:   SINKSWITCH_ONEDIR=1 pyinstaller run_app.spec   (or ./build.sh --onedir)

import os
from pathlib import Path

app_dir = Path(SPEC).resolve().parent
src_dir = app_dir / 'src'
onedir = os.environ.get("SINKSWITCH_ONEDIR", "").lower() in ("1", "true", "yes")

# Ensure certifi's CA bundle is in the bundle (SSL verify in frozen app)
_certifi_datas = []
try:
    import certifi
    _certifi_datas = [(certifi.where(), 'certifi')]
except Exception:
    pass

_brand_icon = []
_p = app_dir / 'data' / 'icons' / 'io.github.crashman79.sinkswitch.png'
if _p.is_file():
    _brand_icon = [(str(_p), 'data/icons')]

a = Analysis(
    [str(app_dir / 'run_app.py')],
    pathex=[str(src_dir)],
    hiddenimports=[
        'host_command',
        'audio_router_gui',
        'device_monitor',
        'config_parser',
        'audio_router_engine',
        'intelligent_audio_router',
        'portal_background',
        'yaml',
        'certifi',
    ],
    datas=_certifi_datas + _brand_icon,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# On Linux, PyInstaller pulls libxkbcommon from the PyQt wheel. Using that copy with the
# system's X11 session and libQt6XcbQpa often crashes (SIGSEGV in xkb_state_* / Qt6XcbQpa).
# Force the distro's libxkbcommon (matches compositor / keymaps / ABI).
_libs_use_from_os = (
    'libxkbcommon.so',
    'libxkbcommon-x11.so',
)
a.binaries = [
    t for t in a.binaries
    if not t[0] or not any(s in t[0] for s in _libs_use_from_os)
]

pyz = PYZ(a.pure)

_exe_kw = dict(
    name='sinkswitch',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not onedir,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if onedir:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        upx_exclude=[],
        **_exe_kw,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='sinkswitch',
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        runtime_tmpdir=None,
        upx_exclude=[],
        **_exe_kw,
    )
