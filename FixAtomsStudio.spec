# Build with: python -m PyInstaller --noconfirm FixAtomsStudio.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH)
datas = [(str(root / name), '.') for name in ('viewer.html', 'viewer.js', '3Dmol-min.js')]
datas += [(str(root / 'assets'), 'assets'), (str(root / 'examples'), 'examples')]
datas += collect_data_files('ase', includes=['spacegroup/*.dat', 'collections/*.json'])
for package in ('ase', 'numpy', 'scipy', 'PySide6', 'shiboken6'):
    datas += copy_metadata(package)

analysis = Analysis(
    [str(root / 'app.py')], pathex=[str(root)], binaries=[], datas=datas,
    hiddenimports=['ase.io.cif', 'ase.io.vasp', 'ase.io.xsd'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'IPython', 'notebook', 'jupyter', 'pandas',
              'torch', 'PyQt5', 'PyQt6', 'PySide2', 'pytest', '__main__'],
    noarchive=False,
)
# Qt 6.11 calls the unsuffixed ICU API supplied by Windows. Conda's same-named
# icuuc.dll exports version-suffixed symbols and must not shadow the system DLL.
analysis.binaries = [entry for entry in analysis.binaries
                     if Path(entry[0]).name.lower() != 'icuuc.dll'
                     and not (Path(entry[0]).name.lower().startswith('icudt')
                              and Path(entry[0]).suffix.lower() == '.dll')]
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name='FixAtomsStudio',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
    icon=str(root / 'assets' / 'fixatoms.ico'),
)
collection = COLLECT(
    exe, analysis.binaries, analysis.datas, strip=False, upx=False,
    name='FixAtomsStudio',
)
