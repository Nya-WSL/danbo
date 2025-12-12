import requests

def get_log() -> dict:
    url = "http://version.nya-wsl.cn/danbo/changelog.json"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        return {}