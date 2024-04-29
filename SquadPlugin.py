import re
import os
import json
import requests
from datetime import datetime
import logging
from rcon.source import rcon
import asyncio
import aiohttp
from aiohttp import ClientTimeout
import time
import traceback  

# 配置项
config = {
    "WoundFeedMode": False,     # 是否开启被击倒反馈
    "KillFeedMode": False,       # 是否开启被击杀反馈
    "JoinWelcomeMode": False,    # 是否开启进服欢迎
    "SquadTimeLimit": False,     # 是否开启小队游戏时间限制
    "squadlimit": 300,          # 小队游戏时间限制
    "server_ip": "0.0.0.0 28000 RconPassword",  # 服务器IP 端口 密码
    "key": "123123123123",  # Steam API Key；不开小队限制可以不用
    "tqkey": "aaabbbcccddd"  # 心知天气API Key；不开进服欢迎可以不用
}

# 日志配置
logging.basicConfig(filename='squad.log', level=logging.INFO, format='%(levelname)s: %(message)s')

# 记录错误信息
logging.basicConfig(filename='squad.log', level=logging.ERROR, format='%(levelname)s: %(message)s')

# 正则表达式
class Patterns:
    player_damaged = re.compile(r'\[([0-9.:-]+)]\[([ 0-9]*)]LogSquad: Player:(.+) ActualDamage=([0-9.]+) from (.+) \(Online IDs: EOS: ([0-9a-f]{32}) steam: (\d{17}) \| Player Controller ID: ([^ ]+)\)caused by ([A-z_0-9-]+)_C')
    player_died = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquadTrace: \[DedicatedServer](?:ASQSoldier::)?Die\(\): Player:(.+) KillingDamage=(?:-)*([0-9.]+) from ([A-z_0-9]+) \(Online IDs: EOS: ([\w\d]{32}) steam: (\d{17}) \| Contoller ID: ([\w\d]+)\) caused by ([A-z_0-9-]+)_C')
    create_squad = re.compile(r'\[([0-9.:-]+)]\[([ 0-9]*)]LogSquad: (.+) \(Online IDs: EOS: ([0-9a-f]{32}) steam: (\d{17})\) has created Squad (\d+) \(Squad Name: (.+)\) on (.+)')
    player_join = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C .+PersistentLevel\.([^\s]+) \(IP: ([\d.]+) \| Online IDs: EOS: ([0-9a-f]{32}) steam: (\d{17})\)')
    player_join_succeeded = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogNet: Join succeeded: (.+)')
    player_wound = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquadTrace: \[DedicatedServer](?:ASQSoldier::)?Wound\(\): Player:(.+) KillingDamage=(?:-)*([0-9.]+) from ([A-z_0-9]+) \(Online IDs: EOS: ([\w\d]{32}) steam: (\d{17}) \| Controller ID: ([\w\d]+)\) caused by ([A-z_0-9-_]+)')
    round_start = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogWorld: Bringing World \/([A-z]+)\/(?:Maps\/)?([A-z0-9-]+)\/(?:.+\/)?([A-z0-9-]+)(?:\.[A-z0-9-]+)')
    round_end = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquadGameEvents: Display: Team ([0-9]), (.*) \( ?(.*?) ?\) has (won|lost) the match with ([0-9]+) Tickets on layer (.*) \(level (.*)\)!')
    player_leave = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogNet: UChannel::Close: Sending CloseBunch\. ChIndex == [0-9]+\. Name: \[UChannel\] ChIndex: [0-9]+, Closing: [0-9]+ \[UNetConnection\] RemoteAddr: ([\d.]+):[\d]+, Name: EOSIpNetConnection_[0-9]+, Driver: GameNetDriver EOSNetDriver_[0-9]+, IsServer: YES, PC: ([^ ]+PlayerController_C_[0-9]+), Owner: [^ ]+PlayerController_C_[0-9]+, UniqueId: RedpointEOS:([\d\w]+)')
                                
    server_tps = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquad: USQGameState: Server Tick Rate: ([0-9.]+)')


