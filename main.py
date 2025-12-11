import os
import json
import asyncio
import traceback
import aiohttp, http.cookies
import blivedm.blivedm.models.web as web_models

import log
import apis

from typing import *
from nicegui import ui
from blivedm import blivedm

version = "1.0.0"

logger = log.logger
logger.debug("version: {}", version)

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
        json.dump([], f, indent=4, ensure_ascii=False)

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

def check_rules(data, data_type: str):
    """
    检查弹幕是否满足规则

    Args:
        data: blivedm弹幕数据
        data_type: 数据类型："danmu"、"sc"

    Returns:
        满足规则返回True，不满足会返回错误信息
    """
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        if data.admin:
            return True

        if data_type == "danmu":
            if config.get("danmu_status", False):
                if config.get("medal_status", False):
                    if data.medal_level >= config.get("medal_level", 0.0):
                        if data.medal_room_id == int(config.get("room_id", 0)):
                            return True
                        else:
                            return f"{data.uname}佩戴的勋章不属于当前直播间"
                    else:
                        return f'{data.uname}佩戴的勋章等级不足{config.get("medal_level", 0.0)}'
                else:
                    return True

        if data_type == "sc":
            if config.get("sc_status", False):
                if data.price >= config.get("sc_level", 0.0):
                    return True
                else:
                    return f'SC不足￥{config.get("sc_level", 0.0)}'

        # if data_type == "gift":
        #     if config.get("gift_status", False):
        #         if data.gift_name in config.get("gift_list", []):
        #             return True

    except Exception as e:
        return f"规则错误：{e}"

def request_song(song, artist, user):
    with open("data/play_list.json", "r", encoding="utf-8") as f:
        play_list = json.load(f)

    if artist != "":
        play_list.append(f"{song} - {artist} - {user}")
    else:
        play_list.append(song)

    with open("data/play_list.json", "w+", encoding="utf-8") as f:
        json.dump(play_list, f, ensure_ascii=False, indent=4)

    refresh_show_card()

def create_show_card():
    with open("data/play_list.json", "r", encoding="utf-8") as f:
        play_list = json.load(f)

    ui.label(f"当前点歌").classes("text-3xl font-bold")

    for i in play_list:
        ui.label(i)

def refresh_show_card():
    show_card.clear()
    with show_card:
        create_show_card()

def send_danmaku(msg: str):
    asyncio.create_task(sender.send_danmaku(config.get("room_id", 0), msg))

# 获取弹幕信息
class BiliHandler(blivedm.BaseHandler):
    heart_count = 0
    # 心跳数据
    def _on_heartbeat(self, client: blivedm.BLiveClient, message: web_models.HeartbeatMessage):
        self.heart_count += 1
        logger.info("触发心跳")
        if self.heart_count == 1:
            b_connect_switch.set_value(True)
            b_connect_switch.set_text("已连接弹幕服务器")
            logger.info(f"已连接至{client.room_id}")

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        user = message.uname
        msg = message.msg
        split_msg = msg.split(" ")

        logger.debug(f"DANMAKU: {user}: {msg}")

        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        if split_msg[0] == "点歌":
            status = check_rules(message, "danmu")
            if status == True:
                request_song(split_msg[1], split_msg[2] if len(split_msg) > 2 else "", user)
            elif status == False:
                return
            else:
                send_danmaku(status)

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        price = message.price
        user = message.uname
        msg = message.message
        split_msg = msg.split(" ")

        logger.debug(f"SC: {user}: {msg} ￥{price}")

        if split_msg[0] == "点歌":
            status = check_rules(message, "sc")
            if status == True:
                request_song(split_msg[1], split_msg[2] if len(split_msg) > 2 else "", user)
            elif status == False:
                return
            else:
                send_danmaku(status)

async def check_b_connect_status():
    global b_connect_status
    switch_value = b_connect_switch.value

    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    # 开关关闭状态：断开连接
    if switch_value == False:
        # 无房间号且未连接
        if config.get("room_id", "") == "" and not b_connect_status:
            b_connect_switch.set_value(False)
            return

        # 断开连接
        b_connect_status = False
        client.stop() # 断开弹幕服务器ws连接
        logger.info("弹幕服务器ws连接已断开")
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

    def play_list_dialog():
        def del_song(song):
            with open("data/play_list.json", "r", encoding="utf-8") as f:
                play_list = json.load(f)

            play_list.remove(song)

            with open("data/play_list.json", "w+", encoding="utf-8") as f:
                json.dump(play_list, f, ensure_ascii=False, indent=4)

            refresh_card()
            refresh_show_card()

        def create_card():
            with open("data/play_list.json", "r", encoding="utf-8") as f:
                play_list = json.load(f)

            for i in play_list:
                with ui.row().classes("w-full"):
                    ui.label(i)
                    ui.space()
                    ui.button("删除", on_click=lambda i = i: del_song(i))

        def refresh_card():
            play_list_card.clear()
            with play_list_card:
                create_card()

        # 弹窗
        with ui.dialog() as play_list_dialog, ui.card(align_items="center"):
            with ui.card().classes("w-full") as play_list_card:
                create_card()

        play_list_dialog.open()

    # GUI界面
    with ui.card(align_items="center").classes("absolute-center"):
        # 按钮组
        with ui.row():
            ui.button("登录账号")
            ui.button("已点列表", on_click=lambda: play_list_dialog())

        # 开关组
        with ui.row():
            with ui.switch("粉丝勋章", on_change=lambda: save_config(config)).bind_value(config, "medal_status"):
                ui.tooltip('是否启用粉丝勋章点歌')

            with ui.switch("SC点歌", on_change=lambda: save_config(config)).bind_value(config, "sc_status"):
                ui.tooltip('是否启用SC点歌')
            
            with ui.switch("弹幕点歌", on_change=lambda: save_config(config)).bind_value(config, "danmu_status"):
                ui.tooltip('是否启用弹幕点歌')

            # with ui.switch("礼物点歌", on_change=lambda: save_config(config)).bind_value(config, "gift_status"):
            #     ui.tooltip('是否启用礼物点歌')

        # 配置项
        with ui.input(label="房间号", on_change=lambda: save_config(config)).bind_value(config, "room_id").style("width: 150px"):
            ui.tooltip('需连接的房间号')

        # with ui.row():
        #     with ui.select(label="选择礼物", options=[], on_change=lambda: save_config(config), multiple=True).bind_value(config, "gift_list").style("width: 150px"):
        #         ui.tooltip("送什么礼物可以点歌")

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

@ui.page("/show")
def index():
    global show_card

    with ui.card(align_items="center").classes("bg-transparent").style("box-shadow: None; left: 50%; transform: translate(-50%, 0%);") as show_card: # 居中、背景透明、取消卡片阴影、置顶居中
        create_show_card()


try:
    ui.run(host=host, port=port, title=f"danbo v{version}", reload=False, native=True, language="zh-CN", reconnect_timeout=30, storage_secret=f"danbo v{version} secret")
except:
    logger.error(traceback.format_exc())