import json
import logging
import os
import secrets
import shutil
import subprocess
import sys

from aiogram import Bot

from manager.config import INSTANCES_DIR, TEMPLATE_DIR

logger = logging.getLogger(__name__)

running_processes = {}


async def fetch_bot_info(token):
    try:
        probe = Bot(token=token)
        info = await probe.get_me()
        await probe.session.close()
        return {"username": info.username, "first_name": info.first_name}
    except Exception as e:
        logger.error(f"could not fetch bot info: {e}")
        return None


def create_instance_dir(user_id):
    path = os.path.join(INSTANCES_DIR, f"{user_id}_{secrets.token_hex(4)}")
    os.makedirs(path, exist_ok=True)
    return path


def setup_instance(instance_dir, bot_token, owner_id):
    for item in os.listdir(TEMPLATE_DIR):
        src = os.path.join(TEMPLATE_DIR, item)
        dst = os.path.join(instance_dir, item)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
        elif os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)

    with open(os.path.join(instance_dir, ".env"), "w") as f:
        f.write(f"BOT_TOKEN={bot_token}\nOWNER_ID={owner_id}\n")

    with open(os.path.join(instance_dir, "data.json"), "w") as f:
        json.dump({"groups": []}, f)


def start_instance(instance_dir) -> bool:
    if not instance_dir or not os.path.exists(instance_dir):
        logger.error(f"instance dir does not exist: {instance_dir}")
        return False

    script = os.path.join(instance_dir, "bot.py")
    if not os.path.exists(script):
        logger.error(f"bot.py missing in {instance_dir}")
        return False

    proc = running_processes.get(instance_dir)
    if proc and proc.poll() is None:
        return True

    try:
        # the handle is left open on purpose, the child owns it until it dies
        log = open(os.path.join(instance_dir, "bot.log"), "a", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-u", script],
            cwd=instance_dir,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    except Exception as e:
        logger.error(f"failed to start instance: {e}")
        return False

    running_processes[instance_dir] = proc
    logger.info(f"started instance {instance_dir}, pid {proc.pid}")
    return True


def stop_instance(instance_dir) -> bool:
    proc = running_processes.get(instance_dir)
    if proc is None:
        return False

    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception as e:
        logger.error(f"failed to stop instance: {e}")
        return False

    del running_processes[instance_dir]
    logger.info(f"stopped instance {instance_dir}")
    return True
