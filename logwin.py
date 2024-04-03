import re
import time
import os
from rcon.source import Client
import mysql.connector
import json
import requests
import threading
from datetime import datetime


WoundFeedMode = False     # 是否开启被击倒反馈
KillFeedMode = True      # 是否开启被击杀反馈
#上面这两建议只开一个

JoinWelcomeMode = True   # 是否开启进服欢迎
SquadTimeLimit = True    # 是否开启小队游戏时间限制(小于squadlimit小时黄字提醒op)
squadlimit = 300         # 小队游戏时间限制
server_ip = "ip port password"# 服务器IP 端口 密码
#格式：server_ip = "180.188.1.1 1234 password"
key = "" # Steam API Key
tqkey = "" # 心知天气API Key，自行进入官网申请

killnumber = {}     # 记录击杀数和对应的name，steamid，killnumber
playerinfos = {}    # 记录玩家信息，SteamID,playername,EOSID,ip

def tail(filename):
    with open(filename, 'r', encoding='utf-8', errors='ignore') as file:
        file.seek(0,2)  # 移动到文件的末尾
        while True:
            line = file.readline()
            if not line:  # 如果没有新的行，等待一段时间再试
                time.sleep(0.1)
                continue
            yield line

def mysql_write(mode, **kwargs):
        cnx = mysql.connector.connect(user='root', password='Wyc011205.', host='localhost', database='Squad')

        cursor = cnx.cursor()

        columns = ', '.join(kwargs.keys())
        placeholders = ', '.join(['%s'] * len(kwargs))
        query = f"INSERT INTO {mode} ({columns}) VALUES ({placeholders})"

        values = tuple(kwargs.values())
        cursor.execute(query, values)

        cnx.commit()
        cursor.close()
        cnx.close()

def handle_timeout():
    raise TimeoutError()

def rcon(command, id, info):
    ip, port, psw = server_ip.split(' ')
    port = int(port)  # 将端口号从字符串转换为整数
    timer = threading.Timer(5, handle_timeout)  # 设置一个5秒的定时器
    timer.start()
    try:
        with Client(ip, port, passwd=psw) as client:
            response = client.run(f'{command} {id} {info}')

        if response == None:
            print ("服务器没有返回任何响应，请检查rcon是否设置正确")
        else:
            print (response)  
    except TimeoutError:
        print ("连接超时，请检查服务器是否在线")
    finally:
        timer.cancel()  # 取消定时器

def get_weather(ip):
    try:
        location_response = requests.get(f"http://ip-api.com/json/{ip}")
        location_data = location_response.json()
    #    print(location_data)
        lat = location_data["lat"]
        lon = location_data["lon"]
        location = f"{lat}:{lon}"
        try:
            isp = location_data["isp"]
            org = location_data["org"]
        except:
            isp = None
            org = None
    except:
        location = ip
        isp = None
        org = None

    
    weather_response = requests.get(f"https://api.seniverse.com/v3/weather/now.json?key={tqkey}&location={location}&language=zh-Hans&unit=c")
    weather_data = weather_response.json()
#    print (weather_data)
    userlocation = weather_data["results"][0]["location"]["name"]
    weather = weather_data["results"][0]["now"]["text"]
    teamperature = weather_data["results"][0]["now"]["temperature"]
    if isp != None and org != None:
        weatherinfo = f"\n您所在城市{userlocation}\n今日天气：{weather}\n当前温度：{teamperature}\nISP：{isp}\nORG：{org}"
    else:
        weatherinfo = f"\n您所在城市{userlocation}\n今日天气：{weather}\n当前温度：{teamperature}"
    return weatherinfo

def playtime(key, steamid):
    data = {
        "steamid": f"{steamid}",
        "appids_filter": [393380]  # 将值改为一个列表
    }
    url = f'https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={key}&format=json&input_json={json.dumps(data)}'
    response = requests.get(url)
    response = response.json()
    return response

