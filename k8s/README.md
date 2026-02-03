# Kubernetes manifests – fraud-pipeline

Namespace: **fraud-pipeline**

**Current setup: CPU-only.** GPU deployments are in `k8s/disabled/` and are not applied by default.

## Active (CPU) deployments

| File | Deployment name | Replicas (default) | Resources |
|------|-----------------|--------------------|-----------|
| `namespace.yaml` | — | — | — |
| `data-gather-deployment.yaml` | data-gather | 1 | CPU |
| `preprocessing-cpu-deployment.yaml` | preprocessing-cpu | 1 | CPU |
| `inference-cpu-deployment.yaml` | inference-cpu | 2 | CPU |

## Apply (CPU-only)

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/data-gather-deployment.yaml
kubectl apply -f k8s/preprocessing-cpu-deployment.yaml
kubectl apply -f k8s/inference-cpu-deployment.yaml
```

Or apply the whole directory (only the files above are in `k8s/` now):

```bash
kubectl apply -f k8s/
```

If you previously applied GPU deployments and want to remove them (e.g. to clear Pending/ImagePullBackOff):

```bash
kubectl delete deployment -n fraud-pipeline model-build preprocessing-gpu inference-gpu --ignore-not-found
```

## Storage / FlashBlade

**You do not need FlashBlade.** The app uses `config_contract.StoragePaths.get_path()`:

- If `/mnt/flashblade` **exists** (e.g. FlashBlade or NFS mounted), it uses that.
- If **not**, it uses in-container fallback paths under the app dir (e.g. `/app/run_data_output`, `/app/run_features_output`), which are created automatically and are writable.

So without FlashBlade, everything works; data is written inside the container. For production you can mount a PVC or NFS at `/mnt/flashblade` if you want shared storage.

## Images

Replace `fraud-pipeline/<name>:latest` with your registry and tags (e.g. build from `pods/data-gather/`, `pods/data-prep/` for preprocessing-cpu, `pods/inference/` for inference-cpu).

## GPU deployments (disabled)

`k8s/disabled/` contains preprocessing-gpu, model-build, and inference-gpu. They are **not** applied with the commands above. To use them later, move the YAML files from `k8s/disabled/` into `k8s/` and ensure GPU nodes have the NVIDIA device plugin (`nvidia.com/gpu`).
