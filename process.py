import subprocess
import time

def run(command):
    result = subprocess.Popen(command, stdout=subprocess.PIPE)
    result.wait()
    lines = []
    with open("output.txt", "a") as outlog:
        outlog.write("[%s] %s: %d\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), command, result.returncode))
        for line in result.stdout:
            outlog.write(line.decode('UTF-8'))
            lines.append(line.decode('UTF-8'))
    return (result.returncode, lines)
