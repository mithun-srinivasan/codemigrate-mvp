# CodeMigrate - Laptop Spec Checker
# Run this in PowerShell to see what AI model size your laptop can handle.
# Right-click this file > "Run with PowerShell", OR open PowerShell and run:
#   powershell -ExecutionPolicy Bypass -File check-specs.ps1

Write-Host "===== LAPTOP SPEC CHECK for CodeMigrate =====" -ForegroundColor Cyan
Write-Host ""

# CPU
$cpu = Get-CimInstance Win32_Processor
Write-Host "CPU: $($cpu.Name)" -ForegroundColor Yellow
Write-Host "Cores: $($cpu.NumberOfCores)  |  Logical Processors: $($cpu.NumberOfLogicalProcessors)"
Write-Host ""

# RAM
$os = Get-CimInstance Win32_OperatingSystem
$totalRAM = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$freeRAM = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
Write-Host "Total RAM: $totalRAM GB" -ForegroundColor Yellow
Write-Host "Free RAM right now: $freeRAM GB"
Write-Host ""

# GPU
$gpus = Get-CimInstance Win32_VideoController
foreach ($gpu in $gpus) {
    $vram = [math]::Round($gpu.AdapterRAM / 1GB, 2)
    Write-Host "GPU: $($gpu.Name)  |  VRAM: $vram GB" -ForegroundColor Yellow
}
Write-Host ""

# Disk space (C: drive)
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$freeDisk = [math]::Round($disk.FreeSpace / 1GB, 2)
$totalDisk = [math]::Round($disk.Size / 1GB, 2)
Write-Host "Disk (C:): $freeDisk GB free of $totalDisk GB" -ForegroundColor Yellow
Write-Host ""

# Windows version (helps rule out compatibility issues)
Write-Host "OS: $($os.Caption) ($($os.OSArchitecture))" -ForegroundColor Yellow
Write-Host ""

Write-Host "===== RECOMMENDATION =====" -ForegroundColor Cyan
if ($totalRAM -ge 16) {
    Write-Host "-> You can run: qwen2.5-coder:7b  (best quality, recommended)" -ForegroundColor Green
} elseif ($totalRAM -ge 8) {
    Write-Host "-> You can run: qwen2.5-coder:7b  (should work, close other apps first)" -ForegroundColor Green
    Write-Host "-> Fallback if slow/laggy: qwen2.5-coder:1.5b" -ForegroundColor Yellow
} else {
    Write-Host "-> Use the lightweight model: qwen2.5-coder:1.5b" -ForegroundColor Yellow
    Write-Host "-> Your RAM is under 8GB, the 7b model will likely be too slow or crash" -ForegroundColor Yellow
}

if ($freeDisk -lt 6) {
    Write-Host "-> WARNING: Low disk space. You need at least 5-6 GB free to download a model." -ForegroundColor Red
}

Write-Host ""
Write-Host "This repo defaults to qwen2.5-coder:1.5b in app.py." -ForegroundColor Cyan
Write-Host "Only change MODEL_NAME to 7b on 16GB+ RAM machines." -ForegroundColor Cyan
