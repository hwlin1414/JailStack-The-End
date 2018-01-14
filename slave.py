#!/usr/bin/env python3

import subprocess
import json
import requests
import flask
import process
import psutil

app = flask.Flask(__name__)

@app.route("/")
def index():
    return "Hello World!"

@app.route("/list")
def lists(tojson = True):
    results = {}
    rets = process.run(["ezjail-admin", "list"])[1]
    for ret in rets[2:]:
        col = ret.split()
        results[col[3]] = {
            "name": col[3],
            "ip": col[2],
            "running": col[1] != 'N/A',
        }
    if tojson == True:
        return json.dumps(results)
    return results

@app.route("/status")
def status():
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory()
    return json.dumps({"cpu": cpu, "mem": mem.percent})

@app.route("/control", methods=['POST'])
def control():
    req = flask.request.json
    li = lists(False)[req['name']]
    if req['action'] == 'start':
        ret = process.run(["ifconfig", "em0", "add", li['ip'], "netmask", "255.255.255.0"])
        ret = process.run(["ezjail-admin", "onestart", req['name']])
        if ret[0] != 0:
            return (json.dumps({"status": "error", "message": ret[1]}), 500)
    elif req['action'] == 'stop':
        ret = process.run(["ifconfig", "em0", "delete", li['ip']])
        ret = process.run(["ezjail-admin", "onestop", req['name']])
        if ret[0] != 0:
            return (json.dumps({"status": "error", "message": ret[1]}), 500)
    else:
        return (json.dumps({"status": "error", "message": "action not recognize, just start or stop"}), 500)
    return json.dumps({"status": "success"})

if __name__ == "__main__":
    app.run(host = '0.0.0.0')
    #app.run(host = '0.0.0.0', port = 5000)
    pass
