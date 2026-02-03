"""
Kubernetes scaling helper for fraud-pipeline namespace.
Uses subprocess to run kubectl scale. Call this from backend/dashboard when scaling pods.
"""

import subprocess
from typing import Tuple

NAMESPACE = "fraud-pipeline"

# K8s deployment names in namespace fraud-pipeline (must match your manifests)
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


def scale_pod(pod_key: str, replicas: int) -> Tuple[bool, str]:
    """
    Scale a pod by logical key. Uses DEPLOYMENT_NAMES and fraud-pipeline namespace.
    pod_key: one of data-gather, preprocessing-cpu, preprocessing-gpu, model-build, inference-cpu, inference-gpu
    Returns (success, message).
    """
    name = DEPLOYMENT_NAMES.get(pod_key)
    if not name:
        return False, f"unknown pod_key: {pod_key}"
    return scale_deployment(name, replicas)


def scale_deployment(deployment_name: str, replicas: int) -> Tuple[bool, str]:
    """
    Scale a deployment in the fraud-pipeline namespace.
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
