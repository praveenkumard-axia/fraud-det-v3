# build-images.ps1: Automate building all fraud pipeline images on Windows
# Run from repo root: .\build-images.ps1

$env:NO_CACHE = ""
powershell -ExecutionPolicy Bypass -File .\k8s\build-images.ps1
