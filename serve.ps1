# Preview the dashboard locally: powershell -ExecutionPolicy Bypass -File serve.ps1  then open http://localhost:8766/
$port = 8766
$root = $PSScriptRoot
$l = New-Object System.Net.HttpListener
$l.Prefixes.Add("http://localhost:$port/")
$l.Start()
Write-Host "Serving $root at http://localhost:$port/"
$types = @{ '.html'='text/html; charset=utf-8'; '.js'='text/javascript'; '.css'='text/css'; '.json'='application/json; charset=utf-8' }
while ($l.IsListening) {
  $c = $l.GetContext()
  $name = [Uri]::UnescapeDataString($c.Request.Url.AbsolutePath.TrimStart('/'))
  if ($name -eq '') { $name = 'index.html' }
  $path = Join-Path $root $name
  if ((Test-Path $path -PathType Leaf) -and ((Resolve-Path $path).Path.StartsWith($root))) {
    $bytes = [IO.File]::ReadAllBytes($path)
    $ext = [IO.Path]::GetExtension($path).ToLower()
    $c.Response.ContentType = $(if ($types[$ext]) { $types[$ext] } else { 'application/octet-stream' })
    $c.Response.OutputStream.Write($bytes, 0, $bytes.Length)
  } else { $c.Response.StatusCode = 404 }
  $c.Response.Close()
}
