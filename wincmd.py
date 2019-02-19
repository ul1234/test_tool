#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, time, subprocess, sys
from datetime import datetime
import win32clipboard, win32con

class WinCmd:
    SHOW_CMD_STRING = False;

    @staticmethod
    def rename_dir(src_dir, dest_dir):
        if not os.path.isdir(src_dir): raise Exception('no such directory: %s' % src_dir)
        WinCmd.del_dir(dest_dir, include_dir = True)
        os.rename(src_dir, dest_dir)

    @staticmethod
    def rename_files(src_files, dest_files, remove_dest_first = False):
        def _check_files_exist(files, check_exist = True):
            result = True
            error_file = None
            for f in files:
                if (check_exist and not os.path.isfile(f)) or (not check_exist and os.path.isfile(f)):
                    result = False
                    error_file = f
                    break
            return (result, error_file)
        if not isinstance(src_files, list): src_files = [src_files]
        if not isinstance(dest_files, list): dest_files = [dest_files]
        if len(src_files) != len(dest_files): raise Exception('files number mismatch. src files %d, dest files %d.' % (len(src_files), len(dest_files)))
        result, error_file = _check_files_exist(src_files, check_exist = True)
        if not result: raise Exception('src file "%s" not exist before rename.' % error_file)
        for src_file, dest_file in zip(src_files, dest_files):
            if remove_dest_first: WinCmd.del_file(dest_file)
            os.rename(src_file, dest_file)
        result, error_file = _check_files_exist(src_files, check_exist = False)
        if not result: raise Exception('src file "%s" cannot be successfully renamed.' % error_file)

    @staticmethod
    def copy_dir(src_dir, dest_dir, empty_dest_first = True, include_src_dir = False):
        if os.path.isdir(src_dir):
            if empty_dest_first: WinCmd.del_dir(dest_dir)
            elif not os.path.isdir(dest_dir): WinCmd.make_dir(dest_dir)
            if include_src_dir:
                dest_dir = os.path.join(dest_dir, os.path.basename(src_dir))
                WinCmd.make_dir(dest_dir)
            WinCmd.cmd(r'xcopy /e /h /y /c /q "%s\*" "%s" > nul' % (src_dir, dest_dir))
            if not WinCmd.cmp_folder(src_dir, dest_dir): raise Exception('cannot copy dir from %s to %s' % (src_dir, dest_dir))
        else:
            raise Exception('no such directory: %s' % src_dir)

    @staticmethod
    def copy_file(src_file, dest, dest_is_dir = True):
        if not os.path.isfile(src_file):
            raise Exception('no such file: %s' % src_file)
        if dest_is_dir and not os.path.isdir(dest):
            raise Exception('no such directory: %s' % dest)
        WinCmd.cmd(r'copy /y "%s" "%s" > nul' % (src_file, dest))  # no output info
        dest_file = dest if not dest_is_dir else os.path.join(dest, os.path.basename(src_file))
        if not os.path.isfile(dest_file) or int(os.path.getmtime(src_file)) != int(os.path.getmtime(dest_file)):
            raise Exception('cannot copy file to %s' % dest_file)

    @staticmethod
    def copy_files(src_files, dest_dir, empty_dir_first = False):
        if empty_dir_first or not os.path.isdir(dest_dir): WinCmd.del_dir(dest_dir)
        exceptions = []
        for src_file in src_files:
            try:
                WinCmd.copy_file(src_file, dest_dir)
            except Exception as e:
                exceptions.append(str(e))
        if exceptions: raise Exception('\n'.join(exceptions))

    @staticmethod
    def del_dir(dest_dir, include_dir = False, show_error_msg = True):
        if os.path.isdir(dest_dir):
            output = '> nul 2>&1' if not show_error_msg else ''
            WinCmd.cmd(r'rmdir /s /q "%s" %s' % (dest_dir, output))
        if not include_dir:
            WinCmd.make_dir(dest_dir)

    @staticmethod
    def make_dir(dest_dir):
        for try_times in range(5):
            if os.path.isdir(dest_dir): break
            try:
                os.makedirs(dest_dir)
            except:
                time.sleep(1)
        if not os.path.isdir(dest_dir): raise Exception('cannot create directory in %d times: %s' % (try_times, dest_dir))

    @staticmethod
    def del_pattern_files(pattern_files):
        WinCmd.cmd(r'del /q /f "%s" > nul 2>&1' % pattern_files)  # no output info and error info

    @staticmethod
    def del_file(file):
        if os.path.isfile(file): os.remove(file)
        if os.path.isfile(file): raise Exception('cannot delete file %s' % file)

    @staticmethod
    def del_file_cmd(file):
        if os.path.isfile(file):  WinCmd.cmd(r'del /q /f "%s" > nul 2>&1' % file)  # no output info and error info
        if os.path.isfile(file): raise Exception('cannot delete file %s' % file)

    @staticmethod
    def force_del_file(file, total_try_times = 10):
        del_file_success = False
        try_times = 0
        while try_times < total_try_times:
            try:
                WinCmd.del_file(file)
                del_file_success = True
                break
            except:
                time.sleep(0.2)
                try_times = try_times + 1
        if not del_file_success: raise Exception('cannot delete file %s within %d try.' % (file, total_try_times))

    @staticmethod
    def explorer(file_or_folder = None):
        if file_or_folder and os.path.exists(file_or_folder):
            WinCmd.cmd(r'explorer "%s"' % file_or_folder)
        else:
            WinCmd.cmd(r'explorer')

    @staticmethod
    def empty_file(file):
        file_path = os.path.dirname(file)
        if not os.path.isdir(file_path): WinCmd.make_dir(file_path)
        open(file, 'w').close()

    @staticmethod
    def check_file_exist(filename, can_be_empty = False):
        if not can_be_empty and not filename: raise Exception('file can not be empty: %s' % filename)
        if filename and not os.path.isfile(filename): raise Exception('file not found: %s' % filename)

    @staticmethod
    def check_folder_exist(folder, can_be_empty = False):
        if not can_be_empty and not folder: raise Exception('folder can not be empty: %s' % folder)
        if folder and not os.path.isdir(folder): raise Exception('folder not found: %s' % folder)

    @staticmethod
    def kill(process):
        WinCmd.cmd(r'taskkill /f /im %s.exe /T' % os.path.splitext(process)[0])

    @staticmethod
    def print_(str, output_time = True):
        if output_time:
            print('[%s]%s' % (datetime.now().strftime('%H:%M:%S'), str))
        else:
            print(str)
        sys.stdout.flush()

    @staticmethod
    def MessageBox(text, title = 'Test Tool Monitor', style = 0):
        from ctypes import windll
        MB_OK = 0x0
        MB_OKCANCEL = 0x1
        MB_ABORTRETRYIGNORE = 0x2
        MB_YESNOCANCEL = 0x3
        MB_YESNO = 0x4
        MB_RETRYCANCEL = 0x5

        MB_ICONHAND = MB_ICONSTOP = MB_ICONERRPR = 0x10
        MB_ICONQUESTION = 0x20
        MB_ICONEXCLAIMATION = 0x30
        MB_ICONASTERISK = MB_ICONINFOMRAITON = 0x40

        MB_DEFAULTBUTTON1 = 0x0
        MB_DEFAULTBUTTON2 = 0x100
        MB_DEFAULTBUTTON3 = 0x200
        MB_DEFAULTBUTTON4 = 0x300

        MB_SETFOREGROUND = 0x10000
        MB_TOPMOST = 0x40000
        windll.user32.MessageBoxA(0, text, title, MB_OK | MB_TOPMOST)

    @staticmethod
    def is_subfolder(subfolder, folder):
        subfolder, folder = [os.path.join(os.path.abspath(f), '').lower() for f in [subfolder, folder]] # add os.sep in the end
        return os.path.commonprefix([subfolder, folder]) == folder

    @staticmethod
    def cmp_folder(folder1, folder2):
        def _list_files_and_folders(folder):
            files_and_folders = []
            for dir_path, subpaths, files in os.walk(folder):
                if files:
                    for f in files:
                        files_and_folders.append(os.path.relpath(os.path.join(dir_path, f), folder))
                else:
                    files_and_folders.append(os.path.relpath(dir_path, folder))
            return list(set(files_and_folders))
        files1 = _list_files_and_folders(folder1)
        files2 = _list_files_and_folders(folder2)
        if len(files1) != len(files2): return False
        for f in files1:
            if f not in files2:
                return False
        return True

    @staticmethod
    def sort_file(filename, target_file = ''):
        WinCmd.check_file_exist(filename)
        temp_file_flag = not target_file
        output_file_name, output_file_ext = os.path.splitext(filename)
        target_file = target_file or ('%s_sort_temp%s' % (output_file_name, output_file_ext))
        WinCmd.cmd(r'sort /REC 65535 %s > %s' % (os.path.basename(filename), target_file), os.path.dirname(filename), showcmdwin = True, minwin = True, wait = True)
        WinCmd.check_file_exist(target_file)
        if temp_file_flag:
            WinCmd.del_file(filename)
            WinCmd.rename_files(target_file, filename)

    @staticmethod
    def cmd(command, path = None, showcmdwin = False, minwin = False, wait = True, retaincmdwin = False, title = ''):
        path_str = r'cd /d "%s" & ' % path if path else ''
        if showcmdwin:
            min_str = r'/min' if minwin else ''
            title_str = r'title %s & ' % title if title else ''
            wait_str = '/wait' if wait else ''
            retain_str = '/k' if retaincmdwin else '/c'
            cmd_str = r'start %s %s cmd.exe %s "%s%s%s"' % (min_str, wait_str, retain_str, title_str, path_str, command)
        else:
            cmd_str = r'%s%s' % (path_str, command)
        if WinCmd.SHOW_CMD_STRING: print '[RUN CMD] %s' % cmd_str
        os.system(cmd_str)

    @staticmethod
    def process(command, path = None, wait = False, shell = False):
        if shell:
            path_str = r'cd /d "%s" & ' % path if path else ''
            command = r'%s%s' % (path_str, command)
        elif path:
            command = os.path.join(path, command)
        if WinCmd.SHOW_CMD_STRING: print '[PROCESS, shell=%s] %s' % (shell, command)
        p = subprocess.Popen(command, shell = shell)
        if wait:
            result = p.wait()
            return result
        return None

    @staticmethod
    def get_clip_text():
        try:
            win32clipboard.OpenClipboard()
            result = win32clipboard.GetClipboardData(win32con.CF_TEXT)
            win32clipboard.CloseClipboard()
            return result
        except:
            win32clipboard.CloseClipboard()
            return ''

    @staticmethod
    def set_clip_text(string):
        while True:
            try:
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                break
            except:
                time.sleep(0.5)
        win32clipboard.SetClipboardData(win32con.CF_TEXT, string)
        win32clipboard.CloseClipboard()

    @staticmethod
    def get_ip_addresses():
        # from http://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
        from ctypes import Structure, windll, sizeof
        from ctypes import POINTER, byref
        from ctypes import c_ulong, c_uint, c_ubyte, c_char
        MAX_ADAPTER_DESCRIPTION_LENGTH = 128
        MAX_ADAPTER_NAME_LENGTH = 256
        MAX_ADAPTER_ADDRESS_LENGTH = 8
        class IP_ADDR_STRING(Structure): pass
        LP_IP_ADDR_STRING = POINTER(IP_ADDR_STRING)
        IP_ADDR_STRING._fields_ = [
            ("next", LP_IP_ADDR_STRING),
            ("ipAddress", c_char * 16),
            ("ipMask", c_char * 16),
            ("context", c_ulong)]
        class IP_ADAPTER_INFO (Structure): pass
        LP_IP_ADAPTER_INFO = POINTER(IP_ADAPTER_INFO)
        IP_ADAPTER_INFO._fields_ = [
            ("next", LP_IP_ADAPTER_INFO),
            ("comboIndex", c_ulong),
            ("adapterName", c_char * (MAX_ADAPTER_NAME_LENGTH + 4)),
            ("description", c_char * (MAX_ADAPTER_DESCRIPTION_LENGTH + 4)),
            ("addressLength", c_uint),
            ("address", c_ubyte * MAX_ADAPTER_ADDRESS_LENGTH),
            ("index", c_ulong),
            ("type", c_uint),
            ("dhcpEnabled", c_uint),
            ("currentIpAddress", LP_IP_ADDR_STRING),
            ("ipAddressList", IP_ADDR_STRING),
            ("gatewayList", IP_ADDR_STRING),
            ("dhcpServer", IP_ADDR_STRING),
            ("haveWins", c_uint),
            ("primaryWinsServer", IP_ADDR_STRING),
            ("secondaryWinsServer", IP_ADDR_STRING),
            ("leaseObtained", c_ulong),
            ("leaseExpires", c_ulong)]
        GetAdaptersInfo = windll.iphlpapi.GetAdaptersInfo
        GetAdaptersInfo.restype = c_ulong
        GetAdaptersInfo.argtypes = [LP_IP_ADAPTER_INFO, POINTER(c_ulong)]
        adapterList = (IP_ADAPTER_INFO * 10)()
        buflen = c_ulong(sizeof(adapterList))
        rc = GetAdaptersInfo(byref(adapterList[0]), byref(buflen))
        if rc == 0:
            for a in adapterList:
                adNode = a.ipAddressList
                while True:
                    ipAddr = adNode.ipAddress
                    if ipAddr: yield ipAddr
                    adNode = adNode.next
                    if not adNode: break


