import multiprocessing

multiprocessing.freeze_support()

import os
import re
import json
import asyncio
import requests
import traceback
import aiohttp, http.cookies
import blivedm.blivedm.models.web as web_models

import log
import apis
import styles
import update as danbo_update
import bili_auth_web as bili_auth

from changelog import get_log

from typing import *
from nicegui import ui, app
from blivedm import blivedm
from itertools import islice

version = "1.6.0"

logger = log.logger
logger.debug("version: {}", version)

# ================================
# 初始化配置文件
# ================================

example_config = {
    "room_id": "",
    "host": "127.0.0.1",
    "port": 65100,
    "SESSDATA": "",
    "bili_jct": "",
    "medal_status": False,
    "sc_status": False,
    "danmu_status": True,
    "medal_level": 0.0,
    "sc_level": 30.0,
    "stop_status": False,
    "guard_status": False,
    "song_font_size": "text-5xl",
    "user_font_size": "text-3xl",
    "badge_font_size": "text-xl",
    "marquee_status": False,
    "marquee_time": 20,
    "marquee_count": 4,
    "song_title": "当前点歌",
    "stop_msg": "当前不允许点歌",
    "cwd": ""
}

example_font_size_list = [
    "text-xs",
    "text-sm",
    "text-base",
    "text-lg",
    "text-xl",
    "text-2xl",
    "text-3xl",
    "text-4xl",
    "text-5xl",
    "text-6xl",
    "text-7xl",
    "text-8xl",
    "text-9xl",
]

if not os.path.exists("data"):
    os.makedirs("data")

# 检查配置文件状态
# 如配置文件不存在，则注入内置预设
if not os.path.exists("config.json"):
    with open("config.json", "w+", encoding="utf-8") as f:
        json.dump(example_config, f, indent=4, ensure_ascii=False)

if not os.path.exists("data/font_size.json"):
    with open("data/font_size.json", "w+", encoding="utf-8") as f:
        json.dump(example_font_size_list, f, indent=4, ensure_ascii=False)

if not os.path.exists("data/play_list.json"):
    with open("data/play_list.json", "w+", encoding="utf-8") as f:
        json.dump([], f, indent=4, ensure_ascii=False)

if not os.path.exists("data/black_list.json"):
    with open("data/black_list.json", "w+", encoding="utf-8") as f:
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

b_connect_status = False

app.add_static_files("/static", "static")

async def start_handler():
    global sender, client

    session: Optional[aiohttp.ClientSession] = None

    # 创建ws
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        # 用户配置
        ROOM_ID = config["room_id"]
        SESSDATA = config["SESSDATA"]
        BILI_JCT = config["bili_jct"]

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

def check_rules(data, data_type: str, owner_uid: int = None) -> bool | str:
    """
    检查弹幕是否满足规则

    Args:
        data: blivedm弹幕数据
        data_type: 数据类型："danmu"、"sc"

    Returns:
        满足规则返回True，不满足会返回错误信息，返回False表示忽略该请求
    """
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)

        if config.get("stop_status", False):
            logger.info("点歌已被停止，忽略请求")
            return False

        if owner_uid != None:
            if data.uid == owner_uid:
                return True

        if data.admin:
            return True

        with open("data/black_list.json", "r", encoding="utf-8") as f:
            black_list = json.load(f)

        song = " ".join(data.msg.split(" ")[1:]).strip()

        for i in black_list:
            if re.search(i, song, re.I): # 大小写不敏感
                return f"{song}在黑名单中"

        if config.get("guard_status", False):
            if data.guard_level != 0:
                return True

        if data_type == "danmu":
            if config.get("danmu_status", False):
                if config.get("medal_status", False):
                    if data.medal_room_id == int(config.get("room_id", 0)):
                        if data.medal_level >= config.get("medal_level", 0.0):
                            return True
                        else:
                            return f'{data.uname}佩戴的勋章等级不足{int(config.get("medal_level", 0.0))}'
                    else:
                        return f"{data.uname}佩戴的勋章不属于当前直播间"
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

def load_play_list():
    """读取点歌列表，兼容旧的纯字符串格式条目"""
    with open("data/play_list.json", "r", encoding="utf-8") as f:
        play_list = json.load(f)

    normalized = []
    for item in play_list:
        if isinstance(item, dict) and "song" in item:
            normalized.append({
                "song": str(item.get("song", "")),
                "user": str(item.get("user", "未知")),
            })
        elif isinstance(item, str):
            # 旧格式如 "1 - 歌曲名"，仅去掉开头的序号前缀
            m = re.match(r"^\s*\d+\s*-\s*(.*)$", item)
            normalized.append({"song": m.group(1).strip() if m else item, "user": "未知"})
    return normalized

