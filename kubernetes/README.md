# Kubernetes

This file includes instructions on how to setup Kubernetes and an image registry.

## Install Kubernetes

The easiest way to install Kubernetes in our experience is to use [k3sup](https://github.com/alexellis/k3sup), a "light-weight utility to get from zero to KUBECONFIG with k3s on any local or remote VM"

After cloning the repository on the server, we just need to run the following command:

```bash
k3sup install --local
```

### Configure Kubernetes

#### Increase the Maximum Number of Pods Allowed

After installing Kubernetes, we need to increase the maximum number of pods allowed per node, if we plan to deploy many challenges. This can be done by editing the `k3s.service` file:

```bash
sudo vim /etc/systemd/system/k3s.service
```

and adding `'--kubelet-arg=max-pods=433'` to the `ExecStart` command.

After that, we need to reload the systemd configuration and restart k3s:

```bash
sudo systemctl daemon-reload
sudo systemctl restart k3s
```

We can check the number of pods allowed per node with the following command:

```bash
kubectl get nodes <NODE_NAME> -o json | jq -r '.status.capacity.pods'
```

#### Set the Range of Node Ports

Since challenges are deployed on ports <30000 (in our case, you can decide to go higher than that though), we need to lower the range of ports allowed in the node port field of services. To do that, we need to edit the `k3s.service` file again:

```bash
sudo vim /etc/systemd/system/k3s.service
```

and add `'--service-node-port-range=MIN_PORT-MAX_PORT'` to the `ExecStart` command.

Then, we need to reload the systemd configuration and restart k3s:

```bash
sudo systemctl daemon-reload` and `sudo systemctl restart k3s
```

**Note**: the `MIN_PORT` should be high enough to not collide with previously existing services (it is recommended at least above 7000). Even better would be to have the challenges directly within the predefined Kubernetes range >30000.

## Setup a Local Registry

To deploy a local registry, we can use the official Docker registry image. We can create a Kubernetes deployment and service for the registry as follows:

```yaml
# Local Docker registry running in Kubernetes - for k3s
#
# kubectl create namespace docker-registry
# kubectl apply -f docker-registry.yaml -n docker-registry
#
# docker build -t registry.localhost/test:latest .
# docker push registry.localhost/test:latest
#---
apiVersion: v1
kind: Service
metadata:
  name: docker-registry-service
  labels:
    app: docker-registry
spec:
  selector:
    app: docker-registry
  ports:
    - protocol: TCP
      port: 5000

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: docker-registry-pvc
  labels:
    app: docker-registry
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: local-path
  resources:
    requests:
      storage: 10Gi

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docker-registry
  labels:
    app: docker-registry
spec:
  replicas: 1
  selector:
    matchLabels:
      app: docker-registry
  template:
    metadata:
      labels:
        app: docker-registry
    spec:
      containers:
      - name: docker-registry
        image: registry:2
        ports:
        - containerPort: 5000
          protocol: TCP
        volumeMounts:
        - name: storage
          mountPath: /var/lib/registry
        env:
        - name: REGISTRY_HTTP_ADDR
          value: :5000
        - name: REGISTRY_STORAGE_FILESYSTEM_ROOTDIRECTORY
          value: /var/lib/registry
      volumes:
      - name: storage
        persistentVolumeClaim:
          claimName: docker-registry-pvc
```

This YAML file creates a service and a deployment for the Docker registry, along with a persistent volume claim to store the images. You can apply this configuration with the following command:

```bash
kubectl apply -f docker-registry.yaml -n docker-registry
```

We need to configure k3s to use the local registry by adding the following to the `/etc/rancher/k3s/registries.yaml` file:

```yaml
mirrors:
  registry.localhost:
    endpoint:
      - "http://registry.localhost:5000"
```

We may need to restart k3s for the changes to take effect:

```bash
sudo systemctl restart k3s
```

Finally, we need to configure the DNS to resolve `registry.localhost` to the IP address of the Kubernetes node. This can be done by adding an entry to the `/etc/hosts` file on the server:

```bash
REGISTRY_IP=$(kubectl get svc docker-registry-service -n docker-registry -o jsonpath='{.spec.clusterIP}')
echo "$REGISTRY_IP registry.localhost" | sudo tee -a /etc/hosts
```

After deploying the registry, we can push images to it using the following command:

```bash
docker build -t registry.localhost/test:latest .
docker push registry.localhost/test:latest
```

## Python env

The script kubernetes_deployer.py requires specific modules. The fastest way to do this is to create an environment with [micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html).

After installation, create the enviroment by using:

```bash
micromamba create -f micromamba-env.yaml
```

It will automatically install all the dependencies. To activate it, simply use:

```bash
micromamba activate ctfkube
```

## k9s

To manage the Kubernetes cluster, the best tool in our opinion is [k9s](https://k9scli.io/), a terminal-based UI to interact with the Kubernetes cluster.
