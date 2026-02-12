# Fraud Detection Pipeline - Makefile
# Run from repo root: make <target>

NAMESPACE := fraud-det-v3
MANIFEST_DUAL := k8s_configs/dual-flashblade.yaml
IMAGES := apandit07650/fraud-det-v3-data-gather:latest apandit07650/fraud-det-v3-data-prep:latest apandit07650/fraud-det-v3-inference:latest apandit07650/fraud-det-v3-model-build:latest apandit07650/fraud-det-v3-dockerfile.backend:latest
BACKEND_URL ?= http://localhost:8000

.PHONY: build build-no-cache load-kind load-minikube deploy deploy-dual start stop port-forward logs status restart clean

build:
	chmod +x k8s/build-images.sh
	./k8s/build-images.sh

build-no-cache:
	NO_CACHE=--no-cache ./k8s/build-images.sh

# Kind: load built images into cluster
load-kind:
	kind load docker-image $(IMAGES)

# Minikube: build images directly into Minikube's Docker (no separate load step)
load-minikube:
	eval $$(minikube docker-env) && $(MAKE) build

deploy:
	kubectl apply -f $(MANIFEST_DUAL)

deploy-dual:
	kubectl apply -f $(MANIFEST_DUAL)

start:
	curl -s -X POST $(BACKEND_URL)/api/control/start

stop:
	curl -s -X POST $(BACKEND_URL)/api/control/stop

port-forward:
	kubectl port-forward -n $(NAMESPACE) svc/backend 8000:8000

logs:
	kubectl logs -n $(NAMESPACE) deployment/data-gather --tail=50 -f

status:
	kubectl get pods -n $(NAMESPACE) -w

restart:
	kubectl -n $(NAMESPACE) get deployments -o name | xargs kubectl -n $(NAMESPACE) rollout restart

clean:
	kubectl delete namespace $(NAMESPACE) --ignore-not-found
