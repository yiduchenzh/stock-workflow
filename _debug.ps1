$path = "D:\Hermes Agent CN Desktop\stock-workflow\core\engine.py"
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
$idx = $content.IndexOf("self.alerts.extend(alerts)")
Write-Host "Found at $idx"
Write-Host $content.Substring($idx, 400)
