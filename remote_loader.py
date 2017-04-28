#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys, os, socket, subprocess, threading, re, time
from wincmd import WinCmd

if __name__ == '__main__':
    #startupinfo = subprocess.STARTUPINFO()
    CREATE_NO_WINDOW = 0x08000000
    #startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    #startupinfo.wShowWindow = subprocess.SW_HIDE
    #proc = subprocess.Popen(command, startupinfo=startupinfo)
    subprocess.Popen('python remote.py', creationflags=CREATE_NO_WINDOW)
    print 'end'
    #WinCmd.cmd('python remote.py', showcmdwin = True, minwin = True)