def timereformat(Time):
        dt = datetime.strptime(Time, '%Y.%m.%d-%H.%M.%S:%f')
        Time = dt.strftime('%Y-%m-%d %H:%M:%S')
        return Time

class PlayerDamaged:
    def __init__(self):
        self.regex = re.compile(r'\[([0-9.:-]+)]\[([ 0-9]*)]LogSquad: Player:(.+) ActualDamage=([0-9.]+) from (.+) \(Online IDs: EOS: ([0-9a-f]{32}) steam: (\d{17}) \| Player Controller ID: ([^ ]+)\)caused by ([A-z_0-9-]+)_C')

    def on_match(self, line):
        match = self.regex.match(line)
        if match:
            damageinfo = f"时间：{match.group(1)} | 玩家：{match.group(5)} {match.group(7)} 使用 {match.group(9)} 对 {match.group(3)}造成了{float(match.group(4))}伤害"
            return damageinfo

class PlayerDied:
    def __init__(self):
        self.regex = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquadTrace: \[DedicatedServer](?:ASQSoldier::)?Die\(\): Player:(.+) KillingDamage=(?:-)*([0-9.]+) from ([A-z_0-9]+) \(Online IDs: EOS: ([\w\d]{32}) steam: (\d{17}) \| Contoller ID: ([\w\d]+)\) caused by ([A-z_0-9-]+)_C')

    def on_match(self, line):
        match = self.regex.match(line)
        if match:
            '''
            data = {
                'raw': match.group(0),
                'time': match.group(1),
                'chainID': match.group(2),
                'victimName': match.group(3),
                'damage': float(match.group(4)),
                'attackerName': match.group(5),
                'attackerEOSID': match.group(6),
                'attackerSteamID': match.group(7),
                'attackerController': match.group(8),
                'weapon': match.group(9)
            }
            '''
            killinfo = f"时间：{match.group(1)} | 玩家：{match.group(3)} 寄！！！ 击杀人{match.group(7)} {match.group(6)}"
            Time = timereformat(match.group(1))
            victimName = match.group(3)
            attackerName = match.group(5)
            attackerEOSID = match.group(6)
            attackerSteamID = match.group(7)
            weapon = match.group(9)
            mode = "kill_data"
            #mysql_write(mode,Time,victimName,attackerName,attackerEOSID,attackerSteamID,weapon)
            killnumber[attackerSteamID] = killnumber.get(attackerSteamID,0) + 1
            with open('kill.json', 'w') as file:
                json.dump(killnumber, file, indent=4)
            try:
                attackerName = playerinfos[match.group(7)]["playername"]
            except:
                attackerName = match.group(7)    
            if KillFeedMode == True:
                if " " in match.group(3):
                    name = match.group(3).split(' ')[1]
                else:
                    name = match.group(3)
                KillFeed = f"你被【{attackerName}】使用{match.group(9)}击杀了（伤害{float(match.group(4))}）"
                rcon("AdminWarn",match.group(3),KillFeed)
                print (f"Log: AdminWarn {name} {KillFeed}")
            return killinfo

