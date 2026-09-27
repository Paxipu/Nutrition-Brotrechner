<#
.SYNOPSIS
    Baut das Windows-Programmpaket und prüft es so, wie ein Anwender es startet.

.DESCRIPTION
    PyInstaller baut den Ordner dist\Brotrechner mit Brotrechner.exe (die
    Oberfläche) und brotrechner-cli.exe (die Kommandozeile). Geprüft wird
    danach das fertige Paket, nicht der Quelltext:

    1. Die Kommandozeile zeigt Version und Bestand, prüft die Startdatenbank
       und schreibt im Selbsttest ein Etikett und einen PDF-Bericht. Fehlt im
       Paket eine Schrift, die PDF-Bibliothek oder die Startdatenbank,
       scheitert es hier.
    2. Das Qt-Plugin für Windows-Fenster liegt im Paket. Die Oberfläche
       startet unten ohne Bildschirm und bräuchte es dafür nicht.
    3. Die Oberfläche startet und meldet im Protokoll "Hauptfenster bereit".
       Ein Startfehler öffnet einen Dialog und hält das Programm am Leben -
       es zählt deshalb der Protokolleintrag, nicht, ob der Prozess noch läuft.

    Dasselbe Skript baut das Paket in der CI und für ein Release. Unter Linux
    läuft es ebenfalls, dort nur zum Ausprobieren.

.PARAMETER Python
    Der Python-Interpreter, mit dem gebaut wird. Er braucht das Projekt mit
    PDF-Unterstützung und PyInstaller:
    pip install ".[pdf]" -r packaging\requirements.txt

.PARAMETER SkipBuild
    Nicht bauen, nur das vorhandene Paket in dist\Brotrechner prüfen.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#>
[CmdletBinding()]
param(
    [string] $Python = "python",
    [switch] $SkipBuild
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$onWindows = $env:OS -eq "Windows_NT"
$suffix = if ($onWindows) { ".exe" } else { "" }
$root = Split-Path -Parent $PSScriptRoot
$package = Join-Path (Join-Path $root "dist") "Brotrechner"
$cli = Join-Path $package "brotrechner-cli$suffix"
$gui = Join-Path $package "Brotrechner$suffix"

function Invoke-Program {
    # Führt ein Programm aus und bricht ab, wenn es mit einem Fehlercode endet.
    param([string] $Program, [string[]] $Arguments)
    Write-Host "> $Program $($Arguments -join ' ')"
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program endete mit Code $LASTEXITCODE."
    }
}

function Read-Log {
    # Liest das Protokoll, während das Programm noch hineinschreibt.
    param([string] $Path)
    if (-not (Test-Path $Path)) {
        return ""
    }
    $stream = [System.IO.File]::Open(
        $Path,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::ReadWrite
    )
    try {
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        return $reader.ReadToEnd()
    }
    finally {
        $stream.Dispose()
    }
}

function Test-Interface {
    # Startet die Oberfläche ohne Bildschirm und wartet auf "Hauptfenster bereit".
    param([string] $Program, [string] $DataDir, [int] $TimeoutSeconds = 120)
    $log = Join-Path $DataDir "brotrechner.log"
    $saved = @{
        QT_QPA_PLATFORM = $env:QT_QPA_PLATFORM
        BROTRECHNER_DATA_DIR = $env:BROTRECHNER_DATA_DIR
    }
    $env:QT_QPA_PLATFORM = "offscreen"
    $env:BROTRECHNER_DATA_DIR = $DataDir
    try {
        $process = Start-Process -FilePath $Program -PassThru
    }
    finally {
        $env:QT_QPA_PLATFORM = $saved.QT_QPA_PLATFORM
        $env:BROTRECHNER_DATA_DIR = $saved.BROTRECHNER_DATA_DIR
    }
    try {
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while ($true) {
            $text = Read-Log $log
            if ($text -match "Start fehlgeschlagen") {
                throw "Die Oberfläche konnte nicht starten:`n$text"
            }
            if ($text -match "Hauptfenster bereit") {
                break
            }
            if ($process.HasExited) {
                throw "Die Oberfläche hat sich beim Start beendet (Code $($process.ExitCode)).`n$text"
            }
            if ((Get-Date) -gt $deadline) {
                throw "Nach $TimeoutSeconds Sekunden stand nicht 'Hauptfenster bereit' im Protokoll.`n$text"
            }
            Start-Sleep -Milliseconds 500
        }
        # Das Fenster steht. Kurz danach darf es auch nicht abstürzen.
        Start-Sleep -Seconds 3
        if ($process.HasExited) {
            throw "Die Oberfläche hat sich nach dem Start beendet (Code $($process.ExitCode))."
        }
        Write-Host (Read-Log $log)
    }
    finally {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
        }
    }
}

Push-Location $root
try {
    if (-not $SkipBuild) {
        $spec = Join-Path "packaging" "brotrechner.spec"
        Invoke-Program $Python @("-m", "PyInstaller", $spec, "--noconfirm", "--clean")
    }
    foreach ($program in @($cli, $gui)) {
        if (-not (Test-Path $program)) {
            throw "Im Paket fehlt $program."
        }
    }

    # Scheitert eine Prüfung, bleibt dieser Ordner zur Untersuchung liegen.
    $work = Join-Path ([System.IO.Path]::GetTempPath()) ("brotrechner-pruefung-" + [guid]::NewGuid().ToString("N"))
    Write-Host "Prüfordner: $work"
    $data = Join-Path $work "daten"
    $selftest = Join-Path $work "selbsttest"

    Invoke-Program $cli @("--version")
    Invoke-Program $cli @("--data-dir", $data, "info")
    Invoke-Program $cli @("--data-dir", $data, "check")
    Invoke-Program $cli @("--data-dir", $data, "selftest", "--output", $selftest)
    # Ohne PDF-Bibliothek überspringt der Selbsttest den Bericht und endet
    # trotzdem mit 0. Im Paket muss sie aber enthalten sein.
    foreach ($name in @("etikett.png", "bericht.pdf")) {
        if (-not (Test-Path (Join-Path $selftest $name))) {
            throw "Der Selbsttest hat $name nicht geschrieben."
        }
    }

    $plugin = if ($onWindows) { "qwindows.dll" } else { "libqxcb.so" }
    if (-not (Get-ChildItem -Path $package -Recurse -Filter $plugin)) {
        throw "Im Paket fehlt das Qt-Plugin $plugin - die Oberfläche könnte kein Fenster öffnen."
    }

    Test-Interface -Program $gui -DataDir (Join-Path $work "oberflaeche")

    Remove-Item -Recurse -Force $work
    Write-Host "Paket gebaut und geprüft: $package"
}
finally {
    Pop-Location
}
