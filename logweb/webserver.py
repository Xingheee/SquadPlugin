from flask import Flask, jsonify, request, render_template
import random
import tailer
import threading
import time
import json
from collections import deque

app = Flask(__name__)

# 存储最后 5000 行的日志
kill_info = []

def update_kill_info():
    global kill_info
    while True:
        # 读取日志文件的最后 5000 行
        with open('../squad.log', 'r') as f:
            kill_info = tailer.tail(f, 5000)
        # 每三秒更新一次
        time.sleep(10)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/ip', methods=['GET'])
def get_ip():
    # 获取访问者的 IP 地址
    ip = request.remote_addr
    return jsonify({"ip": ip})

@app.route('/api/kills', methods=['GET'])
def get_kills():
    # 获取访问者的 IP 地址
    ip = request.remote_addr

    # 读取playerinfo.json文件
    with open('../playerinfos.json', 'r') as f:
        player_info = json.load(f)

    # 搜索与访问者 IP 地址匹配的键值对
    for key, value in player_info.items():
        if value.get('IP') == ip:
            player_name = value['playername']
            player_id = value['SteamID']
            try:
                with open('../kill.json', 'r') as f:
                    data = json.load(f)
                    kills = data.get(player_id)
            except:
                kills = '0'
            break  # 在找到第一个匹配项后退出循环
        else:
            player_name = None
            player_id = None
            kills = '未获取到当前玩家信息'
            
    return jsonify({"player_name": player_name, "kills": kills})  # 返回玩家名字和击杀数

@app.route('/api/kill_info', methods=['GET'])
def get_kill_info():
    # 返回击杀信息
    return jsonify(kill_info)

@app.route('/api/squad_log', methods=['GET'])
def get_squad_log():
    with open('../squad.log', 'r') as f:
        log = ''.join(deque(f, 1000))
    return jsonify({"log": log})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3999)