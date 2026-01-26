#!/usr/bin/env python3

__author__ = "Matteo Golinelli"
__copyright__ = "Copyright (C) 2025 Matteo Golinelli"
__license__ = "MIT"

from kubernetes import client, config
from multiprocessing import Pool
from dotenv import load_dotenv
from scanner import Challenge
from rich import print
import subprocess
import sys
import os

load_dotenv("config.env")

# Configure the Kubernetes client
config.load_kube_config()
core_v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()
autoscaling_v1 = client.AutoscalingV1Api()

DEFAULT_INTERNAL_PORT = 5000
REGISTRY = os.environ.get("REGISTRY")
NAMESPACE = os.environ.get("NAMESPACE")
CTFD_HOST = os.environ.get("CTFD_HOST")
verbose = False

def create_or_update_service(service: dict):
    '''
    Create or update a service.
    '''
    # Check if the service already exists
    try:
        core_v1.read_namespaced_service(namespace=NAMESPACE, name=service["metadata"]["name"])
        # If the service already exists, update it
        core_v1.replace_namespaced_service(namespace=NAMESPACE, name=service["metadata"]["name"], body=service)
    except Exception as e:
        # If the service does not exist, create it
        core_v1.create_namespaced_service(namespace=NAMESPACE, body=service)

def create_or_update_deployment(deployment: dict):
    '''
    Create or update a deployment.
    '''
    # Check if the deployment already exists
    try:
        apps_v1.read_namespaced_deployment(namespace=NAMESPACE, name=deployment["metadata"]["name"])
        # If the deployment already exists, update it
        apps_v1.replace_namespaced_deployment(namespace=NAMESPACE, name=deployment["metadata"]["name"], body=deployment)
    except Exception as e:
        # If the deployment does not exist, create it
        apps_v1.create_namespaced_deployment(namespace=NAMESPACE, body=deployment)

def create_or_update_horizontal_pod_autoscaler(hpa: dict):
    '''
    Create or update a HorizontalPodAutoscaler.
    '''
    # Check if the HorizontalPodAutoscaler already exists
    try:
        autoscaling_v1.read_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE, name=hpa["metadata"]["name"])
        # If the HorizontalPodAutoscaler already exists, update it
        autoscaling_v1.replace_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE, name=hpa["metadata"]["name"], body=hpa)
    except Exception as e:
        # If the HorizontalPodAutoscaler does not exist, create it
        autoscaling_v1.create_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE, body=hpa)

def create_or_update_resource(resource: dict):
    '''
    Create or update a resource.
    '''
    if resource["kind"] == "Service":
        create_or_update_service(resource)
    elif resource["kind"] == "Deployment":
        create_or_update_deployment(resource)
    elif resource["kind"] == "HorizontalPodAutoscaler":
        create_or_update_horizontal_pod_autoscaler(resource)
    else:
        raise ValueError(f"Unknown resource kind: {resource['kind']}")

def run_command(command: str):
    '''
    Run a command in a subprocess and notify on failure.
    '''
    if verbose:
        print(f"{command}", flush=True)

    completed = subprocess.run(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if completed.returncode != 0:
        print(f"[red]Command failed with exit code {completed.returncode}: {command}[/red]", file=sys.stderr)
        if completed.stdout:
            print("[yellow]--- STDOUT ---[/yellow]")
            print(completed.stdout)
        if completed.stderr:
            print("[yellow]--- STDERR ---[/yellow]", file=sys.stderr)
            print(completed.stderr, file=sys.stderr)


def update_pods(images: list[str]):
    '''
    Delete and recreate the pods of the images that have been updated.
    '''
    # Get the pods
    pods = core_v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=f"{CTFD_HOST}/managed-by=true")
    pods_to_delete = []
    for pod in pods.items:
        if pod.spec.containers[0].image in images:
            pods_to_delete.append(pod.metadata.name)

    if len(pods_to_delete) > 0:
        answer = input(f'Found {len(pods_to_delete)} pods to delete: {pods_to_delete}. Do you want to delete them? [y/N] ')
        if answer.lower() == "y":
            for pod_name in pods_to_delete:
                core_v1.delete_namespaced_pod(namespace=NAMESPACE, name=pod_name)
                print(f"Deleted pod {pod_name}")

