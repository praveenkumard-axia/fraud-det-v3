"""
Kubernetes scaling helper for fraud-det-v3 namespace.
Uses subprocess to run kubectl scale. Call this from backend/dashboard when scaling pods.
"""

import json
import subprocess
from typing import Optional, Tuple

NAMESPACE = "fraud-det-v3"

# K8s deployment names in namespace fraud-det-v3 (must match your manifests)
# Pod 1: generation (CPU) | Pod 2: preprocessing CPU | Pod 3: preprocessing GPU
# Pod 4: model-build (GPU) | Pod 5: inference CPU | Pod 6: inference GPU
DEPLOYMENT_NAMES = {
    "data-gather": "data-gather",           # Pod 1 - generation
    "preprocessing-cpu": "preprocessing-cpu",   # Pod 2
    "preprocessing-gpu": "preprocessing-gpu",   # Pod 3
    "model-build": "model-build",            # Pod 4 - training
    "inference-cpu": "inference-cpu",        # Pod 5
    "inference-gpu": "inference-gpu",        # Pod 6
}


def start_pipeline():
    """
    Start the pipeline by scaling all deployments to default replicas.
    """
    for pod_key, replicas in DEPLOYMENT_NAMES.items():
        scale_pod(pod_key, replicas)
    return True, "Pipeline started"


def stop_pipeline():
    """
    Stop the pipeline by scaling all deployments to 0 replicas.
    """
    for pod_key, replicas in DEPLOYMENT_NAMES.items():
        scale_pod(pod_key, 0)

def scale_pod(pod_key: str, replicas: int) -> Tuple[bool, str]:
    """
    Scale a pod by logical key. Uses DEPLOYMENT_NAMES and fraud-det-v3 namespace.
    pod_key: one of data-gather, preprocessing-cpu, preprocessing-gpu, model-build, inference-cpu, inference-gpu
    Returns (success, message).
    """
    name = DEPLOYMENT_NAMES.get(pod_key)
    if not name:
        return False, f"unknown pod_key: {pod_key}"
    return scale_deployment(name, replicas)


def scale_deployment(deployment_name: str, replicas: int) -> Tuple[bool, str]:
    """
    Scale a deployment in the fraud-det-v3 namespace.
    Returns (success, message).
    """
    if replicas < 0:
        return False, "replicas must be >= 0"
    cmd = [
        "kubectl", "scale", f"deployment/{deployment_name}",
        "--replicas", str(replicas),
        "-n", NAMESPACE,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, result.stdout.strip() or f"Scaled {deployment_name} to {replicas}"
        return False, result.stderr.strip() or result.stdout.strip() or "kubectl failed"
    except subprocess.TimeoutExpired:
        return False, "kubectl scale timed out"
    except FileNotFoundError:
        return False, "kubectl not found"
    except Exception as e:
        return False, str(e)


def _get_pod_name(deployment_name: str) -> Optional[str]:
    """Get the first running pod name for a deployment."""
    cmd = [
        "kubectl", "get", "pods", "-n", NAMESPACE,
        "-l", f"app={deployment_name}",
        "-o", "jsonpath={.items[0].metadata.name}",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return None


def patch_pod_resources(
    pod_key: str,
    cpu_limit: str,
    memory_limit: str,
) -> Tuple[bool, str]:
    """
    Patch pod resources (CPU/memory limits). Uses In-Place Pod Resize (K8s 1.33+)
    when available; otherwise falls back to deployment patch (rolling restart).
    pod_key: one of data-gather, preprocessing-cpu, preprocessing-gpu, model-build, inference-cpu, inference-gpu
    cpu_limit: e.g. "4000m" or "4"
    memory_limit: e.g. "4Gi" or "8Gi"
    Returns (success, message).
    """
    deployment_name = DEPLOYMENT_NAMES.get(pod_key)
    if not deployment_name:
        return False, f"unknown pod_key: {pod_key}"

    # CPU: "4" = 4 cores (K8s accepts); "4000m" = 4000 millicores. Pass through as-is.
    # Memory: ensure unit (Gi/Mi)
    if memory_limit.isdigit():
        memory_limit = f"{memory_limit}Gi"

    container_name = deployment_name
    patch_body = {
        "spec": {
            "containers": [{
                "name": container_name,
                "resources": {
                    "limits": {"cpu": cpu_limit, "memory": memory_limit},
                },
            }],
        },
    }

    # Try in-place pod resize first (K8s 1.33+)
    pod_name = _get_pod_name(deployment_name)
    if pod_name:
        cmd = [
            "kubectl", "patch", "pod", pod_name, "-n", NAMESPACE,
            "--subresource=resize", "--type=merge",
            "-p", json.dumps(patch_body),
        ]
        print(f"DEBUG: Executing command: {' '.join(cmd)}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True, f"Resized {pod_key} (in-place) CPU={cpu_limit} memory={memory_limit}"
            # Resize subresource may not exist on older K8s
            stderr_lower = (result.stderr or "").lower()
            if "subresource" in stderr_lower or "not found" in stderr_lower or "notfound" in stderr_lower:
                pass  # Fall through to deployment patch
            else:
                return False, result.stderr.strip() or result.stdout.strip() or "kubectl patch failed"
        except subprocess.TimeoutExpired:
            return False, "kubectl patch timed out"
        except FileNotFoundError:
            return False, "kubectl not found"
        except Exception as e:
            return False, str(e)

    # Fallback: patch deployment (triggers rolling restart)
    cmd = [
        "kubectl", "patch", "deployment", deployment_name, "-n", NAMESPACE,
        "--type=json",
        "-p", json.dumps([
            {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": cpu_limit},
            {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": memory_limit},
        ]),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, f"Resized {pod_key} (rolling restart) CPU={cpu_limit} memory={memory_limit}"
        
        err_msg = result.stderr.strip() or result.stdout.strip()
        if "not found" in err_msg.lower():
             return False, f"Deployment '{deployment_name}' not found. Are you trying to scale a GPU pod on CPU config?"
             
        return False, err_msg or "kubectl patch failed"
    except subprocess.TimeoutExpired:
        return False, "kubectl patch timed out"
    except FileNotFoundError:
        return False, "kubectl not found"
    except Exception as e:
        return False, str(e)

def get_deployment_resources() -> dict:
    """
    Fetch CPU and Memory limits/requests for all deployments in the namespace.
    Returns {deployment_name: {cpu_limit: str, mem_limit: str, cpu_request: str, mem_request: str}}
    """
    cmd = ["kubectl", "get", "deployments", "-n", NAMESPACE, "-o", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {}
        
        data = json.loads(result.stdout)
        resources = {}
        for item in data.get("items", []):
            name = item["metadata"]["name"]
            spec = item["spec"]["template"]["spec"]
            # Assume first container is the main one
            container = spec["containers"][0]
            res = container.get("resources", {})
            limits = res.get("limits", {})
            requests = res.get("requests", {})
            
            resources[name] = {
                "cpu_limit": limits.get("cpu", "N/A"),
                "mem_limit": limits.get("memory", "N/A"),
                "cpu_request": requests.get("cpu", "N/A"),
                "mem_request": requests.get("memory", "N/A"),
            }
        return resources
    except Exception:
        return {}
