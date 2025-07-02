# CTF on Kubernetes

This repository contains the script and the instructions to deploy a CTF platform based on CTFd on Kubernetes, with challenges implemented as Docker containers.

We use this infrastructure for the [Ethical Hacking](https://unitn.coursecatalogue.cineca.it/insegnamenti/2023/50328_642347_96202/2011/50328/10117?annoOrdinamento=2011) course at the University of Trento, Italy.

## Why Kubernetes?

Kubernetes allows us to easily manage and scale our CTF challenges by providing features such as automatic scaling, load balancing, and self-healing, which are essential for running a CTF competition with multiple participants.

## Challenges

Carefully read this README before creating a challenge or deploying the infrastructure.

### Categories folders

The port of the challenge is created from the folder names of form `ID_category`, where the ID is a double-digit number between 7 and 64. This might look like a bad idea, but for our purposes it is very convenient and allows us to easily categorize the challenges and have their ports automatically assigned. For example, we use the following main categories:

- `07_web`
- `08_reverse`
- `09_pwn`
- `10_crypto`

#### Sub-categories folders

Under the main category folder, challenges should be categorized into sub-categories, and their name should be as follows: `ID_category_name`. The ID should be a single-digit number.

For example, all **command injection** challenges should be placed under the `07_web` folder in a sub-folder named `0_command_injection`.

You can find an example of the folder structure in this repository.

#### Challenges folder

The name of the folder of each challenge should follow this format: `ID_name_of_the_challenge`, where the ID is a double-digit number starting from `01`. For example, the first command injection challenge should be placed in a folder named `01_command_injection`.

## How to Create a Challenge

Create the challenge directory in the correct folder based on its category.

Each challenge directory should contain:

- A `config.yaml` file with the following structure:

    ```yaml
    # The title of the challenge, that will be displayed on the platform
    title: Title of the challenge

    # Description of the challenge to be shown on the CTFd interface
    description: Description of the challenge to be shown on the CTFd interface

    # Template for the connection info with the host and port of the challenge, e.g., nc {{host}} {{port}}
    connection_info: http://{{host}}:{{port}} 

    # The flag, CHECK THE REGEX!
    flag: UniTN{[a-zA-Z0-9_?!$.,]+}

    # Points: 100: easy, 200: medium, 300: tough, 400: hard, 500: insane
    points: 500

    # Nickname of the author
    author: author

    # List of docker networks that the challenge should be connected to (see below on how to create a docker network)
    networks:
      - internal

    # List of files that should be downloadable by users on the CTFd interface
    public: 
      - ./src/index.html

    # The type of the challenge, can be either "standard" (default, points do not decrease), or "dynamic" (points decrease after each solve)
    type: standard

    # List of challenges that must be solved for this challenge to be visible by the user
    # each requirement should be in the same category, and should be the unique name of the challenge
    # (i.e. the name of the folder containing this file, e.g. 01_command_injection)
    requires:
      - 01_requirement
    
    # List of hints, having the text and cost fields.
    # The text field can contain some markdown
    # The order is important!
    hints:
      - text: This is a very useful hint # The hint that will be displayed after the user buys it
        cost: 20 # The cost (in user's points) to unlock the hint
    
    # Additional yaml code to be added to the docker-compose
    docker_args:
    ```

- A `src` sub-folder with the challenge files.
- A `Dockerfile` that exposes port 5000 (the final port of the challenge will be set up automatically by the deployer script).
  - Your challenge must also expose the port 5000. Therefore, if you run a server, make sure to make it listen on port 5000.
  - If your challenge does not need a server-side container, you can just avoid creating this file
- A `.gitignore` file specific to your challenge to avoid unnecessary files from being pushed to GitHub.
- If you need some files to be downloadable by users on the CTFd interface, add a list of filenames with a path relative to the challenge directory.
- A `solution` sub-folder with a (preferably markdown) file with the textual solution and, if needed, some scripts that solve the challenge.

### How to create a proper `Dockerfile`

1. Use an **Alpine Linux**-based image (e.g., [https://hub.docker.com/_/alpine](https://hub.docker.com/_/alpine)).

   - If your challenge is in `python`, you might want to use the Python image based on Alpine Linux ([https://hub.docker.com/_/python](https://hub.docker.com/_/python)).

2. Only `COPY` to the container the files that are needed for the challenge.

3. Expose the port 5000 with `EXPOSE 5000`.

4. Make sure that the files in the container are not writable, or more in general, make sure that an attacker cannot disrupt the challenge (e.g., change or delete the flag file or stop the service).

   - For example, you can use the following snippet:

    ```bash
    # Make the /app directory not writeable
    RUN chmod a-w /app
    
    # Create a nonroot user
    RUN adduser -D nonroot && \
        chown nonroot /app
    
    # Make the /static directory writeable
    RUN mkdir /app/static && \
        chown nonroot /app/static

    # ! Important: install the required packages before switching the user

    # Switch to the nonroot user before executing the CMD
    USER nonroot
    ```

5. Make sure that the command specified in `CMD` is the execution of the main script of your challenge (so that if your challenge crashes, that command should fail and the container will be automatically restarted).

## How to Deploy the Challenges

We assume that CTFd is already set up and running (either in the same Kubernetes cluster or in a different way). For more information on how to set up CTFd, please refer to the [CTFd documentation](https://docs.ctfd.io/).

We also assume that a Kubernetes cluster is already set up and a local registry is deployed on it. For more instructions on how to set up a Kubernetes cluster, please refer to [our documentation](./kubernetes/README.md).

1. Pull or copy the whole repository on the server.

2. Make sure to update the `config.env` file with the correct values.

    ```bash
    # The host of the CTFd instance
    CTFD_HOST="example.it"

    # The host of the challenges
    CHALLENGES_HOST="example.it"
    ```

3. Make sure to update the `secrets.env` file with the correct values:

    ```bash
    # CTFd API key
    CTFD_API_KEY="ctfd_aabbccddeeffgghhiijjkkllmmnnooppqqrrssttuuvvwwxxyyzz"
    ```

4. Deploy the challenges on Kubernetes with the following command:

    ```bash
    python ./deployer/kubernetes_deployer.py  --build --challenges path/to/challenges
    ```

    Where `path/to/challenges` is the path to the challenges directory, which should contain the challenges folders as described above. `--build` tells the script to build the Docker images for the challenges and push them to the registry.

5. Update or deploy the challenges on CTFd with the following command:

    ```bash
    ./ctfd_deploy.sh
    ```

### `kubernetes_deployer.py`

This script is responsible for deploying the challenges on Kubernetes. It:

1. Builds the Docker images for the challenges and pushes them to the local registry (if `--build` is passed).
2. Creates the necessary Kubernetes resources to run the challenges and have them accessible from the outside. Specifically, for each challenge, it creates:

   - A `Deployment`: contains the Docker image that will be used to create the pods.
   - A `Service`: exposes the challenge to the outside world, so that it can be accessed from the CTFd platform. This is where the outside port is assigned (based on the folder name of the challenge). The service is of type `LoadBalancer`, so that it can be accessed from the outside world, and it routes traffic to the backend pods based on IP address.
   - Optionally, a `HorizontalPodAutoscaler`: if the challenge is configured to be scalable, it will automatically scale the number of pods based on the CPU usage.

## Authors

This repository is maintained by students at the [University of Trento](https://www.unitn.it/en) and the [Department of Information Engineering and Computer Science](https://www.disi.unitn.it/it). Specifically, it was created by:

- [Carlo Ramponi](https://carloramponi.github.io/)
- [Matteo Golinelli](https://golim.github.io/)