class Profile:
    _profile_dict = {}

    @staticmethod
    def print_(str, output_time = False):
        WinCmd.print_(str, output_time)

    @staticmethod
    def start(id = 'default', name = '', show = True):
        Profile._profile_dict[id] = time.time()
        if show: Profile.print_('[%s] %s start: %.2fs' % (id, name, Profile._profile_dict[id]))

    @staticmethod
    def restart(id = 'default', name = '', show = True):
        now = time.time()
        if not id in Profile._profile_dict.keys(): raise Excpetion('no start for %s' % id)
        elapse = now - Profile._profile_dict[id]
        if show: Profile.print_('[%s] %s: %.2fs. Elapse: %.2fs' % (id, name, now, elapse))
        Profile._profile_dict[id] = now
        return elapse

    @staticmethod
    def end(id = 'default', name = '', show = True):
        now = time.time()
        if not id in Profile._profile_dict.keys(): raise Excpetion('no start for %s' % id)
        elapse = now - Profile._profile_dict[id]
        if show: Profile.print_('[%s] %s: %.2fs. Elapse: %.2fs' % (id, name, now, elapse))
        return elapse


if __name__ == '__main__':
    #WinCmd.copy_dir(r'E:\11.Temp\test1\11', r'E:\11.Temp\test1\22', True)
    print WinCmd.cmp_folder(r'E:\tool\temp\All Batch', r'E:\tool\All Batch')
