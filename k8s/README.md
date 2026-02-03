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

## Fix ImagePullBackOff (local cluster)

Deployments use `imagePullPolicy: Never`, so the cluster will **not** pull from a registry; images must exist on the node.

**1. Build images** (from repo root):

```bash
chmod +x k8s/build-images.sh
./k8s/build-images.sh
```

**2. Load into cluster**

- **Kind:**  
  `kind load docker-image fraud-pipeline/data-gather:latest fraud-pipeline/preprocessing-cpu:latest fraud-pipeline/inference-cpu:latest`

- **Minikube:** run `eval $(minikube docker-env)`, then run `./k8s/build-images.sh` again so images are built in minikube’s Docker.

- **Docker Desktop Kubernetes:** uses the host Docker daemon; after building with `./k8s/build-images.sh`, no load step is needed.

**3. Restart deployments** so they pick up the images:

```bash
kubectl rollout restart deployment -n fraud-pipeline data-gather preprocessing-cpu inference-cpu
```

**Using a real registry:** push the images to your registry, set `image` in the YAML to your image URL, and set `imagePullPolicy: IfNotPresent` (or remove it).

## GPU deployments (disabled)

`k8s/disabled/` contains preprocessing-gpu, model-build, and inference-gpu. They are **not** applied with the commands above. To use them later, move the YAML files from `k8s/disabled/` into `k8s/` and ensure GPU nodes have the NVIDIA device plugin (`nvidia.com/gpu`).
