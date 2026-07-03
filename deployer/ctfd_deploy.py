#!/usr/bin/env python3

__author__ = "Carlo Ramponi"
__copyright__ = "Copyright (C) 2025 Carlo Ramponi"
__license__ = "MIT"

from scanner import main as scan_challenges
from scanner import Challenge, Hint
from dotenv import load_dotenv

import argparse
import requests
import logging
import sys
import os
import re

load_dotenv("config.env")
load_dotenv("secrets.env")
CTFD_HOST = os.environ.get("CTFD_HOST")
CTFD_API_KEY = os.environ.get("CTFD_API_KEY")
CHALLENGES_HOST = os.environ.get("CHALLENGES_HOST")

CHALL_ID_REGEX = re.compile(r"\[\]\(ID:(.+)\)")

HEADERS = {
    "Authorization": f"Token {CTFD_API_KEY}",
    "Content-Type": "application/json"
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('CTFd_deploy')

def create_hints(challenge_id: str, hints: list[Hint]):
    # Check if there are hints
    r = requests.get(
        f"https://{CTFD_HOST}/api/v1/challenges/{challenge_id}/hints",
        headers=HEADERS,
    )
    if r.status_code != 200:
        logger.error(f"Failed to fetch hints for challenge {challenge_id}: {r.status_code} {r.text}")
        sys.exit(1)

    existing_hints = r.json()["data"]
    if len(existing_hints) > 0:
        # TODO: implement automagic hint update, be careful to not delete hints that have been bought by users
        logger.info(f"Challenge {challenge_id} already has hints, skipping...")
        logger.info("TIP: automagic hint update is not yet implemented, if you want to update a hint, do it manually on CTFd (and in the config.yaml file)")
        return

    prev_hints_ids = []
    for hint in hints:
        r = requests.post(
            f"https://{CTFD_HOST}/api/v1/hints",
            headers=HEADERS,
            json={
                "challenge_id": f"{challenge_id}",
                "content": f"{hint.text}",
                "cost": f"{hint.points}",
                "requirements": {
                    "prerequisites": prev_hints_ids
                }
            },
        )
        if r.status_code != 200:
            logger.error(f"Failed to create hint for challenge {challenge_id}: {r.status_code} {r.text}")
            sys.exit(1)
        
        prev_hints_ids.append(r.json()["data"]["id"])

def create_flag(challenge_id: str, flag: str):
    # Get the current flag
    r = requests.get(
        f"https://{CTFD_HOST}/api/v1/challenges/{challenge_id}/flags",
        headers=HEADERS,
    )
    if r.status_code != 200:
        logger.error(f"Failed to fetch flags for challenge {challenge_id}: {r.status_code} {r.text}")
        sys.exit(1)

    flags = r.json()["data"]
    if len(flags) == 0:
        # Create flag
        r = requests.post(
            f"https://{CTFD_HOST}/api/v1/flags",
            headers=HEADERS,
            json={
                "challenge_id": f"{challenge_id}",
                "content": f"{flag}",
                "type": "static",
                "data": ""
            },
        )
        if r.status_code != 200:
            logger.error(f"Failed to create flag for challenge {challenge_id}: {r.status_code} {r.text}")
            sys.exit(1)

    else:
        current_flag = flags[0]["content"]
        if current_flag != flag:
            # Update the flag
            r = requests.patch(
                f"https://{CTFD_HOST}/api/v1/flags/{flags[0]['id']}",
                headers=HEADERS,
                json={
                    "content": f"{flag}",
                },
            )
            if r.status_code != 200:
                logger.error(f"Failed to update flag for challenge {challenge_id}: {r.status_code} {r.text}")
                sys.exit(1)

def upload_files(challenge_id: str, challenge: Challenge):
    # Get the file list and delete them all
    r = requests.get(
        f"https://{CTFD_HOST}/api/v1/challenges/{challenge_id}/files",
        headers=HEADERS,
    )
    if r.status_code != 200:
        logger.error(f"Failed to fetch files for challenge {challenge_id}: {r.status_code} {r.text}")
        sys.exit(1)

    files = r.json()["data"]
    for file in files:
        r = requests.delete(
            f"https://{CTFD_HOST}/api/v1/files/{file['id']}",
            headers=HEADERS,
        )
        if r.status_code != 200:
            logger.error(f"Failed to delete file {file['id']}: {r.status_code} {r.text}")
            sys.exit(1)

    # Upload files
    if challenge.config.public is not None:
        for file in challenge.config.public:
            r = requests.post(
                f"https://{CTFD_HOST}/api/v1/files",
                headers={
                    "Authorization": f"Token {CTFD_API_KEY}",
                },
                data={
                    "challenge": f"{challenge_id}",
                    "type": "challenge",
                },
                files={
                    "file": (os.path.basename(file), open(os.path.join(challenge.path, file), "rb")),
                }
            )
            if r.status_code != 200:
                logger.error(f"Failed to upload file {file} for challenge {challenge_id}: {r.status_code} {r.text}")
                sys.exit(1)

def set_requirement(challenge_id: str, requires: list[str]):
    r = requests.patch(
        f"https://{CTFD_HOST}/api/v1/challenges/{challenge_id}",
        headers=HEADERS,
        json={
            "requirements": {
                "prerequisites": requires
            },
        },
    )
    if r.status_code != 200:
        logger.error(f"Failed to set requirements for challenge {challenge_id}: {r.status_code} {r.text}")
        sys.exit(1)

def deploy_challenge(challenge: Challenge, challenge_id: str | None = None) -> str:

    description = challenge.config.description
    description += f"\n\nAuthor: **{challenge.config.author}**"
    description += f"\n[](ID:{challenge.id})"

    category = f"{challenge.category.title()} - {challenge.subcategory.title()}".replace("_", " ")

    connection_info = challenge.config.connection_info.replace("{{host}}", CHALLENGES_HOST).replace("{{port}}", str(challenge.port))

    MINIMUM_AFTER = 20

    body = {
        "name": challenge.config.title,
        "category": category,
        "description": description,
        "connection_info": connection_info,
        "state": "hidden",
        "max_attempts": 0
    }

    if challenge.config.type == "dynamic":
        body["type"] = "dynamic"
        body["initial"] = challenge.config.points
        body["function"] = "linear"
        body["decay"] = (challenge.config.points - 100) // MINIMUM_AFTER
        body["minimum"] = 100
    else:
        body["type"] = "standard"
        body["value"] = challenge.config.points


    if challenge_id is None:
        # Create challenge
        r = requests.post(
            f"https://{CTFD_HOST}/api/v1/challenges",
            headers=HEADERS,
            json=body,
        )
        if r.status_code != 200:
            logger.error(f"Failed to create challenge {challenge.name} in category {category}: {r.status_code} {r.text}")
            sys.exit(1)
        challenge_id = r.json()["data"]["id"]
    else:
        # Patch challenge
        body.pop("state")
        r = requests.patch(
            f"https://{CTFD_HOST}/api/v1/challenges/{challenge_id}",
            headers=HEADERS,
            json=body,
        )
        if r.status_code != 200:
            logger.error(f"Failed to update challenge {challenge.name} in category {category}: {r.text}")
            sys.exit(1)

    create_flag(challenge_id, challenge.config.flag)
    upload_files(challenge_id, challenge)
    create_hints(challenge_id, challenge.config.hints)
    
    return challenge_id

def get_challenge(challenge_id: int) -> dict:
    r = requests.get(
        f"https://{CTFD_HOST}/api/v1/challenges/{challenge_id}",
        headers=HEADERS,
    )
    if r.status_code != 200:
        logger.error(f"Failed to fetch challenge {challenge_id}: {r.status_code} {r.text}")
        sys.exit(1)

    chall = r.json()["data"]
    chall_id = CHALL_ID_REGEX.search(chall["description"]).group(1)
    logger.debug(f"Identified existing challenge {chall_id} (id: {challenge_id})")
    return (chall["id"], chall_id)

def get_challenges() -> list:
    r = requests.get(
        f"https://{CTFD_HOST}/api/v1/challenges",
        headers=HEADERS,
        params={
            "view": "admin"
        }
    )
    if r.status_code != 200:
        logger.error(f"Failed to fetch challenges: {r.status_code} {r.text}")
        sys.exit(1)

    challenges = r.json()["data"]

    ret = dict()
    for challenge in challenges:

        c = get_challenge(challenge["id"])
        ret[c[1]] = c[0]

    return ret

def main(challenges: list[Challenge]):

    logger.info("Fetching existing challenges...")
    existing_challenges = get_challenges()
    logger.info(f"Found {len(existing_challenges)} existing challenges")

    processed_challenges = dict()

    # Deploy challenges
    for challenge in challenges:
        logger.info(f"Deploying {challenge.name}...")
        if challenge.id in existing_challenges:
            logger.info(f"Challenge {challenge.id} already exists, updating it...")
            c_id = deploy_challenge(challenge, existing_challenges[challenge.id])
            existing_challenges.pop(challenge.id)
        else:
            c_id = deploy_challenge(challenge)
        processed_challenges[challenge.id] = c_id
    
    # Set requirements
    for challenge in challenges:
        if challenge.config.requires is not None:
            logger.info(f"Setting requirements for {challenge.id}...")
            requires = []
            for req in challenge.config.requires:
                req = req.replace("_", "-")
                req_id = f"{challenge.category}-{req}"
                if req_id not in processed_challenges:
                    req_id = f"{challenge.category}-{re.sub(r'^\\d{2}-', '', req)}"
                if req_id not in processed_challenges:
                    logger.error(f"Cannot resolve requirement '{req}' for challenge '{challenge.id}'")
                    sys.exit(1)
                requires.append(processed_challenges[req_id])
            set_requirement(
                processed_challenges[challenge.id],
                requires
            )

    # Delete challenges that are not in the config
    for challenge_id in existing_challenges.values():
        answer = input(f"Delete challenge {challenge_id}? [y/N] ").lower()
        if answer != "y":
            continue
        logger.info(f"Deleting challenge {challenge_id}...")
        r = requests.delete(
            f"https://{CTFD_HOST}/api/v1/challenges/{challenge_id}",
            headers=HEADERS,
        )
        if r.status_code != 200:
            logger.error(f"Failed to delete challenge {challenge_id}: {r.text}")
            sys.exit(1)

if __name__ == "__main__": 
    parser = argparse.ArgumentParser(description="Deploy challenges to CTFd")
    parser.add_argument("-k", "--key", help="CTFd API key", required=False)
    parser.add_argument("-d", "--debug", help="Enable debug logging", action="store_true", required=False)
    parser.add_argument("-c", "--challenges", help="Path to challenges folder", type=str)

    args = parser.parse_args()

    if args.key is not None:
        CTFD_API_KEY = args.key
    if args.debug:
        logger.setLevel(logging.DEBUG)

    if args.challenges is None:
        challenges = scan_challenges()
    else:
        absolute_path = os.path.abspath(args.challenges)

        input(f"Scanning challenges in {absolute_path}. Press Enter to continue...")
        challenges = scan_challenges(absolute_path)
    main(challenges)
