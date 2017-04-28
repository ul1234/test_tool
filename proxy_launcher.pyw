#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import Tkinter as tk


class ProxyLauncher(tk.Toplevel):
    def __init__(self, master):
        tk.Toplevel.__init__(self, master)
        self.protocol('WM_DELETE_WINDOW', self.quit)
        self.resizable(0, 0)

        self.button_start = tk.Button(self, text = 'Start', font = ('courier', 12, 'bold'), command = self.change_proxy_state)
        self.button_quit = tk.Button(self, text = 'Quit', font = ('courier', 12, 'bold'), command = self.quit)
        self.button_start.pack(side = 'left', padx = 10, pady = 10)
        self.button_quit.pack(padx = 10, pady = 10)

        self.button_start_selected(False)
        self.geometry('+%d+%d' % (self.winfo_screenwidth()/2, self.winfo_screenheight()/2))

        self.proxy_tool_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proxy.py')

    def button_start_selected(self, enable):
        if enable:
            self.button_start.config(relief = tk.SUNKEN)
            self.button_start.config(text = 'Stop')
        else:
            self.button_start.config(relief = tk.RAISED)
            self.button_start.config(text = 'Start')
        self.start_selected = enable

    def change_proxy_state(self):
        if self.start_selected:
            self.stop_proxy()
        else:
            self.start_proxy()

    def start_proxy(self, port = 1234):
        if not os.path.isfile(self.proxy_tool_file): raise Exception('no proxy.py file found!')
        self.button_start_selected(True)
        self._cmd(r'taskkill /fi "IMAGENAME eq cmd.exe" /fi "WindowTitle eq Administrator:  proxy_server*" > nul')
        title = 'proxy_server_localhost_%d' % port
        self._cmd(r'python "%s" start local %d' % (self.proxy_tool_file, port), showcmdwin = True, minwin = True, wait = False, retaincmdwin = True, title = title)

    def stop_proxy(self):
        if not os.path.isfile(self.proxy_tool_file): raise Exception('no proxy.py file found!')
        self.button_start_selected(False)
        self._cmd(r'taskkill /fi "IMAGENAME eq cmd.exe" /fi "WindowTitle eq Administrator:  proxy_server*" > nul')
        self._cmd(r'python "%s" stop' % self.proxy_tool_file)

    def quit(self):
        self.stop_proxy()
        tk.Toplevel.quit(self)

    def _cmd(self, command, path = None, showcmdwin = False, minwin = False, wait = True, retaincmdwin = False, title = ''):
        path_str = r'cd /d "%s" & ' % path if path else ''
        if showcmdwin:
            min_str = r'/min' if minwin else ''
            title_str = r'title %s & ' % title if title else ''
            wait_str = '/wait' if wait else ''
            retain_str = '/k' if retaincmdwin else '/c'
            os.system(r'start %s %s cmd.exe %s "%s%s%s"' % (min_str, wait_str, retain_str, title_str, path_str, command))
        else:
            os.system(r'%s%s' % (path_str, command))


if __name__ == '__main__':
    root = tk.Tk(className = 'Proxy Launcher')
    root.withdraw()
    launcher = ProxyLauncher(root)
    launcher.mainloop()
