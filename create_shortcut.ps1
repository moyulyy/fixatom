param([string]$PythonPath = 'D:\miniconda3\envs\chem_env\pythonw.exe')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python executable not found: $PythonPath"
}
$fixAtomsRoot = $PSScriptRoot
$fixAtomsShell = New-Object -ComObject WScript.Shell
$fixAtomsShortcut = $fixAtomsShell.CreateShortcut((Join-Path $fixAtomsRoot 'FixAtoms Studio.lnk'))
$fixAtomsShortcut.TargetPath = $PythonPath
$fixAtomsShortcut.Arguments = '"' + (Join-Path $fixAtomsRoot 'app.py') + '"'
$fixAtomsShortcut.WorkingDirectory = $fixAtomsRoot
$fixAtomsShortcut.IconLocation = (Join-Path $fixAtomsRoot 'assets\fixatoms.ico') + ',0'
$fixAtomsShortcut.Description = 'FixAtoms Studio - local atom structure editor'
$fixAtomsShortcut.Save()
Write-Output "Created shortcut: $(Join-Path $fixAtomsRoot 'FixAtoms Studio.lnk')"
