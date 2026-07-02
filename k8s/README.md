# Kubernetes deployment

Dev-grade manifests (single-replica backing stores with PVCs). Build the two
images and load them into your cluster (e.g. kind/minikube), then apply:

    docker build -t joy-app .
    docker build -t joy-ai -f Dockerfile.ai .
    kubectl apply -k k8s/overlays/dev

Create real secrets before production use (see `base/secret.example.yaml`).
The HPAs need metrics-server. Run the k6 load test against the ingress:

    k6 run k6/load.js --env BASE_URL=http://<ingress-host>
