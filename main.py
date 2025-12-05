import re
import os
import json
import random
import asyncio
import hashlib
import traceback
import aiohttp, http.cookies
import blivedm.blivedm.models.web as web_models

import apis

from typing import *
from nicegui import ui, app
from blivedm import blivedm

version = "1.0.0"

# ================================
# 初始化配置文件
# ================================

example_config = {
    "room_id": "",
    "host": "127.0.0.1",
    "port": 65020,
    "SESSDATA": "",
    "bili_jct": "",
    "medal_status": False,
    "sc_status": False,
    "danmu_status": True,
    "gift_status": False,
    "medal_level": 0.0,
    "sc_level": 30.0
}

if not os.path.exists("data"):
    os.makedirs("data")

# 检查配置文件状态
# 如配置文件不存在，则注入内置预设
if not os.path.exists("config.json"):
    with open("config.json", "w+", encoding="utf-8") as f:
        json.dump(example_config, f, indent=4, ensure_ascii=False)

if not os.path.exists("data/play_list.json"):
    with open("data/play_list.json", "w+", encoding="utf-8") as f:
        json.dump({"medal": "", "sc": "", "gift": ""}, f, indent=4, ensure_ascii=False)

# 加载配置文件
with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# 检查配置文件缺失项
diff = example_config.keys() - config.keys()

for key in diff:
    config[key] = example_config[key]

# 检查配置文件多余项
diff = config.keys() - example_config.keys()

for key in diff:
    config.pop(key, None)

config["cwd"] = os.getcwd() # 保存工作目录用于debug

