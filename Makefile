# Fraud Detection Pipeline - Makefile
# Run from repo root: make <target>

NAMESPACE := fraud-det-v3
MANIFEST_DUAL := k8s_configs/dual-flashblade.yaml
MANIFEST_BACKEND := k8s_configs/backend.yaml
DOCKER_USER := pduraiswamy16722
IMAGES := $(DOCKER_USER)/fraud-det-v3-data-gather:latest $(DOCKER_USER)/fraud-det-v3-data-prep:latest $(DOCKER_USER)/fraud-det-v3-inference:latest $(DOCKER_USER)/fraud-det-v3-model-build:latest $(DOCKER_USER)/fraud-det-v3-backend:latest
BACKEND_URL ?= http://10.23.181.153:30880


.PHONY: build build-no-cache load-kind load-minikube deploy deploy-dual start stop port-forward logs status restart clean

build:
	chmod +x build-images.sh
	./build-images.sh

build-no-cache:
	NO_CACHE=--no-cache ./build-images.sh

# Kind: load built images into cluster
load-kind:
	kind load docker-image $(IMAGES)

# Minikube: build images directly into Minikube's Docker (no separate load step)
load-minikube:
	eval $$(minikube docker-env) && $(MAKE) build

deploy:
	kubectl apply -f $(MANIFEST_DUAL)
	kubectl apply -f $(MANIFEST_BACKEND)

deploy-dual:
	kubectl apply -f $(MANIFEST_DUAL)

start:
	curl -s -X POST $(BACKEND_URL)/api/control/start

stop:
	curl -s -X POST $(BACKEND_URL)/api/control/stop

port-forward:
	kubectl port-forward -n fraud-det-v3 svc/backend 8000:8000

logs:
	kubectl logs -n $(NAMESPACE) deployment/data-gather --tail=50 -f

status:
	kubectl get pods -n $(NAMESPACE) -w

restart:
	kubectl -n $(NAMESPACE) get deployments -o name | xargs kubectl -n $(NAMESPACE) rollout restart

clean:
	kubectl delete namespace $(NAMESPACE) --ignore-not-found