def build_and_push_images(challenges: list[Challenge], ignore_existing: bool = False):
    '''
    Build the images for the challenges and push them to the registry.
    '''
    print("Building and pushing images... sudo is required.")

    images_repo_digests = {}

    # Get the images already in the registry
    images = subprocess.run("sudo docker images --format '{{.Repository}}__:__{{.Digest}}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for repository in images.stdout.split("\n"):
        if repository.replace("__:__", "") == "":
            continue
        repository, digest = repository.split('__:__')
        if repository.startswith(REGISTRY):
            if repository not in images_repo_digests: # Only the first digest is saved
                images_repo_digests[repository] = digest

    if not ignore_existing:
        images_repositories = []

    build_commands = []
    push_commands = []
    for challenge in challenges:
        if not os.path.exists(f"{challenge.path}/Dockerfile"):
            if verbose:
                print(f"Skipping {challenge.id} because it has no Dockerfile.")
            continue

        tag = f"{REGISTRY}{challenge.id}"

        if tag in images_repositories:
            if verbose:
                print(f"Image {tag} already in the registry.")
            continue

        build_commands.append(f"sudo docker build -t {tag} {challenge.path}")

        # Push the image to the registry only if it is not already there
        push_commands.append(f"sudo docker push {tag}")

    # Build the images
    with Pool() as pool:
        pool.map(run_command, build_commands)

    # # Push the images to the registry
    with Pool() as pool:
        pool.map(run_command, push_commands)

    # Get the updated images in the registry
    images = subprocess.run("sudo docker images --format '{{.Repository}}__:__{{.Digest}}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    updated_images = []
    for repository in images.stdout.split("\n"):
        if repository.replace("__:__", "") == "":
            continue
        repository, digest = repository.split('__:__')
        if repository.startswith(REGISTRY):
            if repository in images_repo_digests:
                if images_repo_digests[repository] != digest and digest != "" and images_repo_digests[repository] != "":
                    updated_images.append(repository)

    if len(updated_images) > 0:
        print(f"Updated images: {updated_images}")
        update_pods(updated_images)

def clean_cluster():
    '''
    Delete all the resources created by this script.
    '''
    print("Cleaning the cluster...")
    resources = core_v1.list_namespaced_service(namespace=NAMESPACE, label_selector=f"{CTFD_HOST}/managed-by=true")
    print(f"Deleting {len(resources.items)} services...")
    for resource in resources.items:
        core_v1.delete_namespaced_service(namespace=NAMESPACE, name=resource.metadata.name)

    resources = apps_v1.list_namespaced_deployment(namespace=NAMESPACE, label_selector=f"{CTFD_HOST}/managed-by=true")
    print(f"Deleting {len(resources.items)} deployments...")
    for resource in resources.items:
        apps_v1.delete_namespaced_deployment(namespace=NAMESPACE, name=resource.metadata.name)

    print("Cluster cleaned.")

def main(challenges: list[Challenge], build_images: bool, ignore_existing: bool = False):
    '''
    For each challenge, build the image,
    then create a deployment and a service.
    '''
    print(f"Creating resources for {len(challenges)} challenges...")
    try:
        input("Press Enter to continue...")
    except KeyboardInterrupt:
        print("Aborted.")
        return

    deployed_deployments = []
    deployed_services = []
    deployed_hpas = []

    # Build the images
    if build_images:
        build_and_push_images(challenges, ignore_existing)

    # Check if the namespace exists, if not create it
    try:
        core_v1.read_namespace(name=NAMESPACE)
    except Exception as e:
        print(f"Namespace {NAMESPACE} does not exist, creating it...")
        namespace = {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {
                "name": NAMESPACE,
                "labels": {
                    f"{CTFD_HOST}/managed-by": "true"
                }
            }
        }
        core_v1.create_namespace(body=namespace)
        print(f"Namespace {NAMESPACE} created.")

    for challenge in challenges:
        # If the challenge has no Dockerfile, skip it
        if not os.path.exists(f"{challenge.path}/Dockerfile"):
            if verbose:
                print(f"Skipping {challenge.id} because it has no Dockerfile.")
            continue

        containers = [{
            "name": challenge.id,
            "image": f"{REGISTRY}{challenge.id}",
            "ports": [{
                "containerPort": DEFAULT_INTERNAL_PORT
            }],
        }]

        # Create the deployment
        deployment =         {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": challenge.id,
                "namespace": NAMESPACE,
                "labels": {
                    f"{CTFD_HOST}/managed-by": "true"
                }
            },
            "spec": {
                "replicas": 1,
                "selector": {
                    "matchLabels": {
                        "challenge": challenge.id,
                        f"{CTFD_HOST}/managed-by": "true"
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            f"{CTFD_HOST}/managed-by": "true",
                            "challenge": challenge.id
                        }
                    },
                    "spec": {
                        "containers": containers,
                        "restartPolicy": "Always"
                    }
                }
            }
        }

        if verbose:
            print(f"Deployment for {challenge.id}: {deployment}")
        else:
            print(f"Deployment for {challenge.id} created")
        try:
            create_or_update_resource(deployment)
            deployed_deployments.append(challenge)
        except Exception as e:
            print(f"[magenta]Failed to create deployment for {challenge.id}[/magenta]: {e}", file=sys.stderr)

        # Create the HorizontalPodAutoscaler, if the challenge is rated
        if 1 + 1 == 1: # Make this a condition on the challenge to have the script create an autoscaler
            hpa = {
                "apiVersion": "autoscaling/v1",
                "kind": "HorizontalPodAutoscaler",
                "metadata": {
                    "name": challenge.id,
                    "namespace": NAMESPACE,
                    "labels": {
                        f"{CTFD_HOST}/managed-by": "true"
                    }
                },
                "spec": {
                    "scaleTargetRef": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "name": challenge.id
                    },
                    "minReplicas": 1,
                    "maxReplicas": 10,
                    "targetCPUUtilizationPercentage": 80
                }
            }

            if verbose:
                print(f"HorizontalPodAutoscaler for {challenge.id}: {hpa}")
            else:
                print(f"HorizontalPodAutoscaler for {challenge.id} created")
            try:
                create_or_update_resource(hpa)
                deployed_hpas.append(challenge)
            except Exception as e:
                print(f"[magenta]Failed to create HorizontalPodAutoscaler for {challenge.id}[/magenta]: {e}", file=sys.stderr)

        # Create the service
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": challenge.id,
                "namespace": NAMESPACE,
                "labels": {
                    f"{CTFD_HOST}/managed-by": "true"
                }
            },
            "spec": {
                "type": "LoadBalancer",
                "externalTrafficPolicy": "Local",
                "sessionAffinity": "ClientIP",
                "selector": {
                    "challenge": challenge.id
                },
                "ports": [
                    {
                        "protocol": challenge.config.protocol,
                        "port": challenge.port,
                        "targetPort": DEFAULT_INTERNAL_PORT,
                        "nodePort": challenge.port
                    }
                ]
            }
        }

        try:
            create_or_update_resource(service)
            deployed_services.append(challenge)
            if verbose:
                print(f"Service for {challenge.id}: {service} on port {challenge.port}")
            else:
                print(f"Service for {challenge.id}: on port {challenge.port}")
        except Exception as e:
            print(f"[magenta]Failed to create service for {challenge.id}[/magenta]: {e}", file=sys.stderr)

    # Get all the running deployments and delete the ones that are not in the list of deployed challenges
    deployments = apps_v1.list_namespaced_deployment(namespace=NAMESPACE)
    deployments_to_delete = []
    for deployment in deployments.items:
        if deployment.metadata.name not in [challenge.id for challenge in deployed_deployments]:
            deployments_to_delete.append(deployment.metadata.name)

    if len(deployments_to_delete) > 0:
        answer = input(f'Found {len(deployments_to_delete)} deployments to delete: {deployments_to_delete}. Do you want to delete them? [y/N] ')
        if answer.lower() == "y":
            for deployment_name in deployments_to_delete:
                apps_v1.delete_namespaced_deployment(namespace=NAMESPACE, name=deployment_name)
                print(f"Deleted deployment {deployment_name}")

    # Get all the running services and delete the ones that are not in the list of deployed challenges
    services = core_v1.list_namespaced_service(namespace=NAMESPACE)
    services_to_delete = []
    for service in services.items:
        if service.metadata.name not in [challenge.id for challenge in deployed_services]:
            services_to_delete.append(service.metadata.name)

    if len(services_to_delete) > 0:
        answer = input(f'Found {len(services_to_delete)} services to delete: {services_to_delete}. Do you want to delete them? [y/N] ')
        if answer.lower() == "y":
            for service_name in services_to_delete:
                core_v1.delete_namespaced_service(namespace=NAMESPACE, name=service_name)
                print(f"Deleted service {service_name}")

    hpas = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE)
    hpas_to_delete = []
    for hpa in hpas.items:
        if hpa.metadata.name not in [challenge.id for challenge in deployed_hpas]:
            hpas_to_delete.append(hpa.metadata.name)

    if len(hpas_to_delete) > 0:
        answer = input(f'Found {len(hpas_to_delete)} HorizontalPodAutoscalers to delete: {hpas_to_delete}. Do you want to delete them? [y/N] ')
        if answer.lower() == "y":
            for hpa_name in hpas_to_delete:
                core_v1.delete_namespaced_horizontal_pod_autoscaler(namespace=NAMESPACE, name=hpa_name)
                print(f"Deleted HorizontalPodAutoscaler {hpa_name}")