with open("config.json", "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=4)

host = config["host"]
port = config["port"]

# 用户配置
ROOM_ID = config["room_id"]
SESSDATA = config["SESSDATA"]
BILI_JCT = config["bili_jct"]

b_connect_status = False

async def start_handler():
    global sender, client

    session: Optional[aiohttp.ClientSession] = None

    # 创建ws
    try:
        cookies = http.cookies.SimpleCookie()
        cookies['SESSDATA'] = SESSDATA
        cookies['SESSDATA']['domain'] = 'bilibili.com'

        session = aiohttp.ClientSession()
        session.cookie_jar.update_cookies(cookies)

        room_id = ROOM_ID
        client = blivedm.BLiveClient(room_id, session=session)
        handler = BiliHandler()
        client.set_handler(handler)
        client.start()

        # 创建发送器实例
        sender = apis.BilibiliDanmakuSender(SESSDATA, BILI_JCT)

        try:
            await client.join()
        finally:
            await client.stop_and_close()

    finally:
        await session.close()

def check_rules(data):
    ...

def request_song(song):
    ...

# 获取弹幕信息
class BiliHandler(blivedm.BaseHandler):
    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        user = message.uname
        msg = message.msg
        split_msg = msg.split(" ")

        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        if split_msg[0] == "点歌" and check_rules(message):
            ...

async def check_b_connect_status():
    global b_connect_status
    switch_value = b_connect_switch.value

    # 开关关闭状态：断开连接
    if switch_value == False:
        # 无房间号且未连接
        if config.get("room_id", "") == "" and not b_connect_status:
            b_connect_switch.set_value(False)
            return

        # 断开连接
        b_connect_status = False
        client.stop() # 断开弹幕服务器ws连接
        print("弹幕服务器ws连接已断开")
        ui.notify("已断开连接，这通常是因为手动关闭了连接或房间号不正确")
        b_connect_switch.set_value(False)
        b_connect_switch.set_text("连接至弹幕服务器")

    # 开关为"null"状态：尝试连接
    if switch_value == "null":
        # 检查房间号
        if not config.get("room_id", ""):
            ui.notify("未填入房间号，无法连接弹幕服务器", type="negative")
            b_connect_switch.set_value(False)
            return

        # 启动连接
        if not b_connect_status:
            asyncio.create_task(start_handler())
            b_connect_switch.set_value("null")
            b_connect_switch.set_text("尝试连接弹幕服务器")
            b_connect_status = True
        else:
            b_connect_switch.set_value(True)

    # 开关打开状态：已连接
    if switch_value == True:
        if not config.get("room_id", ""):
            ui.notify("请输入房间号", type="negative")
            b_connect_switch.set_value(False)
            return

        if not b_connect_status:
            b_connect_switch.set_value("null")


# 管理面板
@ui.page('/')
@ui.page('/nicegui/')
def index():
    global b_connect_switch
    # 打开config.json文件，读取配置
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    # 保存配置函数
    def save_config(config):
        # 打开config.json文件，写入配置
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

# 设置背景
    ui.query('body').style('background: url("static/bg2.jpg") 0px 0px/cover fixed; background-attachment: fixed;')

    # GUI界面
    with ui.card(align_items="center").classes("bg-transparent absolute-center").style("box-shadow: None"):
        with ui.card(align_items="center").classes("bg-transparent"):
            # 按钮组
            with ui.row():
                ui.button('修改歌单', on_click=lambda: ui.navigate.to("playlist"), color="")

            # 开关组
            with ui.row():
                with ui.switch("粉丝勋章", on_change=lambda: save_config(config)).bind_value(config, "medal_status"):
                    ui.tooltip('是否启用粉丝勋章点歌')

                with ui.switch("SC点歌", on_change=lambda: save_config(config)).bind_value(config, "sc_status"):
                    ui.tooltip('是否启用SC点歌')
                
                with ui.switch("弹幕点歌", on_change=lambda: save_config(config)).bind_value(config, "danmu_status"):
                    ui.tooltip('是否启用弹幕点歌')

                with ui.switch("礼物点歌", on_change=lambda: save_config(config)).bind_value(config, "gift_status"):
                    ui.tooltip('是否启用礼物点歌')

            # 配置项
            with ui.input(label="房间号", on_change=lambda: save_config(config)).bind_value(config, "room_id").style("width: 150px"):
                ui.tooltip('需连接的房间号')

            with ui.row():
                with ui.select(label="选择礼物", options=[], on_change=lambda: save_config(config), multiple=True).bind_value(config, "gift_list").style("width: 150px"):
                    ui.tooltip("送什么礼物可以点歌")

            with ui.row():
                with ui.number("勋章等级", on_change=lambda: save_config(config), min=0, value=0.0).bind_value(config, "medal_level").style("width: 150px"):
                    ui.tooltip("粉丝勋章超过多少级可以点歌，0=无限制")

                with ui.number("SC价格", on_change=lambda: save_config(config), min=0, value=0.0).bind_value(config, "sc_level").style("width: 150px"):
                    ui.tooltip("SC金额超过多少可以点歌（元），0=无限制")

            # 连接至直播间
            with ui.row():
                b_connect_switch = ui.switch("连接至弹幕服务器", on_change=lambda: check_b_connect_status()).props('checked-icon="check" color="green" unchecked-icon="clear"')

            # obs浏览器源
            with ui.label(f"obs浏览器源：http://{host}:{port}/show").classes("text-sm italic mt-4").on("click", lambda: ui.clipboard.write(f"http://{host}:{port}/show")).on("click", lambda: ui.notify("已复制至剪贴板", type="info")):
                ui.tooltip("将此地址添加至obs浏览器源以显示当前点歌，点击复制到剪贴板")


@ui.page("/playlist")
def index():
    # 打开config.json文件，读取配置
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    with open("data/play_list.json", "r", encoding="utf-8") as f:
        play_list = json.load(f)

    def format_data(data):
        # 去除多余空格和换行符
        data = re.sub(r'\n', '', data)
        # 处理中文逗号
        data = data.replace('，', ',')
        return data

    # 保存配置函数
    def save_config(file, config):
        # 打开config.json文件，写入配置
        with open(file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

    with ui.card(align_items="center").classes("absolute-center w-2/3").style("height: 90%"):
        medal_input = ui.textarea(label="粉丝勋章歌单", on_change=lambda: save_config("data/play_list.json", play_list)).classes("w-full h-60").bind_value(play_list, "medal", backward=lambda value: format_data(value))

        sc_input = ui.textarea(label="SC歌单", on_change=lambda: save_config("data/play_list.json", play_list)).classes("w-full h-60").bind_value(play_list, "sc", backward=lambda value: format_data(value))

        gift_input = ui.textarea(label="礼物歌单", on_change=lambda: save_config("data/play_list.json", play_list)).classes("w-full h-60").bind_value(play_list, "gift", backward=lambda value: format_data(value))

        with ui.row(align_items="center"):
            ui.button("返回", on_click=lambda: ui.navigate.back())

        ui.label("歌单格式：歌名_歌手，逗号分隔")


@ui.page("/show")
def index():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    with open("data/play_list.json", "r", encoding="utf-8") as f:
        play_list = json.load(f)

    ui.label(f"当前点歌").classes("text-3xl font-bold")


try:
    ui.run(host=host, port=port, title=f"danbo v{version}", reload=True, language="zh-CN", reconnect_timeout=30, storage_secret=f"danbo v{version} secret")
except:
    print(traceback.format_exc())