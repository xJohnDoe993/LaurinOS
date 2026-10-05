#!/usr/bin/python3
import sys
from laurinos.osd_state import notify
if len(sys.argv) == 2:
    notify(sys.argv[1])
