param(
    [switch]$WhatIf
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
$StateRoot = [System.IO.Path]::GetFullPath("D:\work\gupiao\data\tail_decision_runtime")
$LogRoot = [System.IO.Path]::GetFullPath(
    (Join-Path $ProjectRoot "reports\tail_decision\scheduler")
)
$TaskSpecs = @(
    [pscustomobject]@{ Name = "UZI-Tail-Warmup"; Time = "14:00"; Phase = "warmup" },
    [pscustomobject]@{ Name = "UZI-Tail-Preview-1410"; Time = "14:10"; Phase = "preview" },
    [pscustomobject]@{ Name = "UZI-Tail-Preview-1420"; Time = "14:20"; Phase = "preview" },
    [pscustomobject]@{ Name = "UZI-Tail-Final"; Time = "14:30"; Phase = "final" },
    [pscustomobject]@{ Name = "UZI-Tail-Close"; Time = "15:05"; Phase = "close" },
    [pscustomobject]@{ Name = "UZI-Tail-ExitOpen"; Time = "09:25"; Phase = "exit_open" },
    [pscustomobject]@{ Name = "UZI-Tail-ExitCheck"; Time = "09:35"; Phase = "exit_check" }
)

if ($WhatIf) {
    foreach ($Spec in $TaskSpecs) {
        Write-Output "CHECKSPEC $($Spec.Name) $($Spec.Time) --phase $($Spec.Phase)"
    }
    exit 0
}

$Failures = [System.Collections.Generic.List[string]]::new()
$AllowedTaskResults = @(0, 267011) # 0x41303: task has not yet run
foreach ($Spec in $TaskSpecs) {
    $Task = Get-ScheduledTask -TaskName $Spec.Name -ErrorAction SilentlyContinue
    if ($null -eq $Task) {
        $Failures.Add("missing_task:$($Spec.Name)")
        continue
    }
    $Action = @($Task.Actions)[0]
    $Arguments = [string]$Action.Arguments
    if (-not $Arguments.Contains($CliPath)) {
        $Failures.Add("wrong_cli:$($Spec.Name)")
    }
    if (-not $Arguments.Contains("--phase $($Spec.Phase)")) {
        $Failures.Add("wrong_phase:$($Spec.Name)")
    }
    if (-not $Arguments.Contains("--state-root") -or -not $Arguments.Contains($StateRoot)) {
        $Failures.Add("wrong_state_root:$($Spec.Name)")
    }
    $Trigger = @($Task.Triggers)[0]
    $ActualTime = ([datetime]$Trigger.StartBoundary).ToString("HH:mm")
    if ($ActualTime -ne $Spec.Time) {
        $Failures.Add("wrong_trigger:$($Spec.Name):$ActualTime")
    }
    $Info = Get-ScheduledTaskInfo -TaskName $Spec.Name
    if (
        $Info.LastRunTime -gt [datetime]::MinValue -and
        $Info.LastTaskResult -notin $AllowedTaskResults
    ) {
        $Failures.Add("last_result:$($Spec.Name):$($Info.LastTaskResult)")
    }
    $LogPath = Join-Path $LogRoot ($Spec.Name + ".log")
    if (Test-Path -LiteralPath $LogPath -PathType Leaf) {
        $Tail = (Get-Content -LiteralPath $LogPath -Tail 40) -join "`n"
        if ($Tail -match "Traceback \(most recent call last\)" -or $Tail -match "unhandled exception") {
            $Failures.Add("unreported_log_failure:$($Spec.Name)")
        }
    }
}

if ($Failures.Count -gt 0) {
    $Failures | ForEach-Object { Write-Error $_ }
    exit 1
}

$TaskSpecs | ForEach-Object { Write-Output "CHECKED $($_.Name) $($_.Time)" }
exit 0
