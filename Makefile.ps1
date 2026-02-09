# PowerShell alternative to Makefile for Fraud Detection Pipeline on Windows.
# Run from repo root: .\Makefile.ps1 <target>

param (
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet("build", "build-no-cache", "deploy", "start", "stop", "port-forward", "logs", "status", "restart", "clean")]
    $Target
)

$Namespace = "fraud-det-v3"
$ManifestDual = "k8s_configs/dual-flashblade.yaml"
$BackendUrl = if ($env:BACKEND_URL) { $env:BACKEND_URL } else { "http://localhost:8000" }

switch ($Target) {
    "build" {
        powershell -ExecutionPolicy Bypass -File .\k8s\build-images.ps1
    }
    "build-no-cache" {
        $env:NO_CACHE = "--no-cache"
        powershell -ExecutionPolicy Bypass -File .\k8s\build-images.ps1
        $env:NO_CACHE = ""
    }
    "deploy" {
        kubectl apply -f $ManifestDual
    }
    "start" {
        Invoke-RestMethod -Method Post -Uri "$BackendUrl/api/control/start"
    }
    "stop" {
        Invoke-RestMethod -Method Post -Uri "$BackendUrl/api/control/stop"
    }
    "port-forward" {
        Write-Host "Starting port-forward... Press Ctrl+C to stop." -ForegroundColor Cyan
        kubectl port-forward -n $Namespace svc/backend 8000:8000
    }
    "logs" {
        kubectl logs -n $Namespace deployment/data-gather --tail=50 -f
    }
    "status" {
        kubectl get pods -n $Namespace -w
    }
    "restart" {
        $deps = kubectl -n $Namespace get deployments -o name
        foreach ($dep in $deps) {
            kubectl -n $Namespace rollout restart $dep
        }
    }
    "clean" {
        kubectl delete namespace $Namespace --ignore-not-found
    }
}
