param(
    [switch]$WhatIf,
    [string]$PythonPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$ProjectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $ScriptRoot))
$ExpectedRoot = [System.IO.Path]::GetFullPath("D:\work\gupiao\UZI-Skill")
if (-not $ProjectRoot.Equals($ExpectedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Project root must resolve to $ExpectedRoot; got $ProjectRoot"
}

$CliPath = [System.IO.Path]::GetFullPath(
    (Join-Path $ProjectRoot "skills\deep-analysis\scripts\run_tail_decision.py")
)
if (-not $CliPath.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "CLI path escaped the project root: $CliPath"
}
if (-not (Test-Path -LiteralPath $CliPath -PathType Leaf)) {
    throw "Tail-decision CLI does not exist: $CliPath"
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
}
$PythonPath = [System.IO.Path]::GetFullPath($PythonPath)
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable does not exist: $PythonPath"
}

$DataRoot = [System.IO.Path]::GetFullPath("D:\work\gupiao\data\tushare_calendar")
$StateRoot = [System.IO.Path]::GetFullPath("D:\work\gupiao\data\tail_decision_runtime")
$LogRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $ProjectRoot "reports\tail_decision\scheduler")
)
if (-not $LogRoot.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Scheduler log path escaped the project root: $LogRoot"
}
if (-not $WhatIf) {
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $StateRoot -Force | Out-Null
}

$TaskSpecs = @(
    [pscustomobject]@{ Name = "UZI-Tail-Warmup"; Time = "14:00"; Phase = "warmup" },
    [pscustomobject]@{ Name = "UZI-Tail-Preview-1410"; Time = "14:10"; Phase = "preview" },
    [pscustomobject]@{ Name = "UZI-Tail-Preview-1420"; Time = "14:20"; Phase = "preview" },
    [pscustomobject]@{ Name = "UZI-Tail-Final"; Time = "14:30"; Phase = "final" },
    [pscustomobject]@{ Name = "UZI-Tail-Close"; Time = "15:05"; Phase = "close" },
    [pscustomobject]@{ Name = "UZI-Tail-ExitOpen"; Time = "09:25"; Phase = "exit_open" },
    [pscustomobject]@{ Name = "UZI-Tail-ExitCheck"; Time = "09:35"; Phase = "exit_check" }
)

function ConvertTo-PowerShellLiteral {
    param([Parameter(Mandatory = $true)][string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

$QuotedPython = ConvertTo-PowerShellLiteral $PythonPath
$QuotedCli = ConvertTo-PowerShellLiteral $CliPath
$QuotedDataRoot = ConvertTo-PowerShellLiteral $DataRoot
$QuotedOutputRoot = ConvertTo-PowerShellLiteral $ProjectRoot
$QuotedStateRoot = ConvertTo-PowerShellLiteral $StateRoot
$PowerShellPath = (Get-Command powershell.exe -ErrorAction Stop).Source
$Weekdays = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

foreach ($Spec in $TaskSpecs) {
    $LogPath = Join-Path $LogRoot ($Spec.Name + ".log")
    $QuotedLog = ConvertTo-PowerShellLiteral $LogPath
    $CliArguments = (
        "$QuotedCli --phase $($Spec.Phase) --data-root $QuotedDataRoot " +
        "--output-root $QuotedOutputRoot --state-root $QuotedStateRoot"
    )
    $Invocation = "& $QuotedPython $CliArguments *>> $QuotedLog; exit `$LASTEXITCODE"

    if ($WhatIf) {
        Write-Output (
            "WHATIF $($Spec.Name) $($Spec.Time) $CliPath --phase $($Spec.Phase) " +
            "--state-root $StateRoot"
        )
        continue
    }

    $EscapedInvocation = $Invocation.Replace('"', '`"')
    $ActionArguments = (
        "-NoProfile -NonInteractive -WindowStyle Hidden -Command `"" +
        $EscapedInvocation + "`""
    )
    $Action = New-ScheduledTaskAction `
        -Execute $PowerShellPath `
        -Argument $ActionArguments `
        -WorkingDirectory $ProjectRoot
    $Trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -WeeksInterval 1 `
        -DaysOfWeek $Weekdays `
        -At $Spec.Time
    $Settings = New-ScheduledTaskSettingsSet `
        -Hidden `
        -StartWhenAvailable `
        -MultipleInstances IgnoreNew
    $Principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Limited

    Register-ScheduledTask `
        -TaskName $Spec.Name `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description "UZI self-sustaining tail decision: $($Spec.Phase)" `
        -Force | Out-Null
    Write-Output "INSTALLED $($Spec.Name) $($Spec.Time) --phase $($Spec.Phase)"
}