def request_song(song, user):
    play_list = load_play_list()

    if len(user) > 8:
        user = user[:5] + "..."
    play_list.append({"song": song, "user": user})

    with open("data/play_list.json", "w+", encoding="utf-8") as f:
        json.dump(play_list, f, ensure_ascii=False, indent=4)

    refresh_show_card()

def create_show_card():
    play_list = load_play_list()

    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    # 垂直滚动样式
    vertical_style = f'''
    @keyframes scroll-up {{
        0% {{ transform: translateY(0); }}
        100% {{ transform: translateY(-50%); }}
    }}

    .marquee-container {{
        height: 400px;
        overflow: hidden;
        position: relative;
    }}

    .marquee-content {{
        animation: scroll-up {config.get("marquee_time", 20)}s linear infinite;
    }}

    .marquee-content:hover {{
        animation-play-state: paused;
    }}
    '''

    ui.add_head_html(f'<style>{vertical_style}</style>')

    with ui.column().classes("marquee-container"):
        with ui.column() as marquee_column:
            if len(play_list) > config.get("marquee_count", 4) and config.get("marquee_status", False):
                marquee_column.classes("marquee-content")

                num = 1
                for i in play_list:
                    with ui.row(align_items="end"):
                        ui.label(f"{num}. {i['song']}").classes(f"{config.get("song_font_size", "text-5xl")} font-bold")
                        ui.label(f"{i['user']}").classes(f"{config.get("user_font_size", "text-3xl")} font-bold")
                    num += 1

            # 复制一份实现无缝滚动
            ui.html("<br/>", sanitize=False)
            num = 1
            for i in play_list:
                with ui.row(align_items="end"):
                    ui.label(f"{num}. {i['song']}").classes(f"{config.get("song_font_size", "text-5xl")} font-bold")
                    ui.label(f"{i['user']}").classes(f"{config.get("user_font_size", "text-3xl")} font-bold")
                num += 1

def refresh_show_card():
    try:
        show_card.clear()

        with show_card:
            create_show_card()

    except NameError:
        logger.warning("show_card未创建，跳过刷新")

def create_badge_row():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    if config.get("danmu_status", False):
        ui.badge("弹幕点歌", outline=True).classes(f"{config.get('badge_font_size', 'text-xl')} font-bold")
    if config.get("guard_status", False):
        ui.badge("舰长点歌", outline=True).classes(f"{config.get('badge_font_size', 'text-xl')} font-bold")
    if config.get("sc_status", False):
        ui.badge(f"SC ≥ {int(config.get('sc_level', 0))}￥", outline=True).classes(f"{config.get('badge_font_size', 'text-xl')} font-bold")
    if config.get("medal_status", False):
        ui.badge(f"粉丝勋章 ≥ {int(config.get('medal_level', 0))}级", outline=True).classes(f"{config.get('badge_font_size', 'text-xl')} font-bold")

def refresh_badge_row():
    try:
        badge_row.clear()

        with badge_row:
            create_badge_row()

    except NameError:
        logger.warning("badge_row未创建，跳过刷新")

def create_cmd_badge():
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    ui.badge("点歌指令：点歌 Tell Your World", outline=True).classes(f"{config.get('badge_font_size', 'text-xl')} font-bold")

def refresh_cmd_badge():
    try:
        cmd_badge_row.clear()

        with cmd_badge_row:
            create_cmd_badge()

    except NameError:
        logger.warning("cmd_badge_row未创建，跳过刷新")

def refresh_element():
    refresh_show_card()
    refresh_badge_row()
    refresh_cmd_badge()

def change_song_title(status: bool):
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    if not status:
        song_title_label.set_text(config.get("song_title", "当前点歌"))
        song_title_label.classes(f"{config.get("song_font_size", "text-5xl")} font-bold")
    else:
        song_title_label.set_text(config.get("stop_msg", "当前不允许点歌"))
        song_title_label.classes(f"{config.get("song_font_size", "text-5xl")} font-bold")

