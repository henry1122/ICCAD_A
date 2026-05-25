$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $root) { $root = (Get-Location).Path }
Set-Location $root

$inputFile = Join-Path $PSScriptRoot "test_input.txt"
if ($args[0] -eq "simple") { $inputFile = Join-Path $PSScriptRoot "test_simple.txt" }

Get-Content $inputFile -Encoding UTF8 | python main.py -config config.yaml
