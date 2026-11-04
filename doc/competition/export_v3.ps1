param(
  [string]$Pptx = "D:\OpenStudy\apps\fastapi-v2\doc\competition\OpenStudy-10页-V3-码道版.pptx",
  [string]$OutDir = "D:\OpenStudy\apps\fastapi-v2\doc\competition\_preview_v3"
)
$ErrorActionPreference = 'Stop'
if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$app = New-Object -ComObject PowerPoint.Application
$app.Visible = 1
$pres = $app.Presentations.Open($Pptx, 0, 0, 0)
$pres.Export($OutDir, "PNG", 1920, 1080)
$pres.Close()
$app.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
Get-ChildItem $OutDir | Select-Object Name, Length
