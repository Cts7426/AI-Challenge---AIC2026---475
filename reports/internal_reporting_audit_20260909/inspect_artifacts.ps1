# Kiểm ZIP và checkpoint chỉ đọc; so sánh file không đồng nghĩa xác định tác giả can thiệp.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$auditRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path

function Read-AuditZip([string]$relativePath) {
    $path = if ([System.IO.Path]::IsPathRooted($relativePath)) { $relativePath } else { Join-Path $auditRoot $relativePath }
    $archive = [System.IO.Compression.ZipFile]::OpenRead($path)
    $rows = @{}
    $dates = @()
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.Name -notlike '*.csv') { continue }
            if ($rows.ContainsKey($entry.Name)) { throw "Trùng tên CSV: $relativePath/$($entry.Name)" }
            $reader = [System.IO.StreamReader]::new($entry.Open())
            try { $content = $reader.ReadToEnd() } finally { $reader.Dispose() }
            # Parse CSV để dấu phẩy trong answer không tạo khác biệt giả.
            $parsed = @(ConvertFrom-Csv -InputObject $content -Header c0,c1,c2,c3,c4,c5,c6,c7,c8,c9)
            $rows[$entry.Name] = @($parsed | ForEach-Object {
                $fields = @($_.PSObject.Properties | Where-Object {$null -ne $_.Value} | ForEach-Object {$_.Value.Trim()})
                ConvertTo-Json -InputObject $fields -Compress
            })
            $dates += $entry.LastWriteTime.ToString('o')
        }
    } finally { $archive.Dispose() }
    return @{path=$relativePath; sha256=(Get-FileHash -LiteralPath $path).Hash; csv_count=$rows.Count; zip_dates=@($dates | Sort-Object -Unique); rows=$rows}
}

function Compare-AuditZip($before, $after) {
    $queries = @()
    foreach ($name in @($before.rows.Keys + $after.rows.Keys | Sort-Object -Unique)) {
        $a = @(); $b = @()
        if ($before.rows.ContainsKey($name)) { $a = @($before.rows[$name]) }
        if ($after.rows.ContainsKey($name)) { $b = @($after.rows[$name]) }
        if (!$before.rows.ContainsKey($name)) { $kind='added_query' }
        elseif (!$after.rows.ContainsKey($name)) { $kind='missing_query' }
        elseif (($a -join "`n") -ceq ($b -join "`n")) { $kind='same_ordered_rows' }
        elseif ((@($a | Sort-Object) -join "`n") -ceq (@($b | Sort-Object) -join "`n")) { $kind='permutation_only' }
        else { $kind='rows_changed' }
        $firstRank = $null
        if ($b.Count -gt 0 -and $before.rows.ContainsKey($name)) {
            for ($i=0; $i -lt $a.Count; $i++) { if ($a[$i] -ceq $b[0]) { $firstRank=$i+1; break } }
        }
        $queries += [pscustomobject]@{query=$name; difference=$kind; before_rows=$a.Count; after_rows=$b.Count; after_top1_rank_in_before=$firstRank; added_unique_rows=@($b | Where-Object {$_ -cnotin $a} | Sort-Object -Unique).Count; human_rerank='unknown'; manual_discovery='unknown'; external_ai='unknown'; official_result='unlinked'}
    }
    return @{before=$before.path; after=$after.path; summary=@($queries | Group-Object difference | Select-Object Name,Count); queries=$queries}
}

$paths = @('submissions/sotuyen1_p1/submission.zip','submissions/THANH_NGHE_round1_manual_222703/submission.zip','submissions/round2/submission.zip','submissions/round3/submission.zip','THANH_NGHE_round3.original.zip','submissions/THANH_NGHE_round3_corrected.zip','submissions/THANH_NGHE_round3_corrected_v2.zip')
$zips = @($paths | ForEach-Object { Read-AuditZip $_ })
$comparisons = @((Compare-AuditZip $zips[0] $zips[1]),(Compare-AuditZip $zips[3] $zips[4]),(Compare-AuditZip $zips[4] $zips[5]),(Compare-AuditZip $zips[5] $zips[6]))
# Hai đường dẫn có sẵn trong build_official_gt.py; chỉ đọc đúng file được dẫn.
foreach ($extraPath in @('C:\Users\lehon\Downloads\Thanh Nghệ_round1 (1).zip','C:\Users\lehon\Downloads\submission_THANH_ NGHỆ.zip')) {
    if (Test-Path -LiteralPath $extraPath) { $zips += Read-AuditZip $extraPath }
}
if ($zips.Count -eq 9) {
    $comparisons += Compare-AuditZip $zips[0] $zips[7]
    $comparisons += Compare-AuditZip $zips[1] $zips[7]
    $comparisons += Compare-AuditZip $zips[2] $zips[8]
}
# Hai file được người dùng dẫn trong chat ngày 04/09; không dò toàn bộ Downloads.
foreach ($chatPath in @('C:\Users\lehon\Downloads\exam_final.zip','C:\Users\lehon\Downloads\THANH_NGHE_round3.zip')) {
    if (Test-Path -LiteralPath $chatPath) { $zips += Read-AuditZip $chatPath }
}
if ($zips.Count -eq 11) {
    $comparisons += Compare-AuditZip $zips[9] $zips[10]
    $comparisons += Compare-AuditZip $zips[10] $zips[4]
}
$checkpoints = @()
foreach ($relative in @('submissions/sotuyen1_p1/checkpoint.jsonl','submissions/round2/checkpoint.before-query-p2-19-qa.jsonl','submissions/round2/checkpoint.jsonl','submissions/round3/checkpoint.jsonl')) {
    $records = @(Get-Content -LiteralPath (Join-Path $auditRoot $relative) | ForEach-Object {ConvertFrom-Json $_})
    $checkpoints += @{path=$relative; sha256=(Get-FileHash -LiteralPath (Join-Path $auditRoot $relative)).Hash; records=$records.Count; at_min=($records.at | Sort-Object | Select-Object -First 1); at_max=($records.at | Sort-Object | Select-Object -Last 1); fingerprints=@($records.runtime_fingerprint | Sort-Object -Unique); manual_overrides=@($records | Where-Object {$_.qa_trace.qa_runtime.manual_override} | Select-Object query_id,at); task_counts=@($records | Group-Object task_type | Select-Object Name,Count)}
}
@{zip_inventory=@($zips | ForEach-Object {@{path=$_.path;sha256=$_.sha256;csv_count=$_.csv_count;zip_dates=$_.zip_dates}}); comparisons=$comparisons; checkpoints=$checkpoints} | ConvertTo-Json -Depth 12
