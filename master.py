#!/usr/bin/env python3

import subprocess
import json
import requests
import flask
import process
import re
import sshpubkeys
import os
import time

app = flask.Flask(__name__)
nodes = {
    '172.17.17.211': 'http://172.17.17.211:5000',
    '172.17.17.212': 'http://172.17.17.212:5000',
}
#nodes = {"172.17.17.211": 'http://172.17.17.211:5000'}

@app.route("/")
def index():
    return "Hello World!"

@app.route("/list", methods=['GET'])
def lists(runtime = True, tojson = True):
    results = []
    rets = process.run(["ezjail-admin", "list"])[1]
    for ret in rets[2:]:
        col = ret.split()
        results.append({
            "name": col[3],
            "ip": col[2],
            "running": col[1] != 'N/A',
            "host": None,
        })
    if runtime == True:
        for node in nodes:
            r = requests.get(nodes[node] + '/list')
            res = r.json()
            for re in res:
                if res[re]['running'] == True:
                    res[re]['host'] = node
                    remove = None
                    for x in results:
                        if x['name'] == re:
                            x['host'] = node
                            x['running'] = True
                    #results.append(res[re])
    if tojson == True:
        return json.dumps(results)
    return results

@app.route("/status", methods=['GET'])
def status():
    results = {"clusters": [], "disk": 0}
    for node in nodes:
        r = requests.get(nodes[node] + '/status')
        res = r.json()
        res['name'] = node
        results['clusters'].append(res)
    ret = process.run(["zfs", "list", "-Hp", "zroot"])
    if ret[0] != 0:
        return json.dumps({"status": "error", "message": "zfs: " + ret[1]})
    ret = ret[1][0].split()
    results['disk'] = round(float(ret[1]) / (int(ret[1]) + int(ret[2])) * 100, 2);
    return json.dumps(results)

def lists_find(name):
    for l in lists(False, False):
        if name == l['name']: return True
    return False

def lists_get(name, runtime = False, tojson = False):
    for l in lists(runtime, tojson):
        if name == l['name']: return l
    return None

@app.route("/create", methods=['POST'])
def create():
    req = flask.request.json
    if 'name' not in req:
        return (json.dumps({"status": "error", "message": "name not given"}), 500)
    if re.match('^[a-zA-Z0-9_.]{3,}$', req['name']) is None:
        return (json.dumps({"status": "error", "message": "name not allow"}), 500)
    if lists_find(req['name']):
        return (json.dumps({"status": "error", "message": "name already exist"}), 500)
    if 'ip' not in req:
        return (json.dumps({"status": "error", "message": "ip not given"}), 500)
    if 'quota' not in req:
        return (json.dumps({"status": "error", "message": "quota not given"}), 500)
    req['quota'] = str(req['quota'])
    if re.match('^[0-9]+$', str(req['quota'])) is None:
        return (json.dumps({"status": "error", "message": "quota error"}), 500)
    if 'sshkey' not in req:
        return (json.dumps({"status": "error", "message": "sshkey not given"}), 500)
    sshkey = sshpubkeys.SSHKey(req['sshkey'], strict_mode=True)
    try:
        sshkey.parse()
    except sshpubkeys.InvalidKeyException as err:
        return (json.dumps({"status": "error", "message": str(err)}), 500)
    # ezjail-admin create
    ret = process.run(["ezjail-admin", "create", req['name'], req['ip']])
    if ret[0] != 0:
        return (json.dumps({"status": "error", "message": "ezjail:" + str(ret[1])}), 500)
    # zfs set
    ret = process.run(["zfs", "set", "quota={quota}G".format(quota=req['quota']), "zroot/usr/jails/{name}".format(name=req['name'])])
    if ret[0] != 0:
        return (json.dumps({"status": "error", "message": "zfs:" + str(ret[1])}), 500)
    # write key
    with open("key/{name}.pub".format(name = req['name']), "w") as keyfile:
        keyfile.write("# {name}\n".format(name = req['name']))
        option = 'command="/usr/local/bin/sudo /usr/local/bin/ezjail-admin console {name}",no-port-forwarding,no-X11-forwarding,no-agent-forwarding'.format(name = req['name'])
        keydata = " ".join(sshkey.keydata.split()[:2])
        keyfile.write("{option} {keydata}\n".format(option = option, keydata = keydata))
    # setup key
    process.run(["sh", "keygen.sh"])
    return json.dumps({"status": "success"})

@app.route("/delete", methods=['POST'])
def delete():
    req = flask.request.json
    if 'name' not in req:
        return (json.dumps({"status": "error", "message": "name not given"}), 500)
    if re.match('^[a-zA-Z0-9_.]{3,}$', req['name']) is None:
        return (json.dumps({"status": "error", "message": "name not allow"}), 500)
    if not lists_find(req['name']):
        return (json.dumps({"status": "error", "message": "name not found"}), 500)
    # ezjail-admin delete
    ret = process.run(["ezjail-admin", "delete", req['name']])
    if ret[0] != 0:
        return (json.dumps({"status": "error", "message": "ezjail:" + str(ret[1])}), 500)
    # zfs destroy
    ret = process.run(["zfs", "destroy", "zroot/usr/jails/{name}".format(name=req['name'])])
    if ret[0] != 0:
        return (json.dumps({"status": "error", "message": "zfs:" + str(ret[1])}), 500)
    # write key
    os.unlink("key/{name}.pub".format(name = req['name']))
    os.rmdir("/usr/jails/{name}".format(name = req['name']))
    # setup key
    process.run(["sh", "keygen.sh"])
    return json.dumps({"status": "success"})

