# Kubernetes

This file includes instructions on how to setup Kubernetes and an image registry.

## Install Kubernetes

The easiest way to install Kubernetes in our experience is to use [k3sup](https://github.com/alexellis/k3sup), a "light-weight utility to get from zero to KUBECONFIG with k3s on any local or remote VM"

To install `k3sup`, we need to run:

```bash
curl -sLS https://get.k3sup.dev | sh
sudo install k3sup /usr/local/bin/
rm k3sup
```

To install Kubernetes locally, we just need to run the following command:

```bash
k3sup install --local
```

Note that `k3sup` creates the `kubeconfig` file in the current working directory from where the command is run. We can move it to the default location with:

```bash
mkdir -p $HOME/.kube
mv kubeconfig $HOME/.kube/config
```

To avoid the need to use `sudo` when running `kubectl` commands, we need to change the ownership of the `.kube` folder to the current user:

```bash
sudo chown -R $USER $HOME/.kube
```

### Connect `kubectl` to the Cluster Remotely

To connect `kubectl` to a remote cluster, we can use `k3sup` as well. On our local machine (not the server where k3s is installed), we need to run:

```bash
k3sup install \
  --skip-install \
  --ip <SERVER_IP_ADDRESS> \
  --user <USER> \
  --ssh-key <PATH/TO/SSH_KEY> \
  --local-path ~/.kube/config \
  --merge
```

Where `<SERVER_IP_ADDRESS>` is the IP address of the server where k3s is installed, and `<USER>` is the user we use to connect to the server via SSH.

And finally, we need to do a port forwarding of the Kubernetes API server port (6443) from the server to our local machine:

```bash
ssh -L 6443:localhost:6443 <USER>@<SERVER_IP_ADDRESS>
```

Now we should be able to run `kubectl` commands from our local machine.

### Configure Kubernetes

#### Increase the Maximum Number of Pods Allowed

After installing Kubernetes, we need to increase the maximum number of pods allowed per node, if we plan to deploy many challenges. This can be done by editing the `k3s.service` file:

```bash
sudo vim /etc/systemd/system/k3s.service
```

and adding `'--kubelet-arg=max-pods=433'` to the end of the `ExecStart` command (`433` is just a specific arbitrary number that makes it easier to debug if we encounter issues).

After that, we need to reload the `systemd` configuration and restart k3s:

```bash
sudo systemctl daemon-reload
sudo systemctl restart k3s
```

We can check the nodes by running:

```bash
kubectl get nodes
```

We can check the number of pods allowed per node with the following command:

```bash
kubectl get nodes <NODE_NAME> -o json | jq -r '.status.capacity.pods'
```

#### Set the Range of Node Ports

We need to specify the range of ports allowed in the node port field of services. To do that, we need to edit the `k3s.service` file again:

```bash
sudo vim /etc/systemd/system/k3s.service
```

and add `'--service-node-port-range=MIN_PORT-MAX_PORT'` to the end of the `ExecStart` command. The suggested range is 5000-40000 to have the 5000 included and also include the Traefik (Kubernetes traffic manager) ports.

After this, the `ExecStart` command should be something like this:

```bash
ExecStart=/usr/local/bin/k3s \
    server \
    '--tls-san' \
    '127.0.0.1' \
    '--kubelet-arg=max-pods=433' \
    '--service-node-port-range=5000-40000'
```

Then, we need to reload the `systemd` configuration and restart k3s:

```bash
sudo systemctl daemon-reload
sudo systemctl restart k3s
```

**Note**: the `MIN_PORT` should be high enough to not collide with previously existing services (it is recommended at least above 7000). Even better would be to have the challenges directly within the predefined Kubernetes range >30000.

## Setup a Local Registry

To deploy a local registry, we can use the official Docker registry image. We can create a Kubernetes deployment and service for the registry as follows.

We can create the namespace, deployment and service by applying the `docker-registry.yaml` file located in this directory:

```bash
kubectl apply -f docker-registry.yaml
```

To check if the deployment was successful, we can run:

```bash
kubectl get deployment,service,persistentvolumeclaim -n docker-registry
```

We should see output similar to this:

```bash
NAME                              READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/docker-registry   1/1     1            1           174m

NAME                              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
service/docker-registry-service   ClusterIP   10.43.16.113    <none>        5000/TCP         174m

NAME                                        STATUS   VOLUME    CAPACITY   ACCESS MODES   STORAGECLASS   VOLUMEATTRIBUTESCLASS   AGE
persistentvolumeclaim/docker-registry-pvc   Bound    pvc-id    10Gi       RWO            local-path     <unset>                 174m
```

To configure k3s to use the local registry we need to add the following to the `/etc/rancher/k3s/registries.yaml` file (or create it if it does not exist):

```yaml
mirrors:
  "registry.localhost:5000":
    endpoint:
      - "http://registry.localhost:5000"
```

This command also marks the registry as insecure, using HTTP. We should then notify Docker about this insecure registry. First, create the Docker configuration directory if it does not exist:

```bash
sudo mkdir -p /etc/docker
```

Then, create the file `/etc/docker/daemon.json` with the following content:

```json
{
  "insecure-registries": [
    "registry.localhost:5000"
  ]
}
```

After that, we need to restart Docker:

```bash
sudo systemctl restart docker
```

And give proper permissions to the `k3s.yaml` file:

```bash
sudo chmod 644 /etc/rancher/k3s/k3s.yaml
```

We may need to restart k3s to apply the changes:

```bash
sudo systemctl restart k3s
```

Finally, we need to configure the DNS to resolve `registry.localhost` to the IP address of the registry service (`10.43.16.113` in the example above).

We can do this by adding the following line to the `/etc/hosts` file:

```bash
REGISTRY_IP=$(kubectl get svc docker-registry-service -n docker-registry -o jsonpath='{.spec.clusterIP}')
echo "$REGISTRY_IP registry.localhost" | sudo tee -a /etc/hosts
```

After deploying the registry, we can push images to it using the following command:

```bash
docker build -t registry.localhost/test:latest .
docker push registry.localhost/test:latest
```

## Python Environment

The script `deployer/kubernetes_deployer.py` requires specific modules. The fastest way to manage them is to create an environment with [micromamba](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html).

After installation, we can create the environment inside `kubernetes/` with the following command:

```bash
micromamba create -f micromamba-env.yaml
```

It will automatically install all the dependencies. To activate it, we need to run:

```bash
micromamba activate ctfkube
```

## k9s

To manage the Kubernetes cluster, the best tool in our opinion is [k9s](https://k9scli.io/), a terminal-based UI to interact with the Kubernetes cluster.