#####################################基础功能部分#####################################
# RCON请求
async def rcon_command(command):
    ip, port, password = config["server_ip"].split(' ')
    port = int(port)
    try:
        response = await asyncio.wait_for(
            rcon(
                f'{command}',
                host=ip, port=port, passwd=password
            ),
            timeout=5  # 设置超时时间为5秒
        )
        if response == None:
            return ("服务器没有返回任何响应，请检查rcon是否设置正确")
        else:
            return (response)  
    except asyncio.TimeoutError:
        return ("连接超时，请检查服务器是否在线")
    except Exception as e:
        return (f"发生错误：{e}")

# 时间格式转换
def timereformat(Time):
        dt = datetime.strptime(Time, '%Y.%m.%d-%H.%M.%S:%f')
        Time = dt.strftime('%Y-%m-%d %H:%M:%S')
        return Time

# 获取玩家信息
async def get_player_info(mode, id, need):
    for ids, info in playerinfos.items():
        if info[mode] == id:
            return info[need]
    return id

# 获取天气信息
def get_weather(ip):
    try:
        location_response = requests.get(f"http://ip-api.com/json/{ip}")
        location_data = location_response.json()
        lat = location_data["lat"]
        lon = location_data["lon"]
        location = f"{lat}:{lon}"
        isp = location_data.get("isp")
        try:
            weather_response = requests.get(f"https://api.seniverse.com/v3/weather/now.json?key={config['tqkey']}&location={location}&language=zh-Hans&unit=c")
            weather_data = weather_response.json()
            user_location = weather_data["results"][0]["location"]["name"]
            weather = weather_data["results"][0]["now"]["text"]
            temperature = weather_data["results"][0]["now"]["temperature"]
            if isp:
                weather_info = f"\n您所在城市{user_location}\n今日天气：{weather}\n当前温度：{temperature}\nISP：{isp}"
            else:
                weather_info = f"\n您所在城市{user_location}\n今日天气：{weather}\n当前温度：{temperature}\n欢迎来到本服务器"
        except Exception as e:
            logging.error(f"Error fetching weather data: {e}")
            weather_info = "欢迎来到本服务器"
    except Exception as e:
        logging.error(f"Error fetching location data: {e}")
        weather_info = "欢迎来到本服务器"

    return weather_info

# 获取玩家游戏时间
async def playtime(steamid):
    key = config["key"]
    data = {
        "steamid": f"{steamid}",
        "appids_filter": [393380]  # 将值改为一个列表
    }
    url = f'https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={key}&format=json&input_json={json.dumps(data)}'
    timeout = ClientTimeout(total=5)  # 5秒超时
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                return await response.json()
    except:
        logging.error(f"Error playtime")
        return None
        

#####################################数据处理部分#####################################
playerinfos = {}
killrecords = {}
players = {}
roundinfo = {}
leaveplayer = []
tps = None
def save_data(data, filename):
    # 先读取原有的内容或创建一个新的空列表或空字典
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        old_data = {}
    else:
        with open(filename, 'r') as f:
            old_data = json.load(f)

    # 将新的内容添加到原有的内容中
    for key, value in data.items():
        if key not in old_data:
            old_data[key] = value
        else:
            # 检查要存储的值是否是列表
            if isinstance(old_data[key], list):
                # 如果是列表，则将新数据添加到列表中
                old_data[key].extend(value)
            elif isinstance(old_data[key], dict):
                # 如果是字典，则将新数据添加到字典中
                old_data[key].update(value)

    # 将所有的内容写入文件
    with open(filename, 'w') as f:
        json.dump(old_data, f, indent=4)
#    data.clear()

#####################################日志处理部分#####################################
# 处理玩家伤害
def handle_player_damaged(line):
    match = Patterns.player_damaged.match(line)
    if match:
        damage_info = f"时间：{match.group(1)} | 玩家：{match.group(5)} {match.group(7)} 使用 {match.group(9)} 对 {match.group(3)} 造成了{float(match.group(4))}伤害"
        return damage_info