def dict_to_yaml(d: dict, indent: int = 0) -> str:
    result = ""
    for key, value in d.items():
        result += " " * indent + f"{key}:"
        if isinstance(value, dict):
            result += "\n" + dict_to_yaml(value, indent + 2)
        elif isinstance(value, list):
            result += "\n"
            for item in value:
                result += " " * (indent + 2) + "- " + item + "\n"
        else:
            result += f" {value}\n"
    return result

if __name__ == "__main__":
    import argparse
    from scanner import main as scan_challenges
    parser = argparse.ArgumentParser(description="Generate docker-compose.yml from challenges")

    parser.add_argument("-c", "--challenges", help="Path to challenges folder", type=str)

    parser.add_argument("-b", "--build", help="Build the images and push them to the registry", action="store_true")

    parser.add_argument("-i", "--ignore-existing", help="Ignore existing images in the registry (do not overwrite)", action="store_true", default=False)

    parser.add_argument("-v", "--verbose", help="Print the resources to stdout", action="store_true", default=False)

    parser.add_argument("--clean", help="Clean the cluster from all the challenges", action="store_true")

    args = parser.parse_args()

    verbose = args.verbose

    if args.clean:
        answer = input("Are you sure you want to delete all the challenges? [y/N] ")
        if answer.lower() != "y":
            print("Aborted.")
            sys.exit(0)
        clean_cluster()
        sys.exit(0)

    if args.challenges is None:
        challenges = scan_challenges()
    else:
        absolute_path = os.path.abspath(args.challenges)
        input(f"Scanning challenges in {absolute_path}. Press Enter to continue...")
        challenges = scan_challenges(absolute_path)
    main(challenges, args.build, args.ignore_existing)
