#!/usr/bin/env python3
import os
import subprocess
import sys


def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    print("starting manager bot...")
    subprocess.run([sys.executable, "manager/manager_bot.py"])


if __name__ == "__main__":
    main()