@app.route("/control", methods=['POST'])
def control():
    req = flask.request.json
    if 'name' not in req:
        return (json.dumps({"status": "error", "message": "name not given"}), 500)
    if re.match('^[a-zA-Z0-9_.]{3,}$', req['name']) is None:
        return (json.dumps({"status": "error", "message": "name not allow"}), 500)
    if not lists_find(req['name']):
        return (json.dumps({"status": "error", "message": "name not found"}), 500)

    if req['action'] == 'start':
        counter = {}
        li = lists(True, False)
        if lists_get(req['name'], True, False)['running'] == True:
            return (json.dumps({"status": "error", "message": "{} already running".format(req['name'])}), 500)
        # Choose least jail host
        for node in nodes:
            counter[node] = 0
        for l in li:
            host = l['host']
            if host is None: continue
            counter[host] += 1
        m = None
        for host in counter:
            if m is None or counter[host] < counter[m]:
                m = host
        if m is None:
            return (json.dumps({"status": "error", "message": "no available host found"}), 500)
        r = requests.post(nodes[m] + '/control', json={"name": req['name'], "action": 'start'})
    elif req['action'] == 'stop':
        m = lists_get(req['name'], True, False)['host']
        if m is None:
            return (json.dumps({"status": "error", "message": "{} already stop".format(req['name'])}), 500)
        r = requests.post(nodes[m] + '/control', json={"name": req['name'], "action": 'stop'})
    else:
        return (json.dumps({"status": "error", "message": "action not recognize, just start or stop"}), 500)
    return (json.dumps(r.json()), r.status_code)

@app.route("/snapshot", methods=['GET'])
def snapshots():
    li = lists(False, False)
    result = {}
    for l in li:
        l = l['name']
        ret = process.run(['zfs', 'list', '-Hprt', 'all', "zroot/usr/jails/{}".format(l)])
        ret = ret[1]
        col = ret[0].split()
        result[l] = {"used": int(col[1]), "available": int(col[1]) + int(col[2]), "snapshots": []}
        for line in ret[1:]:
            col = line.split()
            result[l]["snapshots"].append({"name": col[0].split('@')[1], "used": int(col[1])})
    return json.dumps(result)

@app.route("/snapshot", methods=['POST', 'DELETE'])
def snapshot():
    req = flask.request.json
    if 'name' not in req:
        return (json.dumps({"status": "error", "message": "name not given"}), 500)
    if re.match('^[a-zA-Z0-9_.]{3,}$', req['name']) is None:
        return (json.dumps({"status": "error", "message": "name not allow"}), 500)
    if not lists_find(req['name']):
        return (json.dumps({"status": "error", "message": "name not found"}), 500)
    if 'snap' not in req:
        return (json.dumps({"status": "error", "message": "snap name not given"}), 500)
    if re.match('^[a-zA-Z0-9_.:-]{3,}$', req['snap']) is None:
        return (json.dumps({"status": "error", "message": "snap name not allow"}), 500)
    if flask.request.method == 'POST':
        ret = process.run(['zfs', 'snap', 'zroot/usr/jails/{}@{}'.format(req['name'], req['snap'])])
    elif flask.request.method == 'DELETE':
        ret = process.run(['zfs', 'destroy', 'zroot/usr/jails/{}@{}'.format(req['name'], req['snap'])])
    if ret[0] != 0:
        return (json.dumps({"status": "error", "message": "zfs: " + str(ret[1])}))
    return json.dumps({"status": "success"})

@app.route("/rollback", methods=['POST'])
def rollback():
    req = flask.request.json
    if 'name' not in req:
        return (json.dumps({"status": "error", "message": "name not given"}), 500)
    if re.match('^[a-zA-Z0-9_.]{3,}$', req['name']) is None:
        return (json.dumps({"status": "error", "message": "name not allow"}), 500)
    if not lists_find(req['name']):
        return (json.dumps({"status": "error", "message": "name not found"}), 500)
    if 'snap' not in req:
        return (json.dumps({"status": "error", "message": "snap name not given"}), 500)
    if re.match('^[a-zA-Z0-9_.:-]{3,}$', req['snap']) is None:
        return (json.dumps({"status": "error", "message": "snap name not allow"}), 500)
    ret = process.run(['zfs', 'rollback', '-r', 'zroot/usr/jails/{}@{}'.format(req['name'], req['snap'])])
    if ret[0] != 0:
        return (json.dumps({"status": "error", "message": "zfs: " + str(ret[1])}))
    return json.dumps({"status": "success"})

if __name__ == "__main__":
    app.run(host = '0.0.0.0')
    #app.run(host = '0.0.0.0', port = 5000)
    pass
