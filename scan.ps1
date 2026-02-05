param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$FolderPath
)

function Format-ByteSize {
    param([long]$bytes)
    $sizes = "B", "KB", "MB", "GB", "TB"
    $order = 0
    while ($bytes -ge 1024 -and $order -lt $sizes.Count - 1) {
        $order++
        $bytes = $bytes / 1024
    }
    return "{0:N2} {1}" -f $bytes, $sizes[$order]
}

function Show-Usage {
    Write-Host "Usage: .\scan.ps1 <folder_path>"
    Write-Host "Example: .\scan.ps1 C:\Users\jeffr\Downloads\kids"
    exit 1
}

if ($FolderPath.Count -eq 0) {
    Show-Usage
}

$targetPath = $FolderPath -join " "

if (-not (Test-Path $targetPath)) {
    Write-Host "Error: Path '$targetPath' does not exist" -ForegroundColor Red
    exit 1
}

Write-Host "Scanning folder: $targetPath" -ForegroundColor Cyan
Write-Host "=============================================`n"

$stats = @{
    TotalFiles = 0
    TotalFolders = 0
    TotalSize = 0
    FileTypes = @{}
}

try {
    $items = Get-ChildItem -Path $targetPath -Recurse -ErrorAction SilentlyContinue
    
    foreach ($item in $items) {
        if ($item.PSIsContainer) {
            $stats.TotalFolders++
        } else {
            $stats.TotalFiles++
            $stats.TotalSize += $item.Length
            
            $ext = if ($item.Extension) { $item.Extension } else { "[no extension]" }
            if (-not $stats.FileTypes.ContainsKey($ext)) {
                $stats.FileTypes[$ext] = 0
            }
            $stats.FileTypes[$ext]++
        }
    }
    
    Write-Host "Scan Results:"
    Write-Host "  Total Folders: $($stats.TotalFolders)"
    Write-Host "  Total Files: $($stats.TotalFiles)"
    Write-Host "  Total Size: $(Format-ByteSize $stats.TotalSize)"
    Write-Host "`nFile Types:"
    
    $stats.FileTypes.GetEnumerator() | Sort-Object Value -Descending | ForEach-Object {
        Write-Host "  $($_.Key): $($_.Value) files"
    }
    
    Write-Host "`n=============================================`n"
    Write-Host "Scan completed successfully!" -ForegroundColor Green
}
catch {
    Write-Host "Error during scan: $_" -ForegroundColor Red
    exit 1
}