# 处理玩家死亡
def handle_player_died(line):
    match = Patterns.player_died.match(line)
    if match:
        vicname = match.group(3).strip()
        attacker_name = asyncio.run(get_player_info('SteamID', match.group(7), 'playername'))
        kill_info = f"时间：{match.group(1)} | 玩家：{vicname} 寄！！！ 击杀人{attacker_name} SteamID:{match.group(7)} 武器:{match.group(9)}（伤害{float(match.group(4))}）"

        # 使用 .setdefault() 方法确保不覆盖现有的数据
        killrecords.setdefault(match.group(7), []).append({
            'Time': match.group(1),
            'VicName': vicname,
            'Weapon': match.group(9),
            'Damage': float(match.group(4))
        })
        if config["KillFeedMode"] == True:
        
            try:
                asyncio.run(kill_feed(attacker_name,vicname,match.group(9)))
            except:
                pass
        return kill_info

# 处理玩家击倒
def handle_player_wound(line):
    match = Patterns.player_wound.match(line)
    if match:
        atksteamid = match.group(7)
        if atksteamid in playerinfos:
            attacker_name = playerinfos[match.group(7)]["playername"]
        else:
            attacker_name = None
        wound_info = f"时间：{match.group(1)} | 玩家：{match.group(3)} 被 {attacker_name} {match.group(7)} 使用{match.group(9)} 击倒了（伤害{float(match.group(4))}）"
        if config["WoundFeedMode"] == True:
            asyncio.run(Wound_feed(attacker_name,match.group(3),match.group(9)))    
        return wound_info

# 处理创建小队
def handle_create_squad(line):
    match = Patterns.create_squad.match(line)
    if match:
        create_squad_info = f"时间：{match.group(1)} | {match.group(8)} 玩家：{match.group(3)} {match.group(5)} 创建了 {match.group(7)} 小队"
        if config["SquadTimeLimit"] == True:
            asyncio.run(time_limit(match.group(5),match.group(3),match.group(7),match.group(8)))
        return create_squad_info

# 处理玩家加入
def handle_player_join(line):
    match = Patterns.player_join.match(line)
    match2 = Patterns.player_join_succeeded.match(line)
    if match:
        uid = match.group(2)
        ip = match.group(4).split(':')[0]
        SteamID = match.group(6)
        EOSID = match.group(5)
        playercontrollerid = match.group(3)
        players[uid] = {"Time": None, "SteamID": SteamID, "EOSID": EOSID, "IP": ip, "playername": None, "playercontrollerid": playercontrollerid}
    if match2 and match2.group(2) in players:
        uid = match2.group(2)
        playername = match2.group(3)
        Time = timereformat(match2.group(1))
        players[uid]["Time"] = Time
        players[uid]["playername"] = playername
        if 'SteamID' in players[uid] and 'EOSID' in players[uid] and 'IP' in players[uid]:
            join_info = f"{Time},{players[uid]['SteamID']},{players[uid]['EOSID']},{players[uid]['IP']},{playername}"
            playerinfos[players[uid]['SteamID']] = {
                'SteamID': players[uid]['SteamID'],
                'playername': playername,
                'EOSID': players[uid]['EOSID'],
                'IP': players[uid]['IP'],
                'playercontrollerid': players[uid]['playercontrollerid']
            }
        if config["JoinWelcomeMode"] == True:
            asyncio.run(join_welcome(players[uid]['IP'],players[uid]['SteamID']))

        return join_info

# 处理玩家离开 
def handle_player_leave(line):
    match = Patterns.player_leave.match(line)
    if match:
        ip = match.group(3)
        steamid = asyncio.run(get_player_info('IP', ip, 'SteamID'))
        playername = asyncio.run(get_player_info('IP', ip, 'playername'))
        leave_info = f"时间：{match.group(1)} | 玩家：{playername} {steamid} 离开了服务器"
        leaveplayer.append(steamid)
        #if steamid in playerinfos:
        #    del playerinfos[steamid]
        return leave_info


# 服务器tps 没有添加到输出
def handle_server_tps(line):
    match = Patterns.server_tps.match(line)
    if match:
        tps = float({match.group(3)})

# 处理回合开始
def handle_round_start(line):
    match = Patterns.round_start.match(line)
    if match and match.group(5) != "TransitionMap":
        round_info = f"时间：{match.group(1)} | 地图：{match.group(5)} 新回合开始"
        return round_info

