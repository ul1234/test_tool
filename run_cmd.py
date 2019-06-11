#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys, os, subprocess
from datetime import datetime


class RunCmd(object):
    def __init__(self):
        self.DEBUG = False

    def _update_self(self):
        args = sys.argv[:]
        args.insert(0, sys.executable)
        sys.stdout.flush()
        self.print_('begin updating: %s, %s' % (sys.executable, args))
        os.execv(sys.executable, args)

    def _print(self, str):
        print(str)
        sys.stdout.flush()

    def print_(self, str, output_time = True):
        if output_time:
            self._print('[%s]%s' % (datetime.now().strftime('%y-%m-%d %H:%M:%S'), str))
        else:
            self._print(str)

    def _run(self, cmd):
        try:
            p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(__file__), 'test_tool.py')], shell = True, stdin = subprocess.PIPE, stdout = subprocess.PIPE)
            result = p.communicate(cmd)
        except Exception as e:
            return [str(e)]
        return result[0]

    def run(self, cmd):
        if self.DEBUG:
            self.print_('%s' % cmd, output_time = False)
        else:
            self.print_('(Cmd) %s\n' % cmd, output_time = False)
            result = self._run(cmd)
            result = result.replace('(Cmd) ', '')
            self.print_(result.strip(), output_time = False)
            self.print_('\n{} Finish {}\n'.format('#'*30, '#'*30), output_time = False)

            
if __name__ == '__main__':
    run_cmd = RunCmd()
    run_cmd.run('help clean')
    
    