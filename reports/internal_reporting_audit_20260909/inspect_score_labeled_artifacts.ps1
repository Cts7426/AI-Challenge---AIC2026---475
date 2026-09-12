# Chỉ đọc các ZIP do người dùng gắn điểm; không dùng tên file để suy autonomous.
$ErrorActionPreference = 'Stop'
$null = . (Join-Path $PSScriptRoot 'inspect_artifacts.ps1')
$scoreInputs = @(
    @{round=1;score=8.6;role='final_user_confirmed';name='Thanh Nghệ_round1 (8,6).zip'},
    @{round=1;score=6.8;role='replay_candidate_user_confirmed';name='THANH_NGHỆ_round1 (6,8).zip'},
    @{round=2;score=4.4;role='replay_candidate_user_confirmed';name='Thanh_Nghệ_round2 (4,4).zip'},
    @{round=3;score=11.4;role='intermediate_user_confirmed';name='THANH_NGHE_round3 (11,4).zip'},
    @{round=3;score=11.8;role='final_user_confirmed';name='THANH_NGHE_round3_v4 (11,8).zip'},
    @{round=2;score=13.6;role='final_user_confirmed';name='submission_THANH_ NGHỆ (13,6).zip'},
    @{round=3;score=11.2;role='replay_candidate_user_confirmed';name='THANH_NGHE_submit2_round3 (11,2).zip'}
)
$scoredZips = @()
$scoreInventory = @()
foreach ($scoreInput in $scoreInputs) {
    $scorePath = Join-Path 'C:/Users/lehon/Downloads' $scoreInput.name
    $scoredZip = Read-AuditZip $scorePath
    $scoredZips += $scoredZip
    $scoreFile = Get-Item -LiteralPath $scorePath
    $archive = [System.IO.Compression.ZipFile]::OpenRead($scorePath)
    try {
        $entryInfo = @($archive.Entries | ForEach-Object {
            @{name=$_.FullName;bytes=$_.Length;zip_time=$_.LastWriteTime.ToString('o')}
        })
    } finally { $archive.Dispose() }
    $exactMatches = @($zips | Where-Object {$_.sha256 -eq $scoredZip.sha256} | ForEach-Object {$_.path})
    $contentMatches = @()
    foreach ($existingZip in $zips) {
        $comparison = Compare-AuditZip $existingZip $scoredZip
        if (@($comparison.queries | Where-Object {$_.difference -ne 'same_ordered_rows'}).Count -eq 0) {
            $contentMatches += $existingZip.path
        }
    }
    $scoreInventory += @{
        round=$scoreInput.round; score=$scoreInput.score; role=$scoreInput.role
        path=$scorePath; sha256=$scoredZip.sha256; bytes=$scoreFile.Length
        score_evidence='user supplied filename-to-score mapping; no BTC receipt in ZIP'
        created_utc=$scoreFile.CreationTimeUtc.ToString('o');modified_utc=$scoreFile.LastWriteTimeUtc.ToString('o')
        csv_count=$scoredZip.csv_count;zip_dates=$scoredZip.zip_dates;entries=$entryInfo
        byte_identical_baseline_paths=$exactMatches;normalized_csv_identical_baseline_paths=$contentMatches
        query_summary=@($scoredZip.rows.Keys | Sort-Object | ForEach-Object {
            $queryRows = @($scoredZip.rows[$_])
            @{query=$_;row_count=$queryRows.Count;top1=if ($queryRows.Count) {$queryRows[0]} else {$null}}
        })
    }
}
$scoreComparisons = @(
    (Compare-AuditZip $scoredZips[1] $scoredZips[0]),
    (Compare-AuditZip $scoredZips[2] $scoredZips[5]),
    (Compare-AuditZip $scoredZips[3] $scoredZips[4]),
    (Compare-AuditZip $zips[6] $scoredZips[4]),
    (Compare-AuditZip $zips[0] $scoredZips[1]),
    (Compare-AuditZip $zips[3] $scoredZips[4]),
    (Compare-AuditZip $zips[3] $scoredZips[6]),
    (Compare-AuditZip $scoredZips[6] $scoredZips[3]),
    (Compare-AuditZip $scoredZips[6] $scoredZips[4])
)
@{inputs=$scoreInventory;comparisons=$scoreComparisons;missing_requested_score=$null} | ConvertTo-Json -Depth 14
