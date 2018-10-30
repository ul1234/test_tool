#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys, os, socket, subprocess, threading, re, time
from datetime import datetime, timedelta

######################## decorator ##########################
def thread_func(time_delay = 0.01):
    def _thread_func(func):
        def __thread_func(*args, **kwargs):
            def _func(*args):
                time.sleep(time_delay)
                func(*args, **kwargs)
            threading.Thread(target = _func, args = tuple(args)).start()
        return __thread_func
    return _thread_func


class Remote(object):
    def __init__(self, file_index = 1, directory = None):
        if file_index is None:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except:
                local_ip = None
            file_index = int(local_ip.split('.')[-1]) if local_ip else 0
        self.down_file = self.up_file = ''
        self.reload(file_index, directory)

    def reload(self, file_index = 1, directory = None):
        if not directory:
            directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'remote')
            if not os.path.isdir(directory): os.makedirs(directory)
        if not os.path.isdir(directory): raise Exception('directory not exist! %s' % directory)
        down_file = os.path.join(directory, 'down_%d.txt' % file_index)
        up_file = os.path.join(directory, 'up_%d.txt' % file_index)
        if (down_file != self.down_file):
            self.down_file = down_file
            self.print_('Down File: %s' % self.down_file)
        if (up_file != self.up_file):
            self.up_file = up_file
            self.print_('Up File: %s' % self.up_file)

    def print_(self, str, output_time = False):
        if output_time:
            print('[%s]%s' % (datetime.now().strftime('%H:%M:%S'), str))
        else:
            print(str)
        sys.stdout.flush()

    def empty(self, filename):
        with open(filename, 'w') as f_write:
            f_write.write('CMD')

    def run(self, command):
        if not command.strip(): return
        self.empty(self.down_file)
        with open(self.up_file, 'w') as f_write:
            r = re.search(r'^(.*)--remote(.*)$', command)
            if r: command = r.group(1) + r.group(2)
            f_write.write(command + '\n')
            f_write.write('END')
        if command.strip() == 'remote':  # query
            timeout = 30
        else:
            timeout = 0  # no timeout
        countdown = timeout
        while True:
            lines = open(self.down_file, 'r').readlines()
            if len(lines) > 1 and lines[-1].strip() == 'END':
                for line in lines[:-1]:
                    replace_line = line.strip().replace('(Cmd)', '')
                    if not line.strip() or replace_line:   # remove the last (Cmd)
                        self.print_(replace_line)
                break
            if timeout and not countdown:
                self.print_('no response from the remote server within %ds\n' % timeout)
                break
            time.sleep(1)
            if timeout: countdown = countdown - 1


