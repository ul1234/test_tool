#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys, StringIO
import Tkinter as tk
import time
from subprocess import Popen, PIPE, STDOUT

STDOUT_TO_FILE = False

class Background(tk.Toplevel):
    def __init__(self, master):
        tk.Toplevel.__init__(self, master)
        self.protocol('WM_DELETE_WINDOW', self.quit)
        self.resizable(0, 0)

        self.button_quit = tk.Button(self, text = 'Run in BG', font = ('courier', 12, 'bold'), command = self.run_bg)
        self.button_quit.pack(padx = 10, pady = 10)
        self.button_run = tk.Button(self, text = 'Run', font = ('courier', 12, 'bold'), command = self.run)
        self.button_run.pack(padx = 10, pady = 10)

        self.geometry('+%d+%d' % (self.winfo_screenwidth()/2, self.winfo_screenheight()/2))
        #self.stdin_save = sys.stdin
        #self.stdout_save = sys.stdout
        #self.stderr_save = sys.stderr
        self.cmd_in_file = r'temp/cmd_in.txt'
        self.cmd_out_file = r'temp/cmd_out.txt'
        #self.shell_out_file = r'temp/shell_out.txt'
        
        #if STDOUT_TO_FILE:
        #    sys.stdout = open(self.shell_out_file, 'a+')
        #sys.stderr = sys.stdout
        
    def cmd(self):
        return Popen(['python', 'test_tool.py'], stdout=PIPE, stdin=PIPE, stderr=PIPE, shell = True)

    def show(self):
        self.update()
        self.deiconify()

    def run_bg(self):
        self.withdraw()
        #self.tool = CmdLine()
        #self.tool.cmdloop()
        time.sleep(3)
        self.show()

    def run(self):
        self.run_cmd()
        
    def run_cmd(self, cmd_in_file = ''):
        cmd_in_file = cmd_in_file or self.cmd_in_file
        if not os.path.isfile(cmd_in_file): raise Exception('cmd file: %s not found' % cmd_in_file)
        with open(self.cmd_out_file, 'w') as f_write:
            with open(cmd_in_file, 'r') as f:
                for line in f:
                    if line.strip():
                        print 'run cmd: ', line.strip()
                        t1 = time.time()
                        #output, err = self.cmd().communicate(input = line.strip()+'\nq\n')
                        output, err = self.cmd().communicate('h\nq\n')
                        print 'run end:', time.time() - t1
                        if output: f_write.write(output)
                        #if err: f_write.write(err)
        while True:
            if self.check_cmd_finish(): break
            time.sleep(0.5)
        print 'quit'

    def close_cmd(self):
        print 'close cmd'
        #output, err = self.cmd.communicate(input = 'q\n')
        #self.cmd.terminate()

    def _back_std(self):
        try:
            sys.stdin.close()
        except:
            pass
        if STDOUT_TO_FILE:
            try:
                sys.stdout.close()
            except:
                pass
            sys.stdout = open(self.shell_out_file, 'a+')
        else:
            sys.stdout = self.stdout_save
        sys.stderr = sys.stdout
        sys.stdin = self.stdin_save

    def _run_cmd(self, cmd_in_file = ''):
        cmd_in_file = cmd_in_file or self.cmd_in_file
        if not os.path.isfile(cmd_in_file): raise Exception('cmd file: %s not found' % cmd_in_file)
        if STDOUT_TO_FILE:
            try:
                sys.stdout.close()
            except:
                pass
            print 'gogo'
            cmd_out = open(self.cmd_out_file, 'w')
            sys.stdout = cmd_out
            sys.stderr = cmd_out
        print self.cmd_in_file
        cmd_in = open(self.cmd_in_file, 'r')
        #sys.stdin = cmd_in
        sys.stdin = StringIO.StringIO('h ver\n')
        while True:
            if self.check_cmd_finish(): break
            time.sleep(0.5)
        #self.back_std()

    def check_cmd_finish(self):
        time.sleep(1)
        return True

    def quit(self):
        self.close_cmd()
        tk.Toplevel.quit(self)


if __name__ == '__main__':
    root = tk.Tk(className = 'Background Launcher')
    root.withdraw()
    launcher = Background(root)
    launcher.mainloop()
