import subprocess
from pathlib import Path
import json

subprocess.run(["bash", "/home/julian/python_dev/AlpsArt_Server/git_commit_push.sh", "Auto commit"])

from GIT_LATEST_VERSION import get_latest_tag
version=get_latest_tag()

f = open(str(Path.cwd())+'/alpsart_server.conf')
try:
    data = json.load(f)
    f.close
    data["software_version"]=version
    with open(str(Path.cwd())+'/alpsart_server.conf', "w") as f:
        json.dump(data,f,indent=4)
        print(f"Version number in server configuration file updated to {version}")
except:
    f.close
    

    

