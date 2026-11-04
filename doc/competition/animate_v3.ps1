param(
  [string]$Pptx = "D:\OpenStudy\apps\fastapi-v2\doc\competition\OpenStudy-10页-V3-码道版.pptx"
)
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
$app.Visible = 1
$pres = $app.Presentations.Open($Pptx, 0, 0, 0)

$map = @{
  1  = @('p1_title')
  2  = @('p2b_card_1','p2b_card_2','p2b_card_3','p2b_quote')
  3  = @('p3b_block_1','p3b_block_2','p3b_block_3','p3b_stats')
  4  = @('p4b_row_1','p4b_row_2','p4b_row_3','p4b_row_4','p4b_micro')
  5  = @('p5_band_1','p5_band_2','p5_band_3','p5_band_4','p5_band_5')
  6  = @('p6_node_1','p6_node_2','p6_node_3','p6_node_4','p6_node_5','p6_node_6','p6_node_7','p6_node_8','p6_support','p6_stat_1','p6_stat_2','p6_stat_3','p6_stat_4')
  7  = @('p7_card_1','p7_card_2','p7_card_3','p7_card_4','p7_card_5','p7_card_6')
  8  = @('p8_dot_1','p8_dot_2','p8_dot_3','p8_dot_4','p8_dot_5','p8_dot_6','p8_card_1','p8_card_2','p8_card_3','p8_card_4','p8_card_5','p8_card_6','p8_band')
  9  = @('p9b_card_1','p9b_card_2','p9b_card_3','p9b_card_4')
  10 = @('p10b_col_1','p10b_col_2','p10b_col_3')
}

foreach ($idx in ($map.Keys | Sort-Object)) {
  $slide = $pres.Slides.Item([int]$idx)
  $seq = $slide.TimeLine.MainSequence
  foreach ($name in $map[$idx]) {
    $shape = $null
    foreach ($sh in $slide.Shapes) { if ($sh.Name -eq $name) { $shape = $sh; break } }
    if ($null -ne $shape) {
      try {
        $eff = $seq.AddEffect($shape, 10, 3)  # Fade / After Previous (append)
        $eff.Timing.Duration = 0.35
        try { $eff.Timing.TriggerDelayTime = 0.03 } catch {}
      } catch {
        Write-Host "effect fail: slide $idx / $name : $($_.Exception.Message)"
      }
    } else {
      Write-Host "shape missing: slide $idx / $name"
    }
  }
  try { $slide.SlideShowTransition.EntryEffect = 3846 } catch {}   # fade
}

$pres.Save()
$pres.Close()
$app.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
Write-Host "animations added"