def send_danmaku(msg: str):
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)
    sender.send_danmaku(config.get("room_id", 0), msg)

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
        owner_uid = client.room_owner_uid

        logger.debug(f"DANMAKU: {user}: {msg}")

        if split_msg[0] == "点歌":
            status = check_rules(message, "danmu", owner_uid)
            if status == True:
                request_song(" ".join(split_msg[1:]).strip(), user)
            elif status == False:
                return
            else:
                send_danmaku(status)

        if split_msg[0] == "删除":
            if message.admin or message.uid == owner_uid:
                play_list = load_play_list()

                play_list.pop(int(split_msg[1]) - 1)

                with open("data/play_list.json", "w+", encoding="utf-8") as f:
                    json.dump(play_list, f, indent=4, ensure_ascii=False)
                refresh_show_card()

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        price = message.price
        user = message.uname
        msg = message.message
        split_msg = msg.split(" ")

        logger.debug(f"SC: {user}: {msg} ￥{price}")

        if split_msg[0] == "点歌":
            status = check_rules(message, "sc")
            if status == True:
                request_song(" ".join(split_msg[1:]).strip(), user)
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
            if not config.get("SESSDATA", "") and not config.get("bili_jct", ""):
                ui.notify("未登录B站账号，无法连接弹幕服务器", type="negative")
                b_connect_switch.set_value(False)
                return
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
def index():
    global b_connect_switch
    styles.page_styles() # 加载自定义样式
    # 打开config.json文件，读取配置
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    # 保存配置函数
    def save_config(config, file = "config.json"):
        if file == "config.json":
            with open(file, "r", encoding="utf-8") as f:
                old_config = json.load(f)
            for k in old_config:
                if k in config:
                    old_config[k] = config[k]
            config = old_config

        with open(file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

    def play_list_dialog():
        def del_song(song):
            play_list = load_play_list()

            play_list.remove(song)

            with open("data/play_list.json", "w+", encoding="utf-8") as f:
                json.dump(play_list, f, ensure_ascii=False, indent=4)

            refresh_card()
            refresh_show_card()

        def clear_list():
            with open("data/play_list.json", "w+", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)

            refresh_card()
            refresh_show_card()

        def create_card():
            play_list = load_play_list()

            for i in play_list:
                with ui.row().classes("w-full"):
                    ui.label(f'{i["song"]} - {i["user"]}').on("click", lambda i = i: ui.clipboard.write(i["song"])).on("click", lambda: ui.notify("已复制至剪贴板", type="info"))
                    ui.space()
                    ui.button("删除", on_click=lambda i = i: del_song(i))

        def refresh_card():
            play_list_card.clear()
            with play_list_card:
                create_card()

        # 弹窗
        with ui.dialog() as play_list_dialog, ui.card(align_items="center"):
            with ui.card().classes("min-w-60 min-h-60") as play_list_card:
                create_card()
            ui.button("清空", on_click=lambda: clear_list())

        play_list_dialog.open()

    def list_setting_dialog():
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        with open("data/black_list.json", "r", encoding="utf-8") as f:
            black_list = json.load(f)

        with ui.dialog() as list_setting_dialog, ui.card(align_items="center"):
            ui.textarea(label="黑名单关键词（每行一个）", value="\n".join(black_list), on_change=lambda v: save_config(v.value.splitlines(), "data/black_list.json")).style("width: 400px")

            ui.switch("滚动歌单", on_change=lambda v: save_config({"marquee_status": v.value})).bind_value(config, "marquee_status")

            with ui.row():
                with ui.number(label="滚动速度", value=config.get("marquee_time", 20), on_change=lambda v: save_config({"marquee_time": int(v.value)})).style("width: 150px"):
                    ui.tooltip("滚动整个列表需要多少秒")

                with ui.number(label="滚动阈值", value=config.get("marquee_count", 4), on_change=lambda v: save_config({"marquee_count": int(v.value)})).style("width: 150px"):
                    ui.tooltip("当点歌数量超过该值时开始滚动")

            with ui.row():
                ui.input("歌单标题", value=config.get("song_title", "当前点歌"), on_change=lambda v: save_config({"song_title": v.value})).style("width: 150px")

                ui.input("停止标题", value=config.get("stop_msg", "当前不允许点歌"), on_change=lambda v: save_config({"stop_msg": v.value})).style("width: 150px")

            ui.button("保存并关闭", on_click=lambda: list_setting_dialog.close()).on_click(lambda: refresh_show_card())

        list_setting_dialog.open()

    def check_auth(loginInfo):
        status = bili_auth.login(loginInfo[0])

        if status == True:
            ui.notify("登录成功", type="positive")
            try:
                os.remove(loginInfo[1])
            except:
                logger.warning(f"删除{loginInfo[1]}失败")

        else:
            ui.notify(status, type="negative")

    def bili_login():
        if config["room_id"] == "":
            ui.notify("请先填入房间号", type="negative")
            return

        loginInfo = bili_auth.get_qrcode("bili_qrcode")

        with ui.dialog() as auth_dialog, ui.card(align_items="center"):
            qrcode_ui = ui.image(loginInfo[1])
            ui.label("请使用B站APP扫描二维码登录")
            qr_button = ui.button("已扫码", on_click=lambda: check_auth(loginInfo))
            qr_button.on_click(lambda: auth_dialog.close())

        auth_dialog.open()

    def get_version():
        logs = get_log()
        version_flag = False
        num = 0

        if logs != {}:
            for i in logs.keys():
                if not version_flag:
                    num += 1
                if i == version:
                    version_flag = True
            return dict(islice(logs.items(), num - 1))
        else:
            return {}

    # 检查版本更新按钮
    async def check_update():
        async def update(server, status):
            await danbo_update.update(server, status) # 调用更新函数

        def version_dialog():
            with ui.dialog() as dialog, ui.card(align_items="center"):
                ui.label(f"当前版本：{version} | 最新版本：{status}")
                server_select = ui.select(options={"CN-HK": "国内源", "CN-QN": "国内备用源", "GitHub": "GitHub"}, label="选择更新源", value="CN-HK").classes("w-1/2")
                ui.button("更新", on_click=lambda: update(server_select.value, status))
                for k,v in get_version().items():
                    with ui.timeline(side="right", layout="dense", color="btn"):
                        with ui.timeline_entry(title=f"Release of {k}", subtitle=v["date"]):
                            with ui.column().classes("gap-3"):
                                for item in v["content"]:
                                    ui.label(f"● {item}")

            dialog.open()

        def version_check():
            url = ["http://version.nya-wsl.cn/danbo/version.json"]
            try:
                response = requests.get(url[0]) # 优先从Nya-WSL中国服务器获取版本信息
                if response.status_code == 200:
                    data = response.json()
                    latest_version = data["version"]
                else:
                    raise ValueError("From Nya-WSL CN to get version info was error") # 抛出错误
            except Exception as e:
                logger.error(e)
                latest_version = "Error" # 如果请求均失败版本信息设为"Error"

            return latest_version

        status = version_check()

        if status != version:
            if status != "Error":
                with main_card:
                    version_dialog()
            else:
                with main_card:
                    ui.notify("检查更新失败", type="negative")
        else:
            with main_card:
                ui.notify("已是最新版本", type="positive")

    # GUI界面
    with ui.card(align_items="center").classes("absolute-center").style("width: 95%") as main_card:
        asyncio.create_task(check_update())

        # 按钮组
        with ui.row():
            ui.button("登录账号", on_click=lambda: bili_login())
            ui.button("已点列表", on_click=lambda: play_list_dialog())
            ui.button("歌单设置", on_click=lambda: list_setting_dialog())
            ui.button("检查更新", on_click=lambda: check_update())

        # 开关组
        with ui.row():
            with ui.switch("粉丝勋章", on_change=lambda v: save_config({"medal_status": v.value})).bind_value(config, "medal_status").on_value_change(lambda: refresh_badge_row()):
                ui.tooltip('是否启用粉丝勋章点歌')

            with ui.switch("SC点歌", on_change=lambda v: save_config({"sc_status": v.value})).bind_value(config, "sc_status").on_value_change(lambda: refresh_badge_row()):
                ui.tooltip('是否启用SC点歌')

            with ui.switch("弹幕点歌", on_change=lambda v: save_config({"danmu_status": v.value})).bind_value(config, "danmu_status").on_value_change(lambda: refresh_badge_row()):
                ui.tooltip('是否启用弹幕点歌')

        with ui.row():
            with ui.switch("舰长点歌", on_change=lambda v: save_config({"guard_status": v.value})).bind_value(config, "guard_status").on_value_change(lambda: refresh_badge_row()):
                ui.tooltip('启用后舰长点歌无视规则，黑名单和停止点歌除外')

            with ui.switch("停止点歌", on_change=lambda v: save_config({"stop_status": v.value})).on_value_change(lambda v: change_song_title(v.value)).bind_value(config, "stop_status"):
                ui.tooltip('是否停用点歌，启用后将不会响应任何点歌请求')

            # with ui.switch("礼物点歌", on_change=lambda: save_config(config)).bind_value(config, "gift_status"):
            #     ui.tooltip('是否启用礼物点歌')

        # 配置项
        with ui.row():
            with ui.input(label="房间号", on_change=lambda v: save_config({"room_id": v.value})).bind_value(config, "room_id").style("width: 150px"):
                ui.tooltip('需连接的房间号')

            with open("data/font_size.json", "r", encoding="utf-8") as f:
                font_size_list = json.load(f)

        with ui.row():
            with ui.number("勋章等级", on_change=lambda v: save_config({"medal_level": v.value}), min=0, value=0.0).bind_value(config, "medal_level").style("width: 150px").on_value_change(lambda: refresh_badge_row()):
                ui.tooltip("粉丝勋章超过多少级可以点歌，0=无限制")

            with ui.number("SC价格", on_change=lambda v : save_config({"sc_level": v.value}), min=2, value=2).bind_value(config, "sc_level").style("width: 150px").on_value_change(lambda: refresh_badge_row()):
                ui.tooltip("SC金额超过多少可以点歌（元），最低2")

        with ui.row():
            song_font_size_select = ui.select(label="歌名字体", options=font_size_list, on_change=lambda v: save_config({"song_font_size": v.value})).style("width: 150px")
            song_font_size_select.on_value_change(lambda: refresh_show_card())
            song_font_size_select.bind_value(config, "song_font_size")

            user_font_size_select = ui.select(label="用户字体", options=font_size_list, on_change=lambda v: save_config({"user_font_size": v.value})).style("width: 150px")
            user_font_size_select.on_value_change(lambda: refresh_show_card())
            user_font_size_select.bind_value(config, "user_font_size")

            badge_font_size_select = ui.select(label="规则字体", options=font_size_list, on_change=lambda v: save_config({"badge_font_size": v.value})).style("width: 150px")
            badge_font_size_select.on_value_change(lambda: refresh_element())
            badge_font_size_select.bind_value(config, "badge_font_size")

        # with ui.row():
        #     with ui.select(label="选择礼物", options=[], on_change=lambda: save_config(config), multiple=True).bind_value(config, "gift_list").style("width: 150px"):
        #         ui.tooltip("送什么礼物可以点歌")

        # 连接至直播间
        with ui.row():
            b_connect_switch = ui.switch("连接至弹幕服务器", on_change=lambda: check_b_connect_status()).props('checked-icon="check" color="green" unchecked-icon="clear"')

        # obs浏览器源
        with ui.label(f"obs浏览器源：http://{host}:{port}/show").classes("text-sm italic mt-4").on("click", lambda: ui.clipboard.write(f"http://{host}:{port}/show")).on("click", lambda: ui.notify("已复制至剪贴板", type="info")):
            ui.tooltip("将此地址添加至obs浏览器源以显示当前点歌，点击复制到剪贴板")

        ui.badge(text="更新日志", outline=True).on("click", lambda: ui.navigate.to("http://version.nya-wsl.cn/danbo/changelog.json", new_tab=True)).classes("gap-0")

@ui.page("/show")
def index():
    global show_card, song_title_label, badge_row, cmd_badge_row

    styles.page_styles() # 加载自定义样式
    with open("config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    with ui.card(align_items="center").classes("bg-transparent").style("box-shadow: None; left: 50%; transform: translate(-50%, 0%);"): # 居中、背景透明、取消卡片阴影、置顶居中
        if config.get("stop_status", False):
            song_title_label = ui.label(config.get("stop_msg", "当前不允许点歌")).classes(f"{config.get("song_font_size", "text-5xl")} font-bold")
        else:
            song_title_label = ui.label(config.get("song_title", "当前点歌")).classes(f"{config.get("song_font_size", "text-5xl")} font-bold")

        with ui.card(align_items="center").classes("bg-transparent min-w-96") as show_card:
            create_show_card()

        with ui.row() as cmd_badge_row:
            create_cmd_badge()

        with ui.row() as badge_row:
            create_badge_row()

_webview_storage = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "danbo", "webview")
os.makedirs(_webview_storage, exist_ok=True)
app.native.start_args["storage_path"] = _webview_storage

try:
    ui.run(host=host, port=port, title=f"danbo v{version}", reload=False, native=True, language="zh-CN", reconnect_timeout=30, storage_secret=f"danbo v{version} secret", window_size=[600, 600])
except:
    logger.error(traceback.format_exc())