class RunProxy(object):
    def __init__(self, server_index = 1, directory = None, log_to_file = True):
        if server_index is None:
            try:
                local_ip = socket.gethostbyname(socket.gethostname())
            except:
                local_ip = None
            server_index = int(local_ip.split('.')[-1]) if local_ip else 0
        self.reload(server_index, directory)
        self.version = datetime.fromtimestamp(os.stat(__file__).st_mtime).strftime('%y%m%d_%H%M%S')
        if log_to_file:
            log_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'remote', 'remote_server_log_%d.txt' % server_index)
            print log_filename
            self.output_file = open(log_filename, 'w')
        self.print_('remote proxy server start...')
        self.print_('Down File: %s' % self.down_file)
        self.print_('Up File: %s' % self.up_file)

    def reload(self, server_index = 1, directory = None):
        if not directory:
            directory = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'remote')
            if not os.path.isdir(directory): os.makedirs(directory)
        if not os.path.isdir(directory): raise Exception('directory not exist! %s' % directory)
        self.down_file = os.path.join(directory, 'down_%d.txt' % server_index)
        self.up_file = os.path.join(directory, 'up_%d.txt' % server_index)
        self.empty(self.down_file)
        self.empty(self.up_file)

    def _update_self(self):
        args = sys.argv[:]
        args.insert(0, sys.executable)
        sys.stdout.flush()
        self.print_('begin updating: %s, %s' % (sys.executable, args))
        os.execv(sys.executable, args)

    def _print(self, str):
        if hasattr(self, 'output_file') and self.output_file:
            self.output_file.write(str + '\n')
            self.output_file.flush()
        else:
            print(str)
            sys.stdout.flush()

    def print_(self, str, output_time = True):
        if output_time:
            self._print('[%s]%s' % (datetime.now().strftime('%y-%m-%d %H:%M:%S'), str))
        else:
            self._print(str)

    def empty(self, filename):
        with open(filename, 'w') as f_write:
            f_write.write('CMD')

    def run(self, cmd):
        try:
            p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'test_tool.py'), 'remote'], shell = True, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
            result = p.communicate(cmd)
        except Exception as e:
            return [str(e)]
        return result[0]

    def _time_sleep_if_continous_condition(self, sleep_time, condition, continuous_times):
        if not hasattr(self, 'continuous_times'): self.continuous_times = 0
        self.continuous_times = self.continuous_times + 1 if condition else 0
        if self.continuous_times > continuous_times:
            time.sleep(sleep_time)

    def _check_cmd_deamon(self):
        cmd = ''
        if os.path.isfile(self.up_file):
            lines = open(self.up_file, 'r').readlines()
            if len(lines) == 2 and lines[1] == 'END':
                cmd = lines[0].strip()
                self.empty(self.up_file)
        self._time_sleep_if_continous_condition(10, not cmd, 300)  # if 300 times (5 minutes) no command, wait 10s
        if cmd:
            self.print_('start run cmd: %s' % cmd)
            result = self.run(cmd)
            self.print_('cmd finish')
            r = re.search(r'(<REMOTE>(\w+)</REMOTE>)', result)
            if r: result = result.replace(r.group(1), '')
            with open(self.down_file, 'w') as f_write:
                f_write.write('%s REMOTE v%s %s\n' % ('#'*40, self.version, '#'*40))
                f_write.write(result)
                f_write.write('\nEND')
            if r: return r.group(2)
        return ''

    @thread_func()
    def _deamon(self, stop_flag = []):
        def _close_deamon(result): return result.lower() == 'close'
        def _update_deamon(result): return result.lower() == 'update'
        # self.deamon_config: [(func, time_wait), ...]
        self._deamon_time_cnt = {}
        while True:
            for _func, _time_wait in self.deamon_config:
                if not _func in self._deamon_time_cnt: self._deamon_time_cnt[_func] = -1
                self._deamon_time_cnt[_func] = self._deamon_time_cnt[_func] + 1
                if self._deamon_time_cnt[_func] >= _time_wait:
                    result = _func()
                    if _close_deamon(result): stop_flag.append('close')
                    elif _update_deamon(result): stop_flag.append('update')
                    self._deamon_time_cnt[_func] = 0
            if len(stop_flag): break
            time.sleep(1)

    def _add_deamon_config(self, func, time_wait):
        if not hasattr(self, 'deamon_config'):
            self.deamon_config = []
        self.deamon_config.append((func, time_wait))

    def keep(self):
        stop_flag = []
        self._add_deamon_config(self._check_cmd_deamon, time_wait = 1)
        self._deamon(stop_flag)
        #input = raw_input('keep deamon running! press any key to terminate...\n')
        #stop_flag.append(1)
        while True:
            if len(stop_flag): break
            time.sleep(1)
        if stop_flag[0] == 'close':
            self.print_('the remote proxy server has been closed.')
        elif stop_flag[0] == 'update':
            self.print_('the remote proxy server is updating...')
            time.sleep(1)
            self._update_self()
        self.print_('remote proxy server stop.')
        if self.output_file: self.output_file.close()

    def test_update(self):
        def _print_test_info(index):
            self.print_('test info 1: %d' % index)
        _print_test_info(1)
        input = raw_input('keep deamon running! press any key to terminate...\n')
        print 'gogo'
        #self._update_self()
        print 'gogo............'
        self.print_('test end')


if __name__ == '__main__':
    run = 1
    # python remote.py server_idx [test]
    if run == 1:
        server_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 1
        if len(sys.argv) == 3 and sys.argv[2] == 'test':
            prxy = RunProxy(server_idx, log_to_file = False)
        else:
            prxy = RunProxy(server_idx)
        prxy.keep()
    else:  # test
        remote = Remote()
        print 'haha'
        print 'haha2'
        remote.clear()
        print 'haha3'
        print 'haha4'
        assert False, 'error h'
        print 'hehe'



