param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$FreezeFolder = "2026-04-11--FREEZE-20260412-000400Z",
    [string]$CandidateSessionRoot = "session-run-id2-20260411-1400-qpath-tr008-run",
    [string]$CandidatePackageRoot = "QPDS-PACKAGE-ID2_PREP"
)

$resolvedRepoRoot = (Resolve-Path -LiteralPath $RepoRoot).Path
$trainingPackagesRoot = Join-Path $resolvedRepoRoot "path_2_access_mode_canonical\03_dataset\training_packages"

$global:Path2RepoRoot = $resolvedRepoRoot
$global:Path2FreezeRoot = Join-Path $resolvedRepoRoot "path_2_access_mode_canonical\01_source\$FreezeFolder"
$global:Path2BridgeRoot = Join-Path $resolvedRepoRoot "path_2_access_mode_canonical\02_signals\source_bridge\$FreezeFolder"
$global:Path2CandidateLatestRoot = Join-Path $resolvedRepoRoot "path_2_access_mode_canonical\03_dataset\candidates\$CandidateSessionRoot\$CandidatePackageRoot"
$global:Path2RuntimeSignalRoot = Join-Path $resolvedRepoRoot "path_2_access_mode_canonical\02_signals\runtime_generated"
$global:Path2RegistryPath = Join-Path $resolvedRepoRoot "shared\registry\state1_dataset_registry.json"
$global:Path2BackendProfile = Join-Path $resolvedRepoRoot "shared\configs\training_backend_profile.local_lora.json"

Remove-Variable -Scope Global -Name Path2PackageDir -ErrorAction SilentlyContinue
Remove-Variable -Scope Global -Name Path2DatasetVersion -ErrorAction SilentlyContinue
Remove-Variable -Scope Global -Name Path2TrainingPackage -ErrorAction SilentlyContinue

function global:Resolve-Path2LatestPackage {
    param(
        [string]$CandidateLatestRoot = $global:Path2CandidateLatestRoot,
        [string]$TrainingPackagesRoot = $trainingPackagesRoot
    )

    if (-not (Test-Path -LiteralPath $CandidateLatestRoot)) {
        throw "Path 2 candidate latest-root not found: $CandidateLatestRoot"
    }

    $packageDir = Get-ChildItem -LiteralPath $CandidateLatestRoot -Directory |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName

    if (-not $packageDir) {
        throw "No timestamped Path 2 package directories found under: $CandidateLatestRoot"
    }

    $global:Path2PackageDir = $packageDir
    $global:Path2DatasetVersion = Split-Path $packageDir -Leaf
    $global:Path2TrainingPackage = Join-Path $TrainingPackagesRoot $global:Path2DatasetVersion

    [pscustomobject]@{
        Path2PackageDir = $global:Path2PackageDir
        Path2DatasetVersion = $global:Path2DatasetVersion
        Path2TrainingPackage = $global:Path2TrainingPackage
    }
}

[pscustomobject]@{
    Path2RepoRoot = $global:Path2RepoRoot
    Path2FreezeRoot = $global:Path2FreezeRoot
    Path2BridgeRoot = $global:Path2BridgeRoot
    Path2CandidateLatestRoot = $global:Path2CandidateLatestRoot
    Path2RuntimeSignalRoot = $global:Path2RuntimeSignalRoot
    Path2RegistryPath = $global:Path2RegistryPath
    Path2BackendProfile = $global:Path2BackendProfile
    NextStep = "Run Resolve-Path2LatestPackage after step 3A to populate Path2PackageDir, Path2DatasetVersion, and Path2TrainingPackage."
}
