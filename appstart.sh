#!/bin/bash
cd /opt/pi-one/
pip install -r requirements.txt -U
kill -9 $(ps -ef | grep "python3 /opt/pi-one/pi-one.py" | grep -v grep | awk '{print $2}')
nohup python3 /opt/pi-one/pi-one.py > /dev/null 2> /dev/null < /dev/null &