# 处理回合结束
def handle_round_end(line):
    match = Patterns.round_end.match(line)
    if match and match.group(6) == "won":
        winteam = f"获胜方：{match.group(5)} {match.group(7)}票"
        uid = match.group(2)
        roundinfo[uid] = {"winteam": winteam}
    if match and match.group(6) == "lost":
        lostteam = f"战败方：{match.group(5)} {match.group(7)}票"
        uid = match.group(2)
        winteam = roundinfo[uid]["winteam"]
        mapname = match.group(8)
        round_info = f"时间：{match.group(1)} | {winteam} {lostteam} 地图：{mapname}"
######回合结束清理保存数据######
        save_data(playerinfos, 'playerinfos.json')
        save_data(killrecords, 'killrecords.json')
        for steamid in leaveplayer:
            if steamid in playerinfos:
                del playerinfos[steamid]
        leaveplayer.clear()
        killrecords.clear()
        return round_info

#####################################插件功能部分#####################################
# 进服欢迎信息
async def join_welcome(IP,steamid):
    welcome_info = get_weather(IP)
    await rcon_command(f"AdminWarnPlayer {steamid} {welcome_info}")

# 小队游戏时间限制
async def time_limit(steamid,name,squadid,team):
    response = await playtime(steamid)
    try:
        usertime = response["response"]["games"][0]["playtime_forever"]
        usertime= usertime / 60
        squadlimit = config["squadlimit"]
        if usertime < squadlimit:
            await rcon_command(f"AdminBroadCast {team} 玩家：{name}创建了 {squadid}小队，队长游戏时间{usertime}分钟，未达到{config['squadlimit']}分钟限制，请管理员注意")
    except:
        await rcon_command(f"AdminBroadCast {team} 玩家：{name}创建了 {squadid}小队，未获取到游戏时间，请管理员注意")

# 被击杀反馈
async def kill_feed(atkname,vicname,weapon):
    await rcon_command(f"AdminWarn {vicname} {atkname}使用{weapon}击杀了你")
# 被击倒反馈
async def Wound_feed(atkname,vicname,weapon):
    await rcon_command(f"AdminWarn {vicname} {atkname}使用{weapon}击倒了你")
# 机器人接口


#####################################日志输出部分#####################################
# 将英文处理函数名映射到中文名称
handler_names = {
    'handle_player_damaged': '伤害',
    'handle_player_died': '死亡',
    'handle_create_squad': '建队',
    'handle_player_join': '进服',
    'handle_player_leave': '离开',
    'handle_player_wound': '击倒',
    'handle_round_start': '回合开始',
    'handle_round_end': '回合结束'
}

# 读取并解析日志文件
def read_and_parse_log(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        file.seek(0,2)
        while True:
            line = file.readline()
            if not line:
                time.sleep(0.1)  # 如果没有新行，则等待一段时间再继续尝试读取
                continue
            try:
                parse_line(line)
            except Exception as e:
                # 打印异常信息，但继续执行
                print(f"Error occurred while parsing line: {line}")
                traceback.print_exc()  # 打印异常的堆栈跟踪信息
'''#测试使用
def read_and_parse_log(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
        for line in file:
            parse_line(line)
'''

# 解析日志行
def parse_line(line):
    handlers = [
        handle_player_damaged,
        handle_player_died,
        handle_create_squad,
        handle_player_join,
        handle_player_leave,
        handle_player_wound,
        handle_round_start,
        handle_round_end
    ]
    for handler in handlers:
        try:
            data = handler(line)
            if data:
                handler_name = handler_names.get(handler.__name__, handler.__name__)
                logging.info(f"{handler_name} | {data}")
                print(f"{handler_name} | {data}")
        except Exception as e:
            # 打印异常信息，但继续执行
            print(f"Error occurred while handling line with handler {handler.__name__}: {line}")
            traceback.print_exc()  # 打印异常的堆栈跟踪信息

# 主函数
def main():
    read_and_parse_log('SquadGame.log')

if __name__ == "__main__":
    main()
