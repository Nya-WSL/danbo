import requests
import time
import json
import random

class BilibiliDanmakuSender:
    def __init__(self, sessdata, bili_jct):
        """
        初始化发送器
        :param sessdata: 登录Cookie中的SESSDATA
        :param bili_jct: 登录Cookie中的bili_jct (CSRF Token)
        """
        self.session = requests.Session()
        self.cookies = {
            'SESSDATA': sessdata,
            'bili_jct': bili_jct
        }
        self.csrf = bili_jct
    
    def get_danmaku_config(self, room_id):
        """
        获取直播间弹幕配置
        :param room_id: 直播间ID
        :return: 可用的颜色和模式配置
        """
        url = "https://api.live.bilibili.com/xlive/web-room/v1/dM/GetDMConfigByGroup"
        params = {'room_id': room_id}
        
        try:
            response = self.session.get(
                url,
                params=params,
                cookies=self.cookies
            )
            data = response.json()
            
            if data['code'] != 0:
                print(f"获取弹幕配置失败: {data.get('message')}")
                return None
            
            # 解析可用的颜色和模式
            available_colors = []
            available_modes = []
            
            for group in data['data']['group']:
                for color in group['color']:
                    if color['status'] == 1:  # 只收集可用的颜色
                        available_colors.append({
                            'name': color['name'],
                            'color': color['color'],
                            'hex': color['color_hex']
                        })
            
            for mode in data['data']['mode']:
                if mode['status'] == 1:  # 只收集可用的模式
                    available_modes.append({
                        'name': mode['name'],
                        'mode': mode['mode']
                    })
            
            return {
                'colors': available_colors,
                'modes': available_modes
            }
        
        except Exception as e:
            print(f"获取弹幕配置时出错: {str(e)}")
            return None
    
    def set_danmaku_style(self, room_id, color_hex=None, mode=None):
        """
        设置弹幕样式
        :param room_id: 直播间ID
        :param color_hex: 十六进制颜色值 (如ffffff)
        :param mode: 弹幕模式值 (如1)
        :return: 是否设置成功
        """
        url = "https://api.live.bilibili.com/xlive/web-room/v1/dM/AjaxSetConfig"
        
        # 准备请求参数
        data = {
            'room_id': room_id,
            'csrf': self.csrf,
            'csrf_token': self.csrf
        }
        
        if color_hex:
            # 移除可能的0x前缀并转换为小写
            clean_hex = color_hex.lower().replace('0x', '')
            data['color'] = f"0x{clean_hex}"
        elif mode is not None:
            data['mode'] = mode
        else:
            print("必须提供颜色或模式参数")
            return False
        
        try:
            response = self.session.post(
                url,
                data=data,
                cookies=self.cookies
            )
            result = response.json()
            
            if result['code'] == 0:
                print(f"弹幕样式设置成功: {result['data']['msg']}")
                return True
            else:
                print(f"弹幕样式设置失败: {result.get('message')}")
                return False
        
        except Exception as e:
            print(f"设置弹幕样式时出错: {str(e)}")
            return False
    
    def send_danmaku(self, room_id, message, color=16777215, mode=1, fontsize=25):
        """
        发送弹幕
        :param room_id: 直播间ID
        :param message: 弹幕内容
        :param color: 十进制颜色值 (默认白色: 16777215)
        :param mode: 弹幕模式 (默认滚动: 1)
        :param fontsize: 字体大小 (默认25)
        :return: 是否发送成功
        """
        url = "https://api.live.bilibili.com/msg/send"
        
        with open("config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # 准备请求参数
        data = {
            'roomid': room_id,
            'msg': message,
            'rnd': int(time.time()),  # 当前时间戳
            'fontsize': fontsize,
            'color': color,
            'mode': mode,
            'bubble': 0,
            'csrf': self.csrf,
            'csrf_token': self.csrf
        }
        headers = {
        'Cookie': f'SESSDATA={config["SESSDATA"]}; bili_jct={config["bili_jct"]}',
        'Origin': 'https//live.bilibili.com',
        'Referer': f'https://live.bilibili.com/{config["room_id"]}',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
        }

        try:
            response = self.session.post(
                url,
                data=data,
                headers=headers
            )
            result = response.json()
            
            if result['code'] == 0:
                print(f"弹幕发送成功: {message}")
                return True
            elif result['code'] == 10031:
                # 发送频率过快，随机等待后重试
                wait_time = random.uniform(1.0, 3.0)
                print(f"发送频率过快，等待{wait_time:.1f}秒后重试...")
                time.sleep(wait_time)
                return self.send_danmaku(room_id, message, color, mode, fontsize)
            else:
                print(f"弹幕发送失败 (错误码 {result['code']}): {result.get('message')}")
                return False
        
        except Exception as e:
            print(f"发送弹幕时出错: {str(e)}")
            return False