class CreatSquad:
    def __init__(self):
        self.regex = re.compile(r'\[([0-9.:-]+)]\[([ 0-9]*)]LogSquad: (.+) \(Online IDs: EOS: ([0-9a-f]{32}) steam: (\d{17})\) has created Squad (\d+) \(Squad Name: (.+)\) on (.+)')
    def on_match(self, line):
        match = self.regex.match(line)
        if match:
            CreatSquadinfo = f"时间：{match.group(1)} | {match.group(8)}  玩家：{match.group(3)} {match.group(5)}创建了 {match.group(7)}小队"
            response = playtime(key,f"match.group(5)")
            if SquadTimeLimit == True:
                try:
                    usertime = response["response"]["games"][0]["playtime_forever"]
                    usertime= usertime / 60
                    if usertime < squadlimit:
                        rcon(f"AdminBroadCast",f"{match.group(8)} 玩家：{match.group(3)}创建了 {match.group(7)}小队，游戏时间低于{squadlimit}小时，请管理员处理")
                        print (f"Log: AdminBroadCast {match.group(8)} 玩家：{match.group(3)}创建了 {match.group(7)}小队，游戏时间低于{squadlimit}小时，请管理员处理")
                except:
                    rcon(f"AdminBroadCast",f"{match.group(8)} 玩家：{match.group(3)}创建了 {match.group(7)}小队，无法获取玩家游戏时间，请管理员确认")
                    print (f"Log: AdminBroadCast {match.group(8)} 玩家：{match.group(3)}创建了 {match.group(7)}小队，无法获取玩家游戏时间，请管理员确认")
            else:
                pass
            return CreatSquadinfo
        
class PlayerJoin:
        def __init__(self):
                self.regex1 = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquad: PostLogin: NewPlayer: BP_PlayerController_C .+PersistentLevel\.([^\s]+) \(IP: ([\d.]+) \| Online IDs: EOS: ([0-9a-f]{32}) steam: (\d{17})\)')
                self.regex2 = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogNet: Join succeeded: (.+)')
                self.players = {}

        def on_match(self, line):
                match1 = self.regex1.match(line)
                if match1:
                        uid = match1.group(2)
                        ip = match1.group(4).split(':')[0]
                        SteamID = match1.group(6)
                        EOSID = match1.group(5)
                        self.players[uid] = {"Time": None, "SteamID": SteamID, "EOSID": EOSID, "IP": ip, "playername": None}

                match2 = self.regex2.match(line)
                if match2 and match2.group(2) in self.players:
                        uid = match2.group(2)
                        playername = match2.group(3)
                        Time = timereformat(match2.group(1))
                        self.players[uid]["Time"] = Time
                        self.players[uid]["playername"] = playername
                        if 'SteamID' in self.players[uid]:
                            PlayerIPinfo = f"{Time},{self.players[uid]['SteamID']},{self.players[uid]['EOSID']},{self.players[uid]['IP']},{playername}"
                            playerinfos[self.players[uid]['SteamID']] = {
                                'SteamID': self.players[uid]['SteamID'],
                                'playername': playername,
                                'EOSID': self.players[uid]['EOSID'],
                                'IP': self.players[uid]['IP']
                            }
                        with open('playerinfos.json', 'w') as file:
                            json.dump(playerinfos, file, indent=4) 
                        #mysql_write("player_data",Time = Time,SteamID = self.players[uid]['SteamID'],EOSID = self.players[uid]['EOSID'],IP = self.players[uid]['IP'],playername = playername)                   
                        if JoinWelcomeMode == True:
                            weatherinfo = get_weather(ip)
                            WelcomeInfo = f"{weatherinfo}\n欢迎{playername}进入服务器"
                            rcon(f"AdminWarn",match1.group(6),WelcomeInfo)
                            print (f"Log: AdminWarn {match1.group(6)} 进服欢迎")
                        return PlayerIPinfo

class PlayerWound:
    def __init__(self):
        self.regex = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquadTrace: \[DedicatedServer](?:ASQSoldier::)?Wound\(\): Player:(.+) KillingDamage=(?:-)*([0-9.]+) from ([A-z_0-9]+) \(Online IDs: EOS: ([\w\d]{32}) steam: (\d{17}) \| Controller ID: ([\w\d]+)\) caused by ([A-z_0-9-_]+)')
    def on_match(self, line):
        match = self.regex.match(line)
        if match:
            try:
                attackerName = playerinfos[match.group(7)]["playername"]
            except:
                attackerName = match.group(7)         
            Woundinfo = f"时间：{match.group(1)} | 玩家：{match.group(3)} 被 {attackerName} {match.group(7)} 使用{match.group(9)} 击倒了（伤害{float(match.group(4))}）"
            if WoundFeedMode == True:
                if " " in match.group(3):
                    name = match.group(3).split(' ')[1]
                else:
                    name = match.group(3)
                KillFeed = f"你被【{attackerName}】使用{match.group(9)}击倒了（伤害{float(match.group(4))}）"
                rcon("AdminWarn",match.group(3),KillFeed)
                print (f"Log: AdminWarn {name} {KillFeed}")
            return Woundinfo
        
