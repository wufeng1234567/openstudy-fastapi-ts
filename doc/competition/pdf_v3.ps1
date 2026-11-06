param(
  [string]$Pptx = "D:\OpenStudy\apps\fastapi-v2\doc\competition\OpenStudy-0.5.0-10页-码道版.pptx",
  [string]$Pdf  = "D:\OpenStudy\apps\fastapi-v2\doc\competition\OpenStudy-0.5.0-10页-码道版.pdf"
)
$app = New-Object -ComObject PowerPoint.Application
$app.Visible = 1
$pres = $app.Presentations.Open($Pptx, 0, 0, 0)
$pres.SaveAs($Pdf, 32)
$pres.Close()
$app.Quit()
Write-Host "pdf saved: $Pdf"
