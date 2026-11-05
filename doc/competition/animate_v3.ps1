param(
  [string]$Pptx = "D:\OpenStudy\apps\fastapi-v2\doc\competition\OpenStudy-0.4.1-10页-码道版.pptx"
)
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
$app.Visible = 1
$pres = $app.Presentations.Open($Pptx, 0, 0, 0)

foreach ($slide in $pres.Slides) {
  # 清掉所有逐元素动画：打开即完整呈现，不再等待
  $seq = $slide.TimeLine.MainSequence
  while ($seq.Count -gt 0) { $seq.Item(1).Delete() }

  # 页面切换：Push Left（横向翻页感），速度 Fast
  try { $slide.SlideShowTransition.EntryEffect = 1282 } catch {}
  try { $slide.SlideShowTransition.Speed = 3 } catch {}
  try { $slide.SlideShowTransition.Duration = 0.45 } catch {}
}

$pres.Save()
$pres.Close()
$app.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
Write-Host "transitions set: push-left / fast"
