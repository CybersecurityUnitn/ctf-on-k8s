import os
import re
import sys
from typing import List, Self
import yaml

__author__ = "Carlo Ramponi"
__copyright__ = "Copyright (C) 2025 Carlo Ramponi"
__license__ = "MIT"

CALLENGES_FOLDER = "../challenges"
CATEGORY_REGEX = re.compile(r"([0-9]{2})_(.+)")
SUBCATEGORY_REGEX = re.compile(r"([0-9]{1})_(.+)")
CHALLENGE_REGEX = re.compile(r"([0-9]{2})_(.+)")

class Hint:
    def __init__(self, text: str, points: int):
        self.text: str = text
        self.points: int = points
    
    def fromDict(d: dict) -> Self:
        return Hint(
            text=d["text"],
            points=d["cost"]
        )

class ChallengeConfig:
    def __init__(self,
        title: str,
        description: str,
        connection_info: str,
        protocol: str,
        flag: str,
        points: int,
        author: str,
        networks: list[str],
        public: list[str],
        type: str,
        requires: list[str],
        hints: list[Hint] = [],
        docker_args: dict = None
    ):
        self.title: str = title
        self.description: str = description
        self.connection_info: str = connection_info
        self.protocol: str = protocol
        self.flag: str = flag
        self.points: int = points
        self.author: str = author
        self.networks: List[str] = networks
        self.public: List[str] = public
        self.type: str = type
        self.requires: List[str] = requires
        self.hints: List[Hint] = hints
        self.docker_args: dict = docker_args

    def fromYml(file: str) -> Self:
        with open(file, "r") as f:
            config = yaml.safe_load(f)
            return ChallengeConfig(
                title=config["title"],
                description=config["description"] if "description" in config and config["description"] else "",
                connection_info=config["connection_info"] if "connection_info" in config and config["connection_info"] else "",
                protocol=config["protocol"] if "protocol" in config and config["protocol"] else "TCP",
                flag=config["flag"],
                points=config["points"],
                author=config["author"] if "author" in config and config["author"] else "unitn",
                networks=config["networks"] if "networks" in config and config["networks"] else [],
                public=config["public"] if "public" in config and config["public"] else [],
                type=config["type"] if "type" in config and config["type"] else "standard",
                requires=config["requires"] if "requires" in config and config["requires"] else [],
                hints=map(Hint.fromDict, config["hints"]) if "hints" in config and config["hints"] else [],
                docker_args=config["docker_args"] if "docker_args" in config and config["docker_args"] else None
            )

class Challenge:
    def __init__(self,
        name:str,
        path:str,
        port:int,
        category: str,
        subcategory: str,
        config: ChallengeConfig
    ):
        self.name:str = name
        self.path:str = path
        self.port:int = port
        self.category:str = category
        self.subcategory:str = subcategory
        self.id: str = f"{self.category}-{self.name}"
        self.config: ChallengeConfig = config
    
    def __str__(self) -> str:
        return f"Challenge {self.name}\nPath: {self.path}\nPort: {self.port}\n"

    def __repr__(self) -> str:
        return self.__str__()

def main(challenges_folder=CALLENGES_FOLDER) -> dict[str, list[Challenge]]:
    challenges_folder = os.path.join(os.path.dirname(__file__), challenges_folder)
    folders = [f for f in os.listdir(challenges_folder) if os.path.isdir(os.path.join(challenges_folder, f))]
    challs: list[Challenge] = []

    for category in folders:
        match = CATEGORY_REGEX.match(category)
        
        if match is None:
            print(f"Invalid category name: {category}. Aborting!", file=sys.stderr)
            sys.exit(1)

        category_id = match.group(1)
        category_name = match.group(2)

        subfolders = [f for f in os.listdir(os.path.join(challenges_folder, category)) if os.path.isdir(os.path.join(challenges_folder, category, f))]
        for subcategory in subfolders:
            match = SUBCATEGORY_REGEX.match(subcategory)

            if match is None:
                print(f"Invalid subcategory name: {subcategory} (in category {category_name}). Aborting!", file=sys.stderr)
                sys.exit(1)

            subcategory_id = match.group(1)
            subcategory_name = match.group(2)

            subfolders = [f for f in os.listdir(os.path.join(challenges_folder, category, subcategory)) if os.path.isdir(os.path.join(challenges_folder, category, subcategory, f))]
            for challenge in subfolders:
                match = CHALLENGE_REGEX.match(challenge)

                if match is None:
                    print(f"Invalid challenge name: {challenge} (in subcategory {subcategory_name} in category {category_name}). Aborting!", file=sys.stderr)
                    sys.exit(1)
                
                challenge_id = match.group(1)
                challenge_path = os.path.join(challenges_folder, category, subcategory, challenge)
                challenge_port = int(category_id + subcategory_id + challenge_id)

                try:
                    challenge_config = open(os.path.join(challenge_path, "config.yaml")).read().strip()
                    challenge_config = ChallengeConfig.fromYml(os.path.join(challenge_path, "config.yaml"))
                except FileNotFoundError:
                    print(f"Missing config.yaml in challenge {challenge} (in subcategory {subcategory_name} in category {category_name}). Aborting!", file=sys.stderr)
                    sys.exit(1)
                except yaml.scanner.ScannerError as e:
                    print(f"Invalid config.yaml in challenge {challenge} (in subcategory {subcategory_name} in category {category_name}). Aborting!", file=sys.stderr)
                    sys.exit(1)

                absolute_path = os.path.abspath(challenge_path)

                # Normalise the challenge fields to match /[a-z]([-a-z0-9]*[a-z0-9])?/ (https://docs.docker.com/compose/migrate/#service-container-names)
                challenge_name = re.sub(r"[^a-z0-9]", "-", challenge.lower()) # Replace all non-alphanumeric characters with a dash
                category_name = re.sub(r"[^a-z0-9]", "-", category_name.lower())
                subcategory_name = re.sub(r"[^a-z0-9]", "-", subcategory_name.lower())

                challs.append(Challenge(
                    name=challenge_name,
                    path=absolute_path,
                    port=challenge_port,
                    category=category_name,
                    subcategory=subcategory_name,
                    config=challenge_config
                ))

    return challs

if __name__ == "__main__":
    challs = main()
    for chall in challs:
        print(chall)