class roundstart:
    def __init__(self):
        self.regex = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogWorld: Bringing World \/([A-z]+)\/(?:Maps\/)?([A-z0-9-]+)\/(?:.+\/)?([A-z0-9-]+)(?:\.[A-z0-9-]+)')
    def on_match(self, line):
        match = self.regex.match(line)
        if match:
            roundinfo = f"时间：{match.group(1)} | 地图：{match.group(5)} 新回合开始"
            return roundinfo
        time.sleep(60)
        killnumber_sorted = sorted(killnumber.items(), key=lambda x: x[1], reverse=True)
        if killnumber_sorted:
            max_player, max_value = killnumber_sorted[0]
            max_steamid = max_player.split(',')[0]
            max_name = max_player.split(',')[1]
            rcon("AdminBroadcast",f"玩家「{max_name}」{max_steamid} 上局击杀数最高，共击杀{max_value}人")
            killnumber.clear()

        
class roundend:
    def __init__(self):
        self.regex = re.compile(r'^\[([0-9.:-]+)]\[([ 0-9]*)]LogSquadGameEvents: Display: Team ([0-9]), (.*) \( ?(.*?) ?\) has (won|lost) the match with ([0-9]+) Tickets on layer (.*) \(level (.*)\)!')
    def on_match(self, line):
        match = self.regex.match(line)
        if match:
            if match.group(6) == "won":
                matchresult = "获胜"
            if match.group(6) == "lost":
                matchresult = "失败"

            roundinfo = f"时间：{match.group(1)} | 回合结束 {match.group(3)} {match.group(4)} {match.group(5)} {matchresult} 剩余{match.group(7)}票，地图：{match.group(8)}"
            with open('kill.json', 'w') as file:
                pass
            return roundinfo
        
class LogParser:
    def __init__(self):
        self.handlers = [PlayerDied(), PlayerDamaged(), CreatSquad(), PlayerJoin(), PlayerWound(), roundstart(), roundend()]
        self.file = open('squad.log', 'w', encoding='utf-8')  # 打开文件

    def parse_line(self, line):
        for handler in self.handlers:
            data = handler.on_match(line)
            if handler.__class__.__name__ == "PlayerDied":
                handler.__class__.__name__ = "击杀"
            if handler.__class__.__name__ == "PlayerDamaged":
                handler.__class__.__name__ = "伤害"
            if handler.__class__.__name__ == "CreatSquad":
                handler.__class__.__name__ = "建队"
            if handler.__class__.__name__ == "PlayerJoin":
                handler.__class__.__name__ = "进服"
            if handler.__class__.__name__ == "PlayerWound":
                handler.__class__.__name__ = "击倒"
            if handler.__class__.__name__ == "roundstart":
                handler.__class__.__name__ = "回合开始"
            if handler.__class__.__name__ == "roundend":
                handler.__class__.__name__ = "回合结束"
            if data:
                self.file.write(f"{handler.__class__.__name__}｜{data}\n")  # 写入文件
                self.file.flush()  # 立即将缓冲区内容写入文件
                os.fsync(self.file.fileno())  # 确保操作系统的缓冲区也被写入文件
                print (f"{handler.__class__.__name__}: {data}")

    def close(self):
        self.file.close()  # 关闭文件

parser = LogParser()
for line in tail('SquadGame.log'):
    parser.parse_line(line)
parser.close()  # 记得在结束时关闭文件
