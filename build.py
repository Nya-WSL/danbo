import os
import time
import shutil

def build():
    os.system("poetry run python package.py --name danbo --windowed --icon static/logo.ico main.py")

if __name__ == "__main__":
    build()