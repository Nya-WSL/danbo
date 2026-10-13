import subprocess

def build():
    subprocess.call(["uv", "run", "package.py", "--name", "danbo", "--windowed", "--icon", "static/logo.ico", "main.py"])

if __name__ == "__main__":
    build()