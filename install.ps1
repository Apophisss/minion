# Minion installer for Windows: https://github.com/apophisss/minion
#
#   irm https://raw.githubusercontent.com/apophisss/minion/main/install.ps1 | iex
#
# It installs uv (https://docs.astral.sh/uv/) if it is missing, installs the `minion` command with
# `uv tool install`, then runs `minion setup`. It needs no admin rights and is safe to run again.
# Windows PowerShell 5.1 or PowerShell 7.
#
#   $env:MINION_SPEC = 'git+https://github.com/apophisss/minion@main'   what to install (default: minion-desktop)
#   $env:MINION_NO_SETUP = '1'                                          install only, don't run `minion setup`
#   $env:MINION_SETUP_ARGS = '--yes --profiles office'                  arguments for `minion setup`

# `irm | iex` runs this text in your own PowerShell session. So everything happens inside a script block:
# no variables leak into your session, and nothing here closes it (there is no `exit`).
& {
    # A session set to stop on errors would stop here at uv's first note on stderr ("No tools installed"):
    # Windows PowerShell 5.1 turns redirected stderr into errors. The installer checks exit codes instead.
    $ErrorActionPreference = 'Continue'
    function Say([string]$Text) { Write-Host "==> $Text" -ForegroundColor Magenta }
    function Warn([string]$Text) { Write-Host "Warning: $Text" -ForegroundColor Yellow }
    function Fail([string]$Text) { Write-Host "Error: $Text" -ForegroundColor Red }

    # Windows PowerShell 5.1 may not offer TLS 1.2 by default, which astral.sh and GitHub need.
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch { Write-Verbose "TLS 1.2 is not configurable here: $_" }

    $spec = if ($env:MINION_SPEC) { $env:MINION_SPEC } else { 'minion-desktop' }
    $fallback = 'git+https://github.com/apophisss/minion'

    function Find-Uv {
        $cmd = Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd) { return $cmd.Source }
        foreach ($dir in @($env:UV_INSTALL_DIR, $env:XDG_BIN_HOME, (Join-Path $HOME '.local\bin'), (Join-Path $HOME '.cargo\bin'))) {
            if ($dir -and (Test-Path -LiteralPath (Join-Path $dir 'uv.exe'))) { return (Join-Path $dir 'uv.exe') }
        }
        return $null
    }

    # 1. uv, which installs Minion and the Python it needs into a folder of their own.
    $uv = Find-Uv
    if ($uv) {
        Say "Using uv: $uv"
    } else {
        Say 'Installing uv, the Python package manager Minion installs with (https://docs.astral.sh/uv/)'
        $shell = (Get-Process -Id $PID).Path  # powershell.exe or pwsh.exe: Astral's own install command
        & $shell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        $uv = Find-Uv
        if (-not $uv) {
            Fail 'uv did not install. See https://docs.astral.sh/uv/getting-started/installation/'
            return
        }
    }

    # 2. Minion. Its commands go into uv's tool folder, usually %USERPROFILE%\.local\bin.
    $bin = & $uv tool dir --bin | Select-Object -First 1
    if (-not $bin) { $bin = Join-Path $HOME '.local\bin' }
    $minion = Join-Path $bin 'minion.exe'
    $force = @()
    $managed = & $uv tool list 2>$null | Select-String -Pattern '^minion-desktop ' -Quiet
    if ((Test-Path -LiteralPath $minion) -and -not $managed) {
        if (Select-String -LiteralPath $minion -Pattern 'minion.cli' -SimpleMatch -Quiet) {
            $force = @('--force')  # Minion installed another way (pipx, pip): uv takes its command over
        } else {
            Fail "$minion is another program. Move it out of the way and run this again."
            return
        }
    }
    Say "Installing Minion ($spec)"
    & $uv tool install --upgrade @force $spec
    if ($LASTEXITCODE -ne 0) {
        if ($spec -ne 'minion-desktop') {
            Fail "Installing $spec failed (see above)."
            return
        }
        Warn 'minion-desktop could not be installed from PyPI; installing it from GitHub instead.'
        & $uv tool install --upgrade @force $fallback
        if ($LASTEXITCODE -ne 0) {
            Fail 'Installing Minion failed (see above).'
            return
        }
    }

    # 3. `minion` on PATH: in this window now, and through uv in your user PATH for new windows.
    $newPath = $false
    if (-not (($env:Path -split [IO.Path]::PathSeparator) -contains $bin)) {
        $env:Path = $bin + [IO.Path]::PathSeparator + $env:Path
        & $uv tool update-shell *> $null
        $newPath = $true
    }

    # 4. The first-run wizard.
    if ($env:MINION_NO_SETUP) {
        Say "Minion is installed. Run 'minion setup' when you're ready."
    } else {
        $setupArgs = @()
        if ($env:MINION_SETUP_ARGS) { $setupArgs = @($env:MINION_SETUP_ARGS -split '\s+' | Where-Object { $_ }) }
        & $minion setup @setupArgs
        if ($LASTEXITCODE -ne 0) {
            Warn "Minion is installed, but setup isn't finished. Run 'minion setup' again once the problem above is fixed."
        }
    }
    if ($newPath) { Say "This window can use 'minion' now; new windows can too once they open." }
}
