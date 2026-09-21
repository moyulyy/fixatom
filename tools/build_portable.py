"""Build a self-contained Windows folder and a ZIP for distribution."""
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm',
                    '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build'),
                    str(ROOT / 'FixAtomsStudio.spec')], cwd=ROOT, check=True)
    folder = ROOT / 'dist' / 'FixAtomsStudio'
    shutil.copytree(ROOT / 'examples', folder / 'examples', dirs_exist_ok=True)
    shutil.copy2(ROOT / 'assets' / 'fixatoms.ico', folder / 'fixatoms.ico')
    shutil.copy2(ROOT / 'PORTABLE_README.txt', folder / '使用说明.txt')
    shutil.copy2(ROOT / 'README.md', folder / '开发版说明.md')
    archive = ROOT / 'dist' / 'FixAtomsStudio-Windows-x64-portable.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                output.write(path, path.relative_to(folder.parent))
    print(f'Portable EXE: {folder / "FixAtomsStudio.exe"}')
    print(f'Portable ZIP: {archive}')


if __name__ == '__main__':
    main()
