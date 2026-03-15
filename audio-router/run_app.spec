# PyInstaller spec for PipeWire Audio Router
# Build: pyinstaller run_app.spec   (or ./build.sh)

from pathlib import Path

app_dir = Path(SPEC).resolve().parent
src_dir = app_dir / 'src'

a = Analysis(
    [str(app_dir / 'run_app.py')],
    pathex=[str(src_dir)],
    hiddenimports=[
        'audio_router_gui',
        'device_monitor',
        'config_parser',
        'audio_router_engine',
        'intelligent_audio_router',
        'yaml',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='pipewire-audio-router',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No terminal window on Linux
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
