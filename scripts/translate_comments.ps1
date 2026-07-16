param(
    [string]$BaseUrl = "https://ssafy-first-team.onrender.com",
    [string]$ImportKey = $env:DATA_IMPORT_API_KEY,
    [ValidateRange(1, 100)]
    [int]$Limit = 100
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ImportKey)) {
    throw "X-Import-Key is required. Pass -ImportKey or set DATA_IMPORT_API_KEY."
}

$endpoint = "$($BaseUrl.TrimEnd('/'))/api/v1/admin/data-import/comment-translations?limit=$Limit"
$headers = @{ "X-Import-Key" = $ImportKey }
$totalTranslated = 0

do {
    $response = Invoke-RestMethod -Method Post -Uri $endpoint -Headers $headers
    $translatedCount = [int]$response.translatedCount
    $remainingCount = [int]$response.remainingCount
    $totalTranslated += $translatedCount
    Write-Host "Translated: $translatedCount / Remaining: $remainingCount / Total: $totalTranslated"

    if ($remainingCount -gt 0 -and $translatedCount -eq 0) {
        throw "No progress was made. Check the server logs and OpenAI API configuration."
    }

    if ($remainingCount -gt 0) {
        Start-Sleep -Seconds 1
    }
} while ($remainingCount -gt 0)

Write-Host "Comment translation completed. Total: $totalTranslated"
