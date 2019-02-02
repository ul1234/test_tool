#!/usr/bin/python
# -*- coding: utf-8 -*-

from optparse import OptionParser, make_option, OptParseError
from glob import glob
import os, re, sys, traceback, cmd, time, ConfigParser, urllib2, socket, threading, urllib, subprocess
import win32api, win32gui, win32con
from decorator import thread_func, use_system32_on_64bit_system
from datetime import datetime, timedelta
from wincmd import WinCmd
from clipcomm import ClipComm, ZipUtil
from cctool import CcTool
from strtool import StrTool
from remote import Remote
from tsms import TSMS
from proxy import WindowsProxySetting
from check import CodeCheck
from tc import TC
from hook_tc import HookToolCacheManager, TeamcityIni
# import readline

######################## command line interface ##########################
class CmdException(Exception): pass

class OptParser(OptionParser):
    def error(self, msg):
        raise OptParseError(msg)

    def format_help(self):
        return OptionParser.format_help(self) + (self._example if hasattr(self, '_example') else '')

    def set_example(self, example = ''):
        if example:
            first_line_found = False
            self._example = '\nExamples:\n'
            for line in example.split('\n'):
                if not first_line_found:
                    if not line.strip(): continue
                    align_leading_spaces = len(line) - len(line.lstrip())
                    first_line_found = True
                remain_leading_spaces = max(0, len(line) - len(line.lstrip()) - align_leading_spaces)
                self._example += ' '*remain_leading_spaces + line.strip() + '\n'

# decoration function
def options(option_list, usage = '', example = ''):
    _abbrev_class = CmdLineWithAbbrev
    if not isinstance(option_list, list):
        option_list = [option_list]
    option_list += _abbrev_class.ALL_OPTIONS_ADD
    def option_setup(func):
        optParser = OptParser(option_list = option_list)
        optParser.set_example(example)
        func_name = func.__name__[3:]
        usage_already_set = False
        if hasattr(_abbrev_class, 'ABBREV'):
            for f, abbrev in _abbrev_class.ABBREV:
                if func_name == f:
                    optParser.set_usage("%s(%s) %s" % (func_name, abbrev, usage))
                    usage_already_set = True
                    break
        if not usage_already_set:
            optParser.set_usage("%s %s" % (func_name, usage))
        def new_func(instance, arg):
            try:
                opts, new_args = optParser.parse_args(arg.split())
            except OptParseError as e:
                print (e)
                optParser.print_help()
                return
            try:
                result = func(instance, new_args, opts)
                return result
            except CmdException as e:
                print '%s RUN EXCEPTION: %s\n' % (func_name, e)
                optParser.print_help()
                return
            except Exception as e:
                print '%s RUN EXCEPTION: %s\n' % (func_name, e)
                print traceback.format_exc()
                optParser.print_help()
                return
        func_doc = ('%s\n' % func.__doc__) if func.__doc__ else ''
        new_func.__doc__ = '%s%s' % (func_doc, optParser.format_help())
        return new_func
    return option_setup

def min_args(num = 1):
    def _min_args(func):
        def _func(instance, args, opts):
            if len(args) < num:
                raise CmdException('args number should >= %d' % num)
            return func(instance, args, opts)
        _func.__name__ = func.__name__      # fake function name
        return _func
    return _min_args

class CmdLineWithAbbrev(cmd.Cmd):
    ABBREV = [('build', 'b'), ('gen_batch', 'g'), ('run_batch', 'r'), ('open', 'o'), ('ana_rslt', 'a'), ('proxy', 'p'), ('remote_copy', 'c'), ('monitor', 'm'),
              ('run_bat', 'bat'), ('find_hde_vector', 'vec'), ('html_to_script', 'h2s'), ('split_files', 'spl'), ('open_case', 'oc'), ('load_bin', 'lb'),
              ('copy_case', 'cc'), ('delete_binary', 'dbin'), ('gen_rav_priv_bin', 'ravbin'), ('gen_rav_cases_batch', 'ravbatch'), ('gen_cpu_sym', 'cpu'),
              ('copy_result', 'cr'), ('cmp_rslt', 'cmrlt'), ('open_soft', 'soft'), ('msg_identify', 'msg'), ('copy_change_files', 'cchange'),
              ('gen_log', 'glog'), ('change_ulan', 'ulan'), ('test_re', 're'), ('filter_logs', 'filter'), ('set_run1', 'r1'), ('ubi_file', 'ubi'),
              ('fix_remote_copy', 'fix'), ('extract_log', 'extract'), ('trc_file', 'trc'), ('update_rav', 'urav'), ('build_py', 'bpy'),
              ('update_batch', 'ubatch'), ('build_lte', 'blte'), ('remote_run_sanity', 'rr'),
              ('run_teamcity', 'rtc'), ('get_usf_and_script', 'script'), ('list_files', 'ls'), ('copy', 'cp'),
              ('EOF', 'q'), ('EOF', 'quit'), ('EOF', 'exit'), ('help', 'h')]

    MONITOR_CMD = [] #['env', 'run_batch', 'build', 'update_rav']
    REMOTE_CMD = ['remote']
    NON_REMOTE_CMD = ['mode', 'EOF', 'nothing']
    ALL_OPTIONS_ADD = [make_option("--monitor", action = "store_true", dest = "_monitor", default = False, help = "report finish status to monitor"),
                       make_option("--cmd", action = "store_true", dest = "_cmd_show", default = False, help = "show command string for debug"),
                       make_option("--remote", action = "store_true", dest = "_remote", default = False, help = "remote run the command"),
                      ]

    ALL_OPTIONS_CMD = {'--cmd': ('_precmd_cmd', '_postcmd_cmd')}

class CmdLine(CmdLineWithAbbrev):
    # class cmd.Cmd([completekey[, stdin[, stdout]]])
    # Cmd.use_rawinput = False to use sys.stdout.write() and sys.stdin.readline()
    def __init__(self, remote_call = False, *args, **kwargs):
        cmd.Cmd.__init__(self, *args, **kwargs)
        self.tool = TestTool(clear_signals = not remote_call)
        self._check_abbrev()
        self._set_default_project_path()
        self._set_window_title()
        self.remote_call = remote_call
        self.prompt_save = self.prompt
        self.always_remote = False

    def _split_option(self, option):
        main_delimiter = self.tool.option_delimiters[0]
        for delimiter in self.tool.option_delimiters[1:]:
            option = option.replace(delimiter, main_delimiter)
        return option.split(main_delimiter) if option else []

    def _set_default_project_path(self, project_path = ''):
        self.default_project_path = project_path
        if project_path: self.tool.print_('set default project path: %s' % project_path)

    def _set_window_title(self):
        v = datetime.fromtimestamp(os.stat(__file__).st_mtime).strftime('%y%m%d_%H%M%S')
        WinCmd.cmd('title TEST TOOL v%s !' % v)   # must end with ! to enable close other command window

    def _get_project_path(self, project_path = ''):
        if not project_path and not self.default_project_path: raise CmdException('no project path exist!')
        if not project_path: self.tool.print_('get default project path: %s' % self.default_project_path)
        return project_path or self.default_project_path

    def _check_abbrev(self):
        abb = [a for f, a in self.ABBREV]
        if len(abb) != len(set(abb)):
            raise CmdException('check ABBREV failure! the same abbreviation for commands, please check!!!')

    def _onecmd_with_abbrev(self, line):
        def _deal_with_abbrev(line_cmd):
            if len(line_cmd):
                for f, abbrev in self.ABBREV:
                    if abbrev == line_cmd[0]:
                        line_cmd[0] = f
                        break
            return line_cmd
        def _deal_with_help(line_cmd):
            return [line_cmd[0]] + _deal_with_abbrev(line_cmd[1:])
        # deal with abbreviation
        line_cmd = line.strip().split()
        if len(line_cmd):
            if line_cmd[0] == 'help':
                line_cmd = _deal_with_help(line_cmd)
            else:
                line_cmd = _deal_with_abbrev(line_cmd)
                if line_cmd[0] == 'help':
                    line_cmd = _deal_with_help(line_cmd)
        else:
            line_cmd = ['nothing']
        return ' '.join(line_cmd)

    def _runcmd(self, line):
        return self.onecmd(self._onecmd_with_abbrev(line))

    def _command_line_with_remote(self, lines):
        if not self.remote_call:
            multi_lines = lines.split('&&')
            for line in multi_lines:
                if line.strip():
                    c = line.strip().split()[0]
                    for f, abbrev in self.ABBREV:
                        if abbrev == c:
                            c = f
                            break
                    if (hasattr(self, 'NON_REMOTE_CMD') and c in self.NON_REMOTE_CMD):
                        return False
                    if line.find('--remote') > 0 or (hasattr(self, 'REMOTE_CMD') and c in self.REMOTE_CMD):
                        return True
            if self.always_remote: return True
        return False

    def precmd(self, lines):
        if self._command_line_with_remote(lines):
            self.remote_run = True
            if not hasattr(self, 'remote'): self.remote = Remote()
            self.remote.run(lines)
            return self._onecmd_with_abbrev('nothing')
        else:
            self._run_global_precmd(lines)
            self.last_run_line = lines
            multi_lines = lines.split('&&')     # support multi-lines, use '&&' to concatenate
            for line in multi_lines[:-1]:
                self._runcmd(line)
            return self._onecmd_with_abbrev(multi_lines[-1])

    def postcmd(self, stop, line):
        if not hasattr(self, 'remote_run') or not self.remote_run:
            self._run_global_postcmd()
            self.tool.print_(' ', output_time = False)
            if self._command_line_with_monitor(self.last_run_line):
                self.tool.report_finish(msg = self.last_run_line)
        self.remote_run = False
        return stop

    def _command_line_with_monitor(self, lines):
        multi_lines = lines.split('&&')
        for line in multi_lines:
            if line:
                c = line.strip().split()[0]
                for f, abbrev in self.ABBREV:
                    if abbrev == c:
                        c = f
                        break
                if line.find('--monitor') > 0 or (hasattr(self, 'MONITOR_CMD') and c in self.MONITOR_CMD):
                    return True
        return False

    def _precmd_cmd(self):
        WinCmd.SHOW_CMD_STRING = True

    def _postcmd_cmd(self):
        WinCmd.SHOW_CMD_STRING = False

    def _run_global_precmd(self, lines):
        for _option, (_pre, _post) in self.ALL_OPTIONS_CMD.items():
            if lines.find(_option) > 0:
                if _pre: getattr(self, _pre)()

    def _run_global_postcmd(self):
        lines = self.last_run_line
        for _option, (_pre, _post) in self.ALL_OPTIONS_CMD.items():
            if lines.find(_option) > 0:
                if _post: getattr(self, _post)()

    def _change_prefix_str(self, str = ''):
        self.prompt = str or self.prompt_save

    @options([], "")
    def do_nothing(self, args, opts = None):
        pass

    @options([], "")
    def do_test_exception(self, args, opts = None):
        raise CmdException('test exception!')

    @options([make_option("-s", "--test_string", action = "store", type = "string", dest = "test_string", default = "", help = "test string"),
              make_option("-t", "--test_bool", action = "store_true", dest = "test_bool", default = False, help = "test bool"),
             ], "[-s string] [-t bool] args",
             example = '''
                1) test for example options
                2) test -s aaa -t
                    output aaa and True ''')
    @min_args(1)
    def do_test(self, args, opts = None):
        self.tool.print_('test_string is %s. test_bool is %s. args is %s' % (opts.test_string, opts.test_bool, args[0]))

    @options([make_option("-p", "--priority", action = "store", type = "string", dest = "priority", default = "0", help = "debug priority"),
             ], "[-p priority] {enable|disable}")
    @min_args(1)
    def do_debug(self, args, opts = None):
        self.tool.debug_enable = True if args[0] == 'enable' else False
        self.tool.print_('set debug enable to %s' % self.tool.debug_enable)

    @options([make_option("-p", "--priority", action = "store", type = "string", dest = "priority", default = "0", help = "debug priority"),
             ], "[-p priority] {enable|disable}")
    @min_args(1)
    def do_ls(self, args, opts = None):
        self.tool.debug_enable = True if args[0] == 'enable' else False
        self.tool.print_('set debug enable to %s' % self.tool.debug_enable)

    @options([make_option("-c", "--close", action = "store_true", dest = "close", default = False, help = "close remote server"),
              make_option("-r", "--remote_server", action = "store", type = "string", dest = "remote_server", default = "", help = "remote server index"),
             ], "[-c] [-r server_index]")
    def do_mode(self, args, opts = None):
        if opts.close:
            self._change_prefix_str()
            self.always_remote = False
        elif opts.remote_server:
            server_index = int(opts.remote_server)
            self._change_prefix_str('[SERVER %d] ' % server_index)
            self.always_remote = True
            if not hasattr(self, 'remote'):
                self.remote = Remote(server_index)
            else:
                self.remote.reload(server_index)

    @options([make_option("-c", "--close", action = "store_true", dest = "close", default = False, help = "close remote server"),
              make_option("-u", "--update", action = "store_true", dest = "update", default = False, help = "update remote server"),
             ], "[-c] [-u]")
    def do_remote(self, args, opts = None):
        ip, ip_str = self.tool.get_ip_addr()
        ip_string = '%s(%s)' % (ip_str, ip)
        if opts.update:
            self.tool.print_(r'<REMOTE>UPDATE</REMOTE>', output_time = False)
            self.tool.print_(r'remote server %s updated successfully! wait 2 seconds to proceed.' % ip_string)
        elif opts.close:
            self.tool.print_(r'<REMOTE>CLOSE</REMOTE>', output_time = False)
            self.tool.print_(r'remote server %s closed successfully!' % ip_string)
        else:  # query
            self.tool.print_(r'<REMOTE>QUERY</REMOTE>', output_time = False)
            self.tool.print_(r'remote server %s is running.' % ip_string)

    @options([make_option("-w", "--window", action = "store_true", dest = "window", default = False, help = "remote server show window"),
              make_option("-l", "--log", action = "store_true", dest = "log", default = False, help = "show remote server log"),
             ], "[-w] [-l]")
    def do_server(self, args, opts = None):
        if opts.log:
            if not len(args): self.print_('please set the server index.')
            server_idx = int(args[0])
            log_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'remote', 'remote_server_log_%d.txt' % server_idx)
            if not os.path.isfile(log_filename): self.print_('no log file found! %s' % log_filename)
            WinCmd.explorer(log_filename)
        else:
            if len(args):
                server_idx = int(args[0])
            else:
                ip, ip_str = self.tool.get_ip_addr()
                server_idx = int(ip.split('.')[-1])
            remote_filename = os.path.join(os.path.dirname(__file__), 'remote.py')
            if opts.window:
                WinCmd.cmd('python %s %d test' % (remote_filename, server_idx), showcmdwin = True, wait = True)
            else:
                CREATE_NO_WINDOW = 0x08000000
                subprocess.Popen([sys.executable, remote_filename, '%d' % server_idx], creationflags = CREATE_NO_WINDOW)
            self.tool.print_('remote server %d running successfully!' % server_idx)

    @options([make_option("-p", "--port", action = "store", type = "string", dest = "port", default = "1234", help = "proxy server port"),
              make_option("-n", "--no_hack", action = "store_true", dest = "no_hack", default = False, help = "no hack, only direct proxy"),
              make_option("-l", "--local", action = "store_true", dest = "local", default = False, help = "local http proxy"),
             ], "[-p port] [-l] [-n] {on|off}")
    @min_args(1)
    def do_proxy(self, args, opts = None):
        proxy_enable = True if args[0] == 'on' else False
        if opts.local:
            self.tool.stop_proxy_server()
            if proxy_enable:
                self.tool.start_proxy_server(int(opts.port), opts.no_hack)
                self.tool.print_('start proxy server at localhost:%s successfully.' % opts.port)
            else:
                self.tool.print_('stop proxy server successfully.')
        else:
            self.tool.set_remote_proxy(proxy_enable)
            self.tool.print_('set http proxy successfully.')

    def _parse_cpu_num(self, cpu_string):
        # format: c66cpu(0,1,2) or cpu(0-3,5)
        cpu_nums = []
        prefix_content = cpu_string.split('(')
        if len(prefix_content) == 1:
            cpu_nums = [cpu_string]
        else:
            prefix, content = prefix_content
            if content.endswith(')'): content = content[:-1]
            for n in content.split(','):
                n_range = n.split('-')
                if len(n_range) == 1:
                    cpu_nums.append('%s%s' % (prefix, n))
                else:
                    start_range, end_range = n_range
                    for i in range(int(start_range), int(end_range)+1):
                        cpu_nums.append('%s%d' % (prefix, i))
        if not cpu_nums: raise CmdException('cannot detect partial builds from %s' % cpu_string)
        return cpu_nums

    def _copy_binary(self, output_paths, project_path, build_binary_path, dest_dir_name, backup = False):
        #WinCmd.explorer(build_log_file)
        for output_path in output_paths:
            dest_dir = os.path.join(output_path, dest_dir_name)
            if os.path.isdir(dest_dir):
                if backup: WinCmd.rename_dir(dest_dir, dest_dir + '_1')
                else: WinCmd.del_dir(dest_dir, include_dir = True)
            total_try_times = 2
            while True:
                total_try_times -= 1
                try:
                    self.tool.print_('start copying to folder: %s ...' % dest_dir)
                    WinCmd.copy_dir(build_binary_path, dest_dir)
                    pyd_dest_dir = os.path.join(dest_dir, self.tool.rel_pyd_dir)
                    WinCmd.make_dir(pyd_dest_dir)
                    for pyd_file in self.tool.pyd_file:
                        WinCmd.copy_file(os.path.join(project_path, self.tool.rel_build_pyd_path, pyd_file), pyd_dest_dir)
                    self.tool.print_('copy to folder: %s successfully!' % dest_dir)
                    break
                except:
                    if total_try_times == 0:
                        self.tool.print_('Caution: copy to folder: %s failure!!!' % dest_dir)
                        WinCmd.del_dir(dest_dir, include_dir = True)
                        error_occured = True
                        break
                    self.tool.print_('copy to folder: %s failure, try to release some disk space...' % dest_dir)
                    WinCmd.del_dir(dest_dir, include_dir = True)
                    self.tool.delete_earliest_subfolders(2)

    @options([make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "sue:[4x2]|4x4|2x2|4x2ULMIMO, mue:[2x2]|2x2_SPLIT_DL, cue:[EXTMUE]|LOADSYS_SPLIT_DL|LS2_DL|LS2"),
              make_option("-w", "--window", action = "store_true", dest = "window", default = False, help = "compile in window and wait"),
             ], "[-p PRODUCT] [-w] project_path [cpu/c66cpu(0-5, 7, 9-11)]")
    @min_args(1)
    def do_build_py(self, args, opts = None):
        project_path = args[0]
        WinCmd.check_folder_exist(project_path)
        self._set_default_project_path(project_path)
        project_name = os.path.basename(project_path)
        products, ue = self.tool.get_build_products(self._split_option(opts.product), project_name)
        if not products: raise CmdException('cannot determine the products from %s, please specify using -p.' % project_name)
        product = products[0].lower()
        if product.startswith('ls2_') and not product == 'ls2_2dsp': product = 'ls2'
        partial_builds = self._parse_cpu_num(args[1])
        if not partial_builds: raise CmdException('cannot detect partial builds from %s' % args[1])
        self.tool.print_('partial builds: %s' % str(partial_builds))
        py_base_path = os.path.join(project_path, r'lte_dsp_app\main\%s\%s' % (ue, product))
        WinCmd.check_folder_exist(py_base_path)
        for partial_build in partial_builds:
            py_file = os.path.join(py_base_path, partial_build, '%s.py' % partial_build)
            WinCmd.check_file_exist(py_file)
            WinCmd.cmd('python %s' % os.path.basename(py_file), os.path.dirname(py_file), showcmdwin = True, wait = False, retaincmdwin = False)
            self.tool.print_('Run %s finished.' % py_file)

    @options([make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "sue:[4x2]|4x4|2x2|4x2ULMIMO, mue:[2x2]|2x2_SPLIT_DL, cue:[EXTMUE]|LOADSYS_SPLIT_DL|LS2_DL|LS2"),
              make_option("-d", "--hde", action = "store_true", dest = "hde", default = False, help = "build hde or target"),
              make_option("-n", "--name", action = "store", type = "string", dest = "name", default = "", help = "binary path name"),
              make_option("-j", "--cpu_num", action = "store", type = "string", dest = "cpu_num", default = "8", help = "cpu num used"),
              make_option("-w", "--window", action = "store_true", dest = "window", default = False, help = "compile in window and wait"),
              make_option("-1", "--backup", action = "store_true", dest = "backup", default = False, help = "backup old binary first when copy"),
              make_option("-m", "--asm", action = "store_true", dest = "asm", default = False, help = "asm output when build"),
              make_option("-c", "--clean", action = "store_true", dest = "clean", default = False, help = "clean the build files before building"),
              make_option("-b", "--binary", action = "store_true", dest = "binary", default = False, help = "output to binary folder, shortcut for -o user"),
              make_option("-o", "--output", action = "store", type = "string", dest = "output", default = "", help = "output path, path1|path2"),
              make_option("-0", "--not_build", action = "store_true", dest = "not_build", default = False, help = "do not actually build, may use to move binary only")],
             "[-p PRODUCT] [-d] [-b] [-0] [-n name] [-w] [-j 8] [-1] [-m] [-o bin_path1|bin_path2] project_path [cpu/c66cpu(0-5, 7, 9-11)]")
    @min_args(1)
    def do_build_lte(self, args, opts = None):
        project_path, output_paths = args[0], self._split_option(opts.output)
        WinCmd.check_folder_exist(project_path)
        self._set_default_project_path(project_path)
        output_paths = ['default' if p == 'user' else p for p in output_paths]
        if opts.binary: output_paths.append('default')
        output_paths = list(set(output_paths))
        temp_output_paths, output_paths = output_paths, []
        for output_path in temp_output_paths:
            if output_path == 'default': output_path = self.tool.binary_path
            WinCmd.check_folder_exist(output_path, can_be_empty = True)
            output_paths.append(output_path)
        build_cmd_path = os.path.join(project_path, self.tool.rel_build_path)
        build_binary_path = os.path.join(project_path, self.tool.rel_build_hde_path if opts.hde else self.tool.rel_build_ftp_path)
        build_str = 'build=hde' if opts.hde else ''
        # no products specified means all products for project name
        project_name = os.path.basename(project_path)
        products, ue = self.tool.get_build_products(self._split_option(opts.product), project_name)
        if not products: raise CmdException('cannot determine the products from %s, please specify using -p.' % project_name)
        self.tool.print_('build total %d products: %s,   ' % (len(products), products))
        error_occured = False
        if opts.clean: self._runcmd('clean %s' % project_path)
        if opts.not_build:
            if not output_paths: self.tool.print_('no output path setting.')
            else:
                dest_dir_name = '%s_%s' % (opts.name or os.path.basename(project_path), products[0])
                self._copy_binary(output_paths, project_path, build_binary_path, dest_dir_name, opts.backup)
            return
        for product in products:
            if len(args) > 1:
                partial_builds = self._parse_cpu_num(args[1])
                if not partial_builds: raise CmdException('cannot detect partial builds from %s' % args[1])
                self.tool.print_('partial builds: %s' % str(partial_builds))
                is_partial_build = True
            else:
                partial_builds = ['all all=all']
                is_partial_build = False

            for partial_build in partial_builds:
                build_start_time = time.time()
                asm_out = 'asmout=on' if opts.asm else ''
                build_cmd = 'scons %s product=%s %s -j%s %s quick=yes' % (partial_build, product.upper(), build_str, opts.cpu_num, asm_out)
                self.tool.print_('start build "%s"...' % build_cmd)
                if opts.hde or opts.window:
                    WinCmd.cmd(build_cmd, build_cmd_path, showcmdwin = True, wait = True, retaincmdwin = True)
                else:
                    WinCmd.del_dir(build_binary_path)
                    temp_build_file = self.tool.get_temp_build_file(project_path)
                    if os.path.isfile(temp_build_file): WinCmd.del_file(temp_build_file)
                    start_time = time.time()
                    WinCmd.cmd('%s >> %s' % (build_cmd, temp_build_file), build_cmd_path, showcmdwin = False)
                    elapse_time = time.time() - start_time
                    #self.tool.print_('Output temp log file: %s' % temp_build_file)  # for debug
                    build_result = self.tool.parse_build_logs(temp_build_file)
                    build_success, build_msg = build_result[0], build_result[1]
                    if build_success:
                        self.tool.print_('[PASS]%s' % build_msg)
                    else:
                        self.tool.print_('[Error!!!!!!!!!!!]%s' % build_msg)
                        if len(build_result) > 2:
                            for error_line in build_result[2]:
                                self.tool.print_('%s' % error_line)
                        continue
                    if output_paths:
                        dest_dir_name = '%s_%s' % (opts.name or os.path.basename(project_path), product)
                        self._copy_binary(output_paths, project_path, build_binary_path, dest_dir_name, opts.backup)
                build_elapse_time = time.time() - build_start_time
                time_str = '%ds' % build_elapse_time if build_elapse_time < 60 else '%dm%ds' % (int(build_elapse_time/60), build_elapse_time%60)
                self.tool.print_('build %s done after %s!' % (product, time_str))
                self.tool.print_('#'*60)
        if error_occured: self.tool.print_('Error Occured! Please take care!!!')

    @options([make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "nr or nbiot"),
              make_option("-d", "--hde", action = "store_true", dest = "hde", default = False, help = "build hde or target"),
              make_option("-u", "--ut", action = "store_true", dest = "ut", default = False, help = "build unittest"),
              make_option("-c", "--ct", action = "store_true", dest = "ct", default = False, help = "build comptest"),
              make_option("-n", "--name", action = "store", type = "string", dest = "name", default = "", help = "binary path name"),
              make_option("-j", "--cpu_num", action = "store", type = "string", dest = "cpu_num", default = "8", help = "cpu num used"),
              make_option("-w", "--window", action = "store_true", dest = "window", default = False, help = "compile in window and wait"),
              make_option("-1", "--backup", action = "store_true", dest = "backup", default = False, help = "backup old binary first when copy"),
              make_option("-b", "--binary", action = "store_true", dest = "binary", default = False, help = "output to binary folder, shortcut for -o user"),
              make_option("-o", "--output", action = "store", type = "string", dest = "output", default = "", help = "output path, path1|path2"),
              make_option("-0", "--not_build", action = "store_true", dest = "not_build", default = False, help = "do not actually build, may use to move binary only")],
             "[-p PRODUCT] [-d] [-u] [-c] [-b] [-0] [-n name] [-w] [-j 8] [-1] [-o bin_path1|bin_path2] project_path")
    @min_args(1)
    def do_build(self, args, opts = None):
        project_path, output_paths = args[0], self._split_option(opts.output)
        WinCmd.check_folder_exist(project_path)
        self._set_default_project_path(project_path)
        output_paths = ['default' if p == 'user' else p for p in output_paths]
        if opts.binary: output_paths.append('default')
        output_paths = list(set(output_paths))
        temp_output_paths, output_paths = output_paths, []
        for output_path in temp_output_paths:
            if output_path == 'default': output_path = self.tool.binary_path
            WinCmd.check_folder_exist(output_path, can_be_empty = True)
            output_paths.append(output_path)
        build_cmd_path = os.path.join(project_path, self.tool.rel_build_path)
        build_binary_path = os.path.join(project_path, self.tool.rel_build_hde_path if opts.hde else self.tool.rel_build_ftp_path)
        if opts.hde:
            build_str = 'build=hde'
        elif opts.ut:
            build_str = 'build=unittest'
        elif opts.ct:
            build_str = 'build=comptest'
        else:
            build_str = ''
        products = [opts.product] if opts.product else ['NR5G']
        error_occured = False
        if opts.not_build:
            if not output_paths: self.tool.print_('no output path setting.')
            else:
                dest_dir_name = '%s_%s' % (opts.name or os.path.basename(project_path), products[0])
                self._copy_binary(output_paths, project_path, build_binary_path, dest_dir_name, opts.backup)
            return
        for product in products:
            build_start_time = time.time()
            build_cmd = 'scons all product=%s %s -j%s quick=yes' % (product.upper(), build_str, opts.cpu_num)
            self.tool.print_('start build "%s"...' % build_cmd)
            if build_str or opts.window:
                WinCmd.cmd(build_cmd, build_cmd_path, showcmdwin = True, wait = True, retaincmdwin = True)
            else:
                WinCmd.del_dir(build_binary_path)
                temp_build_file = self.tool.get_temp_build_file(project_path)
                if os.path.isfile(temp_build_file): WinCmd.del_file(temp_build_file)
                start_time = time.time()
                WinCmd.cmd('%s >> %s' % (build_cmd, temp_build_file), build_cmd_path, showcmdwin = False)
                elapse_time = time.time() - start_time
                #self.tool.print_('Output temp log file: %s' % temp_build_file)  # for debug
                build_result = self.tool.parse_build_logs(temp_build_file)
                build_success, build_msg = build_result[0], build_result[1]
                if build_success:
                    self.tool.print_('[PASS]%s' % build_msg)
                else:
                    self.tool.print_('[Error!!!!!!!!!!!]%s' % build_msg)
                    if len(build_result) > 2:
                        for error_line in build_result[2]:
                            self.tool.print_('%s' % error_line)
                    continue
                if output_paths:
                    dest_dir_name = '%s_%s' % (opts.name or os.path.basename(project_path), product)
                    self._copy_binary(output_paths, project_path, build_binary_path, dest_dir_name, opts.backup)
            build_elapse_time = time.time() - build_start_time
            time_str = '%ds' % build_elapse_time if build_elapse_time < 60 else '%dm%ds' % (int(build_elapse_time/60), build_elapse_time%60)
            self.tool.print_('build %s done after %s!' % (product, time_str))
            self.tool.print_('#'*60)
        if error_occured: self.tool.print_('Error Occured! Please take care!!!')

    @options([make_option("-i", "--pieces", action = "store", type = "string", dest = "pieces", default = "", help = "piece index, 0~total n, example: 1|3"),
              make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "data folder to be processed"),
              make_option("-l", "--last_pieces", action = "store", type = "string", dest = "last_pieces", default = "", help = "last piece index, 1 mean n-1, etc."),
              make_option("-d", "--default_split", action = "store_true", dest = "default_split", default = False, help = "default split pieces with -p or -l"),
              make_option("-z", "--latest", action = "store_true", dest = "latest", default = False, help = "latest file with all found files"),
              make_option("-a", "--all_pieces", action = "store_true", dest = "all_pieces", default = False, help = "all the pieces be generated"),
              make_option("-c", "--excel", action = "store_true", dest = "excel", default = False, help = "excel file, split files always contain the header"),
              make_option("-b", "--bytes_align", action = "store_true", dest = "bytes_align", default = False, help = "split files in absolutely bytes alignment, not line break alignment"),
              make_option("-s", "--piece_size", action = "store", type = "string", dest = "piece_size", default = "30", help = "piece size, [30]Mbytes"),
              make_option("-r", "--from_remote_run1", action = "store_true", dest = "from_remote_run1", default = False, help = "split logs from remote run1, output to run_result"),
              make_option("-x", "--remove_size", action = "store", type = "string", dest = "remove_size", default = "200", help = "remove files that size smaller than size, default: 200 KBytes)"),
              make_option("-n", "--last_number", action = "store", type = "string", dest = "last_number", default = "1", help = "result from run last number, 0 means all run"),
             ], "[-p path] [-i pieces] [-l last_pieces] [-s piece_size] [-z] [-a] [-d] [-x] [-b] [-r] [-n last_number] {files(regex)}")
    @min_args(1)
    def do_split_files(self, args, opts = None):
        pieces = [int(p) for p in self._split_option(opts.pieces)] if opts.pieces else []
        last_pieces = [int(p) for p in self._split_option(opts.last_pieces)] if opts.last_pieces else []
        piece_size = int(opts.piece_size)
        if opts.from_remote_run1:
            args = [os.path.join(self.tool.run_result_path, self.tool.re_delimiters[0]+a) for a in args]
            dest_folder = self.tool.get_remote_run1_path()
        files = self.tool.get_re_files([os.path.join(opts.path, a) for a in args])
        if opts.from_remote_run1:
            last_number = int(opts.last_number)
            files = self.tool.files_in_last_run(files, last_number)
        if opts.latest and len(files) > 1:
            files_mtime = [(os.stat(f).st_mtime, f) for f in files]
            files_mtime.sort(reverse = True)
            files = [files_mtime[0][1]]
        for f in files:
            if os.path.splitext(f)[1] in ['.csv', '.xls', '.xlsx'] or opts.excel:
                excel_file = True
                self.tool.print_('Excel file detected. Adding headers to each split file...')
            else:
                excel_file = False
            result_files = self.tool.file_split(f, pieces, last_pieces, piece_size, opts.all_pieces, opts.default_split, opts.bytes_align, excel_file)
            if opts.from_remote_run1 and not result_files: # file too small to split
                if os.stat(f).st_size > int(opts.remove_size) * 1000: # KBytes -> Bytes:
                    result_files = [f]
                else:
                    self.tool.print_('file (%d Kbytes) too small, drop: %s' % (os.stat(f).st_size/1000, f))
            for result_file in result_files:
                if opts.from_remote_run1:
                    WinCmd.copy_file(result_file, dest_folder)
                    result_file = os.path.join(dest_folder, os.path.basename(result_file))
                self.tool.print_('split file from %s to %s successfully!' % (f, result_file))
        if not files: self.tool.print_('no files found from %s' % str([os.path.join(opts.path, a) for a in args]))

    @options([make_option("-r", "--regex", action = "store", type = "string", dest = "regex", default = "", help = "regular expression to search"),
              make_option("-s", "--piece_size", action = "store", type = "string", dest = "piece_size", default = "30", help = "piece size, [30]Mbytes"),
              make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "data folder to be processed"),
              make_option("-0", "--not_split", action = "store_true", dest = "not_split", default = False, help = "only search, do not split"),
              make_option("-c", "--excel", action = "store_true", dest = "excel", default = False, help = "excel file, split files always contain the header"),
              make_option("-b", "--bytes_align", action = "store_true", dest = "bytes_align", default = False, help = "split files in absolutely bytes alignment, not line break alignment"),
             ], "[-p path] [-r regex] [-s piece_size] [-x] [-b] [-0] {files(regex)}")
    @min_args(1)
    def do_search(self, args, opts = None):
        files = self.tool.get_re_files([os.path.join(opts.path, a) for a in args])
        for f in files:
            excel_file = True if os.path.splitext(f)[1] in ['.csv', '.xls', '.xlsx'] or opts.excel else False
            index, total_n = self.tool.search_in_file(f, opts.regex, int(opts.piece_size), opts.bytes_align, excel_file)
            if index < 0:
                self.tool.print_('cannot find string (%s) in file %s.' % (opts.regex, os.path.basename(f)))
            else:
                self.tool.print_('Index %d/%d found string (%s) in file %s.' % (index, total_n, opts.regex, os.path.basename(f)))
                if not opts.not_split:
                    self._runcmd('split_files -s %s -i %d %s %s %s' % (opts.piece_size, index, '-x' if opts.excel else '', '-b' if opts.bytes_align else '', f))
                break
        if not files: self.tool.print_('no files found from %s' % str([os.path.join(opts.path, a) for a in args]))

    @options([make_option("-r", "--regex", action = "store", type = "string", dest = "regex", default = "", help = "regular expression to search"),
              make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "data folder to be processed"),
              make_option("-o", "--output", action = "store", type = "string", dest = "output", default = "", help = "output result file"),
              make_option("-l", "--lines", action = "store", type = "string", dest = "lines", default = "0", help = "lines before and after the filtered line"),
              make_option("-0", "--no_sort", action = "store_true", dest = "no_sort", default = False, help = "do not sort the output logs"),
             ], "[-p path] [-r regex] [-l 0] [-o output_file] [-s] {files(regex)}")
    @min_args(1)
    def do_filter_logs(self, args, opts = None):
        files = self.tool.get_re_files([os.path.join(opts.path, a) for a in args], sort_by_time = True)
        if not files:
            self.tool.print_('no files found from %s' % str([os.path.join(opts.path, a) for a in args]))
        else:
            output_file_name, output_file_ext = os.path.splitext(files[0])
            output_file = opts.output or ('%s_filter%s' % (output_file_name, output_file_ext))
            if os.path.isfile(output_file): WinCmd.del_file(output_file)
            filtered_lines = 0
            for f in files:
                filtered_lines += self.tool.filter_in_file(f, opts.regex, int(opts.lines), output_file, file_flag = opts.no_sort)
            if filtered_lines:
                WinCmd.check_file_exist(output_file)
                if not opts.no_sort: WinCmd.sort_file(output_file)
                self.tool.print_('Filtered %d lines among %d files to %s successfully!' % (filtered_lines, len(files), output_file))
            else:
                self.tool.print_('cannot find "%s" among %d files.' % (opts.regex, len(files)))

    @options([make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "data folder to be processed"),
             ], "[-p path] {files(regex)}")
    @min_args(1)
    def do_combine(self, args, opts = None):
        files = self.tool.get_re_files([os.path.join(opts.path, a) for a in args])
        if files:
            files.sort()
            output_file_name, output_file_ext = os.path.splitext(files[0])
            output_file = '%s_combine%s' % (output_file_name, output_file_ext)
            with open(output_file, 'w') as f_write:
                for f in files:
                    f_write.write(open(f).read())
                    f_write.write('\r\n')
            self.tool.print_('combine file to %s successfully!' % os.path.basename(output_file))
        else:
             self.tool.print_('no files found from %s' % str([os.path.join(opts.path, a) for a in args]))

    @options([make_option("-d", "--dsp_cores", action = "store", type = "string", dest = "dsp_cores", default = "", help = "dsp core number, e.g. 4.1|2, default means all"),
              make_option("-m", "--hlc_cores", action = "store", type = "string", dest = "hlc_cores", default = "", help = "hlc core number, e.g. 4.1|2, default means all"),
              make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "data folder to be processed"),
              make_option("-0", "--only_dedicated", action = "store_true", dest = "only_dedicated", default = False, help = "only_dedicated core extraced, default is all, include dsp,hlc,umb,etc."),
              make_option("-z", "--latest", action = "store_true", dest = "latest", default = False, help = "latest file with all found files"),
              make_option("-x", "--remove_size", action = "store", type = "string", dest = "remove_size", default = "200", help = "remove files that size smaller than size, default: 200 KBytes)"),
             ], "[-p path] [-d dsp_cores] [-h hlc_cores] [-0] [-z] [-x remove_size] {files(regex)}")
    @min_args(1)
    def do_extract_log(self, args, opts = None):
        re_files = self.tool.get_re_files([os.path.join(opts.path, a) for a in args])
        if opts.latest and len(re_files) > 1:
            files_mtime = [(os.stat(f).st_mtime, f) for f in re_files]
            files_mtime.sort(reverse = True)
            re_files = [files_mtime[0][1]]
        for file in re_files:
            self.tool.print_('start extracting file from %s...' % file)
            all_result_files = self.tool.extract_log(file, self._split_option(opts.dsp_cores), self._split_option(opts.hlc_cores), opts.only_dedicated)
            result_files = self.tool.remove_smaller_files(all_result_files, int(opts.remove_size))
            if all_result_files:
                self.tool.print_('%d files extracted (%d files removed smaller than %s KBytes)!' % (len(result_files), len(all_result_files) - len(result_files), opts.remove_size))
            else:
                self.tool.print_('no files extracted from %s!' % (file))
        if not re_files: self.tool.print_('no files found from %s' % str([os.path.join(opts.path, a) for a in args]))

    @options([make_option("-v", "--verbose", action = "store_true", dest = "verbose", default = False, help = "list all files verbosely"),
              make_option("-f", "--to_file", action = "store_true", dest = "to_file", default = False, help = "result to file"),
             ], "[-v] [-f] [directory or files (re)] [files2...]")
    def do_list_files(self, args, opts = None):
        def print_output(self, str):
            if opts.to_file:
                self.temp_file.write(str + '\n')
            else:
                self.tool.print_(str, output_time = False)
        if len(args) == 0: args = [os.getcwd()]
        if opts.to_file:
            temp_filename = self.tool.get_temp_filename()
            self.temp_file = open(temp_filename, 'w')
        for d in args:
            if d.find(':') < 0 and not d.startswith('\\\\'): d = os.path.join(os.getcwd(), d)
            if os.path.isdir(d): d = os.path.join(d, '.*')
            parent_folder = os.path.dirname(d)
            if not os.path.isdir(parent_folder):
                self.tool.print_('invalid folder: %s' % parent_folder)
                continue
            pattern = os.path.basename(d)
            if len(pattern) > 1 and pattern[0] in self.tool.re_delimiters: pattern = pattern[1:]
            all_files = []
            for f in os.listdir(parent_folder):
                r = re.search(pattern, f, flags = re.IGNORECASE)
                if r: all_files.append(f)
            print_output(self, '\n[%s]\n' % d)
            if all_files:
                files_str = '\n'.join(all_files) if opts.verbose else '    '.join(all_files)
                print_output(self, files_str)
            else:
                print_output(self, 'no files found')
        if opts.to_file and self.temp_file:
            self.temp_file.close()
            WinCmd.explorer(temp_filename)
            self.tool.print_('generate file %s successfully!' % temp_filename)

    @options([], "change_list_file")
    @min_args(1)
    def do_copy_change_files(self, args, opts = None):
        file_list = os.path.join(args[0], 'file_change_list.txt') if os.path.isdir(args[0]) else args[0]
        WinCmd.check_file_exist(file_list)
        self.tool.copy_change_files(file_list)
        self.tool.print_('copy change files successfully!')

    @options([make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "test case or vector folder"),
              make_option("-v", "--vector", action = "store", type = "string", dest = "vector", default = "", help = "copy vector, *.aiq to pxi folder, or html file"),
              make_option("-f", "--from", action = "store_true", dest = "copy_from", default = False, help = "copy script from automation folder"),
              make_option("-e", "--remove", action = "store_true", dest = "remove", default = False, help = "remove the file first, force copy"),
             ], "[-f] [-e] [-v aiq_file or html_file] [-p folder] {case1|case2 or reg_file or none}")
    @min_args(1)
    def do_copy_case(self, args, opts = None):
        folder = self.tool.get_temp_path(opts.path) or self.tool.get_abs_path(opts.path)
        WinCmd.check_folder_exist(folder)
        vectors = []
        if opts.copy_from:
            self.tool.copy_case_from_automation(self._split_option(args[0]), folder)
        else:
            self.tool.copy_case_to_automation(folder, args)
            if opts.vector:
                if opts.vector.endswith('html'):
                    html_file = self._get_html_filename(opts.vector)
                    if not os.path.dirname(html_file): html_file = self.tool.get_re_files(os.path.join(folder, html_file))[0]
                    WinCmd.check_file_exist(html_file)
                    vec_numbers, vectors, _ = self.tool.gen_script_from_html(html_file)
                    vectors = [os.path.join(self.tool.aiq_path, p) for p in vectors]
                else:
                    vectors = self.tool.get_re_files(os.path.join(folder, opts.vector))
        if vectors:
            self.tool.copy_vectors(vectors, opts.remove)
            self.tool.print_('copy %d vectors to folder %s successfully!' % (len(vectors), self.tool.pxi_path))

    @options([], "update_file")
    @min_args(1)
    def do_gen_change_files(self, args, opts = None):
        update_file = os.path.join(args[0], 'file_change_list.txt') if os.path.isdir(args[0]) else args[0]
        change_list_file = os.path.join(os.path.dirname(args[0]), 'file_change_list.txt')
        WinCmd.check_file_exist(update_file)
        self.tool.update_file_to_change_file(update_file, change_list_file)

    @options([], "[working_dir]")
    def do_cd(self, args, opts = None):
        if not len(args): self.tool.print_('the current working directory: %s' % os.getcwd())
        if len(args) > 0:
            os.chdir(args[0])        # change working directory
            self.tool.print_('change working directory to: %s' % os.getcwd())

    @options([], "")
    def do_remote_copy(self, args, opts = None):
        text = WinCmd.get_clip_text()
        if text:
            self.tool.set_remote_clip_text(text)
            self.tool.print_('set remote clipboard with %d characters!' % len(text))

    @options([make_option("-c", "--cue", action = "store", type = "string", dest = "cue", default = "7c", help = "product: 5c|7c"),
              make_option("-s", "--sgh", action = "store_true", dest = "sgh", default = False, help = "shanghai server"),
              make_option("-v", "--vector", action = "store_true", dest = "vector", default = False, help = "load test vector"),
              make_option("-0", "--vector_only", action = "store_true", dest = "vector_only", default = False, help = "load test vector only"),
              make_option("-f", "--fum", action = "store", type = "string", dest = "fum_binary", default = "", help = "binary to run fum"),
             ], "[-f fum_binary] [-c cue_5c_7c] {sue|mue|cue} {tdd|fdd}")
    @min_args(1)
    def do_env(self, args, opts = None):
        product, rat = args[0], 'fdd' if len(args) == 1 else args[1]
        self.tool.set_env(product, rat, opts.fum_binary, opts.cue, opts.vector, opts.vector_only, opts.sgh)

    @options([make_option("-d", "--delete", action = "store_true", dest = "delete", default = False, help = "delete src_folder after copy"),
              make_option("-t", "--trace", action = "store_true", dest = "trace", default = False, help = "include trace result"),
              make_option("-p", "--pxi", action = "store_true", dest = "pxi", default = False, help = "include pxi file"),
              make_option("-l", "--log", action = "store", type = "string", dest = "log", default = "", help = "log files filter, can be 'all'"),
              make_option("-m", "--mux_log", action = "store_true", dest = "mux_log", default = False, help = "include mux log file"),
              make_option("-f", "--filter", action = "store", type = "string", dest = "filter", default = "", help = "regex filter to copy"),
              make_option("-s", "--src_folder", action = "store", type = "string", dest = "src_folder", default = "", help = "source folder"),
              make_option("-a", "--all", action = "store_true", dest = "all", default = False, help = "all files, default only files from latest run"),
              make_option("-0", "--no_common_files", action = "store_true", dest = "no_common_files", default = False, help = "no common files, use with -t/-m, etc."),
              make_option("--start", action = "store_true", dest = "start", default = False, help = "include the start commands html"),
              make_option("-n", "--last_number", action = "store", type = "string", dest = "last_number", default = "1", help = "result from run last number"),
             ], "[-d] [-t] [-l] [-m] [-p] [-0] [--start] [-f filter] [-a] [-n last_number] [-s src_folder] [dest_folder]")
    def do_copy_result(self, args, opts = None):
        if len(args) == 0:  # to remote run folder
            dest_folder = self.tool.get_remote_run1_path()
        else:
            dest_folder = args[0]
        last_number = int(opts.last_number)
        assert last_number > 0, 'invalid param last_number %d' % last_number
        if opts.all: last_number = 0
        need_copy_files_num, total_files_num = self.tool.copy_result(dest_folder, opts.src_folder, opts.trace, opts.pxi, opts.log, opts.mux_log, opts.delete, opts.start, opts.filter, last_number, opts.no_common_files)
        self.tool.print_('copy %d (out of %d) result files to %s successfully!' % (need_copy_files_num, total_files_num, dest_folder))

    @options([make_option("-e", "--empty_dest", action = "store_true", dest = "empty_dest", default = False, help = "empty dest folder first"),
             ], "src_folder(or regex files, @***) [dest_folder(default: temp folder)]")
    @min_args(1)
    def do_copy(self, args, opts = None):
        src_folder = args[0]
        if src_folder.find(':') < 0 and not src_folder.startswith('\\\\'): src_folder = os.path.join(os.getcwd(), src_folder)
        if not os.path.isdir(src_folder):
            src_folder = self.tool.get_re_files(src_folder, exclude_dir = False)
        dest_folder = args[1] if len(args) > 1 else self.tool.temp_path
        if not os.path.isdir(dest_folder): dest_folder = os.path.join(os.getcwd(), dest_folder)
        WinCmd.check_folder_exist(dest_folder)
        if opts.empty_dest: WinCmd.del_dir(dest_folder)
        if not isinstance(src_folder, list): src_folder = [src_folder]
        for s in src_folder:
            if os.path.isdir(s): WinCmd.copy_dir(s, dest_folder, empty_dest_first = False, include_src_dir = True)
            elif os.path.isfile(s): WinCmd.copy_file(s, dest_folder)
        self.tool.print_('copy %d folders(files) to %s successfully!' % (len(src_folder), dest_folder))

    @options([make_option("-p", "--project_path", action = "store", type = "string", dest = "project_path", default = "", help = "project path to find rrc tools"),
              make_option("-e", "--encode", action = "store_true", dest = "encode", default = False, help = "rrc encode / (decode otherwise)"),
              make_option("-f", "--from_clipboard", action = "store_true", dest = "from_clipboard", default = False, help = "load from clipboard, only for encode"),
              make_option("-n", "--file_name_id", action = "store", type = "string", dest = "file_name_id", default = "0", help = "file name to save or load"),
              make_option("-d", "--DL-DCCH-Message", action = "store_true", dest = "DL_DCCH_Message", default = False, help = "DL-DCCH-Message"),
              make_option("-u", "--UL-DCCH-Message", action = "store_true", dest = "UL_DCCH_Message", default = False, help = "UL-DCCH-Message"),
              make_option("-c", "--UE-EUTRA-Capability", action = "store_true", dest = "UE_EUTRA_Capability", default = False, help = "UE-EUTRA-Capability"),
             ], "[-p project_path][-e] [-f] [-n name] [-d|-u|-c(only for decode)]")
    def do_rrc(self, args, opts = None):
        if opts.encode:
            self.tool.rrc_encode(opts.project_path, opts.from_clipboard, opts.file_name_id)
        else:
            if opts.DL_DCCH_Message:
                message_name = 'DL-DCCH-Message'
            elif opts.UL_DCCH_Message:
                message_name = 'UL-DCCH-Message'
            elif opts.UE_EUTRA_Capability:
                message_name = 'UE-EUTRA-Capability'
            else:
                message_name = ''
            self.tool.rrc_decode(opts.project_path, opts.file_name_id, message_name)

    @options([make_option("-g", "--gen_case_cache", action = "store_true", dest = "gen_case_cache", default = False, help = "force generate hde case cache file"),
              make_option("-f", "--dest_folder", action = "store", type = "string", dest = "dest_folder", default = ".", help = "destination folder"),
             ], "[-g] [-f dest_folder] case1 [case2]")
    def do_find_hde_vector(self, args, opts = None):
        if opts.gen_case_cache: self.tool.gen_hde_case_cache()
        if len(args): self._find_hde_vector(args, dest_folder = opts.dest_folder)

    def _find_hde_vector(self, cases, no_vec_usf_files = [], dest_folder = '.'):
        files_found = 0
        for case in cases:
            results = self.tool.search_hde_vector(case, os.path.join(dest_folder, case))
            for result in results:
                files_found += 1
                self.tool.print_('case %s: found %s.' % (case, result))
            if not results: self.tool.print_('case %s: not found.' % case)
        for usf in no_vec_usf_files:
            results = self.tool.search_hde_vector(usf, dest_folder)
            for result in results:
                files_found += 1
                self.tool.print_('usf %s: found %s.' % (usf, result))
            if not results: self.tool.print_('usf %s: not found.' % usf)
        if files_found > 0: self.tool.print_('copy %d files to %s.' % (files_found, dest_folder))

    def _get_html_filename(self, html_file):
        for leading_slash_num in range(6,1,-1):
            if html_file.startswith('file:'+'/'*leading_slash_num):
                html_file = html_file[5+leading_slash_num-2:].replace(r'/', '\\')
                break
        if len(html_file) > 6 and ':' in html_file[:6] and html_file.startswith('\\'):
            html_file = html_file[2:]   # remove leading '\\' in case of ' \\P:\AAS_TM500_LTE\...'
        return html_file

    @options([make_option("-o", "--output_file", action = "store", type = "string", dest = "output_file", default = "", help = "output script file"),
              make_option("-v", "--vector", action = "store_true", dest = "vector", default = False, help = "find vector"),
             ], "[-v] [-o output_file] html")
    @min_args(1)
    def do_html_to_script(self, args, opts = None):
        # do not change, for others use...
        html_file = self._get_html_filename(args[0])
        html_path, filename = os.path.split(html_file)
        output_file = opts.output_file or '%s.txt' % filename[:5]
        WinCmd.copy_file(html_file, '.')
        vec_numbers, aiq_files, _ = self.tool.gen_script_from_html(html_file, output_file)
        self.tool.print_('generate %s successfully! vec numbers %s.' % (output_file, vec_numbers))
        self.latest_script_file = output_file
        if opts.vector: self._find_hde_vector(vec_numbers)

    @options([make_option("-o", "--output", action = "store", type = "string", dest = "output_folder", default = "", help = "output folder"),
              make_option("-v", "--vector", action = "store_true", dest = "vector", default = False, help = "find vector"),
              make_option("-m", "--lte_dcch_msg", action = "store_true", dest = "lte_dcch_msg", default = False, help = "add first LTE dcch msg after switch vector, for ENDC case"),
              make_option("-n", "--number", action = "store", type = "string", dest = "number", default = "", help = "manually set test number"),
             ], "[-v] [-o output_folder] [-n test_number] html")
    @min_args(1)
    def do_get_usf_and_script(self, args, opts = None):
        html_file = self._get_html_filename(args[0])
        WinCmd.check_file_exist(html_file)
        html_path, filename = os.path.split(html_file)
        case_num = filename[:5]
        try:
            case_num_int = int(case_num)
        except:
            if not opts.number: raise CmdException('cannot detect case num from %s' % filename)
            case_num = '%05d' % int(opts.number)
            self.tool.print_('cannot detect case num, use manually setting %s' % case_num)
        if opts.output_folder:
            output_folder = opts.output_folder
        else:
            WinCmd.check_folder_exist(self.tool.script_path)
            output_folder = os.path.join(self.tool.script_path, case_num)
            if not os.path.isdir(output_folder): WinCmd.make_dir(output_folder)
        WinCmd.check_folder_exist(output_folder)
        output_file = os.path.join(output_folder, '%s.txt' % case_num)
        WinCmd.copy_file(html_file, output_folder)
        case_file = self.tool.get_case_file_from_html(html_file)
        if case_file:
            if not os.path.isfile(case_file):
                self.tool.print_('Warning: no such case file, %s' % case_file)
            else:
                WinCmd.copy_file(case_file, output_folder)
        else:
            self.tool.print_('Warning: cannot find case file from %s' % os.path.basename(html_file))
        vec_numbers, aiq_files, no_vec_aiq_files = self.tool.gen_script_from_html(html_file, output_file, first_dcch_msg_after_switch_vector = opts.lte_dcch_msg)
        self.tool.print_('generate %s successfully! vec numbers %s.' % (output_file, vec_numbers))
        for aiq in no_vec_aiq_files:
            self.tool.print_('AIQ file(no vec): %s.' % aiq)
        self.latest_script_file = output_file
        if opts.vector:
            no_vec_usf_files = [os.path.splitext(f)[0] + '.usf' for f in no_vec_aiq_files]
            self._find_hde_vector(vec_numbers, no_vec_usf_files = no_vec_usf_files, dest_folder = output_folder)

    @options([make_option("-o", "--output_file", action = "store", type = "string", dest = "output_file", default = "", help = "output usf file"),
              make_option("-u", "--usf_path", action = "store", type = "string", dest = "usf_path", default = "", help = "usf path"),
             ], "[-o output_usf] [-u usf_path] usf_file1 usf_file2 ...")
    @min_args(2)
    def do_combine_usf(self, args, opts = None):
        if opts.usf_path:
            output_file = opts.output_file or 'combine.usf'
        else:
            if opts.output_file:
                output_file = opts.output_file
            elif hasattr(self, 'latest_script_file'):
                output_file = os.path.splitext(self.latest_script_file)[0] + '_combined.usf'
            else:
                raise CmdException('no output file specified.')
        output_file = self.tool.combine_usf(output_file, args, opts.usf_path)
        self.tool.print_('combine file to %s successfully' % os.path.abspath(output_file))

    @options([make_option("-p", "--project_path", action = "store", type = "string", dest = "project_path", default = "", help = "project path to find hde tools"),
              make_option("-u", "--usf_file_path", action = "store", type = "string", dest = "usf_file_path", default = "", help = "usf file path"),
              make_option("-0", "--no_usf_load", action = "store_true", dest = "no_usf_load", default = False, help = "do not load any usf"),
              make_option("-r", "--restart", action = "store_true", dest = "restart", default = False, help = "restart hde case"),
              make_option("-c", "--close", action = "store_true", dest = "close", default = False, help = "close hde window"),
             ], "[-p project_path] [-u usf_file_path] [-0] [-r] [-c] usf_file0(re) [usf_file1(re) ...]")
    def do_hde(self, args, opts = None):
        hde_tool_path = os.path.join(opts.project_path, 'tm_build_system', 'build', 'hde') if opts.project_path else ''
        usf_files = [self.tool.get_re_files(os.path.join(opts.usf_file_path, f))[0] for f in args]
        close_window = True if opts.restart else opts.close
        if close_window:
            WinCmd.check_file_exist(os.path.join(hde_tool_path, 'kill_hlc_dsp.bat'))
            WinCmd.cmd('kill_hlc_dsp.bat', hde_tool_path, showcmdwin = True)
            self._runcmd('close error')
            self.tool.print_('kill all hlc dsp window.')
        if not opts.no_usf_load and not close_window:
            self.tool.set_vumbra(usf_files, hde_tool_path)
            self.tool.print_('configure vumbra with %d usf files, %s' % (len(usf_files), str([os.path.basename(f) for f in usf_files])))
        if opts.close:
            self.tool.print_('close hde in project %s successfully' % opts.project_path)
        else:
            WinCmd.check_file_exist(os.path.join(hde_tool_path, 'start_hde.pyw'))
            WinCmd.cmd('start_hde.pyw', hde_tool_path)
            self.tool.print_('start hde in project %s successfully' % opts.project_path)

    @options([make_option("-p", "--prefix", action = "store", type = "string", dest = "prefix", default = "", help = "prefix to be deleted from the file"),
             ], "[-p prefix] folder")
    @min_args(1)
    def do_change_files_name(self, args, opts = None):
        folder = args[0]
        WinCmd.check_folder_exist(folder)
        prefix = opts.prefix if opts.prefix else (os.path.basename(folder) + '_')
        files_num = self.tool.change_files_name(folder, prefix)
        self.tool.print_('delete prefix %s for %d files successfully.' % (prefix, files_num))

    @options([make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "binary path, default: user binary path"),
              make_option("-r", "--reserve", action = "store", type = "string", dest = "reserve", default = "14", help = "reserve the latest n days of binary"),
             ], "[-p bin_path] [-r reserve_days] [bin_num]")
    def do_delete_binary(self, args, opts = None):
        reserve_days = int(opts.reserve)
        delete_num = 1 if len(args) == 0 else min(5, int(args[0]))
        num = self.tool.delete_earliest_subfolders(delete_num, reserve_days, opts.path)
        self.tool.print_('delete %d folders from %s.' % (num, opts.path or self.tool.binary_path))

    @options([make_option("-r", "--regen_cache", action = "store_true", dest = "regen_cache", default = False, help = "regenerate rav case cache file"),
             ], "[-r] case_num")
    @min_args(1)
    def do_open_case(self, args, opts = None):
        if opts.regen_cache:
            self.tool.gen_rav_case_cache()
        for case in self._split_option(args[0]):
            self.tool.explorer_case(case)

    @options([], "bin_path [boot_path]")
    @min_args(1)
    def do_load_bin(self, args, opts = None):
        boot_path = '' if len(args) < 2 else args[1]
        bin1_path = self.tool.get_abs_path(args[0], 'binary')
        self.tool.load_binary(bin1_path, boot_path)

    @options([make_option("-i", "--info", action = "store_true", dest = "info", default = False, help = "show station info"),
              make_option("-l", "--log", action = "store_true", dest = "log", default = False, help = "debug log enable"),
              make_option("-d", "--reload", action = "store_true", dest = "reload", default = False, help = "reload station info"),
              make_option("--ip", action = "store_true", dest = "only_show_ip", default = False, help = "show station ip only"),
              make_option("-b", "--book", action = "store", type = "string", dest = "book", default = "", help = "book machine, format: start time,end time,duration, e.g. 8,11.5, or 8,,3.5"),
             ], "[-i] [-l] [-d] [--ip] [-b time] {r20|f14(farm or rav machine)|ip_address} [machine2] [...]")
    def do_tsms(self, args, opts = None):
        machines = self._farm_rav_machines(args)
        self.tool.tsms_param(debug_log = opts.log, reload = opts.reload)
        if machines or len(args) == 0:   # no args means all stations
            if opts.info: self.tool.tsms_info(machines, only_show_ip = opts.only_show_ip)
        if 1<=len(machines)<=2 and opts.book:
            self.tool.tsms_book(machines, opts.book)

    def _farm_rav_machines(self, machines_or_ip):
        farm_rav_machines = []
        for m in machines_or_ip:
            if re.search(r'^(\d+\.){3}\d+$', m):  # ip address
                farm_rav_machines.append(m)
            else:
                r = re.search(r'^(r|rav)(\d+)$', m, flags = re.IGNORECASE)
                if r:
                    farm_rav_machines.append('RAV%02d' % int(r.group(2)))
                else:
                    r = re.search(r'^(f|farm|pfc)(\d+)$', m, flags = re.IGNORECASE)
                    if r:
                        farm_rav_machines.append('PFC%02d' % int(r.group(2)))
                    else:
                        self.tool.print_('invalid rav or farm machine %s' % m)
        return farm_rav_machines

    @options([make_option("-v", "--vnc", action = "store_true", dest = "vnc", default = False, help = "keep vnc alive"),
              make_option("-s", "--session", action = "store_true", dest = "session", default = False, help = "keep windows session alive"),
              make_option("-0", "--not_all", action = "store_true", dest = "not_all", default = False, help = "do not keep all by default"),
             ], "[-v] [-s] [-0]")
    def do_keep(self, args, opts = None):
        keep_vnc = opts.vnc or not opts.not_all
        keep_session = opts.session or not opts.not_all
        self.tool.keep(keep_vnc, keep_session)

    @options([make_option("-l", "--log", action = "store_true", dest = "log", default = False, help = "debug log enable"),
              make_option("-k", "--keep", action = "store_true", dest = "keep", default = False, help = "keep all vnc window alive"),
              make_option("-g", "--login", action = "store_true", dest = "login", default = False, help = "vnc login"),
              make_option("-d", "--reload", action = "store_true", dest = "reload", default = False, help = "reload station info"),
             ], "[-d] [-l] [-k] [-g] {r20|f14(farm or rav machine)|ip_address}")
    def do_vnc(self, args, opts = None):
        if opts.login:
            self.tool.vnc_login()
        elif opts.keep:
            self.tool.keep(keep_vnc = True)
        else:
            machines = self._farm_rav_machines(args)
            if not machines: raise CmdException('no machines found!')
            self.tool.tsms_param(debug_log = opts.log, reload = opts.reload)
            self.tool.vnc_connect(machines, debug_log = opts.log)
            self.tool.print_('vnc connected %d machines!' % len(machines))

    @options([make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "data folder to be processed"),
              make_option("-o", "--only", action = "store_true", dest = "only", default = False, help = "dsp log only"),
              make_option("-d", "--dsp", action = "store_true", dest = "dsp", default = False, help = "dsp files"),
              make_option("-f", "--force", action = "store_true", dest = "force", default = False, help = "force gen log, do not check file exist"),
              make_option("-z", "--latest", action = "store_true", dest = "latest", default = False, help = "latest file with all found files"),
              make_option("-0", "--no_sort", action = "store_true", dest = "no_sort", default = False, help = "do not sort the logs"),
             ], "[-0] [-p path] [-d] [-o] [-z] [-f] {files(regex)}")
    @min_args(1)
    def do_gen_log(self, args, opts = None):
        for tool_file in ['loganalyse.exe', 'loganalyse.dll']:
            WinCmd.check_file_exist(os.path.join(opts.path, tool_file))
        if not opts.force: WinCmd.check_file_exist(os.path.join(opts.path, 'tm500defs.dll'))
        files = self.tool.get_re_files(os.path.join(opts.path, args[0]))
        if not (opts.dsp and opts.only):
            self.tool.log_format(files, domain = 'hlc', no_sort = opts.no_sort, latest = opts.latest)
            self.tool.print_('change %d hlc files log format successfully!' % len(files))
        if opts.dsp:
            self.tool.log_format(files, domain = 'dsp', no_sort = opts.no_sort, latest = opts.latest)
            self.tool.print_('change %d dsp files log format successfully!' % len(files))
        self.tool.print_('if the output file is zero length, try with -0 no sort option.')

    @options([make_option("-f", "--farm", action = "store", type = "string", dest = "farm", default = "", help = "farm machine, ip: FARM14: 10.120.163.114"),
             ], "[-f farm] {ulan_ver(e.g. 2.6)}")
    @min_args(1)
    def do_change_ulan(self, args, opts = None):
        exe_path = ''
        if opts.farm:
            farm_addr = self.tool.get_farm_addr(opts.farm)
            self.tool.reload_farm_path(farm_addr)
            reload_back_farm_path = True
            exe_path = self.tool.exe_path
            if reload_back_farm_path: self.tool.reload_farm_path()
        self.tool.change_ulan(args[0], exe_path)

    @options([make_option("-v", "--environment", action = "store", type = "string", dest = "env", default = "", help = "environment: sue_tdd or mue_fdd, etc."),
              make_option("-e", "--empty_run", action = "store_true", dest = "empty", default = False, help = "empty RUN1 folder before run batch"),
              make_option("-f", "--fum", action = "store_true", dest = "fum", default = False, help = "run batch_fum.txt at first"),
              make_option("-b", "--batches", action = "store", dest = "batches", default = "", help = "batches copy (temporary for tdd script copy)"),
              make_option("-0", "--no_bin", action = "store_true", dest = "no_bin", default = False, help = "do not load any binary"),
              make_option("-1", "--bin1", action = "store", type = "string", dest = "bin1", default = "", help = "the first binary used"),
              make_option("-s", "--pfc_config", action = "store", type = "string", dest = "pfc_config", default = "", help = "config, for example: PFC10-CA"),
              make_option("-r", "--re_filter", action = "store", type = "string", dest = "re_filter", default = "", help = "filter batches by regular expression"),
              make_option("-n", "--start_batch_num", action = "store", type = "string", dest = "start_batch_num", default = "0", help = "start batch number, from 0"),
             ], "[-v env] [-e] [-f] [-b batches] [-s pfc_config] [-r filter] [-n start_num] [-1 bin1] [-0] bat_file")
    @min_args(1)
    def do_run_bat(self, args, opts = None):
        bin1_path = [] if opts.no_bin else self.tool.get_abs_path(opts.bin1, 'binary')
        if opts.env: self.tool.set_env(*tuple(opts.env.split('_')))
        if opts.empty: self.tool.empty_run_folder()
        self.tool.mark_timestamp()
        if opts.batches:
            WinCmd.copy_dir(opts.batches, self.tool.batch_path)
            self.tool.print_('change batches successfully from folder: %s.' % opts.batches)
        if bin1_path: self.tool.load_binary(bin1_path)
        files = self.tool.add_default_folder(args, default_folder = self.tool.test_batch_path)
        bat_file = self.tool.get_re_files(files)[0]
        WinCmd.copy_file(bat_file, self.tool.python_path)
        # change bat file
        if int(opts.start_batch_num) > 0 or opts.pfc_config or opts.re_filter:
            abs_bat_file = os.path.join(self.tool.python_path, os.path.basename(bat_file))
            self.tool._change_bat_file(abs_bat_file, int(opts.start_batch_num), opts.pfc_config, opts.re_filter)
        if opts.fum: self.tool.run_fum(opts.pfc_config)
        WinCmd.cmd(os.path.basename(bat_file), self.tool.python_path, showcmdwin = True, wait = False, retaincmdwin = True)
        self.tool.print_('start to run bat %s successfully!' % bat_file)

    @options([make_option("-v", "--environment", action = "store", type = "string", dest = "env", default = "", help = "environment: sue_tdd or mue_fdd, etc."),
              make_option("-e", "--empty_run", action = "store_true", dest = "empty", default = False, help = "empty RUN1 folder before run batch"),
              make_option("-a", "--auto_result", action = "store_true", dest = "auto_result", default = False, help = "auto show run result after finished"),
              make_option("-b", "--backup_boot", action = "store_true", dest = "backup_boot", default = False, help = "backup boot and recovery after run"),
              make_option("-r", "--change_run1", action = "store_true", dest = "change_run1", default = False, help = "change run1 folder to P volume"),
              make_option("-w", "--retain_win", action = "store_true", dest = "retain_win", default = False, help = "retain window after ttm_runner.py"),
              make_option("-m", "--min_win", action = "store_true", dest = "min_win", default = False, help = "minimum window when running"),
              make_option("-u", "--update_case", action = "store_true", dest = "update_case", default = False, help = "update cases if possible"),
              make_option("-f", "--fum", action = "store_true", dest = "fum", default = False, help = "run batch_fum.txt at first"),
              make_option("-t", "--times", action = "store", type = "string", dest = "times", default = "1", help = "run times for each batch"),
              make_option("-s", "--pfc_config", action = "store", type = "string", dest = "pfc_config", default = "", help = "config, for example: PFC10-CA"),
              make_option("-0", "--no_bin", action = "store_true", dest = "no_bin", default = False, help = "do not load any binary"),
              make_option("-1", "--bin1", action = "store", type = "string", dest = "bin1", default = "", help = "the first binary used"),
              make_option("-2", "--bin2", action = "store", type = "string", dest = "bin2", default = "", help = "the second binary used"),
              make_option("-3", "--bin3", action = "store", type = "string", dest = "bin3", default = "", help = "the third binary used"),
             ], "[-v env] [-e] [-f] [-a] [-r] [-w] [-u] [-t times] [-s config] [-1 bin1] [-2 bin2] [-3 bin3] [-0] batch_file1(or '*') [batch_file2 ...]")
    @min_args(1)
    def do_run_batch(self, args, opts = None):
        if len(args) == 1:
            p = self.tool.get_temp_path(args[0])
            if p: args[0] = os.path.join(p, '@^aTest.*.txt')  # '*': use newly gen cases
        files = [os.path.join(p, '@^aTest.*.txt') if self.tool.get_abs_path(p, only_test_valid = True) else p for p in args]
        batches = self.tool.get_re_files(files)
        if not batches: self.tool.print_('warning: no batches found!')
        bins = [[]] if opts.no_bin else [self.tool.get_abs_path(bin, 'binary') for idx, bin in enumerate([opts.bin1, opts.bin2, opts.bin3]) if idx == 0 or bin]
        if opts.env: self.tool.set_env(*tuple(opts.env.split('_')))
        if opts.change_run1:
            run1_folder = self.tool.get_remote_run1_path()
            self.tool.set_run1_folder(run1_folder, show_config_file = False)
        if opts.backup_boot: self.tool.backup_recover_boot(backup = True)
        marked_timestamp = False
        show_auto_result = False
        try:
            self.tool.update_cases(batches, opts.update_case)
            if opts.empty: self.tool.empty_run_folder()
            marked_timestamp = self.tool.mark_timestamp()
            run_fum_first = opts.fum
            for bin in bins:
                if bin: self.tool.load_binary(bin)
                if run_fum_first:
                    self.tool.run_fum(opts.pfc_config)
                    run_fum_first = False
                for i, batch in enumerate(batches):
                    self.tool.run_one_batch(batch, int(opts.times), opts.pfc_config, opts.retain_win, info = '(%d/%d) ' % (i+1, len(batches)), min_win = opts.min_win)
            show_auto_result = opts.auto_result
        finally:
            if marked_timestamp: self.tool.mark_timestamp(case_stop = True)
            if show_auto_result: self.tool.show_run_result()
            if opts.change_run1: self.tool.set_run1_folder()  # change back to default run1 folder
            if opts.backup_boot: self.tool.backup_recover_boot(backup = False)  # recover original boot folder

    @options([make_option("-f", "--fum", action = "store_true", dest = "fum", default = False, help = "run batch_fum.txt at first"),
              make_option("-t", "--times", action = "store", type = "string", dest = "times", default = "1", help = "run times for each batch"),
              make_option("-s", "--pfc_config", action = "store", type = "string", dest = "pfc_config", default = "default", help = "config, for example: CA, 8x8, etc."),
              make_option("-v", "--rav_type", action = "store", type = "string", dest = "rav_type", default = "", help = "the type of rav, 8x82CC, etc."),
              make_option("-m", "--mk", action = "store", type = "string", dest = "mk", default = "", help = "1/3/4 or MK1/MK3/MK4.x"),
              make_option("-0", "--no_bin", action = "store_true", dest = "no_bin", default = False, help = "do not load any binary"),
              make_option("-1", "--bin1", action = "store", type = "string", dest = "bin1", default = "", help = "the first binary used"),
             ], "[-f] [-t times] [-s config] [-v rav_type] [-m mk] [-1 bin1] [-0] batch_file1(or '*') [batch_file2 ...]")
    @min_args(1)
    def do_run_teamcity(self, args, opts = None):
        mk_all = {'MK1': ['1', 'MK1'], 'MK3': ['3', 'MK3'], 'MK4.x': ['4', 'MK4', 'MK4.X']}
        mk = ''
        for key, item in mk_all.items():
            if opts.mk.upper() in item:
                mk = key
                break
        if not mk: raise CmdException('invalid mk setting: %s, please use -m option' % opts.mk)
        if not hasattr(self, 'tc'): self.tc = TC()
        if len(args) == 1:
            p = self.tool.get_temp_path(args[0])
            if p: args[0] = os.path.join(p, '@^aTest.*.txt')  # '*': use newly gen cases
        files = [os.path.join(p, '@^aTest.*.txt') if self.tool.get_abs_path(p, only_test_valid = True) else p for p in args]
        batches = self.tool.get_re_files(files)
        vec_files = [os.path.join(os.path.dirname(f), '@.*.aiq$') for f in files]
        vectors = self.tool.get_re_files(vec_files)
        if not batches: self.tool.print_('warning: no batches found!')
        bin = '' if opts.no_bin else self.tool.get_abs_path(opts.bin1, 'binary')
        self.tc.empty_dest_folder(empty_bin_folder = True if bin else False)
        if bin: self.tc.copy_binary(bin)
        self.tc.copy_batches(batches, opts.pfc_config, rav_type = opts.rav_type, umbra_update = opts.fum, run_times = int(opts.times))
        if vectors: self.tc.gen_vec_list_file(vectors)
        self.tool.print_('all files for teamcity have been prepared.')
        self.tc.gen_all_upload_files(mk)
        self.tc.run_tc()

    @options([make_option("-b", "--select_batches_key", action = "store", type = "string", dest = "select_batches_key", default = "", help = "sanity batches: 15k|120k|basic|2cell|3cell"),
              make_option("-1", "--cell_1_batch_one_run", action = "store_true", dest = "cell_1_batch_one_run", default = False, help = "cell 1 batches, run in one go"),
              make_option("-r", "--rav", action = "store", type = "string", dest = "rav", default = "", help = "rav selected, RAV99-2, RAV100-1, etc."),
              make_option("-d", "--debug", action = "store_true", dest = "debug", default = False, help = "debug output"),
             ], "[-b batches] [-1] [-d] [-r RAV] project_path  (default: 3 runs (2cell, basic, 15k+120k))",
             example = '''
                1) rr D:\Projects\swang2_view_cue_tot_feature_2
                    submit 3 remote runs, 1--basic 1cell batch, 2--15k+120k 1cell batch, 3--2cell batch
                2) rr D:\Projects\swang2_view_cue_tot_feature_2 -b 2cell
                    submit 2cell batch sanity run ''')
    @min_args(1)
    def do_remote_run_sanity(self, args, opts = None):
        project_path = args[0]
        WinCmd.check_folder_exist(project_path)
        self._set_default_project_path(project_path)
        self.tool.teamcity_remote_run(project_path, self._split_option(opts.select_batches_key), opts.cell_1_batch_one_run, opts.rav, opts.debug)

    @options([make_option("-c", "--config_pattern", action = "store", type = "string", dest = "config_pattern", default = "", help = "re config pattern to filter config files"),
             ], "[-c pattern]")
    def do_rav(self, args, opts = None):
        if opts.config_pattern:
            files = [f for f in os.listdir(self.tool.config_path) if re.search(opts.config_pattern, f, flags = re.IGNORECASE)]
            results = []
            for f in files:
                r = re.search('^(.*)_station_config.txt', f)
                if r: results.append(r.group(1))
            if results:
                self.tool.print_('Find configs: %s' % results)
            else:
                self.tool.print_('No configs found for %s!' % opts.config_pattern)

    @options([make_option("-n", "--last_number", action = "store", type = "string", dest = "last_number", default = "1", help = "result from run last number"),
              make_option("-a", "--all", action = "store_true", dest = "all", default = False, help = "all run result"),
              make_option("-v", "--view", action = "store_true", dest = "view", default = False, help = "view result file"),
              make_option("-b", "--last_batch", action = "store_true", dest = "last_batch", default = False, help = "show last batch html"),
              make_option("-c", "--last_case", action = "store_true", dest = "last_case", default = False, help = "show last case html"),
              make_option("-r", "--remote_run1", action = "store_true", dest = "remote_run1", default = False, help = "remote run1 folder in P volume"),
              make_option("-s", "--src_folder", action = "store", type = "string", dest = "src_folder", default = "", help = "source folder"),
             ], "[-n 1] [-a] [-r] [-v] [-b] [-c] [-s folder]")
    def do_result(self, args, opts = None):
        last_number = int(opts.last_number)
        assert last_number > 0, 'invalid param last_number %d' % last_number
        if not opts.last_batch and not opts.last_case:
            self.tool.show_run_result(last_number, opts.all, opts.remote_run1, opts.src_folder, opts.view)
        else:
            self.tool.show_last_html(opts.last_batch, opts.last_case, opts.remote_run1, opts.src_folder)

    @options([make_option("-o", "--output_path", action = "store", type = "string", dest = "output_path", default = r"C:\wang\00.Work\04.result", help = "file output path"),
             ], "[-o output_path] remote_run_number")
    def do_remote_result(self, args, opts = None):
        output_path = opts.output_path
        WinCmd.check_folder_exist(output_path)
        self.tool.get_files_from_teamcity(args[0], output_path)

    @options([make_option("-r", "--readonly", action = "store_true", dest = "readonly", default = False, help = "read the current RUN1"),
             ], "[-r] [run1_folder]")
    def do_set_run1(self, args, opts = None):
        if opts.readonly:
            self.tool.print_('current run1 folder: %s' % self.tool.get_run1_folder())
        else:
            run1_folder = args[0] if len(args) else ''
            if run1_folder: WinCmd.check_folder_exist(run1_folder)
            self.tool.set_run1_folder(run1_folder)

    @options([make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "format: [ue]_[product]_[rat]: sue_4x2_fdd, sue_4x2_ulmimo_tdd, mue_2x2_fdd, etc."),
              make_option("-r", "--folder", action = "store", type = "string", dest = "folder", default = "", help = "run result folder, default RUN1"),
              make_option("-f", "--farm", action = "store", type = "string", dest = "farm", default = "", help = "run result folder, format: [farm],[folder]: 14,RUN1"),
              make_option("-g", "--regen_search_folder", action = "store_true", dest = "regen_search_folder", default = False, help = "regenerate rav search folder"),
              make_option("-0", "--from_file", action = "store_true", dest = "from_file", default = False, help = "generate more results directly from result file"),
             ], "[-g] [-p product] [-f farm,folder] [-r folder] [-0] {output_filename|output_path|input_filename}")
    @min_args(1)
    def do_ana_rslt(self, args, opts = None):
        if os.path.isdir(args[0]):
            output_file = os.path.join(args[0], 'result_1.txt')
        else:
            output_file = args[0]
            WinCmd.check_folder_exist(os.path.dirname(output_file))
            if os.path.splitext(output_file)[-1] != '.txt': raise CmdException('invalid file (*.txt): %s' % output_file)
        if opts.from_file:
            WinCmd.check_file_exist(output_file)
            self.tool.print_('generate more results from file: %s' % output_file)
            self.tool.gen_more_result(output_file, opts.folder, opts.product, opts.regen_search_folder)
        else:
            folder = (self.tool.get_farm_run_folder(opts.farm) if opts.farm else opts.folder) or self.tool.run_result_path
            self.tool.print_('generate result from folder: %s' % folder)
            self.tool.save_folder_sesult(output_file, folder, opts.product, opts.regen_search_folder)
        self.tool.print_('generate result in %s successfully!' % os.path.dirname(output_file))

    @options([], "result_file ref_file1 [ref_file2 ...]")
    @min_args(2)
    def do_cmp_rslt(self, args, opts = None):
        fail_file = args[0]
        for ref_file in args[1:]:
            fail_file = self.tool.compare_result(fail_file, ref_file)
            self.tool.print_('generate %s successfully!' % fail_file)

    @options([make_option("-c", "--cases", action = "store", type = "string", dest = "cases", default = "", help = "test cases, 30000|80000|..."),
              make_option("-p", "--batch_dir", action = "store", type = "string", dest = "batch_dir", default = "", help = "batch directory"),
              make_option("-b", "--batches", action = "store", type = "string", dest = "batches", default = "", help = "batches, regex"),
              make_option("-e", "--empty_batch", action = "store_true", dest = "empty", default = False, help = "empty batches before generate file"),
              make_option("-t", "--tma", action = "store_true", dest = "tma", default = False, help = "used for TMA run on target"),
              make_option("-a", "--assert", action = "store_true", dest = "manual_assert", default = False, help = "add manual assert in the case"),
              make_option("-x", "--except_batch", action = "store", type = "string", dest = "except_batch", default = "", help = "except batch file"),
              make_option("-s", "--select_batch", action = "store", type = "string", dest = "select_batch", default = "", help = "select batch file"),
              make_option("-0", "--not_change_batch", action = "store_true", dest = "not_change_batch", default = False, help = "do not change batch, all cases remained"),
             ], "[-e] [-t] [-a] [-0] [-c cases] [-b batches] [-p batch_dir] [-x except_batch1|except_batch2] [-s batch1|batch2] err_file (or dest_path or '*'{{default}})")
    @min_args(1)
    def do_gen_batch(self, args, opts = None):
        if opts.cases and opts.batches: raise CmdException('cannot specify -c cases and -b bacthes simultaneously!')
        dest_path = args[0] if opts.cases or opts.batches else os.path.dirname(args[0])
        temp_path = self.tool.get_temp_path(dest_path)
        if temp_path:
            dest_path = temp_path
            opts.empty = True    # empty old cases
            if not os.path.isdir(dest_path): WinCmd.make_dir(dest_path)
            self.tool.print_('output path: %s' % dest_path)
        if opts.empty:
            WinCmd.del_pattern_files(os.path.join(dest_path, 'aTest_err*'))
        except_batches = self._split_option(opts.except_batch)
        select_batches = self._split_option(opts.select_batch)
        cases_info = {}
        if opts.cases:
            if opts.cases[0] in self.tool.re_delimiters:
                cases = self.tool.get_re_cases(opts.cases)
            else:
                cases = self._split_option(opts.cases)
            batch_files, remain_cases, cases_info = self.tool.gen_batch_from_cases(cases, dest_path, opts.batch_dir, except_batches, select_batches, opts.not_change_batch)
            if remain_cases: self.tool.print_('such cases not found: %s' % remain_cases)
            if opts.tma and opts.manual_assert: raise CmdException('cannot enable both TMA and Assert!')
            if opts.tma or opts.manual_assert:
                case_files = self.tool.copy_case_from_automation(cases, dest_path)
                gen_files = [self.tool.modify_case(case_file, 'tma' if opts.tma else 'assert') for case_file in case_files]
                self.tool.copy_case_to_automation(dest_path, r'%s^00_.*\.txt$' % self.tool.re_delimiters[0])
                if opts.tma:
                    self.tool.modify_batch(batch_files.keys(), 'tma', True, modify_case = True)
                else:
                    self.tool.modify_batch(batch_files.keys(), modify_case = True)
        elif opts.batches:
            batch_dir = opts.batch_dir or self.tool.batch_path
            batches = self.tool.get_re_files(os.path.join(batch_dir, opts.batches))
            WinCmd.copy_files(batches, dest_path)
            src_batches = [os.path.join(dest_path, os.path.basename(f)) for f in batches]
            dest_batches = [os.path.join(dest_path, 'aTest_err_'+os.path.basename(f)) for f in batches]
            WinCmd.rename_files(src_batches, dest_batches)
            self.tool.modify_batch(dest_batches, 'remove_case')
            batch_files = dict(zip(dest_batches, [[]]*len(dest_batches)))
        else:
            batch_files = self.tool.generate_batch(args[0], opts.batch_dir)
        for batch_file, batch_cases in batch_files.items():
            self.tool.print_('generate %s (%d cases, %s) successfully!' % (os.path.basename(batch_file), len(batch_cases), str(batch_cases)))
        print_first_line = False
        for case, batches in cases_info.items():
            if len(batches) > 1:
                if not print_first_line:
                    self.tool.print_('%s Warning %s' % ('='*20, '='*20))
                    print_first_line = True
                self.tool.print_('Case %s in several batches, %s' % (case, str(batches)))
        #bat_file = self.tool.gen_run_bat(batch_files)
        #self.tool.print_('generate %s successfully!' % os.path.basename(bat_file))

    @options([make_option("-c", "--use_cache", action = "store_true", dest = "use_cache", default = False, help = "use cache if possible"),
              make_option("-u", "--upper_lower", action = "store_true", dest = "upper_lower", default = False, help = "do not ignore upper lower cases"),
              make_option("-a", "--all_cases", action = "store_true", dest = "all_cases", default = False, help = "all cases, no default filter, at least 1 pass"),
              make_option("-r", "--regex_filter", action = "store", type = "string", dest = "regex_filter", default = "", help = "regex filter"),
             ], "[-c] [-a] [-u] [-r regex_filter] product {{format: [ue]_[pro]_[rat]: sue_4x2_tdd, mue_5c_fdd, cue_ls2_fdd, etc.}}")
    @min_args(1)
    def do_filter_cases(self, args, opts = None):
        product = args[0]
        flags = re.IGNORECASE if opts.upper_lower else 0
        cases_info = self.tool.get_rav_cases_info(product, opts.regex_filter, flags, opts.all_cases)
        temp_file = self.tool.get_temp_filename()
        with open(temp_file, 'w') as f_write:
            for info in cases_info:
                f_write.write(info + '\n')
        WinCmd.explorer(temp_file)
        self.tool.print_('get %d cases for %s successfully!' % (len(cases_info), product))

    @options([make_option("-b", "--batch_dir", action = "store", type = "string", dest = "batch_dir", default = "", help = "batch directory"),
              make_option("-r", "--results_folder", action = "store", type = "string", dest = "results_folder", default = "", help = "results folder from rav"),
              make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "format: [ue]_[pro]_[rat]: sue_4x2_tdd, mue_5c_fdd, cue_ls2_fdd, etc."),
              make_option("-x", "--except_batch", action = "store", type = "string", dest = "except_batch", default = "", help = "except batch file"),
             ], "[-r results_folder] [-p product] [-b batch_dir] [-x except_batch1|except_batch2] bat_file")
    @min_args(1)
    def do_gen_rav_cases_batch(self, args, opts = None):
        WinCmd.check_folder_exist(opts.batch_dir, can_be_empty = True)
        bat_file = os.path.join(self.tool.get_abs_path(os.path.dirname(args[0])), os.path.basename(args[0]))
        if opts.results_folder:
            self.tool.gen_rav_batch_bat_from_results_folder(bat_file, opts.results_folder)
        else:
            except_batches = self._split_option(opts.except_batch)
            self.tool.gen_rav_batch_bat(bat_file, opts.product, opts.batch_dir, except_batches)
        self.tool.print_('generate %s successfully!' % bat_file)

    @options([make_option("-r", "--rat_tdd", action = "store", type = "string", dest = "rat_tdd", default = "none", help = "[none]|on|off, add or delete tdd script"),
              make_option("-t", "--tma", action = "store", type = "string", dest = "tma", default = "none", help = "[none]|on|off, add or delete tma script"),
              make_option("-p", "--path", action = "store", type = "string", dest = "path", default = "", help = "batch path, for file mode"),
             ], "[-r tdd] [-p path] [-t tma] batch_file1 [batch_file2, ...]")
    @min_args(1)
    def do_modify_batch(self, args, opts = None):
        content = 'none'
        for opt in [opts.rat_tdd, opts.tma]:
            if opt in ['on', 'off']:
                if content != 'none': raise CmdException('only can change 1 thing at a time.')
                content = 'tdd'
                param = True if opt == 'on' else False
        batch_path = opts.path
        if batch_path:
            batches = [os.path.join(batch_path, b) for b in self.tool.select_batches(args[0])]
        else:
            batches = self.tool.get_re_files(args)
        changed_batches = self.tool.modify_batch(batches, content, param)
        self.tool.print_('changed %d batches successfully!' % len(changed_batches))

    @options([], "[tx|rx]")
    def do_update_tx_rx(self, args, opts = None):
        def _backup_files(files, folder):
            WinCmd.del_dir(folder)
            for file in files: WinCmd.copy_file(file, folder)
        py_files = self.tool.get_re_files([os.path.join(self.tool.file_path, r'%s.*py$' % self.tool.re_delimiters[0])])
        if len(args) > 0 and args[0] == 'tx':
            comm = ClipComm('client')
            filename = comm.enc_file(py_files, magic = '100')
            self.tool.print_('start send %s...' % filename)
            comm.send_file(filename)
        elif len(args) == 0 or args[0] == 'rx':
            comm = ClipComm('server')
            self.tool.print_('start receiving...')
            file = comm.receive_file()
            _backup_files(py_files, os.path.join(self.tool.file_path, 'backup'))
            comm.dec_file(file, os.path.join(self.tool.file_path))
            self.tool.print_('update receive file successfully!')

    @options([make_option("-m", "--magic_number", action = "store", type = "string", dest = "magic", default = "000", help = "magic number, to support resume transfer"),
              make_option("-c", "--cont_mode", action = "store_true", dest = "cont_mode", default = False, help = "continuous mode, allow for resume transfer"),
              make_option("-i", "--info", action = "store_true", dest = "info", default = False, help = "info transfer mode, only transmit needed files"),
              make_option("-b", "--max_tx_bytes", action = "store", type = "string", dest = "max_tx_bytes", default = "50000", help = "max tx bytes in one transfer"),
             ], "[-c] [-i] [-m magic] [-b max_tx_bytes] src_dir1 [src_dir2 ...]")
    @min_args(1)
    def do_send(self, args, opts = None):
        comm = ClipComm('client', int(opts.max_tx_bytes))
        if opts.info:
            WinCmd.check_folder_exist(args[0])
            filename = comm.send_file_info(args[0])
        else:
            filename = comm.enc_file(self.tool.get_re_files(args, exclude_dir = False), opts.magic, opts.cont_mode)
        if filename:
            self.tool.print_('start send %s...' % filename)
            comm.send_file(filename)
        else:
            self.tool.print_('do not need send any file.')

    @options([make_option("-c", "--cont_mode", action = "store_true", dest = "cont_mode", default = False, help = "continuous mode, allow for resume transfer"),
              make_option("-r", "--ref_folder", action = "store", type = "string", dest = "ref_folder", default = "", help = "info transfer mode, reference folder"),
             ], "[-c] [-r ref_folder] [dest_folder]")
    def do_receive(self, args, opts = None):
        ref_folder, dest_folder = opts.ref_folder, args[0] if len(args) > 0 else ''
        comm = ClipComm('server')
        self.tool.print_('start receiving...')
        if ref_folder:
            if not dest_folder:
                ref_folder, dest_folder = ref_folder + '_1', ref_folder
                if os.path.isdir(dest_folder): WinCmd.rename_dir(dest_folder, ref_folder)
            remain_files = comm.receive_file_info(ref_folder, dest_folder)
            if not remain_files:
                self.tool.print_('do not need receive any file.')
                return
            file = comm.receive_file()
        else:
            file = comm.receive_file(opts.cont_mode)
        comm.dec_file(file, dest_folder)
        self.tool.print_('received file %s successfully!' % file)

    @options([make_option("-k", "--kill", action = "store_true", dest = "kill", default = False, help = "kill log process"),
              make_option("-p", "--project_path", action = "store", type = "string", dest = "project_path", default = "", help = "project path"),
              make_option("-o", "--output_path", action = "store", type = "string", dest = "output_path", default = "", help = "output log path"),
              make_option("-d", "--dsp", action = "store", type = "string", dest = "dsp", default = "", help = "logged dsp core, example: server or 13|16 or 1.0|2.1 "),
             ], "[-k] [-p project_path] [-o output_path] [-d dsp]")
    def do_hde_log(self, args, opts = None):
        if opts.kill:
            self.tool.kill_hde_log()
        else:
            if not opts.project_path or not opts.output_path or not opts.dsp: raise CmdException('should set para')
            log = self.tool.start_hde_log(opts.project_path, opts.output_path, self._split_option(opts.dsp))
            self.tool.print_('start %s successfully!' % log)

    @options([make_option("-r", "--remove_time", action = "store_true", dest = "remove_time", default = True, help = "remove time"),
              make_option("-p", "--pattern", action = "store", type = "string", dest = "pattern", default = "", help = "search pattern "),
              make_option("-s", "--start_numbers", action = "store", type = "string", dest = "start_numbers", default = "", help = "start_numbers, number1|number2"),
              make_option("-e", "--end_number_offset", action = "store", type = "string", dest = "end_number_offset", default = "20", help = "end_number_offset"),
             ], "[-r] [-p pattern] [-s start_numbers] [-e end_number_offset] log_file1 [log_file2]")
    @min_args(1)
    def do_retrieve_log(self, args, opts = None):
        log_files = self.tool.get_re_files(args)
        start_numbers = self._split_option(opts.start_numbers)
        if len(log_files) != len(start_numbers): raise CmdException('len(start_numbers ) != len(files), start_numbers %s, files %s.' % (start_numbers, log_files))
        for log_file, start_number in zip(log_files, start_numbers):
            dest_file = os.path.join(os.path.dirname(log_file), '00_' + os.path.basename(log_file))
            self.tool.retrieve_log_pattern(log_file, dest_file, opts.pattern, int(start_number), int(opts.end_number_offset), opts.remove_time)
            self.tool.print_('generate file %s successfully!' % dest_file)

    @options([make_option("-p", "--project_path", action = "store", type = "string", dest = "project_path", default = "", help = "project path"),
              make_option("-c", "--cc_tool", action = "store", type = "string", dest = "cc_tool", default = "", help = "manual set cleartool.exe"),
             ], "[-p project_path] [-c cc_tool] cmd{'checkout', 'checkin', 'undo_checkout'} list_file")
    @min_args(2)
    def do_clearcase(self, args, opts = None):
        cmd, file_list = args[0], os.path.join(args[1], 'file_change_list.txt') if os.path.isdir(args[1]) else args[1]
        WinCmd.check_file_exist(file_list)
        if opts.cc_tool and os.path.isfile(opts.cc_tool): CcTool.set_cctool(opts.cc_tool)
        if cmd in ['checkout', 'checkin', 'undo_checkout']:
            self.tool.check_change_files(cmd, file_list, opts.project_path)
        else:
            raise CmdException('cmd "%s" not valid!' % cmd)
        self.tool.print_('%s files finished.' % cmd)

    @options([make_option("-v", "--dynamic_view", action = "store", type = "string", dest = "dynamic_view", default = "Z:", help = "dynamic view path, default: Z:/"),
              make_option("-0", "--manual", action = "store_true", dest = "manual", default = False, help = "do not change, manual select files and builds"),
              make_option("-d", "--debug", action = "store_true", dest = "debug", default = False, help = "debug output"),
             ], "[-0] [-v dynamic_view_path] [-d] project_path",
             example = '''
                1) presub D:\Projects\swang2_view_cue_tot_feature_2
                    run presub for the folder, use default Z: as dynamic view path
                2) presub D:\Projects\swang2_view_cue_tot_feature_2 -v X:
                    run presub for the folder, use X: as dynamic view path ''')
    @min_args(1)
    def do_presub(self, args, opts = None):
        self.tool.presub(args[0], opts.dynamic_view, opts.manual, opts.debug)
        self.tool.print_('presub run ok!')

    @options([make_option("-u", "--username", action = "store", type = "string", dest = "username", default = "swang2", help = "username"),
              make_option("-d", "--days_ago", action = "store", type = "string", dest = "days_ago", default = "200", help = "days ago to obsolete"),
              make_option("-r", "--regen", action = "store_true", dest = "regen", default = False, help = "regenerate branches cache"),
              make_option("-i", "--info", action = "store_true", dest = "info", default = False, help = "show branch info"),
             ], "[-u swang2] [-d 200] [-r] [-i] [branch_name]")
    def do_obsolete(self, args, opts = None):
        if len(args) > 0:
            branch = args[0]
            if opts.info:
                result, t, u, o = self.tool.check_branch(branch)
                self.tool.print_('branch [%s]: username %s, time %s, %s' % (branch, u, t.strftime('%Y%m%d'), 'Active' if not o else 'Obsoleted'))
            else:
                result, _, _, _ = self.tool.check_branch(branch, opts.username)
                if result: self.tool.obsolete_branch(branch)
        else:  # all branches
            cache_file = os.path.join(self.tool.rav_cache_path, 'cc_all_branches_cache.txt')
            if opts.regen:
                self.tool.print_('start to find all branches...')
                CcTool.find_all_branches(cache_file)
                self.tool.print_('generate branches cache file successfully! %s' % cache_file)
            branches = self.tool.extract_branches(cache_file, opts.username)
            self.tool.obsolete_branches(branches, opts.username, days_ago = int(opts.days_ago))

    @options([make_option("-s", "--spec", action = "store_true", dest = "spec", default = False, help = "open spec"),
              make_option("-l", "--log", action = "store_true", dest = "log", default = False, help = "open logcombuilder"),
              make_option("-v", "--view", action = "store_true", dest = "view", default = False, help = "open version folder"),
              make_option("-t", "--tma", action = "store_true", dest = "tma", default = False, help = "copy TMA folder"),
              make_option("-0", "--force_temp_binary", action = "store_true", dest = "force_temp_binary", default = False, help = "force to be a temporary binary"),
              make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "product, SUE/MUE/CUE"),
              make_option("-o", "--to", action = "store", type = "string", dest = "to", default = "", help = "copy to default User binary folder, or boot folder"),
              make_option("-b", "--binary", action = "store_true", dest = "binary", default = False, help = "copy binary folder"),
             ], "[-v] [-b] [-t] [-s] [-l] [-p product] [-o folder(boot)] {version(eg: K4.6.4REV50 or K_04_06_04_REV50)}")
    @min_args(1)
    def do_ver(self, args, opts = None):
        label, path = self.tool.get_ver_label(args[0], opts.product, opts.force_temp_binary)
        if opts.spec:
            spec_file = os.path.join(path, 'build_config_spec.txt')
            WinCmd.check_file_exist(spec_file)
            WinCmd.explorer(spec_file)
        if opts.log: WinCmd.explorer(os.path.join(path, 'loganalyse'))
          #  log_file = os.path.join(path, 'loganalyse', 'logcombuilder.pyw')
         #   WinCmd.check_file_exist(log_file)
         #   tool_path, tool_name = os.path.split(log_file)
         #   WinCmd.cmd(r'python "%s"' % tool_name, tool_path, showcmdwin = True, wait = False)
        if opts.view: WinCmd.explorer(path)
        self.tool.print_('find label %s from %s successfully!' % (label, path))
        if opts.binary or opts.tma:
            copy_pyd_files_to_asn_folder = False
            if not opts.to:
                dest_dir = os.path.join(self.tool.binary_path, label)
                if os.path.isdir(dest_dir): WinCmd.rename_dir(dest_dir, dest_dir + '_1')
            elif opts.to.lower() == 'boot':
                dest_dir = self.tool.boot_path
                copy_pyd_files_to_asn_folder = True
            else:
                dest_dir = self.tool.get_abs_path(opts.to, 'binary')
                WinCmd.check_folder_exist(dest_dir)
            if opts.binary:
                version_binary_path = os.path.join(path, 'ppc_pq', 'public', 'ftp_root')
                WinCmd.copy_dir(version_binary_path, dest_dir)
                pyd_dest_dir = os.path.join(dest_dir, self.tool.rel_pyd_dir)
                WinCmd.make_dir(pyd_dest_dir)
                for pyd_file in self.tool.pyd_file:
                    try:
                        WinCmd.copy_file(os.path.join(path, 'tools', pyd_file), pyd_dest_dir)
                        if copy_pyd_files_to_asn_folder: WinCmd.copy_file(os.path.join(path, 'tools', pyd_file), self.tool.asn_path)
                    except:
                        self.tool.print_('no file found: %s' % pyd_file)
                WinCmd.make_dir(os.path.join(dest_dir, 'tools'))
                for tool_file in ['socket_log.exe', 'socket_log64.exe']:
                    try:
                        WinCmd.copy_file(os.path.join(path, 'tools', tool_file), os.path.join(dest_dir, 'tools'))
                    except:
                        self.tool.print_('no file found: %s' % tool_file)
                if os.path.isdir(os.path.join(path, 'loganalyse')):
                    WinCmd.copy_dir(os.path.join(path, 'loganalyse'), dest_dir, empty_dest_first = False, include_src_dir = True)
                else:
                    self.tool.print_('no dir found: %s' % os.path.join(path, 'loganalyse'))
            if opts.tma:
                tma_path = os.path.join(path, 'TMA')
                if not os.path.isdir(tma_path):
                    self.tool.print_('no TMA folder found: %s' % tma_path)
                else:
                    WinCmd.copy_dir(tma_path, dest_dir, empty_dest_first = False, include_src_dir = True)
            self.tool.print_('copy to folder: %s successfully!' % dest_dir)

    @options([make_option("-o", "--trace_file_path", action = "store", type = "string", dest = "trace_file_path", default = "", help = "trace file path"),
              make_option("-0", "--force_temp_binary", action = "store_true", dest = "force_temp_binary", default = False, help = "force to be a temporary binary"),
              make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "product, SUE/MUE/CUE"),
             ], "[-o trace_file_path] [-0] [-p product] {version(eg: K4.6.4REV50)}")
    @min_args(1)
    def do_trace(self, args, opts = None):
        if opts.trace_file_path: WinCmd.check_folder_exist(opts.trace_file_path)
        label, path = self.tool.get_ver_label(args[0], opts.product, opts.force_temp_binary)
        traceviewer_path = os.path.join(path, 'traceviewer')
        WinCmd.check_folder_exist(traceviewer_path)
        if opts.trace_file_path:
            WinCmd.copy_dir(traceviewer_path, opts.trace_file_path, empty_dest_first = False, include_src_dir = True)
            WinCmd.copy_file(os.path.join(traceviewer_path, 'msg_nums.dat'), opts.trace_file_path)
        run_traceviewer_path = os.path.join(opts.trace_file_path, 'traceviewer') if opts.trace_file_path else traceviewer_path
        WinCmd.process(r'traceviewer.exe', run_traceviewer_path, shell = True)
        self.tool.print_('open trace for label %s successfully!' % label)

    @options([make_option("-p", "--trace_file_path", action = "store", type = "string", dest = "trace_file_path", default = "", help = "trace file path"),
              make_option("-t", "--traceviewer", action = "store_true", dest = "traceviewer", default = False, help = "copy and open traceviewer if possible"),
              make_option("-0", "--no_copy", action = "store_true", dest = "no_copy", default = False, help = "do not copy trace file"),
              make_option("-e", "--empty_dest", action = "store_true", dest = "empty_dest", default = False, help = "empty dest folder first"),
             ], "[-p trace_file_path] [-t] [-0] html")
    @min_args(1)
    def do_trc_file(self, args, opts = None):
        if opts.trace_file_path: WinCmd.check_folder_exist(opts.trace_file_path)
        html_file = self._get_html_filename(args[0])
        html_path, filename = os.path.split(html_file)
        trc_file = self.tool.get_trc_file_from_html(html_file)
        if trc_file:
            dest_folder = opts.trace_file_path or self.tool.temp_trace_path
            if not os.path.isdir(dest_folder): WinCmd.make_dir(dest_folder)
            if opts.empty_dest: WinCmd.del_dir(dest_folder)
            if not opts.no_copy:
                WinCmd.copy_file(trc_file, dest_folder)
                self.tool.print_('copy %s to %s.' % (os.path.basename(trc_file), dest_folder))
            if opts.traceviewer:
                traceviewer_path = self.tool.find_traceviewer_path(html_file)
                if traceviewer_path:
                    WinCmd.copy_dir(traceviewer_path, dest_folder, empty_dest_first = False, include_src_dir = True)
                    WinCmd.copy_file(os.path.join(traceviewer_path, 'msg_nums.dat'), dest_folder)
                    WinCmd.process(r'traceviewer.exe', os.path.join(dest_folder, 'traceviewer'), shell = True)
                else:
                    self.tool.print_('Warning: cannot find traceviewer from folder, %s' % os.path.dirname(html_file))
        else:
            self.tool.print_('Warning: cannot find trc file from html file, %s' % html_file)

    @options([make_option("-l", "--log", action = "store_true", dest = "log", default = False, help = "open log builder"),
              make_option("-t", "--trace", action = "store_true", dest = "trace", default = False, help = "open trace"),
              make_option("-r", "--remote_run", action = "store_true", dest = "remote_run", default = False, help = "open remote run"),
             ], "[-l] [-t] [-r] project_path")
    def do_tool(self, args, opts = None):
        project_path = args[0] if len(args) > 0 else self._get_project_path()
        if opts.log:
            tool_path, tool_name = os.path.split(self.tool.get_logcombuilder(project_path))
            WinCmd.cmd(r'python "%s"' % tool_name, tool_path, showcmdwin = True, wait = False)
        if opts.trace:
            tool_path, tool_name = os.path.split(self.tool.get_traceviewer(project_path))
            WinCmd.process(tool_name, tool_path, shell = True)
        if opts.remote_run:
            tool_path, tool_name = os.path.split(self.tool.get_remote_run(project_path))
            WinCmd.cmd(r'python "%s"' % tool_name, tool_path, showcmdwin = True, wait = False)
        if opts.log or opts.trace:
            self.tool.print_('open tool in path %s successfully!' % tool_path)

    @options([make_option("-o", "--output_path", action = "store", type = "string", dest = "output_path", default = "", help = "file output path"),
             ], "[-o output_path] ubi_number")
    def do_ubi_file(self, args, opts = None):
        output_path = opts.output_path or self.tool.ubi_path
        WinCmd.check_folder_exist(output_path)
        self.tool.get_files_from_clearquest(args[0], output_path)

    @options([], "")
    def do_reboot(self, args, opts = None):
        input = raw_input(r'you want to REBOOT the machine!!! yes/(no):')
        if input == 'yes':
            WinCmd.cmd(r'shutdown -r -f -t 0')
            self.tool.print_('start REBOOT...')
        else:
            self.tool.print_('reboot cancelled.')

    @options([make_option("-t", "--time", action = "store", type = "string", dest = "time", default = "", help = "time [0, 1]"),
             ], "[1] {insight}")
    def do_open_soft(self, args, opts = None):
        times = 1 if len(args) == 0 else int(args[0])
        soft = 'insight' if len(args) < 2 else args[1]
        soft_path = {'insight': (r'C:\Program Files (x86)\Source Insight 3\Insight3.exe', '01-03-2014')}
        file_location, install_date = soft_path[soft]
        if opts.time:
            install_time_candidates = ['01-03-2014', '18-01-2018'];
            install_date = install_time_candidates[int(opts.time)]
        file_locations = [file_location, file_location.replace(r'C:\Program Files (x86)', r'C:\Program Files')]
        file_locations = [f for f in file_locations if os.path.isfile(f)]
        if not file_locations: raise CmdException('No software %s found!' % soft)
        file_location = file_locations[0]
        cur_date = datetime.now().strftime('%d-%m-%y')
        WinCmd.cmd('date, %s' % install_date)
        for i in range(times):
            WinCmd.process(file_location)
            time.sleep(1)
        input = raw_input(r'press any key when the software opened successfully...')
        WinCmd.cmd('date, %s' % cur_date)
        self.tool.print_('open software %d times successfully.' % times)

    @options([make_option("-f", "--force", action = "store_true", dest = "force", default = False, help = "force rename, delete dest folder if exist"),
              make_option("-p", "--from_path", action = "store", type = "string", dest = "from_path", default = "run1", help = "rename source dir, default relpath: run1's parent folder"),
              make_option("-n", "--full_name", action = "store_true", dest = "full_name", default = False, help = "full dest name, not just postfix"),
             ], "[-f] [-p from_path] [-n] [dest folder name postfix: default: .On]")
    def do_rename(self, args, opts = None):
        folder = opts.from_path
        if os.path.basename(folder) == folder:
            folder = os.path.join(os.path.dirname(self.tool.run_result_path), folder)
        src_folder_name = os.path.basename(folder)
        if len(args) > 0:
            dest_folder = args[0]
            if os.path.basename(dest_folder) == dest_folder:
                dest_folder_name = dest_folder if opts.full_name else src_folder_name + dest_folder
                dest_folder = os.path.join(os.path.dirname(folder), dest_folder_name)
        else:
            dest_folder = os.path.join(os.path.dirname(folder), 'Run1.On')
        WinCmd.check_folder_exist(folder)
        if not opts.force and os.path.isdir(dest_folder): raise CmdException('dest folder already exist! %s' % dest_folder)
        try:
            WinCmd.rename_dir(folder, dest_folder)
        except:
            pass
        rename_success = True
        if os.path.isdir(folder):
            self.tool.print_('rename folder failed, kill python.exe and try again...')
            self.tool.kill_other_process(python_exe = True)
            WinCmd.kill('loganalyse')
            WinCmd.kill('socket_log')
            WinCmd.rename_dir(folder, dest_folder)
            if os.path.isdir(folder): rename_success = False
        if rename_success:
            self.tool.print_('rename %s to %s successfully.' % (folder, dest_folder))
        else:
            self.tool.print_('FAILED: rename %s to %s failed.' % (folder, dest_folder))

    @options([make_option("-f", "--farm", action = "store", type = "string", dest = "farm", default = "", help = "farm machine, ip: FARM14: 10.120.163.114"),
              make_option("-r", "--rav", action = "store", type = "string", dest = "rav", default = "", help = "rav machine, ip: RAV31: 10.120.165.31"),
             ], "[-r rav_num] [-f farm_num] {dir|file}")
    def do_open(self, args, opts = None):
        # deal with abbreviation
        def _abbrev(name, abbrev_list):
            for f, abbv in abbrev_list:
                if not isinstance(abbv, tuple): abbv = (abbv,)
                if name in abbv:
                    name = f
                    break
            return name
        temp_path_abbr = '*'
        farm = opts.farm
        resource = args[0] if len(args) else 'base'
        reload_back_farm_path = False
        if farm or opts.rav:
            if farm:
                farm_addr = self.tool.get_farm_addr(farm)
            else:
                farm_addr = self.tool.get_rav_addr(opts.rav)
            self.tool.reload_farm_path(farm_addr)
            reload_back_farm_path = True
        run_result_path = self.tool.run_result_path if os.path.isdir(self.tool.run_result_path) else os.path.dirname(self.tool.run_result_path)
        abbrev = [('run', 'r'), ('automation', 'auto'), ('python', 'py'), ('config', 'cfg'), ('batch', 'bat'),
                  ('user', 'u'), ('binary', ('bin', 'b')), ('tools', 't'), ('constant', 'cnt'),
                  ('user_batch', 'u/batch'), ('user_ubi', 'u/ubi'), ('user_script', 'u/script'), ('user_result', 'u/result'),
                  ('user_cue', 'u/cue'), ('user_mue', 'u/mue'), ('user_sue', 'u/sue'),
                  ('temp_path', temp_path_abbr)]
        debug_path = os.path.join(self.tool.test_path, 'debug')
        folder_dict = {'base': self.tool.base_path,
                       'run': run_result_path, 'boot': self.tool.boot_path, 'automation': self.tool.automation_path, 'batch': self.tool.batch_path, 'python': self.tool.python_path,
                       'config': self.tool.config_path, 'exe': self.tool.exe_path, 'pxi': self.tool.pxi_path,
                       'binary': self.tool.binary_path, 'user': self.tool.user_path, 'tools': self.tool.tool_path,
                       'user_batch': self.tool.test_batch_path, 'user_ubi': self.tool.ubi_path, 'user_script': self.tool.script_path, 'user_result': self.tool.remote_run_result_path,
                       'user_cue': os.path.join(debug_path, 'cue'), 'user_mue': os.path.join(debug_path, 'mue'), 'user_sue': os.path.join(debug_path, 'sue'),
                       'temp_path': self.tool.temp_case_path, 'transfer': self.tool.transfer_folder, 'mirror': self.tool.mirror_transfer_folder, 'monitor': self.tool.signal_folder,
                       'rav': self.tool.rav_path, 'vec': self.tool.hde_case_root_path, 'tma': self.tool.tma_path,
                       'constant': self.tool.constant_file}
        if reload_back_farm_path: self.tool.reload_farm_path()
        folders = self._split_option(resource)
        for folder in folders:
            if folder.startswith(temp_path_abbr):
                real_folder = os.path.join(self.tool.temp_case_path, os.path.relpath(folder, temp_path_abbr))
                if not os.path.isdir(real_folder): real_folder = self.tool.temp_case_path
            else:
                folder = _abbrev(folder, abbrev)
                if folder in folder_dict:
                    real_folder = folder_dict[folder]
                else:
                    self.tool.print_('not a abbreviation...')
                    if os.path.isdir(folder) or os.path.isfile(folder):
                        real_folder = folder
                    else:
                        real_folder = os.path.join(self.tool.user_path, folder)
                        if not os.path.isdir(real_folder) and not os.path.isfile(real_folder): raise CmdException('cannot find this folder:%s or %s' % (folder, real_folder))
            self.tool.print_('try to open: %s' % real_folder)
            WinCmd.explorer(real_folder)
        self.tool.print_('open %d folders successfully!' % len(folders))

    @options([], "{all|dir|file|run|error(loganalyse error)}")
    @min_args(1)
    def do_close(self, args, opts = None):
        if args[0] == 'run':
            self.tool.kill_run_batch_window()
        else:
            if args[0] == 'error': args[0] = 'WerFault'
            processes = ['explorer', 'iexplore', 'notepad++', 'cmd'] if args[0] == 'all' else [args[0]]
            for process in processes:
                WinCmd.kill(process)
                if process == 'explorer':
                    time.sleep(3)
                    WinCmd.explorer()
        self.tool.print_('close processes successfully!')

    @options([make_option("-0", "--only_update", action = "store_true", dest = "only_update", default = False, help = "only update the result, not terminate the test"),
             ], "[-0]")
    def do_update_rav(self, args, opts = None):
        if not opts.only_update:
            self.tool.kill_other_process(cmd_win = True, python_exe = True)
            raw_input(r'press any key to continue...')
        self.tool.update_result()
        if not opts.only_update: self._runcmd('rename')

    @options([make_option("-g", "--git_path", action = "store", type = "string", dest = "git_path", default = r"C:\wang\02.Git\tm_tests\batch", help = "git path"),
              make_option("-p", "--path", action = "store", type = "string", dest = "batch_path", default = r"C:\wang\03.Batch", help = "batch path"),
              make_option("-b", "--backup", action = "store_true", dest = "backup", default = False, help = "backup the old batch"),
             ], "")
    def do_update_batch(self, args, opts = None):
        batches = self.tool.update_batch(opts.git_path, opts.batch_path, opts.backup)
        self.tool.print_('updated %d batches to %s successfully!' % (len(batches), opts.batch_path))

    @options([], "")
    def do_fix_remote_copy(self, args, opts = None):
        self.tool.fix_remote_copy_paste()
        self.tool.print_('fix remote copy successfully!')

    @options([], "{project_path}")
    @min_args(1)
    def do_clean(self, args, opts = None):
        #clean_tool = os.path.join(args[0], 'tm_build_system', 'utilities', 'remove_all_derived_files.pyw')
        #WinCmd.check_file_exist(clean_tool)
        #WinCmd.cmd('python %s' % os.path.basename(clean_tool), os.path.dirname(clean_tool), showcmdwin = True)
        self.tool.clean_build_files(args[0])
        self.tool.print_('clean %s successfully!' % args[0])

    @options([make_option("-r", "--remove_folder", action = "store", type = "string", dest = "remove_folder", default = "build", help = "remove folder name, [build]|other"),
              make_option("-o", "--output", action = "store", type = "string", dest = "output", default = "", help = "output file for result"),
             ], "[-r folder] [-o output] base_folder")
    @min_args(1)
    def do_remove(self, args, opts = None):
        folders = self._split_option(opts.remove_folder)
        outputs = self.tool.retrieve_folders(args[0], folders)
        if opts.output:
            with open(opts.output, 'w') as f:
                for output in outputs: f.write(output + '\n')
        for output in outputs: WinCmd.del_dir(output, include_dir = True)
        self.tool.print_('remove folder successfully!')

    @options([make_option("-r", "--reg_value", action = "store", type = "string", dest = "reg_value", default = "", help = "register value, hex format, commonly NRP regsiter"),
              make_option("-6", "--c66", action = "store_true", dest = "c66", default = False, help = "c66cpu, c66 type"),
              make_option("-p", "--project_or_bin_path", action = "store", type = "string", dest = "project_or_bin_path", default = "", help = "project or binary path, auto-detect"),
             ], "[-r reg(NRP)] [-p project_or_bin_path] [-6] cpu_num")
    @min_args(1)
    def do_gen_cpu_sym(self, args, opts = None):
        output_file, info = self.tool.gen_cpu_symbol(opts.project_or_bin_path, args[0], opts.reg_value, c66cpu_type = opts.c66)
        for line in info:
            self.tool.print_(' '.join(line))
        self.tool.print_('generate %s successfully!' % output_file)

    @options([], "msg_hex")
    @min_args(1)
    def do_msg_identify(self, args, opts = None):
        m = self.tool.msg_identify(args[0])
        if m:
            self.tool.print_(m)
            self.tool.print_('Look at lte_msgbases.h for more details.')

    @options([make_option("-t", "--template_folder", action = "store", type = "string", dest = "template_folder", default = "", help = "template folder"),
              make_option("-o", "--output_folder", action = "store", type = "string", dest = "output_folder", default = "", help = "output folder"),
              make_option("-p", "--product", action = "store", type = "string", dest = "product", default = "", help = "sue or mue or cue, auto-detect"),
              make_option("-1", "--bin1", action = "store", type = "string", dest = "bin1", default = "", help = "the first binary used"),
              make_option("-2", "--bin2", action = "store", type = "string", dest = "bin2", default = "", help = "the second binary used"),
             ], "[-p product] [-1 bin1] [-2 bin2] [-t template_folder] [-o output_folder] target_name1 [target_name2]")
    @min_args(1)
    def do_gen_rav_priv_bin(self, args, opts = None):
        bin1_path = self.tool.get_abs_path(opts.bin1, 'binary')
        template_folder = opts.template_folder or self.tool.template_path
        output_folder = opts.output_folder or template_folder
        product = self.tool.gen_rav_priv_bin(bin1_path, template_folder, output_folder, args[0], opts.product)
        self.tool.print_('generate %s:%s successfully!' % (product.upper(), os.path.join(output_folder, args[0])))
        if len(args) > 1:
            bin2_path = self.tool.get_abs_path(opts.bin2, 'binary')
            product = self.tool.gen_rav_priv_bin(bin2_path, template_folder, output_folder, args[1], opts.product)
            self.tool.print_('generate %s:%s successfully!' % (product.upper(), os.path.join(output_folder, args[1])))

    @options([make_option("-m", "--matlab", action = "store_true", dest = "matlab", default = False, help = "monitor matlab flag"),
             ], "")
    def do_monitor(self, args, opts = None):
        self.tool.monitor_signal(opts.matlab)

    @options([], "")
    def do_reload(self, args, opts = None):
        self.tool.update_self()
        self.tool.print_('Update finished. Never see this line.')

    @options([make_option("-v", "--view", action = "store_true", dest = "view", default = False, help = "view all pre-saved text"),
             ], "[-v] [number]")
    def do_text(self, args, opts = None):
        PRE_SAVED_TEXT = [r'python \\ubimelfs.aeroflex.corp\UbiNetics\Development\Projects\AAS_TM500_LTE\User_Working_Folders\WangShouliang\tools\test_tool.py',
                          r'python P:\AAS_TM500_LTE\User_Working_Folders\WangShouliang\tools\test_tool.py',
                          r'P:\AAS_TM500_LTE\User_Working_Folders\WangShouliang']
        if opts.view:
            for i, text in enumerate(PRE_SAVED_TEXT):
                self.tool.print_('[%d] %s' % (i, text), output_time = False)
        else:
            number = args[0] if len(args) > 0 else 0
            if number >= len(PRE_SAVED_TEXT): raise CmdException('number %d is too large, should < %d' % (number, len(PRE_SAVED_TEXT)))
            WinCmd.set_clip_text(PRE_SAVED_TEXT[number])
            self.tool.print_('Set clipboard: %s' % PRE_SAVED_TEXT[number])

    @options([make_option("-p", "--project_path", action = "store", type = "string", dest = "project_path", default = "", help = "project path"),
              make_option("-o", "--output_file", action = "store", type = "string", dest = "output_file", default = "", help = "output file"),
             ], "[-p project_path] [-o output_file] list_file")
    @min_args(1)
    def do_check(self, args, opts = None):
        file_list = os.path.join(args[0], 'file_change_list.txt') if os.path.isdir(args[0]) else args[0]
        WinCmd.check_file_exist(file_list)
        output_file = opts.output_file or self.tool.get_temp_filename()
        self.tool.code_check_files(file_list, output_file, opts.project_path)
        self.tool.print_('check files finished with output %s' % output_file)
        WinCmd.explorer(output_file)

    @options([], "")
    def do_matlab(self, args, opts = None):
        user, start_time = self.tool.check_matlab_user()
        if user:
            self.tool.print_('Currently [%s] is using matlab from [%s] !' % (user, start_time))
        else:
            self.tool.print_('No user is using matlab now !')

    @options([make_option("-r", "--re", action = "store", type = "string", dest = "regex", default = "", help = "search with regular expression"),
              make_option("-f", "--findall", action = "store", type = "string", dest = "findall", default = "", help = "find all with regular expression"),
             ], "[-r regex] [-f regex] expression1 [expression2]")
    @min_args(1)
    def do_test_re(self, args, opts = None):
        if not opts.regex and not opts.findall: raise CmdException('no regular expression')
        if opts.regex:
            pattern = opts.regex
            matches = 0
            for expression in args:
                m = re.search(pattern, expression)
                if m:
                    matches = matches + 1
                    self.tool.print_('Match: %s. Groups: %d.' % (expression, len(m.groups())))
                    for i in range(len(m.groups())+1):
                        self.tool.print_('    Group %d: %s' % (i, m.group(i)))
            self.tool.print_('Total Matches: %d' % matches)
        if opts.findall:
            pattern = opts.findall
            for expression in args:
                m = re.findall(pattern, expression)
                self.tool.print_('Expression: %s' % expression)
                self.tool.print_('FindAll: %s' % m)

    def do_EOF(self, line):
        return True

######################## tools ##########################
class TestTool:
    def __init__(self, clear_signals = True):
        self.debug_enable = False
        self.local_ip = None
        self.analyse_path = ''
        self.ini = ConfigParser.ConfigParser()
        self.re_delimiters = ['@', '\"']     # delimiter: @ or ", the same key in Chinese and British keyboard respectively
        self.option_delimiters = ['|', '~']  # delimiter | or ~

        self.file_path = os.path.dirname(os.path.abspath(__file__))
        self.proxy_tool_file = os.path.join(self.file_path, 'proxy.py')
        self.reload_farm_path()
        self.default_run1_folder = self.run_result_path
        self.pxi_path = r'E:\PXI_TV'
        self.aiq_path = r'\\stv-nas.aeroflex.corp\LTE_Test_Vectors\PXI_C'
        #self.rav_path = r'\\stv-nas.aeroflex.corp\LTE_Results_Builds\Release_Candidates\LTE'
        self.rav_path = r'\\ltn3-pur-lteres.aeroflex.corp\Data'
        self.user_path = os.path.dirname(self.file_path)
        self.binary_path = os.path.join(self.user_path, 'binary')
        self.test_path = os.path.join(self.user_path, 'test')
        self.script_path = os.path.join(self.user_path, 'script')
        self.ubi_path = os.path.join(self.user_path, 'ubi')
        self.test_batch_path = os.path.join(self.test_path, 'batch')
        self.temp_case_path = os.path.join(self.test_path, 'temp')
        self.temp_trace_path = os.path.join(self.test_path, 'trace')
        self.remote_run_result_path = os.path.join(self.test_path, 'run_result')

        self.tool_path = os.path.join(self.user_path, 'tools')
        self.template_path = os.path.join(self.file_path, 'template')
        self.temp_path = os.path.join(self.file_path, 'temp')
        self.rav_cache_path = os.path.join(self.file_path, 'rav_cache')
        self.hde_case_cache_file = os.path.join(self.rav_cache_path, 'hde_case_cache.dat')
        #self.hde_case_root_path = r'\\stv-nas.aeroflex.corp\LTE_Test_Vectors\Vector Input files and Output files'
        #self.hde_case_root_path = r'\\stv-archive\Test_Vectors'
        self.hde_case_root_path = r'\\ltn3-pur-ltevec.aeroflex.corp\Data'
        self.tma_path = r'\\ubigen01.aeroflex.corp\CAMGEN04\Jobs\3GReleases\TM500'
        self.ulan_path = r'\\ubimelfs\UbiNetics\Development\Dept\AAG_R&D_general\Software\Algos\LTE_A_ULAN'
        self.target_driver_letter = {'cue_fdd': 'M', 'cue_tdd': 'Z', 'mue_fdd': 'G', 'mue_tdd': 'S', 'sue_fdd': 'N', 'sue_tdd': 'K'}
        self.target_driver_letter_sgh = {'cue_fdd': 'Z', 'cue_tdd': 'Z', 'mue_fdd': 'G', 'mue_tdd': 'S', 'sue_fdd': 'N', 'sue_tdd': 'K'}
        self.target_product_letter = {'sue': 'c', 'mue': 'm', 'cue_lmc_5c': 'ft1', 'cue_lmc_7c': 'ftx1'}
        self.target_product_letter_sgh = {'sue': 'sgh', 'mue': 'sgh', 'cue_lmc_5c': 'sgh', 'cue_lmc_7c': 'sgh'}
        # build path
        self.rel_build_path = 'tm_build_system'
        self.rel_build_temp_path = os.path.join(self.rel_build_path, 'tmp_files')
        self.rel_build_file = os.path.join(self.rel_build_path, 'scons')
        self.rel_build_tool_path = [os.path.join(self.rel_build_path, r'build\win32'), os.path.join(self.rel_build_path, r'build\host32')]
        self.rel_build_ftp_path = os.path.join(self.rel_build_path, r'build\ftp')
        self.rel_build_hde_path = os.path.join(self.rel_build_path, r'build\hde')
        self.rel_build_pyd_path = r'lte_shared_app\database\config_db\cdd\asn\pyd'
        self.pyd_file = ['_tm500_asn1_codec_25.pyd', '_tm500_asn1_codec_26.pyd', '_tm500_asn1_codec_27.pyd']
        self.rel_pyd_dir = '_pyd'
        self.traceviewer_rel_paths = [r'tm_build_system\build\release\traceviewer', r'tm_build_system\build\win32_obsolete', r'tm_build_system\build\win32']
        self.log_rel_paths = [r'tm_build_system\build\win32_obsolete', r'tm_build_system\build\win32', r'tm_build_system\build\release\loganalyse']
        self.teamcity_rel_paths = [r'tm_build_system\teamcity']
        # TI tool path
        self.ti_tool_paths = [r'C:\BuildTools\ti_cgtools_v7_3\C\bin', 'C:\BuildTools\ti_cgtools_v7_3\B\bin']
        self.rav_url_product_alias = {'mue_tdd': 'lte-mue-tdd',
                                      'mue_fdd': 'lte-mue-c0309',
                                      'mue_tdd_ho': 'lte-plat-c-tdd3gpp-mue-ho',
                                      'mue_fdd_ho': 'lte-mue-c0309-ho',
                                      'cue_fdd': 'lte_3gpp_fdd_platc_cue',
                                      'cue_tdd': 'lte_3gpp_tdd_platc_cue',
                                      'cue_fdd_ho': 'lte-cue-fdd-ho',
                                      'cue_tdd_ho': 'lte-cue-tdd-ho',
                                      'sue_fdd': 'lte_sue_c0309',
                                      'sue_tdd': 'lte-plat-c-tdd3gpp'
                                      }
        self.rav_url_product_all, self.rav_url_product, self.rav_url_product_search = {}, {}, {}
        for product, alias in self.rav_url_product_alias.items():
            self.rav_url_product_all[product] = r'http://ukrav/results/tables_30.php?page=%s' % alias
            self.rav_url_product[product] = r'http://ukrav/results/tables_30_filter.php?page=%s&var=' % alias
            self.rav_url_product_search[product] = r'http://ukrav/results/history_plot.php?table=%s&branch=ALL&var=ALL&tnum=' % alias

        self.avail_product = {'mue': ['5C', '8C'], 'cue': ['5C', '7C', 'LS2', 'LS2_4x4']}
        # file://\\ltn3-pur-lteres.aeroflex.corp\Data\CUE\LTE-CUE-LS2-8x8merge_L1_17_03_17_07_38_22\Results\RAV64_17_03_17_18_43\30113_3GPP_PDCP_5MHz_UL_POWER_CAPPING_PUSCH_VERIFY_N_20170318-18-00-03.html
        self.rav_mue_search_pattern = r"href='file:[/\\]+(\w.*?\\Results\\([-\w]+))\\'"
        #self.rav_mue_search_pattern = r"href='file:/+(stv-nas\\LTE_Results_Builds\\Release_Candidates\\LTE\\\w+\\([-\w]+)\\Results\\([-\w]+))\\'"
        self.farm_ip_addr_base = '10.120.163.100'
        self.rav_ip_addr_base = '10.120.165.0'
        self.shanghai_ip_addr_base = '10.130.0.0'
        self.stevenage_ip_addr_base = '10.120.169.0'
        self.tsms = TSMS(path = os.path.join(self.file_path, 'tsms'))
        self.transfer_folder = r'\\ltn3-eud-nas01\data\SHA2\swang2\transfer'
        self.mirror_transfer_folder = r'\\ltn3-apd-nas01\data\SHA2\swang2\transfer'  # shanghai
        self.signal_folder = os.path.join(self.transfer_folder, 'signal')
        self.remote_copy_folder = os.path.join(self.transfer_folder, 'clipboard')
        ## disable the clear signals, the signal monitors cannot be used
        #if clear_signals: self.clear_signals()
        # teamcity
        self.sanity_batch_path = r'C:\wang\03.Batch\sanity'
        self.sanity_batches_config = {'2cell': '2CELL4G5G', '3cell': '3CELL4G5G', 'default': ''}
        self.sanity_batches_dict = {'2cell': [r'batch_CUE_NAS_NR5G_ENDC_2CELL_Basic.txt',
                                              r'batch_CUE_NAS_NR5G_ENDC_2CELL_June18_Basic.txt',
                                              r'batch_CUE_NAS_NR5G_ENDC_2CELL_June18_120KHz_Basic.txt'],
                                    #'3cell': [r'batch_CUE_NAS_NR5G_ENDC_3CELL_June18_120KHz_Basic.txt'],
                                    '15k': [r'batch_CUE_PDCP_NR5G_1CELL_15kHz_Basic.txt'],
                                    '120k': [r'batch_CUE_PDCP_NR5G_1CELL_SCS120KHz_Basic.txt'],
                                    'basic': [r'batch_CUE_PDCP_NR5G_1CELL_Basic.txt']}
        self.sanity_batches = reduce(list.__add__, self.sanity_batches_dict.values(), [])
        self.other_batches = [r'batch_OVERNIGHT_CUE_PDCP_NR5G_1CELL.txt',
                              r'batch_OVERNIGHT_CUE_PDCP_NR5G_SCS120KHz.txt',
                              r'batch_OVERNIGHT_CUE_NAS_NR5G_ENDC_2CELL_120Khz.txt',
                              r'batch_OVERNIGHT_CUE_NAS_NR5G_ENDC_2CELL.txt']
        self.all_batches = self.sanity_batches + self.other_batches

    def reload_farm_path(self, farm_base_path = 'C:\\'):
        self.base_path = farm_base_path
        self.autotest_path = os.path.join(farm_base_path, r'AUTO_TEST')
        self.exe_path = os.path.join(self.autotest_path, r'Testing\external_exe')
        self.batch_path = os.path.join(self.autotest_path, r'Testing\batch')
        self.python_path = os.path.join(self.autotest_path, r'Testing\python')
        self.asn_path = os.path.join(self.python_path, 'asn')
        self.automation_path = os.path.join(self.autotest_path, r'Testing\tests\automation')
        self.config_path = os.path.join(self.autotest_path, r'Testing\config')
        self.run_result_path = os.path.join(self.autotest_path, r'TEMP\RUN1')
        self.boot_path = os.path.join(self.autotest_path, 'Boot')
        self.run1_config_file = os.path.join(self.python_path, 'paths.txt')
        self.constant_file = os.path.join(self.config_path, 'constant.txt')

    def get_remote_run1_path(self):
        run_result_folder = self.remote_run_result_path
        WinCmd.check_folder_exist(run_result_folder)
        _, ip_str = self.get_ip_addr()
        ip_str = ip_str + '_' if ip_str else ''
        run1_folder = os.path.join(run_result_folder, 'run1_%s%s' % (ip_str, datetime.now().strftime('%y%m%d')))
        if not os.path.isdir(run1_folder): WinCmd.make_dir(run1_folder)
        return run1_folder

    def _get_tool(self, project_path, rel_paths, tool_name):
        tool_found = ''
        for p in rel_paths:
            tool_path = os.path.join(project_path, p, tool_name)
            if os.path.isfile(tool_path):
                tool_found = tool_path
                break
        if not tool_found: raise CmdException('cannot find %s in %s' % (tool_name, project_path))
        return tool_found

    def get_traceviewer(self, project_path):
        return self._get_tool(project_path, self.traceviewer_rel_paths, tool_name = 'traceviewer.exe')

    def get_logcombuilder(self, project_path):
        return self._get_tool(project_path, self.log_rel_paths, tool_name = 'logcombuilder.pyw')

    def get_remote_run(self, project_path):
        return self._get_tool(project_path, self.teamcity_rel_paths, tool_name = 'remote_run.pyw')

    def get_presub(self, project_path):
        return self._get_tool(project_path, self.teamcity_rel_paths, tool_name = 'presub.pyw')

    def get_temp_build_file(self, project_path, unique = False):
        build_temp_path = os.path.join(project_path, self.rel_build_temp_path)
        if not os.path.isdir(build_temp_path): WinCmd.make_dir(build_temp_path)
        filename = 'temp_build_output.txt' if not unique else 'temp_build_output_%s.txt' % datetime.now().strftime('%y%m%d%H%M%S')
        return os.path.join(build_temp_path, filename)

    def get_temp_name(self, unique = False, suffix = ''):
        pass

    def get_temp_filename(self, unique = False, suffix = ''):
        if not os.path.isdir(self.temp_path): WinCmd.make_dir(self.temp_path)
        filename_1 = 'temp' if not unique else 'temp_%s' % datetime.now().strftime('%y%m%d%H%M%S')
        filename = filename_1 + suffix + '.txt'
        return os.path.join(self.temp_path, filename)

    def _get_ip_addr_mask(self, ip):
        ip_parts = ip.split('.')
        if len(ip_parts) != 4: raise CmdException('not a valid ip: %s' % ip)
        return '.'.join(ip_parts[:3])

    def check_ip_addr(self, local_ip):
        if self._get_ip_addr_mask(local_ip) == self._get_ip_addr_mask(self.shanghai_ip_addr_base):
            description = 'SGH%03d' % (int(local_ip.split('.')[-1]) - int(self.shanghai_ip_addr_base.split('.')[-1]))
            weight = 4
        elif self._get_ip_addr_mask(local_ip) == self._get_ip_addr_mask(self.stevenage_ip_addr_base):
            description = 'STV%03d' % (int(local_ip.split('.')[-1]) - int(self.stevenage_ip_addr_base.split('.')[-1]))
            weight = 4
        else:
            try:
                description = self.tsms.ip_to_name(local_ip)
                weight = 3
            except Exception as e:
                self.print_('Exception in ip_to_name: %s' % e)
                description = ''
        if not description:
            if self._get_ip_addr_mask(local_ip) == self._get_ip_addr_mask(self.farm_ip_addr_base):
                description = 'PFC%02d' % (int(local_ip.split('.')[-1]) - int(self.farm_ip_addr_base.split('.')[-1]))
                weight = 2
            elif self._get_ip_addr_mask(local_ip) == self._get_ip_addr_mask(self.rav_ip_addr_base):
                description = 'RAV%02d' % (int(local_ip.split('.')[-1]) - int(self.rav_ip_addr_base.split('.')[-1]))
                weight = 1
            else:
                description = 'NONE%02d' % (int(local_ip.split('.')[-1]))
                weight = 0
        return weight, local_ip, description

    def get_ip_addr(self):
        if not self.local_ip is None: return self.local_ip
        try:
            #local_ip = socket.gethostbyname(socket.gethostname())
            local_ip_addresses = [ip for ip in WinCmd.get_ip_addresses()]
        except:
            local_ip_addresses = []
        if local_ip_addresses:
            ip_list = map(self.check_ip_addr, local_ip_addresses)
            ip_list.sort(reverse = True)
            self.local_ip = ip_list[0][1:]
        else:
            self.local_ip = ('0.0.0.0', 'unknown00')
        # (ip, host_name)
        return self.local_ip

    def get_farm_addr(self, farm_num):
        farm_num = int(farm_num)
        if farm_num not in [1,2,3,4,5,6,9,10,11,12,13,14,16,17,19]: raise CmdException('can not find FARM %d' % farm_num)
        #farm_addr = r'\\%s' % farm_ip_addr_base
        farm_addr = r'\\10.120.163.1%02d' % farm_num
        return farm_addr

    def get_rav_addr(self, rav_num):
        rav_num = int(rav_num)
        rav_addr = r'\\10.120.165.%02d' % rav_num
        return rav_addr

    def get_farm_run_folder(self, farm_str):
        farm = farm_str.split(',')
        if len(farm) == 1:
            machine, folder = farm[0], None
        else:
            machine, folder = farm[0], farm[1]
        machine_addr = self.get_farm_addr(machine)
        self.reload_farm_path(machine_addr)
        run_folder = self.run_result_path
        self.reload_farm_path()
        if folder: run_folder = os.path.join(os.path.dirname(run_folder), folder)
        return run_folder

    def add_default_folder(self, files, default_folder):
        if not default_folder: return files
        WinCmd.check_folder_exist(default_folder)
        input_is_file = False
        if not isinstance(files, list):
            files = [files]
            input_is_file = True
        out_files = [os.path.join(default_folder, f) if f.find(os.path.sep) < 0 else f for f in files]
        return out_files[0] if input_is_file else out_files

    def get_temp_path(self, rel_path):
        default_flag = '*'
        if rel_path.startswith(default_flag):  # '*' means default, '*/temp_folder'
            temp_path = self.temp_case_path if rel_path == default_flag else os.path.join(self.temp_case_path, os.path.relpath(rel_path, default_flag))
        else:
            temp_path = ''
        return temp_path

    def get_abs_path(self, rel_path, path_ref = 'user', only_test_valid = False):
        if not rel_path or os.path.isdir(rel_path): return rel_path
        ref_path = self.binary_path if path_ref == 'binary' else self.user_path
        abs_path = os.path.join(ref_path, rel_path)
        if os.path.isdir(abs_path): return abs_path
        if only_test_valid: return ''  # not a valid path
        raise CmdException('Path not found: both %s and %s.' % (rel_path, abs_path))

    def get_re_files(self, file_patterns, exclude_dir = True, sort_by_time = False):
        ''' retrieve all files that indicated by regular expressions '''
        file_exist = os.path.isfile if exclude_dir else os.path.exists
        re_files = []
        if not isinstance(file_patterns, list): file_patterns = [file_patterns]
        main_delimiter = self.re_delimiters[0]
        for file_pattern in file_patterns:
            for delimiter in self.re_delimiters[1:]:
                file_pattern = file_pattern.replace(delimiter, main_delimiter)
            if main_delimiter in file_pattern:
                temp_path, pattern = file_pattern.split(main_delimiter)
                path = self.get_abs_path(os.path.dirname(temp_path + 'temp'))
                for f in os.listdir(path):
                    abs_f = os.path.join(path, f)
                    if file_exist(abs_f) and re.search(pattern, f, flags = re.IGNORECASE) and not abs_f in re_files:
                        re_files.append(abs_f)
            else: # not a regular expression
                path, file = os.path.split(file_pattern)
                abs_f = os.path.join(self.get_abs_path(path), file)
                if file_exist(abs_f) and not abs_f in re_files:
                    re_files.append(abs_f)
        files = list(set(re_files))
        files.sort()
        if sort_by_time and len(files) > 1:
            files_mtime = [(os.stat(f).st_mtime, f) for f in files]
            files_mtime.sort()  # from old to new
            files = [f for t, f in files_mtime]
        return files

    def get_re_cases(self, re_cases):
        cases = []
        if re_cases[0] in self.re_delimiters:
            main_delimiter = self.re_delimiters[0]
            for delimiter in self.re_delimiters[1:]:
                re_cases = re_cases.replace(delimiter, main_delimiter)
            re_cases = re_cases[1:].split(main_delimiter)
            for case in range(100000):
                case = '%05d' % case
                for pattern in re_cases:
                    if re.search(pattern, case) > 0:
                        cases.append(case)
                        break
        if cases: self.print_('re cases(%d): %s' % (len(cases), ','.join(cases)))
        return cases

    def print_(self, str, output_time = True):
        if output_time:
            print('[%s]%s' % (datetime.now().strftime('%H:%M:%S'), str))
        else:
            print(str)
        sys.stdout.flush()

    def debug_print(self, str):
        if self.debug_enable:
            self.print_(str)

    def change_files_name(self, folder, prefix_deleted):
        files = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith(prefix_deleted)]
        letters_num = len(prefix_deleted)
        for f in files:
            os.rename(f, os.path.join(folder, os.path.basename(f)[letters_num:]))
        return len(files)

    def change_ulan(self, ulan_ver = '', dest_folder = ''):
        if ulan_ver:
            if not dest_folder: dest_folder = self.exe_path
            ver = 'ULAN_VER_%s_%s' % tuple(ulan_ver.split('.'))
            ulan_file = os.path.join(self.ulan_path, ver, 'LteUlan.exe')
            WinCmd.check_file_exist(ulan_file)
            WinCmd.copy_file(ulan_file, dest_folder)
            self.print_('ulan version changed to %s (from %s to %s)' % (ulan_ver, os.path.dirname(ulan_file), dest_folder))

    def get_run1_folder(self):
        if not os.path.isfile(self.run1_config_file):
            self.print_('run1 config file : %s not found! Set to default run1 folder.' % self.run1_config_file)
            return self.default_run1_folder
        #WinCmd.check_file_exist(self.run1_config_file)
        run1_folders = []
        with open(self.run1_config_file, 'r') as f:
            for line in f:
                line = line.strip()
                r = re.search('^results_default\s*=\s*(.*)$', line, flags = re.IGNORECASE)
                if r: run1_folders.append(r.group(1))
        output_folder = None
        if len(run1_folders) > 1:
            self.print_('Warning: more than 1 run1 folder found! %s' % run1_folders)
            output_folder = run1_folders[-1]
        elif len(run1_folders) == 0:
            self.print_('Error: no run1 folder found!')
        else:
            output_folder = run1_folders[0]
        if output_folder: output_folder = os.path.abspath(os.path.join(os.path.dirname(self.run1_config_file), output_folder))
        return output_folder

    def backup_recover_boot(self, backup = True):
        boot_path = self.boot_path

        self.print_('start to change binary...')
        if not bin_path: raise CmdException('no valid binary path: %s.' % bin_path)
        boot_path = boot_path or self.boot_path
        if os.path.isdir(boot_path): WinCmd.del_dir(boot_path)
        WinCmd.copy_dir(bin_path, boot_path)
        try:
            pyd_path = os.path.join(bin_path, self.rel_pyd_dir)
            pyd_files = [os.path.join(pyd_path, f) for f in self.pyd_file if os.path.isfile(os.path.join(pyd_path, f))]
            if pyd_files: WinCmd.copy_files(pyd_files, self.asn_path)
        except Exception as e:
            self.print_(str(e))
            self.print_('copy asn files failed!!!')
        self.print_('change binary to %s successfully!' % bin_path)


    def set_run1_folder(self, run1_folder = '', show_config_file = True):
        WinCmd.check_file_exist(self.run1_config_file)
        if not run1_folder: run1_folder = self.default_run1_folder
        if self.get_run1_folder() == run1_folder:
            self.print_('run1 folder no need change: %s' % run1_folder)
            return
        lines = open(self.run1_config_file, 'r').readlines()
        modify_lines = 0
        with open(self.run1_config_file, 'w') as f_write:
            for line in lines:
                line = line.strip()
                r = re.search('^results_default\s*=\s*(.*)$', line, flags = re.IGNORECASE)
                if r:
                    f_write.write(r'results_default=%s' % run1_folder + '\n')
                    modify_lines += 1
                else:
                    f_write.write(line + '\n')
        if modify_lines != 1:
            self.print_('change run1 folder fail. changed lines: %d' % modify_lines)
            WinCmd.explorer(self.run1_config_file)
        else:
            self.print_('change run1 folder %s successfully.' % run1_folder)
            if run1_folder != self.default_run1_folder and show_config_file: WinCmd.explorer(self.run1_config_file)

    def delete_earliest_subfolders(self, num = 1, reserve_days = 14, folder = ''):
        folder = folder or self.binary_path
        WinCmd.check_folder_exist(folder)
        threshold = time.time() - reserve_days * 24*3600
        subfolders = [os.path.join(folder, f) for f in os.listdir(folder) if os.path.isdir(os.path.join(folder, f))]
        subfolders_mtime = [(os.stat(f).st_mtime, f) for f in subfolders if os.stat(f).st_mtime < threshold or os.path.basename(f).endswith('_1')]
        subfolders_mtime.sort()
        delete_num = min(num, len(subfolders_mtime))
        for i in range(delete_num):
            WinCmd.del_dir(subfolders_mtime[i][1], include_dir = True)
            self.print_('deleted folder %s' % subfolders_mtime[i][1])
        return delete_num

    def _get_ue_from_project_name(self, project_name):
        ue_options = ['sue', 'mue', 'cue']
        if not project_name: return ''
        ues = [u for u in ue_options if project_name.find(u) >= 0]
        return ues[0] if len(ues) == 1 else ''

    def get_build_products(self, products, project_name = ''):
        ue_options = ['sue', 'mue', 'cue']
        pro_options = {'sue': ['4x2', '2x2', 'sue2'], 'mue': ['5c', '8c', 'ca', 'mue2'], 'cue': ['5c', '7c', 'ls2', '4x4', '8x8']}
        def _build_product_alias(alias, ue = ''):
            alias_dict = {'mue': {'5c': '2x2_split_dl', '8c': '2x2', 'ca': '2x2_split_dl_ca'}, 'cue': {'5c': 'extmue', '7c': 'loadsys_split_dl', '4x4': 'ls2_4x4', '8x8': 'ls2_8x8'}}
            if not ue or ue not in alias_dict.keys(): return alias
            if alias not in alias_dict[ue].keys(): return alias
            return alias_dict[ue][alias]
        ue = self._get_ue_from_project_name(project_name)
        if products:
            build_products = []
            for product in products:
                if product in ue_options:
                    if ue and product != ue: raise CmdException('incorrect %s detected for %s.' % (product, ue))
                    return [_build_product_alias(alias, product) for alias in pro_options[product]], ue
                elif product:
                    build_products.append(_build_product_alias(product, ue))
            return build_products, ue
        elif ue:
            return [_build_product_alias(alias, ue) for alias in pro_options[ue]], ue
        return [], ue

    def _product_alias(self, product):
        # product: [ue]_[pro]_[rat]_[ho] or [ue]_[rat]
        ue_options = ['sue', 'mue', 'cue']
        pro_options = {'sue': ['4x2', '2x2', 'sue2'], 'mue': ['5c', '8c', 'mue2'], 'cue': ['5c', '7c', 'ls2', '4x4']}
        rat_options = ['tdd', 'fdd']
        ho_options = ['ho']

        elements = product.split('_')
        ue = pro = rat = ho = None
        for elem in elements:
            if elem in ue_options:
                ue = elem
            elif elem in rat_options:
                rat = elem
            elif elem in ho_options:
                ho = elem
            else:  # pro
                if not ue: raise CmdException('invalid product aliasing: %s' % product)
                if elem in pro_options[ue]:
                    pro = elem
        return [ue, pro, rat, ho]

    def _get_rav_html_page(self, product):
        # product: [ue]_[pro]_[rat] or [ue]_[rat]
        # sue: '4x2', '2x2', 'NX', mue: '5c', '8c', 'HW', cue: '5c', '7c', '-LS2-'
        ue, pro, rat, ho = self._product_alias(product)
        if not ue or not rat: raise CmdException('invalid product aliasing: %s' % product)
        # map mue mue2->hw, cue ls2->-ls2-, sue sue2->nx
        if ue == 'mue' and pro == 'mue2': pro = 'hw'
        elif ue == 'cue' and pro in ['ls2', '4x4']: pro = '-ls2-'
        elif ue == 'sue' and pro == 'sue2': pro = 'nx'
        url_product = '%s_%s' % (ue, rat) if not ho else '%s_%s_%s' % (ue, rat, ho)
        url = self.rav_url_product_all[url_product] if not pro else self.rav_url_product[url_product] + pro.upper()
        if self.debug_enable:
            self.print_('Try to get the url: %s' % url)
        try:
            html = urllib2.urlopen(url, timeout = 3)
        except Exception as e:
            raise CmdException('open RAV page error! "%s", %s' % (url, e))
        return html

    def _get_search_folders(self, product):
        html = self._get_rav_html_page(product)
        content = html.read()
        if self.debug_enable:
            temp_file = self.get_temp_filename()
            open(temp_file, 'w').write(content)
            WinCmd.explorer(temp_file)
        ue = product.split('_')[0]
        if ue in ['cue', 'mue']:
            folders = [r'\\%s' % s.group(1) for s in re.finditer(self.rav_mue_search_pattern, content)]
        else:
            raise CmdException('%s (from %s) not supported.' % (ue, product))
        return folders

    def get_rav_cases_info(self, product, re_filter = '', flags = 0, all_cases = False):
        # rav_cases_info: (rav_case_txt, run_history)
        rav_cases_info = self._get_rav_cases(product, get_case_info = True)
        filter_case_info = []
        results = ['PASS', 'FAIL', 'CRASH', 'FATAL', 'COMMAND ERROR', 'MISSING RESOURCE']
        for rav_case_txt, run_history in rav_cases_info:
            if not re_filter or re.search(re_filter, rav_case_txt, flags = flags):
                run_result = {}
                statistic_str = ''
                total_run = 0
                for r in results:
                    run_result[r] = run_history.count(r)
                    statistic_str += '%s: %2d,' % (r, run_result[r])
                    total_run += run_result[r]
                if all_cases or run_result['PASS']:
                    filter_case_info.append('%s   Run: %d, %s' % (rav_case_txt, total_run, statistic_str))
        return filter_case_info

    def _get_rav_cases(self, product, get_case_info = False):
        html = self._get_rav_html_page(product)
        rav_cases = []
        rav_cases_info = []
        for line in html.readlines():
            s_script = re.search(r'>((\d{5})_.*\.txt)', line.rstrip().lower())
            if s_script:
                rav_case_txt, rav_case = s_script.group(1), s_script.group(2)
                if rav_case[0] != '0' and rav_case[:2] != '48':
                    rav_cases.append(rav_case)
                    if get_case_info:
                        run_history = re.findall(r'(?<=>)[ \w]+(?=</a>)', line.rstrip())
                        if len(run_history) <= 2:
                            self.print_('Warning in history: case %s, html %s' % (rav_case, html))
                        else:
                            run_history = run_history[2:]
                            rav_cases_info.append((rav_case_txt, run_history))
        return rav_cases if not get_case_info else rav_cases_info

    def _get_product_batch(self, product, batch_dir = None, except_batches = []):
        if not batch_dir: batch_dir = self.batch_path
        rav_cases_not_in_any_batch = []
        batches = {}
        for filename in self._get_batch_files(batch_dir, except_batches):
            batch_cases = []
            with open(filename, 'r') as f:
                for line in f:
                    s_batch = re.search(r'^(\d{5})_.*\.txt', line.strip().lower())
                    if s_batch and s_batch.group(1)[0] != '0':
                        batch_cases.append(s_batch.group(1))  # only case number
            batches[os.path.basename(filename)] = batch_cases
        test_cases = {}  # all cases in batch
        for batch, cases in batches.items():
            for case_num in cases:
                if not case_num in test_cases: test_cases[case_num] = []
                if not batch in test_cases[case_num]: test_cases[case_num].append(batch)
        rav_cases_num = list(set(self._get_rav_cases(product)))
        #print rav_cases_num
        output_batches = []
        rav_cases_not_in_batch = []
        redundant_cases_in_batch = []
        while True:
            # found rav case only in one batch
            select_rav_case = None
            for rav_case_num in rav_cases_num:
                if rav_case_num not in test_cases:
                    rav_cases_not_in_batch.append(rav_case_num)
                    rav_cases_num.remove(rav_case_num)
                elif len(test_cases[rav_case_num]) == 1:
                    select_rav_case = rav_case_num
                    break
            if not select_rav_case:
                # found rav case in two or more batches
                if not rav_cases_num: break
                select_rav_case = rav_cases_num[0]
                if not select_rav_case in test_cases: continue
            # select batch which has minimum cases
            select_batch = test_cases[select_rav_case][0]
            for batch in test_cases[select_rav_case][1:]:
                if len(batches[batch]) < len(batches[select_batch]): select_batch = batch
            if select_batch in output_batches: continue  # this batch already processed
            # process batch
            output_batches.append(select_batch)
            for batch_case in batches[select_batch]:
                if batch_case in rav_cases_num: rav_cases_num.remove(batch_case)
                else: redundant_cases_in_batch.append((batch_case, select_batch, test_cases[batch_case]))
            if not rav_cases_num: break
        return (output_batches, rav_cases_not_in_batch, redundant_cases_in_batch)

    def gen_rav_batch_bat(self, bat_file, product, batch_dir = None, except_batches = []):
        WinCmd.check_folder_exist(os.path.dirname(bat_file))
        batches, remain_rav_cases, redundant_batch_cases = self._get_product_batch(product, batch_dir, except_batches)
        ordered_batches, ordered_batches_for_print = self._sort_batches(batches)
        if remain_rav_cases:
            self.print_('remain_rav_cases:')
            for case in remain_rav_cases:
                self.print_(case)
        if redundant_batch_cases:
            self.print_('redundant_batch_case:')
            for case in redundant_batch_cases:
                self.print_(case)
        self.print_('total %d batches, %d remain cases, %d redundant cases' % (len(ordered_batches), len(remain_rav_cases), len(redundant_batch_cases)))
        self._save_batch_to_bat_file(bat_file, ordered_batches, ordered_batches_for_print)

    def _sort_batches(self, batches):
        def select_match_batch(batches, match_str):
                if not isinstance(match_str, list): match_str = [match_str]
                select_batches = []
                for s in match_str:
                    for batch in batches:
                        if s in batch.lower():
                            select_batches.append(batch)
                return list(set(select_batches))
        # sort batch files
        modes = ['harq', 'mac', 'pdcp', 'rlc', 'nas']
        features_1 = ['normal', '4x2']
        features_2 = ['beamforming', 'embms', '8x2', '_ca']
        #order = [('harq', 'normal'), ('mac', 'normal'), ('pdcp', 'normal'), ('rlc', 'normal'), ('nas', 'normal'),
        remain_batches, ordered_batches, ordered_batches_for_print = batches, [], []
        #print 'batches:', len(batches), batches
        for mode in modes:
            select_batches = select_match_batch(remain_batches, mode)
            remain_batches = list(set(remain_batches) - set(select_batches))
            batches_2 = select_match_batch(select_batches, features_2)
            select_batches = list(set(select_batches) - set(batches_2))
            batches_1 = select_match_batch(select_batches, features_1)
            batches_default = list(set(select_batches) - set(batches_1))
            ordered_batches += batches_1 + batches_default + batches_2
            ordered_batches_for_print += batches_1 + batches_default + batches_2 + [None]
        #print 'ordered_batches:', len(ordered_batches), ordered_batches
        #print 'remain_batches:', len(remain_batches), remain_batches
        ordered_batches += remain_batches
        ordered_batches_for_print += remain_batches
        #print 'ordered_batches:', len(ordered_batches), ordered_batches
        if len(ordered_batches) != len(batches): raise CmdException('batches %d ordered to %d!' % (len(batches), len(ordered_batches)))
        return ordered_batches, ordered_batches_for_print

    def _save_batch_to_bat_file(self, bat_file, ordered_batches, ordered_batches_for_print):
        if not ordered_batches:
            self.print_('no batches found!')
            return
        if not ordered_batches_for_print: ordered_batches_for_print = ordered_batches
        with open(bat_file, 'w') as f:
            f.write('@REM total %d batches\n' % len(ordered_batches))
            for batch in ordered_batches_for_print:
                if batch: f.write('call ttm_runner.py %s\n' % batch)
                else: f.write('\n')

    def get_batch_from_results_folder(self, results_folder):
        WinCmd.check_folder_exist(results_folder)
        batches = []
        for filename in glob(os.path.join(results_folder, '*.html')):
            f = os.path.basename(filename)
            r = re.search(r'(batch_.*?)_\d{8}-\d{2}-\d{2}-\d{2}\.html', f)
            if r:
                batch_name = r.group(1) + '.txt'
                if batch_name.find('batch_fum') < 0 and batch_name.find('batch_manf_plat_c') < 0:
                    batches.append(batch_name)
        return list(set(batches))

    def gen_rav_batch_bat_from_results_folder(self, bat_file, results_folder):
        batches = self.get_batch_from_results_folder(results_folder)
        ordered_batches, ordered_batches_for_print = self._sort_batches(batches)
        self.print_('total %d batches.' % (len(ordered_batches)))
        self._save_batch_to_bat_file(bat_file, ordered_batches, ordered_batches_for_print)

    def set_env(self, product, rat = 'fdd', fum_binary = '', cue = '7c', load_vector = False, load_vector_only = False, sgh = False):
        product, rat = product.lower(), rat.lower()
        key = '%s_%s' % (product, rat)
        driver_letter = self.target_driver_letter[key] if not sgh else self.target_driver_letter_sgh[key]
        if product in ['mue', 'sue', 'cue'] and driver_letter:
            if product == 'cue':
                if not cue in ['5c', '7c']: raise CmdException('please specify cue type 5c or 7c.')
                product = 'cue_lmc_%s' % cue
            product_letter = self.target_product_letter[product] if not sgh else self.target_product_letter_sgh[product]
            path = r'%s:\lte_i_and_v\Process\Release' % driver_letter
            if not load_vector_only:
                self.print_(r'start to run "%s\release_new.bat 8 %s" ...' % (path, product_letter))
                WinCmd.cmd('release_new.bat 8 %s' % product_letter, path, showcmdwin = True)
                self.print_(r'run "%s\release_new.bat 8 %s" finished' % (path, product_letter))
            if load_vector:
                self.print_(r'start to run "%s\release_new.bat 9 %s" seperately...' % (path, product_letter))
                WinCmd.cmd('release_new.bat 9 %s' % product_letter, path, showcmdwin = True, wait = False, retaincmdwin = True)       # do not wait for 9c and leave the cmd window
            if fum_binary:
                bin = self.get_abs_path(fum_binary, 'binary')
                self.load_binary(bin)
                self.run_fum()

    def log_format(self, files, domain = 'dsp', no_sort = False, latest = False):
        if not isinstance(files, list): files = [files]
        flags = {'dsp': '-ddsp', 'hlc': '-dhlc', 'umbra': '-dumbra'}
        if not domain in flags: raise CmdException('invalid domain %s' % domain)
        flag = flags[domain]
        if latest and len(files) > 1:
            files_mtime = [(os.stat(f).st_mtime, f) for f in files]
            files_mtime.sort(reverse = True)
            files = [files_mtime[0][1]]
        for f in files:
            WinCmd.check_file_exist(f)
            src_f = os.path.basename(f)
            dest_f = '%s_%s.txt' % (os.path.splitext(src_f)[0], domain)
            WinCmd.cmd(r'loganalyse.exe %s %s > %s' % (flag, src_f, dest_f), os.path.dirname(f), showcmdwin = True, minwin = True, wait = True)
            if not no_sort: WinCmd.sort_file(os.path.join(os.path.dirname(f), dest_f))

    def gen_cpu_symbol(self, project_or_bin_path, cpu_num, reg_value = '', c66cpu_type = False):
        ti_tool = 'nm6x.exe'
        cpu_num = int(cpu_num)
        ti_tool_path = [p for p in self.ti_tool_paths if os.path.isfile(os.path.join(p, ti_tool))]
        if not ti_tool_path: raise CmdException('TI tool %s not found!' % ti_tool)
        cpu_files = [os.path.join(self.get_abs_path(project_or_bin_path, 'binary'), '%s%d.out' % (cpu, cpu_num)) for cpu in ['cpu', 'c66cpu']] \
                   +[os.path.join(project_or_bin_path, self.rel_build_ftp_path, '%s%d.out' % (cpu, cpu_num)) for cpu in ['cpu', 'c66cpu']]
        cpu_files = [f for f in cpu_files if os.path.isfile(f)]
        if not cpu_files: raise CmdException('cpu file [c66]cpu%d.out not found!' % cpu_num)
        if len(cpu_files) > 1:
            if c66cpu_type:
                cpu_files = [f for f in cpu_files if os.path.basename(f).startswith('c66cpu')]
            else:
                cpu_files = [f for f in cpu_files if os.path.basename(f).startswith('cpu')]
            if not cpu_files: raise CmdException('cpu file [c66]cpu%d.out not found! c66cpu type: %s' % (cpu_num, str(c66cpu_type)))
            cpu_file = cpu_files[0]
        else:
            cpu_file = cpu_files[0]
        self.print_('found cpu file: %s' % cpu_file)
        output_file = os.path.join(os.path.dirname(cpu_file), '%s_symbols.txt' % os.path.splitext(os.path.basename(cpu_file))[0])
        WinCmd.cmd('%s -n %s > %s' % (ti_tool, cpu_file, output_file), ti_tool_path[0])
        WinCmd.explorer(output_file)
        if reg_value:
            int_reg_value = int(reg_value, 16)
            with open(output_file, 'r') as f:
                lines = [line.strip().split() for line in f]
            for i, line in enumerate(lines):
                if int(line[0], 16) > int_reg_value: break
            for t_i in xrange(i-1, 0, -1):
                if lines[t_i][1] == 'T': break
            return (output_file, [['[line: %d]' % (t_i+1)] + lines[t_i], ['[line: %d]' % (i)] + lines[i-1], ['[line: %d]' % (i+1)] + lines[i]])
        return (output_file, [])

    def msg_identify(self, msg_hex):
        # ['F01x', 'F02x', 'F03x', 'F04x', 'F05x']
        copro_base = ['MSG_BASE_VD_COPRO', 'MSG_BASE_TD_COPRO', 'MSG_BASE_UCP_COPRO', 'MSG_BASE_SC_COPRO', 'MSG_BASE_PCP_COPRO']
        # from sys_msgif.h
        domain_name = ['domain_PLATFORM', 'domain_SEGMENTATION', 'domain_CSYS', 'domain_RADIO_UPDATE', 'domain_CRADIO', 'domain_APP_COMMON', 'domain_LPHY', 'domain_PSERV',
                      'domain_INTRA_DSP', 'domain_CPHY', 'domain_PHY', 'domain_GPHY', 'domain_RPHY', 'domain_L2_LO', 'domain_L2_HI', 'domain_INTRA_UMBRA', 'domain_MANF',
                      'domain_VUMBRA', 'domain_UMBRATEST', 'domain_SLAVE_CHASSIS', 'domain_URI', 'domain_UL_PHY', 'domain_FUM', 'domain_RXPHY', 'domain_HSPHY',
                      'domain_EDPHY', 'domain_TXPHY']
        # from sys_msgbases.h
        msg_bases = ['MSG_BASE_KERNEL', 'MSG_BASE_UMBRA_UPDATE', 'MSG_BASE_CUMBRA', 'MSG_BASE_CUMBRA_TEST', 'MSG_BASE_CUMBRA_DEBUG', 'MSG_BASE_UMBRA',
                    'MSG_BASE_UMBRA_INTERNAL', 'MSG_BASE_CUMBRA_LTE', 'MSG_BASE_UMBRA_LTE']
        try:
            msg_bin = bin(int(msg_hex,16))
            msg_bin = '0'*24+msg_bin[2:]
            # Domain(6bit)+1 (1bit) + Src(5bit) + Dest(5bit) + MsgNum(7bit), total 24 bits
            domain_index, src, dest, msg_num = [int(x,2) for x in [msg_bin[-24:-18],msg_bin[-17:-12], msg_bin[-12:-7], msg_bin[-7:]]]
        except:
            self.print_('analyse fail for msg %s' % msg_hex)
            return ''
        domain = '%s' % (domain_name[domain_index] if 0<= domain_index < len(domain_name) else '%d' % domain_index)
        intra_dsp_index = domain_name.index('domain_INTRA_DSP')
        if domain_index < intra_dsp_index:
            if src >= len(msg_bases):
                self.print_('seems invalid copro base, see sys_msgbases.h')
                msg_base = '0x%02x000' % src
            else:
                msg_base = '%s' % msg_bases[src]
        elif src == 15 and dest == 0:  # copro
            index = msg_num / 2**4 - 1
            if 0 <= index < len(copro_base):
                msg_num = msg_num % 2**4
                msg_base = '%s' % copro_base[index]
            else:
                self.print_('seems invalid copro base')
                msg_base = 'MAKE_DSP_BASE(%d, %d)' % (src, dest)
        else:
            msg_base = 'MAKE_DSP_BASE(%d, %d)' % (src, dest)
        return 'DEF_MSG_BASE(%s, %s): Msg %d.    (number from 1).' % (domain, msg_base, msg_num)

    def gen_rav_priv_bin(self, bin_path, template_folder, output_folder, target_name, product = ''):
        WinCmd.check_folder_exist(bin_path)
        WinCmd.check_folder_exist(template_folder)
        WinCmd.check_folder_exist(output_folder)
        target_folder = os.path.join(output_folder, target_name)
        WinCmd.del_dir(target_folder)
        # check product
        bin_path_filename = os.path.basename(bin_path)
        product_choice = ['sue', 'mue', 'cue']
        pro = [p for p in product_choice if p in bin_path_filename.lower().replace('extmue', 'ext')]
        if len(pro) > 1: raise CmdException('binary %s product %s confused' % (bin_path_filename, str(pro)))
        if product:
            if not product.lower() in product_choice: raise CmdException('invalid product %s' % product)
            if pro and product.lower() != pro[0]: raise CmdException('binary %s not suitable for product %s' % (bin_path_filename, product))
        else:
            if not pro: raise CmdException('no product information for binary %s' % bin_path_filename)
            product = pro[0]
        template = [os.path.join(template_folder, t) for t in os.listdir(template_folder) if t.lower().find(product) > 0 and t.find('_{Name}') > 0 and os.path.isdir(os.path.join(template_folder, t))]
        if len(template) != 1: raise CmdException('cannot find product %s template in %s' % (product, template_folder))
        WinCmd.copy_dir(template[0], target_folder)
        target_bin_folder = os.path.join(target_folder, 'ppc_pq', 'public', 'ftp_root')
        target_tools_folder = os.path.join(target_folder, 'tools')
        target_loganalyse_folder = os.path.join(target_folder, 'loganalyse')
        WinCmd.copy_dir(os.path.join(bin_path, 'tools'), target_tools_folder)               # copy tools
        pyd_path = os.path.join(bin_path, self.rel_pyd_dir)
        for pyd_file in [os.path.join(pyd_path, f) for f in self.pyd_file]:                 # copy pyd files
            WinCmd.check_file_exist(pyd_file)
            WinCmd.copy_file(pyd_file, target_tools_folder)
        WinCmd.copy_dir(os.path.join(bin_path, 'loganalyse'), target_loganalyse_folder)     # copy loganalyse
        except_files = [self.rel_pyd_dir] if not isinstance(self.rel_pyd_dir, list) else self.rel_pyd_dir
        except_files += ['tools', 'loganalyse']
        for f in [os.path.join(bin_path, f) for f in os.listdir(bin_path) if not f in except_files]:
            if os.path.isfile(f): WinCmd.copy_file(f, target_bin_folder)
            else: WinCmd.copy_dir(f, target_bin_folder, empty_dest_first = False, include_src_dir = True)
        return product

    def filter_in_file(self, filename, regex, lines_around, output_file, file_flag = True):
        filtered_line_num = []
        with open(filename, 'r') as f:
            for line_num, line in enumerate(f):
                if re.search(regex, line, flags = re.IGNORECASE):
                    filtered_line_num.append(line_num)
        if filtered_line_num:
            target_line_num = reduce(lambda x,y: x+range(y-lines_around, y+lines_around+1), filtered_line_num, [])
            target_line_num = filter(lambda x: x >= 0, list(set(target_line_num)))
            target_line_num.sort()
            with open(output_file, 'a') as f_write:
                if file_flag: f_write.write('\n%s %s %s\n\n' % ('#'*20, filename, '#'*20))
                with open(filename, 'r') as f:
                    target_line = target_line_num.pop(0)
                    for line_num, line in enumerate(f):
                        if line_num == target_line:
                            if len(target_line_num) == 0: break
                            target_line = target_line_num.pop(0)
                            f_write.write(line)
        return len(filtered_line_num)

    def search_in_file(self, filename, regex, piece_size = 30, bytes_align = False, excel_file = False):
        filesize = os.path.getsize(filename)
        gen_pieces, n = self._gen_all_pieces(filesize, piece_size)
        index_found = -1
        for i, piece in enumerate(gen_pieces):
            data = self._file_split_data(filename, piece, n, not bytes_align)
            if re.search(regex, data, flags = re.IGNORECASE):
                index_found = i
                break
        return (index_found, n)

    def _gen_all_pieces(self, filesize, piece_size):
        piece_size = piece_size * 1000000
        n = (filesize + piece_size -1) / piece_size  # ceil
        if n < 2: return ([(0, 0, filesize)], n)  # if file too small to split, return directly
        start, gen_pieces = 0, []
        for i in range(n):
            if i == n-1:
                gen_pieces.append((i, start, filesize - start))
            else:
                gen_pieces.append((i, start, piece_size))
            start += piece_size
        return (gen_pieces, n)

    def file_split(self, filename, init_piece_idx = [], init_last_piece_idx = [], piece_size = 30, all_pieces = False, default_split = False, bytes_align = False, excel_file = False):    # piece_size: Mbytes
        filesize = os.path.getsize(filename)
        gen_pieces, n = self._gen_all_pieces(filesize, piece_size)
        if n < 2: return []  # if file too small to split, return directly
        piece_idx, last_piece_idx = [], []
        piece_idx += init_piece_idx
        last_piece_idx += init_last_piece_idx
        if all_pieces:
            piece_idx = range(n)
        else:
            if last_piece_idx:
                if 1 in last_piece_idx and not 2 in last_piece_idx:
                    # if only the last piece is specified and the last piece is smaller than 5Mbytes, then add the n-2 piece also
                    last_piece_size = gen_pieces[n-1][2]
                    if last_piece_size < 5000000: last_piece_idx.append(2)
                last_piece_idx = [n-i for i in last_piece_idx if n>=i>=1]
                piece_idx += last_piece_idx
            if not piece_idx or default_split:
                if n < 4:
                    piece_idx += range(n)
                elif (3*n)/5 == (n-2):
                    piece_idx += [0, (3*n)/5, n-1]     #scale = [0 3/5 n-1]
                else:
                    piece_idx += [0, (3*n)/5, n-2]     #scale = [0 3/5 n-2]
        piece_idx = [i for i in piece_idx if n-1>=i>=0]
        piece_idx = list(set(piece_idx))
        if not piece_idx: return []  # no piece index specified
        pieces = [gen_pieces[i] for i in piece_idx]
        if excel_file:
            header = self._excel_file_header(filename)
            split_at_line_break = True
        else:
            header = ''
            split_at_line_break = not bytes_align
        files = [self._file_split(filename, piece, n, split_at_line_break, header) for piece in pieces]
        return files

    def _file_split_data(self, filename, piece, n, split_at_line_break = False, header_data = ''):
        data = ''
        line_break = '\n'
        back_chars = 2000  # assume the max chars of one line is less than 2000
        i, start_bytes, piece_size = piece[0], piece[1], piece[2]
        with open(filename, 'rb') as f:
            f.seek(start_bytes)
            read_size = piece_size
            if i > 0 and split_at_line_break:  # not the first block
                read_size += self._locate_back_line_break(f, line_break = line_break, back_chars = back_chars)
            data = f.read(read_size)
            if i < n-1 and split_at_line_break:  # not the last block
                data_end = data[-back_chars:]
                index = data_end.rfind(line_break)
                if index >= 0: data = data[:read_size-back_chars+index+1]
            if header_data and i > 0: data = header_data + data
        if not data: self.print_('no data split from file: %s, piece %d/%d.' % (filename, i, n))
        return data

    def _file_split(self, filename, piece, n, split_at_line_break = False, header_data = ''):
        i, start_bytes, piece_size = piece[0], piece[1], piece[2]
        fpath, fext = os.path.splitext(filename)
        file_write = '%s_%d_%d%s' % (fpath, n, i, fext)
        data = self._file_split_data(filename, piece, n, split_at_line_break, header_data)
        if data: open(file_write, 'wb').write(data)
        return file_write

    def _locate_back_line_break(self, fid, line_break = '\n', back_chars = 2000):
        actual_back_chars = 0
        line_break_found = False
        seek_error = False
        try:
            fid.seek(-back_chars, 1)
        except:
            seek_error = True
            self.print_('file seek error. current pos %d, offset %d.' % (fid.tell(), -back_chars))
        if not seek_error:
            data = fid.read(back_chars)
            index = data.rfind(line_break)
            if index >= 0:
                fid.seek(index-back_chars+1, 1)  # just move after the line_break character
                line_break_found = True
                actual_back_chars = -(index-back_chars+1)
        return actual_back_chars

    def _excel_file_header(self, filename):
        header_data = ''
        header_found = False
        max_header_lines = 30
        with open(filename, 'r') as f:
            for i, line in enumerate(f):
                if i > max_header_lines: break
                header_data += line
                if line.startswith('#State'):  # the header finished
                    header_data += '\n'   # add one more blank line
                    header_found = True
                    break
        if not header_found:
            header_data = ''
            self.print_('cannot find header data for excel file: %s' % filename)
        return header_data

    def extract_log(self, filename, dsp_cores_str = [], hlc_cores_str = [], only_dedicated = False):
        # 8343.013191769:   LTE DSP   4.1	LOG_UL_BRP_PUCCH_BASE_ENC_MESSAGE_HARQ_COMMON_1(...
        if only_dedicated:
            devices_filter = ['ALL']
            device_cores_str = ['DSP_%s' % s for s in dsp_cores_str] + ['HLC_%s' % s for s in hlc_cores_str]
        else:
            devices_filter, device_cores_str = [], []
            if dsp_cores_str:
                devices_filter += ['DSP']
                device_cores_str += ['DSP_%s' % s for s in dsp_cores_str]
            if hlc_cores_str:
                devices_filter += ['HLC']
                device_cores_str += ['HLC_%s' % s for s in hlc_cores_str]
        pattern = r'LTE\s+(\w+)\s+([\d\.]+)\s+\w'
        fpath, fext = os.path.splitext(filename)
        device_cores_write = {}
        files_write = []
        with open(filename, 'r') as f:
            for line in f:
                r = re.search(pattern, line)
                if r:
                    device, core_str = r.group(1), r.group(2)
                    device_core_str = '%s_%s' % (device, core_str)
                    if device_core_str in device_cores_str or (device not in devices_filter and 'ALL' not in devices_filter):
                        if not device_core_str in device_cores_write:
                            file_write = '%s_%s%s' % (fpath, device_core_str, fext)
                            files_write.append(file_write)
                            device_cores_write[device_core_str] = open(file_write, 'w')
                        device_cores_write[device_core_str].write(line)
                elif line.strip():
                    self.print_('warning: line not in pattern: %s' % line.strip())
        for d, f in device_cores_write.items():
            f.close()
        return files_write

    def remove_smaller_files(self, files, remove_size = 200):
        if not remove_size: return files
        remove_size *= 1000 # KBytes -> Bytes
        output_files = []
        for f in files:
            if os.stat(f).st_size > remove_size:
                output_files.append(f)
            else:
                os.remove(f)
        return output_files

    def copy_result(self, dest_folder, src_folder = '', include_trace = False, include_pxi = False, log_filter = '', include_mux_log = False, del_flag = False, start_html = False, filter = '', last_timestamp_num = 1, no_common_files = False):
        if not src_folder: src_folder = self.run_result_path
        if not os.path.isdir(dest_folder): WinCmd.make_dir(dest_folder)
        patterns = []
        if not filter:
            if not no_common_files: patterns += [r'^[\d_]*\d{5}_.*\.html$', r'^[\d_]*\d{5}_.*\.raw_results$', r'^[\d_]*\d{5}_.*\.txt$']
            if start_html: patterns.append(r'^Start.*\.html$')
            if include_trace: patterns.append(r'\.trc$')
            if include_pxi: patterns.append(r'\.pxi$')
            if log_filter == 'all':
                patterns.append(r'^la_log_.*\.txt$')
                #patterns.append(r'^SLOG_Chassis.*\.dat$')  # SLOG_Chassis_6_5726_20150728-11-13-15_1.dat
            elif log_filter:
                patterns.append(r'^la_log_.*%s.*\.txt$' % log_filter)
            if include_mux_log:
                patterns.append(r'^SLOG_.*_MUX_.*\.dat$') # SLOG_LA_MUX_DATA_25700_20150714-07-58-27_1.dat
                # only the smallest(latest due to the cyclic buffering) SLOG need copy
        else:
            if filter[0] in self.re_delimiters: filter = filter[1:]  # remove the optional delimiter
            patterns.append(filter)
        files = self.get_re_files([os.path.join(src_folder, self.re_delimiters[0]+pattern) for pattern in patterns])
        files = self.files_in_last_run(files, last_timestamp_num, src_folder)
        total_files_num = len(files)
        temp_files, files = files, []
        for f in temp_files:
            target_file = os.path.join(dest_folder, os.path.basename(f))
            if not os.path.isfile(target_file):
                files.append(f)
            elif os.stat(f).st_mtime != os.stat(target_file).st_mtime:   # additional copy
                files.append(f)
        need_copy_files_num = len(files)
        self.print_('starting to copy %d files (out of %d) from %s ...' % (need_copy_files_num, total_files_num, src_folder))
        if files: WinCmd.copy_files(files, dest_folder)
        if del_flag: WinCmd.del_dir(src_folder)
        return need_copy_files_num, total_files_num

    def copy_vectors(self, vectors, remove_flag = False):
        def _delete_big_file():
            big_files = ['LTE_eNodeB_2_Cell_20_DRB_7-bit-sn_UM-5bit-SN_DL_UL_Batch_1_To_Batch_20_Ant1.aiq',
                 'LTE38060_Cell_0_DRB_7-bit-sn_UM-5bit-SN_DL_UL_Batch_1_To_Batch_20_UL_MCS_28.aiq',
                 'LTE38060_Cell_1_DRB_7-bit-sn_UM-5bit-SN_DL_UL_Batch_1_To_Batch_20_UL_MCS_28.aiq',
                 'LTE38060_Cell_2_DRB_7-bit-sn_UM-5bit-SN_DL_UL_Batch_1_To_Batch_20_UL_MCS_28.aiq',
                 'LTE38060_Cell_3_DRB_7-bit-sn_UM-5bit-SN_DL_UL_Batch_1_To_Batch_20_UL_MCS_28.aiq',
                 'LTE38060_Cell_4_DRB_7-bit-sn_UM-5bit-SN_DL_UL_Batch_1_To_Batch_20_UL_MCS_28.aiq',
                 'LTE_eNodeB_7_Cell_70_Eps_Bearer_5_DRB_PN9_PAYLOAD_7-bit-sn_UM-5bit-SN_DL_UL_Batch_16_To_Batch_20.aiq',
                 'LTE_eNodeB_7_Cell_70_Eps_Bearer_5_DRB_PN9_PAYLOAD_7-bit-sn_UM-5bit-SN_DL_UL_Batch_11_To_Batch_15.aiq',
                 'LTE_eNodeB_7_Cell_70_Eps_Bearer_5_DRB_PN9_PAYLOAD_7-bit-sn_UM-5bit-SN_DL_UL_Batch_6_To_Batch_10.aiq',
                 'LTE_eNodeB_7_Cell_70_Eps_Bearer_5_DRB_PN9_PAYLOAD_7-bit-sn_UM-5bit-SN_DL_UL_Batch_1_To_Batch_5.aiq']
            big_files = [os.path.join(self.pxi_path, p) for p in big_files]
            for f in big_files:
                if os.path.isfile(f) and os.path.getsize(f) > 1000:
                    os.remove(f)
                    self.print_('delete big file %s for more spaces' % os.path.basename(f))
                    return True
            return False
        def _copy_vec(vector, remove_flag):
            target_file = os.path.join(self.pxi_path, os.path.basename(vector))
            if os.path.isfile(target_file):
                if remove_flag or os.path.getsize(target_file) < 1000:
                    os.remove(target_file)
                else:
                    return True
            WinCmd.check_file_exist(vector)
            try:
                WinCmd.copy_file(vector, self.pxi_path)
                self.print_('copy vector %s to folder %s successfully' % (vector, self.pxi_path))
                return True
            except:
                return False
        deleted_big_files_num = 0
        for vector in vectors:
            result = _copy_vec(vector, remove_flag)
            if not result:
                if deleted_big_files_num > 3: raise CmdException('cannot copy file %s to folder %s' % (vector, self.pxi_path))
                if not _delete_big_file(): raise CmdException('cannot find big file to remove for more spaces')
                deleted_big_files_num += 1
                if not _copy_vec(vector, remove_flag): raise CmdException('cannot copy file %s to folder %s after delete big file' % (vector, self.pxi_path))

    def run_fum(self, pfc_config = ''):
        self.print_('start run batch_fum.txt...')
        new_fum = self.create_fum()
        pfc_config_str = ' -s %s' % pfc_config if pfc_config else ''
        #WinCmd.cmd('call ttm_runner.py batch_fum.txt', self.python_path, showcmdwin = True)
        WinCmd.cmd('call ttm_runner.py %s%s' % (new_fum, pfc_config_str), self.python_path, showcmdwin = True)
        self.print_('run batch_fum.txt successfully!')

    def create_fum(self):
        new_fum = os.path.join(self.batch_path, 'batch_fum_.txt')
        if not os.path.isfile(new_fum):
            batch_fum = os.path.join(self.batch_path, 'batch_fum.txt')
            WinCmd.check_file_exist(batch_fum)
            copy_line = True
            with open(batch_fum, 'r') as f:
                with open(new_fum, 'w') as f_write:
                    for line in f:
                        if copy_line:
                            f_write.write(line)
                        else:
                            break
                        if line.strip() == 'tests_start': copy_line = False
                    f_write.write('\n00002_FUM_UMBRA.txt\ntests_stop\n')
        return os.path.basename(new_fum)

    def _change_batch_run_times(self, batch_file, run_times = 1):
        WinCmd.check_file_exist(batch_file)
        if run_times > 1:
            batch_cases, batch_head = self._get_batch_cases(batch_file)
            with open(batch_file, 'w') as f_write:
                for line in batch_head:
                    f_write.write(line + '\n')
                f_write.write('\n## error script\n\n')
                for times in range(run_times):
                    for case in batch_cases:
                        f_write.write(case + '\n')
                    f_write.write('\n')
                f_write.write('\ntests_stop\n')

    def _change_bat_file(self, bat_file, start_batch_num = 0, pfc_config = '', re_filter_pattern = ''):
        WinCmd.check_file_exist(bat_file)
        if start_batch_num > 0 or pfc_config or re_filter_pattern:
            batch_line_prefix = 'call ttm_runner.py'
            with open(bat_file, 'r') as f:
                all_batches = []
                for line in f:
                    if line.strip().startswith(batch_line_prefix) and re.search(re_filter_pattern, line.strip()[len(batch_line_prefix):], flags = re.IGNORECASE):
                        all_batches.append(line.strip())
            if start_batch_num >= len(all_batches): raise CmdException('cannot start from batch number %d, total %d batches.' % (start_batch_num, len(all_batches)))
            pfc_config_str = ' -s %s' % pfc_config if pfc_config else ''
            with open(bat_file, 'w') as f_write:
                for line in all_batches[start_batch_num:]:
                    f_write.write('%s%s\n' % (line, pfc_config_str))

    def run_one_batch(self, batch_file, run_times = 1, pfc_config = '', retain_win = False, info = '', min_win = False):
        if os.path.isfile(batch_file):
            self.print_('start run %s%s...' % (info, batch_file))
            WinCmd.copy_file(batch_file, self.batch_path)        # copy batch
            if run_times > 1:
                self._change_batch_run_times(os.path.join(self.batch_path, os.path.basename(batch_file)), run_times)
            pfc_config_str = ' -s %s' % pfc_config if pfc_config else ''
            WinCmd.cmd('call ttm_runner.py %s%s' % (os.path.basename(batch_file), pfc_config_str), self.python_path, showcmdwin = True, minwin = min_win, retaincmdwin = retain_win, title = 'Test Running by Shouliang...')
            self.print_('run %s%s (%d times) successfully!' % (info, batch_file, run_times))
        else:
            self.print_('batch file %s%s not exist!' % (info, batch_file))

    def empty_run_folder(self):
        run1_folder = self.get_run1_folder()
        if not run1_folder: raise CmdException('run1 folder not found!')
        if run1_folder.lower() != self.run_result_path.lower():
            # additional check, run1 folder should have no subfolder
            subfolder = [f for f in os.listdir(run1_folder) if os.path.isdir(os.path.join(run1_folder, f))]
            if len(subfolder): raise CmdException('run1 folder %s have subfolders %s, please check.' % (run1_folder, subfolder))
            self.print_('Warning: not default run1 folder: %s. wait 3s to empty...' % run1_folder)
            time.sleep(3)
        WinCmd.del_dir(run1_folder)
        self.print_('empty %s successfully!' % run1_folder)

    def load_binary(self, bin_path, boot_path = ''):
        self.print_('start to change binary...')
        if not bin_path: raise CmdException('no valid binary path: %s.' % bin_path)
        boot_path = boot_path or self.boot_path
        if os.path.isdir(boot_path): WinCmd.del_dir(boot_path)
        WinCmd.copy_dir(bin_path, boot_path)
        try:
            pyd_path = os.path.join(bin_path, self.rel_pyd_dir)
            pyd_files = [os.path.join(pyd_path, f) for f in self.pyd_file if os.path.isfile(os.path.join(pyd_path, f))]
            if pyd_files: WinCmd.copy_files(pyd_files, self.asn_path)
        except Exception as e:
            self.print_(str(e))
            self.print_('copy asn files failed!!!')
        self.print_('change binary to %s successfully!' % bin_path)

    def _get_timestamp_file(self, run1_folder = ''):
        run1_folder = run1_folder or self.get_run1_folder()
        if not run1_folder: raise CmdException('no run1 folder found!')
        timestamp_file = os.path.join(run1_folder, '00009_private_timestamp.txt')
        return timestamp_file

    def mark_timestamp(self, case_stop = False):
        timestamp_file = self._get_timestamp_file()
        folder = os.path.dirname(timestamp_file)
        if not os.path.isdir(folder): WinCmd.make_dir(folder)
        if not os.path.isfile(timestamp_file):
            self.print_('try to mark timestamp: %s, case stop: %s' % (timestamp_file, case_stop))  # test, wangsl???
        with open(timestamp_file, 'a') as f_write:
            timestamp = datetime.now().strftime('%Y%m%d_%H_%M_%S')
            f_write.write(timestamp if case_stop else '\n%s--' % timestamp)
        if not os.path.isfile(timestamp_file):
            self.print_('WARNING: timestamp file: %s cannot be created' % (timestamp_file))
        return True

    def _get_period(self, last_timestamp_num = 1, run1_folder = ''):
        timestamp_file = self._get_timestamp_file(run1_folder)
        WinCmd.check_file_exist(timestamp_file)
        lines = [tuple(line.strip().split('--')) for line in open(timestamp_file, 'r').readlines() if line.strip()]
        lines = lines[-min(last_timestamp_num, len(lines)):]
        period = []
        for i, (start, stop) in enumerate(lines):
            if i == len(lines)-1 and not stop: stop = datetime.now().strftime('%Y%m%d_%H_%M_%S')
            if not stop: continue
            datetime_params = []
            for t in [start, stop]:
                temp, hour, minute, second = t.split('_')
                year, month, day = temp[:4], temp[4:6], temp[6:]
                param = tuple([int(x) for x in [year, month, day, hour, minute, second]])
                datetime_params.append(datetime(*param))
            period.append(tuple(datetime_params))
        return period

    def show_run_result(self, last_timestamp_num = 1, all = False, remote_run1 = False, src_folder = '', open_file = False):
        run1_folder = src_folder or (self.get_run1_folder() if not remote_run1 else self.get_remote_run1_path())
        if not run1_folder: raise CmdException('no run1 folder found!')
        period = self._get_period(last_timestamp_num, run1_folder) if not all else None
        if period: self.print_('result period, %s' % str(period))
        filename = self.get_temp_filename(unique = True, suffix = '_All0')
        status = self._gen_result_0(run1_folder, filename, period)
        # (total_num, pass_num, crash_num, fail_num, other_num)
        self.print_('total: %d, pass: %d, crash: %d, fail: %d, other: %d' % status)
        self.print_('generate run result file: %s successfully.' % filename)
        if open_file: WinCmd.explorer(filename)

    def show_last_html(self, last_batch = False, last_case = False, remote_run1 = False, src_folder = ''):
        if not last_batch and not last_case: return
        run1_folder = src_folder or (self.get_run1_folder() if not remote_run1 else self.get_remote_run1_path())
        if not run1_folder: raise CmdException('no run1 folder found!')
        last_batch_found = last_case_found = None
        for f in os.listdir(run1_folder):
            filename = os.path.join(run1_folder, f)
            if re.search(r'^(?!.*batch_fum)00000_.*\.html$', f):
                if not last_batch_found or os.stat(filename).st_mtime > last_batch_found[1]:
                    last_batch_found = (filename, os.stat(filename).st_mtime)
            if re.search(r'^(?!0000)(\d+_)?\d{5}_.*\.html$', f):
                if not last_case_found or os.stat(filename).st_mtime > last_case_found[1]:
                    last_case_found = (filename, os.stat(filename).st_mtime)
        if last_batch:
            if not last_batch_found: raise CmdException('no last batch file found!')
            WinCmd.explorer(last_batch_found[0])
            self.print_('show batch result file: %s successfully.' % last_batch_found[0])
        if last_case:
            if not last_case_found: raise CmdException('no last case file found!')
            WinCmd.explorer(last_case_found[0])
            self.print_('show case result file: %s successfully.' % last_case_found[0])

    def _file_in_period(self, filename, period):
        WinCmd.check_file_exist(filename)
        file_time = datetime.fromtimestamp(os.stat(filename).st_mtime)
        sec_dev = timedelta(seconds = 2)
        for p_start, p_end in period:
            if p_start-sec_dev <= file_time <= p_end+sec_dev:
                return True
        return False

    def files_in_last_run(self, files, last_timestamp_num = 1, run1_folder = ''):
        if not run1_folder: run1_folder = self.run_result_path
        period = self._get_period(last_timestamp_num, run1_folder) if last_timestamp_num > 0 else None
        return [f for f in files if self._file_in_period(f, period)] if period else files

    def analyse_folder(self, folder, period = None):
        folder_result = []
        self._analyse_folder(folder, folder_result, period)
        return folder_result

    def _analyse_folder(self, folder, folder_result, period = None):
        '''analyse every 00001_*.raw_results files in the folder, recursively analyse each sub-folder'''
        result = []
        for filename in glob(os.path.join(folder, '00001_*.raw_results')):
            if os.path.basename(filename).find('batch_fum') >= 0: continue  # do not analyse batch_fum
            if period and not self._file_in_period(filename, period): continue  # if period exist, only analyse the file in the period
            self.print_('analyse file: %s' % filename)
            r = self.analyse_file(filename)
            if r:   # change filename from '00001_*.raw_results' to '00000_*.html'
                path, name = os.path.split(filename)
                name = name.replace('00001_', '00000_').replace('.raw_results', '.html')
                result.append([os.path.join(path, name), r])
        folder_result += result

        for d in os.listdir(folder):
            subfolder = os.path.join(folder, d)
            if os.path.isdir(subfolder):
                self._analyse_folder(subfolder, folder_result, period)

    def save_folder_sesult(self, filename, folder = '', product = '', re_gen_search_folder = False):
        if not folder: folder = self.run_result_path
        file, ext = os.path.splitext(filename)
        files = ['%s_%s%s' % (file, i, ext) for i in ['All0', 'Fail1', 'Rav2', 'Crash3', 'Auto4', 'Remove5', 'Summarise6']]
        self._gen_result_0(folder, files[0])        # generate 'All0' file
        self._gen_result_info(files[0], files[6])   # generate 'Summarise6' file
        self._gen_result_1(files[0], files[1])      # generate 'Fail1' file
        self._gen_result_3(files[0], files[3])      # generate 'Crash3' file
        if product:
            (rav_cache_path, search_folders) = self.gen_rav_search_folders(product, except_folder = folder, re_gen_search_folder = re_gen_search_folder)
            self._gen_result_2(files[1], files[2], rav_cache_path, search_folders)
            self._gen_result_4(files[2], files[4], files[5])

    def _gen_result_0(self, folder, file_all, period = None):
        # generate 'All0' file
        result_all = self.analyse_folder(folder, period)
        batch_num = len(result_all)
        fail_num = other_num = crash_num = pass_num = 0
        for fresult in result_all:
            # fresult format: [filename, [[fail], [other], [pass]]]
            fail_num += len(fresult[1][0])
            other_num += len(fresult[1][1])
            pass_num += len(fresult[1][2])
            for pass_fail in fresult[1]:
                for c in pass_fail:
                    # c format: ['FAIL', '*.txt', ['info1', 'info2']] or ['PASS', '*.txt']
                    if c[0] == 'CRASH': crash_num += 1
        fail_num -= crash_num
        total_num = fail_num + pass_num + other_num + crash_num
        status = (total_num, pass_num, crash_num, fail_num, other_num)

        with open(file_all, 'w') as f:
            for fresult in result_all:
                # fresult format: [filename, [[fail], [other], [pass]]]
                f.write(fresult[0] + '\n')
                for pass_fail in fresult[1]:
                    if pass_fail: f.write(' '*4 +'-'*100+'\n')
                    for c in pass_fail:
                        # c format: ['FAIL', '*.txt', ['info1', 'info2']] or ['PASS', '*.txt']
                        f.write(' '*4 + ' : '.join(c[:2]) + '\n')   # 4 space indentation
                        if len(c) == 3 and c[2]:  # the last is info
                            for info in c[2]:
                                if info: f.write(' '*8 + info + '\n')    # 8 space indentation
                f.write('\n')
        return status

    def gen_more_result(self, from_file, folder = '', product = '', re_gen_search_folder = False):
        name = ['All0', 'Fail1', 'Rav2', 'Crash3', 'Auto4', 'Remove5', 'Summarise6']
        from_name = ''
        for n in name:
            pos = os.path.basename(from_file).find(n)
            if pos > 0:
                from_name = n
                break
        if not from_name: raise CmdException('not a valid file %s, no suffix in %s.' % (from_file, name))
        files = []
        for n in name:
            files.append(from_file.replace(from_name, n))
        # All0-> Fail1, Crash3
        # if product: Fail1 -> Rav2
        # Rav2 -> Auto4, Remove5
        gen_from_file_num = 0
        if from_name == 'All0':
            self._gen_result_info(files[0], files[6])   # generate 'Summarise6' file
            self._gen_result_1(files[0], files[1])      # generate 'Fail1' file
            self._gen_result_3(files[0], files[3])      # generate 'Crash3' file
            gen_from_file_num = 1
        if (from_name == 'Fail1' or gen_from_file_num == 1) and product:
            (rav_cache_path, search_folders) = self.gen_rav_search_folders(product, except_folder = folder, re_gen_search_folder = re_gen_search_folder)
            self._gen_result_2(files[1], files[2], rav_cache_path, search_folders)
            gen_from_file_num = 2
        if from_name == 'Rav2' or gen_from_file_num == 2:
            self._gen_result_4(files[2], files[4], files[5])

    def _gen_result_info(self, file_all, file_info):
        KEY_TOTAL = 'TOTAL'
        KEY_ALL_BATCHES = 'all_batches'
        def __print_batch(info, batch_file, append_str = ''):
            order = ['PASS', 'CRASH', 'FAIL', 'FATAL']
            f_write.write(batch_file + ':%s\n' % append_str)
            for o in order:
                if o in info[batch_file]:
                    f_write.write('    %s: %s/%s\n' % (o, info[batch_file][o], info[batch_file][KEY_TOTAL]))
            for k, v in info[batch_file].items():
                if not k.startswith(KEY_TOTAL) and not k in order:
                    f_write.write('    %s: %s/%s\n' % (k, v, info[batch_file][KEY_TOTAL]))
            f_write.write('\n')
        info = {}
        info[KEY_ALL_BATCHES] = {}
        info[KEY_ALL_BATCHES][KEY_TOTAL] = 0
        current_batch_name = ''
        with open(file_all, 'r') as f_all:
            for line in f_all:
                if not line.strip(): continue
                if not line.startswith(' '):  # file line
                    r = re.search(r'00000_(.*batch.*)_\d{8}-\d{2}-\d{2}-\d{2}.html', line, flags = re.IGNORECASE)
                    if not r: raise CmdException('analyse fail on file line: %s' % line)
                    current_batch_name = r.group(1)
                    info[current_batch_name] = {}  # total, pass, fail, crash, other
                    info[current_batch_name][KEY_TOTAL] = 0
                elif line.startswith(' '*8): continue  # content
                elif line.startswith(' '*4):
                    if line.startswith(' '*4+'-'): continue  # separate line
                    r = re.search(r'^\s+(\w+)\s*:', line)
                    if not r: raise CmdException('analyse fail on line: %s' % line)
                    run_result = r.group(1).strip()
                    if run_result not in info[current_batch_name]: info[current_batch_name][run_result] = 0
                    info[current_batch_name][run_result] += 1
                    info[current_batch_name][KEY_TOTAL] += 1
                    if run_result not in info[KEY_ALL_BATCHES]: info[KEY_ALL_BATCHES][run_result] = 0
                    info[KEY_ALL_BATCHES][run_result] += 1
                    info[KEY_ALL_BATCHES][KEY_TOTAL] += 1
        # info -> file_info
        with open(file_info, 'w') as f_write:
            __print_batch(info, KEY_ALL_BATCHES, ' [total %d batches]' % (len(info)-1))
            for k in info:
                if not k.startswith(KEY_ALL_BATCHES):
                    __print_batch(info, k)

    def _gen_result_1(self, file_all, file_fail):
        former_line = ''    # always write the former line, in order to remove the '---' line before the first 'PASS :' line
        with open(file_all, 'r') as f_all:
            with open(file_fail, 'w') as f_fail:
                for line in f_all:
                    if line.find('PASS :') < 0:
                        f_fail.write(former_line)       # remove PASS line
                        former_line = line
                    else:
                        former_line = ''
                f_fail.write(former_line)

    def _gen_result_3(self, file_all, file_crash):
        has_seperate_line = False
        is_crash_content = False
        with open(file_all, 'r') as f_all:
            with open(file_crash, 'w') as f_crash:
                for line in f_all:
                    if not line.strip():
                        f_crash.write(line)
                    elif not line.startswith(' '):  # file line
                        f_crash.write(line)
                        has_seperate_line = False   # '---------------' line
                        is_crash_content = False
                    elif line.startswith(' '*8) and is_crash_content:
                        f_crash.write(line)
                    elif line.startswith(' '*4):
                        if line.find('CRASH :') >= 0:
                            if not has_seperate_line:
                                f_crash.write(' '*4 +'-'*100+'\n')
                                has_seperate_line = True
                            f_crash.write(line)
                            is_crash_content = True
                        else:
                            is_crash_content = False

    def _gen_result_2(self, file_fail, file_rav, rav_cache_path, search_folders):
        search_result = None
        with open(file_fail, 'r') as f_fail:
            with open(file_rav, 'w') as f_rav:
                for line in f_fail:
                    if not search_result is None and not line.startswith(' '*8):
                        for result in search_result:    #[[folder, 'FAIL', [info1, info2]], [folder, 'PASS', []], ...]
                            f_rav.write('%s%s: %s\n' % (' '*12, result[1], result[0]))
                            for r in result[2]:
                                f_rav.write(' '*16 + r + '\n')
                        f_rav.write(' '*4 +'-'*100+'\n')
                        search_result = None
                    f_rav.write(line)
                    s_script = re.search(r'(FAIL|FATAL|CRASH) : (\d{5})_.*.txt', line)
                    if s_script:
                        search_result = self.search_case_on_rav(s_script.group(2), rav_cache_path, search_folders)

    def _get_one_case(self, file_rav):
        output_file, output_case, valid = '', '', False
        with open(file_rav, 'r') as f_rav:
            for line in f_rav:
                if not line.strip(): continue
                elif not line.startswith(' '):  # file line
                    output_file = line.strip()
                elif line.startswith(' '*4) and line[4] in ['F', 'C']:
                    case = line.strip()
                elif line.startswith(' '*8) and line[8] != ' ':
                    pass

    def _load_file_rav(self, file_rav):
        all_results = []
        batch_result = case_info = history_case_info = case_result = None
        # case info: (version name, pass or fail, fail info)
        # results: [(batch name, [(case name, [case info, history case info1, ...]), (case name, (case info, ...)), ... ]), (batch name, ...)]
        with open(file_rav, 'r') as f:
            for line in f:
                if line.startswith(' '*16) and line[16] != ' ':  # history case info
                    history_case_info[2].append(line.strip())
                else:
                    if history_case_info:
                        case_result[1].append(history_case_info)
                        history_case_info = None
                    if line.startswith(' '*12) and line[12] != ' ':  # history case line
                        if case_info:
                            case_result[1].append(case_info)
                            case_info = None
                        s = re.search('(\w+) *: *(\w.*$)', line.strip())
                        history_case_info = (s.group(2), s.group(1), [])
                    elif line.startswith(' '*8) and line[8] != ' ':  # case info
                        case_info[2].append(line.strip())
                    else:
                        if case_info:
                            case_result[1].append(case_info)
                            case_info = None
                        if line.startswith(' '*4) and line[4] in ['F', 'C']:  # case line
                            if case_result:
                                batch_result[1].append(case_result)
                                case_result = None
                            s = re.search('(\w+) *: *(\d{5}.*txt$)', line.strip())
                            case_result = (s.group(2), [])
                            case_info = (None, s.group(1), [])
                        elif line.strip() and not line.startswith(' '):  # file line
                            if case_result:
                                batch_result[1].append(case_result)
                                case_result = None
                            if batch_result:
                                all_results.append(batch_result)
                                batch_result = None
                            batch_result = (line.strip(), [])
        if history_case_info: case_result[1].append(history_case_info)
        if case_info: case_result[1].append(case_info)
        if case_result: batch_result[1].append(case_result)
        if batch_result: all_results.append(batch_result)
        return all_results

    def _platform_issue(self, run_info):
        platform_msg = [r'The RF hardware fitted does not support the specified carrier frequencies',
                        r'Capture_IQ_CaptMem: ERROR',
                        r'FAIL: Data Captured',
                        r'ERROR: RF Input Level out of range',
                        r'Socket Error : [Errno 10060] A connection attempt failed']
        for info in run_info:
            for msg in platform_msg:
                if info.find(msg) >= 0:
                    return True
        return False

    def _same_fail_as_tot_or_platform_issue(self, case_result, judge_level = 0):
        def _info_silimar(info1, info2, threshold = 75):      # 75% similarity
            if not info1 or not info2: return False
            if len(info1) != len(info2): return False
            for i1, i2 in zip(info1, info2):
                if not StrTool.similar(i1, i2, threshold = threshold): return False
            return True
        # [case info, history case info1, ...]
        # case info: (version name, pass or fail, fail info)
        if not case_result: raise CmdException('case result empty.')
        run_result, history_result = case_result[0], case_result[1:]
        run_version, run_fail, run_info = run_result
        if self._platform_issue(run_info): return True  # platform issue, remove the fail log
        if run_version != None: raise CmdException('case result process wrong:' + str(run_result))
        if not history_result: return False
        tot_history_result = [(version, fail, info) for version, fail, info in history_result if version and '0' <= version[-1] <= '9'] # tot version, not a private version
        threshold = max(len(tot_history_result)/2, 2)
        similar_num = 0
        remain_num = len(tot_history_result)
        for version, fail, info in tot_history_result:
            remain_num -= 1
            if run_fail == fail and _info_silimar(run_info, info):
                similar_num += 1
                if similar_num >= threshold: # similar result >= 1/2, at least 2
                    return True
                elif (similar_num + remain_num) < threshold:
                    return False
        return False

    def _gen_result_4(self, file_rav, file_auto, file_remove):
        def _write_batch_result(batch_name, batch_result, f_write):
            if batch_result:
                first_line = False
                f_write.write(batch_name + '\n')
                for case_name, case_result in batch_result:
                    run_result, history_result = case_result[0], case_result[1:]
                    if not first_line:
                        f_write.write(' '*4 +'-'*100+'\n')
                        first_line = True
                    f_write.write(' '*4 + run_result[1] + ' : ' + case_name + '\n')   # 4 space indentation
                    for info in run_result[2]:
                        if info: f_write.write(' '*8 + info + '\n')    # 8 space indentation
                    for version, fail, history_info in history_result:
                        f_write.write(' '*12 + fail + ': ' + version + '\n')   # 4 space indentation
                        for info in history_info:
                            if info: f_write.write(' '*16 + info + '\n')    # 8 space indentation
                    f_write.write(' '*4 +'-'*100+'\n')
                f_write.write('\n')
        # case info: (version name, pass or fail, fail info)
        # results: [(batch name, [(case name, [case info, history case info1, ...]), (case name, (case info, ...)), ... ]), (batch name, ...)]
        results = self._load_file_rav(file_rav)
        with open(file_auto, 'w') as f_auto:
            with open(file_remove, 'w') as f_remove:
                for batch_name, batch_result in results:
                    if not batch_result:
                        f_auto.write(batch_name + '\n\n')
                    else:
                        remain_batch_result = []
                        remove_batch_result = []
                        for case_name, case_result in batch_result:
                            if self._same_fail_as_tot_or_platform_issue(case_result):
                                remove_batch_result.append((case_name, case_result))
                            else:
                                remain_batch_result.append((case_name, case_result))
                        _write_batch_result(batch_name, remain_batch_result, f_auto)
                        _write_batch_result(batch_name, remove_batch_result, f_remove)

    def analyse_file(self, filename):
        '''retrieve fail/fatal/crash cases as well as pass cases, save the result to a file'''
        result_fail = []    # format: [['FAIL', '*.txt', ['info1', 'info2']], ['FATAL', '*.txt', ['info1', 'info2']], ...]
        result_pass = []    # format: [['PASS', '*.txt'], ['PASS', '*.txt'], ...]
        result_other = []
        with open(filename, 'r') as f:
            for line in f:
                if line.strip():
                    m = re.search(r'^(\d{5})###(\w+)###.*###(\d{5}_.*)(_\d{8}-\d{2}-.*.html)', line.strip())
                    if m:
                        keyword, script, result_html = m.group(2), m.group(3)+'.txt', m.group(3)+m.group(4)
                        if keyword == 'PASS':
                            result_pass.append([keyword, script])
                        elif keyword in ['FAIL', 'FATAL', 'CRASH']:
                            fail_info = self.analyse_html(os.path.join(os.path.dirname(filename), result_html), keyword)
                            result_fail.append([keyword, script, fail_info])
                        else: # missing resource or others
                            result_other.append([keyword, script])
        # put pass case to the bottom together
        # format: [[fail1, fail2, ...], [other1, other2, ...], [pass1, pass2, ...]]
        return [result_fail, result_other, result_pass]

    def _remove_html_tag(self, html, is_limit = False):
        line = re.sub(r'\s\s+', ' ', html.strip())
        line = re.sub(r'</?\w+[^>]*>', '', line)
        if is_limit:
            line = line if len(line) < 300 else line[:300].rstrip()  # limit the line length to 300 chars
        return line

    def analyse_html(self, html_file, keyword = 'FAIL'):
        save_line_num = 2
        first_assert_fail_line = 0
        fail_info_lines = []
        fail_lines = []
        try:
            with open(html_file, 'r') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    if keyword == 'CRASH':
                        if not first_assert_fail_line and line.find('Assert Fail:') >= 0:
                            first_assert_fail_line = i
                        elif first_assert_fail_line and (line.find('CRASH:') >= 0 or (i - first_assert_fail_line) > 10):
                            # find lines between 'Assert Fail:' and 'CRASH:', at most 10 lines
                            return [self._remove_html_tag(h, is_limit = True) for h in lines[first_assert_fail_line:i+1]]
                    elif line.find('FAIL:') >= 0 and line.find('The test ran to completion') < 0:       # keyword is 'FAIL' or 'FATAL'
                        fail_info_lines += range(max(0, i-save_line_num+1), i+1)  # all fail lines will be reported
                        fail_lines.append(i)
                fail_info_lines = list(set(fail_info_lines))
                # if fail info too long ( > 6 lines), only report the fail line ( max 10 lines reported)
                if len(fail_info_lines) > 6: fail_info_lines = fail_lines if len(fail_lines) <= 10 else (fail_lines[:5] + fail_lines[-5:])
                fail_info_lines.sort()
                return [self._remove_html_tag(lines[h], is_limit = True) for h in fail_info_lines]
        except:
            return []

    def generate_batch(self, err_file, batch_dir = ''):
        '''generate batch file include error cases got from the result file'''
        if not batch_dir: batch_dir = self.batch_path
        err_file_path = os.path.dirname(err_file)
        gen_batch_files = {}
        buffer_batch_file = None    # file name
        f_write = None              # file handle
        gen_batch_file = None
        with open(err_file, 'r') as f:
            for line in f:
                if line.strip():
                    # find batch file name, compatible for old version generate *.raw_results while new version generate *.html
                    s_batch = re.search(r'0000[01].*_(batch.*)_\d{8}-\d{2}-.*.(raw_results|html)', line.strip())
                    # find error script name
                    s_script = re.search(r'(FAIL|FATAL|CRASH) : ((\d{5})_.*.txt)', line.strip())
                    if s_batch:
                        buffer_batch_file = s_batch.group(1)+'.txt'

                        if f_write:     # actually write a batch file
                            f_write.write('\ntests_stop\n')
                            f_write.close()            # close the last opened file
                            f_write = None
                    elif s_script and (buffer_batch_file or f_write):
                        if buffer_batch_file and not f_write:
                            batch_file = os.path.join(batch_dir, buffer_batch_file)
                            gen_batch_file = os.path.join(err_file_path, 'aTest_err_'+buffer_batch_file)
                            gen_batch_files[gen_batch_file] = []
                            buffer_batch_file = None

                            f_write = open(gen_batch_file, 'w')
                            with open(batch_file, 'r') as bf:
                                for line in bf:
                                    f_write.write(line)
                                    if line.find('tests_start') >= 0:
                                        f_write.write('\n## error script\n\n')
                                        break
                        f_write.write(s_script.group(2)+'\n')
                        gen_batch_files[gen_batch_file].append(s_script.group(3))
        if f_write:
            f_write.write('\ntests_stop\n')
            f_write.close()
        return gen_batch_files

    def _gen_rav_case_cache_product(self, product):
        rav_cases = self._get_rav_cases(product)
        with open(os.path.join(self.rav_cache_path, '%s_rav_cases_cache.txt' % product), 'w') as f_write:
            f_write.write('# total %d cases\n' % len(rav_cases))
            for rav_case in rav_cases:
                f_write.write(rav_case + '\n')

    def gen_rav_case_cache(self):
        self.print_('start gen rav cases cache...')
        rav_case_product = ['mue_fdd', 'mue_tdd', 'cue_fdd', 'cue_tdd', 'sue_fdd', 'sue_tdd']
        for product in rav_case_product:
            self._gen_rav_case_cache_product(product)
        self.print_('gen rav cases cache successfully!')

    def get_case_product(self, case):
        rav_case_product = ['mue_fdd', 'mue_tdd', 'cue_fdd', 'cue_tdd', 'sue_fdd', 'sue_tdd']
        rav_cases_cache_file = [(product, os.path.join(self.rav_cache_path, '%s_rav_cases_cache.txt' % product)) for product in rav_case_product]
        for product, cache_file in rav_cases_cache_file:
            if not os.path.isfile(cache_file):
                self._gen_rav_case_cache_product(product)
            cases = open(cache_file, 'r').read()
            if case in cases: return product
        return None

    def explorer_case(self, case):
        product = self.get_case_product(case)
        if not product:
            self.print_('can not find case %s' % case)
        else:
            url = self.rav_url_product_search[product] + case
            #try:
            #    html = urllib2.urlopen(url, timeout = 3)
            #except Exception as e:
            #    raise CmdException('open RAV page error! "%s", %s' % (url, e))
            #if not os.path.isdir(self.temp_path): WinCmd.make_dir(self.temp_path)
            #temp_html_file = os.path.join(self.temp_path, 'temp.html')
            #open(temp_html_file, 'wb').write(html.read())
            #WinCmd.explorer(temp_html_file)
            WinCmd.cmd(r'explorer "%s"' % url)

    def _get_batch_files(self, batch_dir = '', except_batches = [], select_batches = []):
        if not batch_dir: batch_dir = self.batch_path
        except_batches = [os.path.splitext(b)[0].lower() for b in except_batches]
        except_batches += ['fail', 'manf_plat']  # do not find case in fail batch and remove 'batch_manf_plat_c.txt'
        select_batches = [os.path.splitext(b)[0].lower() for b in select_batches]
        search_files = []
        for search_file in glob(os.path.join(batch_dir, 'batch_*.txt')):
            filename = os.path.splitext(os.path.basename(search_file))[0].lower()
            should_except_this_batch = False
            for except_batch in except_batches:
                #if filename.find(except_batch) >= 0:
                if re.search(except_batch, filename):  # use regular expression
                    should_except_this_batch = True
                    break
            if not should_except_this_batch:
                for select_batch in select_batches:
                    #if not filename.find(select_batch) >= 0:
                    if not re.search(select_batch, filename):  # use regular expression
                        should_except_this_batch = True
                        break
            if should_except_this_batch: continue
            if filename.find('normal') >= 0:
                search_files.insert(0, search_file)     # normal batch file search first
            else:
                search_files.append(search_file)
        return search_files

    def gen_batch_from_cases(self, cases, dest_path, batch_dir = '', except_batches = [], select_batches = [], not_change_batch = False):
        remain_cases = set([str(case) for case in cases])   # integer to string
        if not remain_cases: return []
        gen_batch_files = {}
        all_found_cases = []
        cases_info = {}  # each case: all the batches this case lies in
        for filename in self._get_batch_files(batch_dir, except_batches, select_batches):
            found_cases_in_this_file = []
            file_buffer = ''
            with open(filename, 'r') as f:
                select_batch = False
                for line in f:
                    if not select_batch:
                        file_buffer += line
                        if line.find('tests_start') >= 0:
                            file_buffer += '\n## error script\n\n'
                            select_batch = True
                    elif line.find('tests_stop') >= 0:
                        break
                    else:
                        if remain_cases:
                            s_batch = re.search(r'^(%s)_.*\.txt' % '|'.join(remain_cases), line.strip().lower())
                            if s_batch:
                                file_buffer += line
                                case_num = s_batch.group(1)
                                remain_cases.remove(case_num)  # remove current case
                                found_cases_in_this_file.append(case_num)
                                cases_info[case_num] = [os.path.basename(filename)]
                        if all_found_cases:
                            s_batch = re.search(r'^(%s)_.*\.txt' % '|'.join(all_found_cases), line.strip().lower())
                            if s_batch:
                                case_num = s_batch.group(1)
                                cases_info[case_num].append(os.path.basename(filename))
                file_buffer += '\ntests_stop\n'
            all_found_cases += found_cases_in_this_file
            if found_cases_in_this_file:
                gen_batch_file = os.path.join(dest_path, 'aTest_err_'+os.path.basename(filename))
                if not_change_batch:
                    WinCmd.copy_file(filename, gen_batch_file, dest_is_dir = False)
                else:
                    with open(gen_batch_file, 'w') as f_write:
                        f_write.write(file_buffer)
                gen_batch_files[gen_batch_file] = found_cases_in_this_file
            #if not remain_cases: break   # all cases have been generated
        return (gen_batch_files, remain_cases, cases_info)

    def gen_run_bat(self, batch_files):
        ''' generate bat file for the auto-generated batch files'''
        if batch_files:
            batch_file_path = os.path.dirname(batch_files[0])
            run_bat_f = os.path.join(batch_file_path, 'aTest_err.bat')
            with open(run_bat_f, 'w') as f:
                # prepare the environment
                f.write(r'set bat_dir=%cd%' + '\n\n')
                f.write(r'copy /Y aTest_err_*.txt C:\AUTO_TEST\Testing\batch' + '\n\n')
                f.write(r'cd /d C:\AUTO_TEST\Testing\python' + '\n\n')
                f.write('@REM call ttm_runner.py batch_fum.txt\n')
                for batch_file in batch_files:
                    f.write('call ttm_runner.py '+os.path.basename(batch_file)+'\n')
                f.write('\n' + r'cd /d %bat_dir%' + '\n')
            return run_bat_f
        else:
            return ''

    def compare_result(self, result_file, base_file):
        '''compare result file to the base file, find the case that failed in result file but succeeded in base file'''
        write_file_name = '%s_gen_fail%s' % os.path.splitext(result_file)
        f_write = open(write_file_name, 'w')
        write_info = False

        with open(base_file, 'r') as b:
            with open(result_file, 'r') as f:
                base_lines = b.read()
                for line in f:
                    if not line.strip():
                        f_write.write(line.strip() + '\n')
                    elif line.find('.raw_results') >= 0:
                        f_write.write(line.rstrip() + '\n')
                    else:
                        # find error script name
                        s_script = re.search(r'(FAIL|FATAL|CRASH) : (\d{5}_.*.txt)', line.rstrip())
                        if s_script:
                            write_info = False
                            fail_script = s_script.group(2)
                            # find the fail script in the base file
                            s_base = re.search(r'(FAIL|FATAL|CRASH) : %s' % fail_script, base_lines)
                            if not s_base:
                                f_write.write(line.rstrip() + '\n')
                                write_info = True
                        elif write_info and line.startswith(' '*8):    # fail info is starts with 8 spaces
                            f_write.write(line.rstrip() + '\n')
        if f_write: f_write.close()
        return write_file_name

    def select_batches(self, file):
        batches = []
        with open(file, 'r') as f:
            for line in f:
                s_batch = re.search(r'^[^(REM|@REM|#)].*(batch_.*.[tT][xX][tT])', line.rstrip())
                if s_batch and s_batch.group(1).find('batch_fum.') < 0:
                    batches.append(s_batch.group(1))
        return batches

    def update_cases(self, batches, update_case = False):
        files = []
        for batch in batches:
            folder = os.path.dirname(batch)
            files += [os.path.join(folder, c) for c in self._get_batch_cases(batch)[0] if os.path.isfile(os.path.join(folder, c))]
        if files:
            dest_folder = self.automation_path
            add_files, newer_files, older_files, same_files = [], [], [], []
            for f in files:
                dest_file = os.path.join(dest_folder, os.path.basename(f))
                if not os.path.isfile(dest_file):
                    add_files.append(f)
                elif os.stat(dest_file).st_mtime < os.stat(f).st_mtime:
                    newer_files.append(f)
                elif os.stat(dest_file).st_mtime > os.stat(f).st_mtime:
                    older_files.append(f)
                else:
                    same_files.append(f)
            updated_files = [0, 0, 0]
            if add_files: WinCmd.copy_files(add_files, dest_folder); updated_files[0] = len(add_files)
            if update_case:
                if newer_files: WinCmd.copy_files(newer_files, dest_folder); updated_files[1] = len(newer_files)
                if older_files: WinCmd.copy_files(older_files, dest_folder); updated_files[2] = len(older_files)
                if same_files: self.print_('%d same files, need not update' % len(same_files))
            else:
                if newer_files or older_files: self.print_('[WARNING] %d/%d newer/older files, please check if need update...' % (len(newer_files), len(older_files)))
            if updated_files != [0, 0, 0]:
                self.print_('copy %d/%d/%d (add/newer/older) files to folder %s successfully!' % (updated_files[0], updated_files[1], updated_files[2], dest_folder))

    def _get_batch_cases(self, batch):
        cases = []
        batch_head = []
        with open(batch, 'r') as f:
            start_flag = False
            for line in f:
                line = line.strip()
                if start_flag:
                    if not line or line.startswith('#'): continue
                    if line.startswith('tests_stop'): start_flag = False
                    elif not line.lower().endswith('txt'): raise CmdException('case error: %s, in batch %s' % (line, batch))
                    else: cases.append(line)
                else:
                    batch_head.append(line)
                    if line.startswith('tests_start'): start_flag = True
        return cases, batch_head

    def copy_case_from_automation(self, cases, dest_folder):
        if not isinstance(cases, list): cases = [cases]
        files = self.get_re_files([os.path.join(self.automation_path, r'%s^%s_.*\.txt' % (self.re_delimiters[0], case)) for case in cases])
        if files:
            WinCmd.copy_files(files, dest_folder)
            out_files = [os.path.join(dest_folder, os.path.basename(f)) for f in files]
        else:
            out_files = []
        self.print_('copy %d files to folder %s successfully!' % (len(files), dest_folder))
        return out_files

    def copy_case_to_automation(self, folder, file_patterns):
        if not isinstance(file_patterns, list): file_patterns = [file_patterns]
        files = [] if file_patterns[0] == 'none' else self.get_re_files([os.path.join(folder, pattern) for pattern in file_patterns])
        dest_folder = self.automation_path
        if files: WinCmd.copy_files(files, dest_folder)
        self.print_('copy %d files to folder %s successfully!' % (len(files), dest_folder))

    def modify_case(self, case_file, content = 'assert', pos_include_ulan = True):
        tma_logs_folder = os.path.join(os.path.dirname(os.path.abspath(case_file)), 'tmalogs')
        _manual_crash_lines = ['mci.wait(1)', 'mci.run_command("forw l1 l0gencmd32 1 0xffffffff 0")', 'mci.run_command("forw l1 forceassert 1")']
        _tma_wait_lines = ['mci.run_command(r\'#$$DATA_LOG_FOLDER 1 "%s"\')' % tma_logs_folder, 'mci.wait(300)']
        content_map = {'assert': _manual_crash_lines, 'tma': _tma_wait_lines}
        if not content in content_map.keys(): raise CmdException('there is no content found! content: %s' % content)
        if content == 'tma': WinCmd.make_dir(tma_logs_folder)
        add_lines = [line + '\n' for line in content_map[content]]
        add_front_lines = ['mci.wait(20)'] if content == 'tma' else []
        case_file = os.path.abspath(case_file)
        gen_file = os.path.join(os.path.dirname(case_file), '00_' + os.path.basename(case_file))
        with open(case_file, 'r') as f:
            lines = []
            temp_lines = []
            delete_found = False
            for line in f:
                temp_lines.append(line)
                if not delete_found and re.search(r'delete', line.lower()): delete_found = True
                if not delete_found:
                    # include ulan: add script right before the first delete operation
                    # not include ulan: add script after the Activate command before the delete operation
                    if (pos_include_ulan and not line.startswith('###')) or re.search(r'activate', line.lower()):
                        lines += temp_lines
                        temp_lines = []
            lines += ['\n################### add for temporary test ###############\n\n']
            lines += add_lines + ['\n####################################################\n\n']
            lines += temp_lines
        # add wait in front, before pxi load, to enable TMA log start
        if add_front_lines:
            total_lines = lines
            lines = []
            temp_lines = []
            first_pxi_found = False
            for line in total_lines:
                temp_lines.append(line)
                if not first_pxi_found and re.search(r'pxi', line.lower()): first_pxi_found = True
                if not first_pxi_found:
                    lines += temp_lines
                    temp_lines = []
            lines += ['\n################### add for temporary test ###############\n\n']
            lines += add_front_lines + ['\n####################################################\n\n']
            lines += temp_lines
        with open(gen_file, 'w') as f_write:
            for line in lines:
                f_write.write(line)
        return gen_file

    def modify_batch(self, batches, content = 'none', param = True, modify_case = False):
        def _tdd(data, param = True):
            if param:
                data = data.replace('func_begining_of_test_start', 'func_begining_of_test_start\nmci.run_command("forw mte PHYSETRATTYPE 1")')
                data = data.replace('func_reset_start', 'func_reset_start\nmci.run_command("forw mte PHYSETRATTYPE 1")')
            else:
                data = data.replace('mci.run_command("forw mte PHYSETRATTYPE 1")\n', '')
            return data
        def _tma(data, param = True):
            if param:  # TMA , should be proxy_yes
                data = data.replace('proxy_no', 'proxy_yes')
            else:
                data = data.replace('proxy_yes', 'proxy_no')
            return data
        def _case(data):
            if re.search(r'^\d{5}_.*\.txt', data) > 0:
                data = '##%s00_%s' % (data, data)
            return data
        def _remove_case(data):
            if data.find('tests_start') >= 0:
                data += '\n## error script\n\n'
            elif re.search(r'^\d{5}_.*\.txt', data) > 0:
                data = ''
            return data

        changed_batches = []
        for batch in batches:
            try:
                lines = open(batch, 'r').readlines()
                with open(batch, 'w') as f:
                    for line in lines:
                        if content == 'tma': line = _tma(line, param)
                        elif content == 'tdd': line = _tdd(line, param)
                        elif content == 'remove_case': line = _remove_case(line)
                        if modify_case: line = _case(line)
                        f.write(line)
                    changed_batches.append(batch)
            except Exception as e:
                self.print_('Error modify file %s: %s' % (batch, e))
        return changed_batches

    def _check_product(self, product):
        # product: [ue]_[pro]_[rat], example: sue_4x2_fdd, mue_5c_tdd, cue_ls2_fdd, etc.
        ues = ['sue', 'mue', 'cue']
        rats = ['fdd', 'tdd']
        products = {'sue': ['4x2', '4x4', '4x2_ulmimo', 'sue2'],
                    'mue': ['2x2', '2x2_split_dl', 'mue2'],
                    'cue': ['extmue', 'loadsys_split_dl', 'ls2_dl', 'ls2']
                    }
        # wangsl???
        pass

    # version: K4.6.4REV50 or K_04_06_04_REV50 or LTE-CUE-LS2_L1L2_LME_3_3_2_REV50 or LTE-SUE-2X2-LSA_L1_01_00_00_REV01
    #          or LTE-MUE-C0309_TDD_5C_L1_14_10_09_17_05_04 ( temporary binary)
    def get_ver_label(self, version, explicit_pro = '', force_temp_binary = False):
        label = None
        search_multi_folders = False
        if os.path.isdir(version):
            # \\stv-nas.aeroflex.corp\LTE_Results_Builds\Release_Candidates\LTE\FDD\MUE\LTE-MUE-C0309_5C_L1_15_12_11_19_46_13
            folders = [version]
            rav_path, version = os.path.split(version)
            label = version
        else:
            if force_temp_binary:
                v = None
            else:
                v_real = re.search(r'^(?:.*_)?([^_\d]+)(\d+)\.(\d+)\.(\d+)[Rr][Ee][Vv](\d+)$', version)  # K4.6.4REV50
                v = v_real or re.search(r'^(?:.*[_-])?([^_\d]+)_(?:L1_)?(\d+)_(\d+)_(\d+)(_[Rr]|$)', version)  # LTE-CUE-LS2_L1L2_LME_3_3_2_REV50 or LTE-CUE-LS2_L1L2_LME_3_3_2
                v = v or re.search(r'^(?:.*_)?([^_\d]+)(\d+)\.(\d+)\.(\d+)$', version) # K4.6.4
            if v:  # a real version , has label
                pro = v.group(1).lower()
                product_ver = {'k': 'sue_all_tdd', 'c': 'sue_all_fdd', 's': 'mue_all_tdd', 'v': 'mue_all_fdd', 'lsa': 'sue_all', 'lsb': 'sue_all', 'ldc': 'mue_all', 'lde': 'mue_all'}
                if pro in product_ver:
                    product = product_ver[pro]
                else:
                    product = 'cue_all'
                rav_path, not_used = self._get_rav_path(product)
                v_real = v_real or re.search(r'^(?:.*[_-])?([^_\d]+)_(?:L1_)?(\d+)_(\d+)_(\d+)_[Rr][Ee][Vv](\d+)$', version)
                if v_real:
                    ver_str = r'_0?%d_0?%d_0?%d_rev0?%d(\D|$)' % tuple([int(v_real.group(i)) for i in [2,3,4,5]])
                else: # search for all real versions
                    ver_str = r'_0?%d_0?%d_0?%d(\D|$)' % tuple([int(v.group(i)) for i in [2,3,4]])
                    search_multi_folders = True
                folders = [os.path.join(rav_path, x) for x in os.listdir(rav_path) if re.search(ver_str, x.lower())]
                if len(folders) > 1 and (not search_multi_folders or not explicit_pro):
                    folders = [f for f in folders if os.path.split(f)[-1].lower().find(pro) >= 0]
            else: # temporary binary
                v = re.search(r'^LTE-([SMC]UE)-', version)
                rat = 'tdd' if version.lower().find('tdd') > 0 else 'fdd'
                if not explicit_pro:
                    if not v: raise CmdException('cannot detect product(SUE/MUE/CUE) from %s, try to use -p to specify.' % version)
                    pro = v.group(1).lower()
                else:
                    if v and v.group(1).lower() != explicit_pro.lower(): raise CmdException('invalid version: %s with specified product %s' % (version, explicit_pro))
                    pro = explicit_pro.lower()
                if pro == 'cue':
                    product = 'cue_all'
                elif pro == 'sue' and (version.lower().find('lsa') > 0 or version.lower().find('lsb') > 0):
                    product = 'sue_all'
                elif pro == 'mue' and (version.lower().find('ldc') > 0 or version.lower().find('lde') > 0):
                    product = 'mue_all'
                else:
                    product = '%s_all_%s' % (pro, rat)
                rav_path, not_used = self._get_rav_path(product)
                folders = [os.path.join(rav_path, version)]
                WinCmd.check_folder_exist(folders[0])
                self.print_('it should be a temporary binary.')
                label = version
        if not folders: raise CmdException('cannot find version(%s): %s' % (version, ver_str))
        for folder in folders:
            self.print_('find folders: %s' % folder)
        if search_multi_folders:
            folders = [max(folders)]
            self.print_('choose folders: %s' % folders[0])
        if len(folders) > 1: raise CmdException('find %d folders, more than 1' % len(folders))
        if not label:
            label_file = os.path.join(folders[0], 'labeling.txt')
            WinCmd.check_file_exist(label_file)
            lines = open(label_file, 'r').readlines()
            label_r = re.search(r'label\s+\b([-\w]*)\b', lines[0].strip())
            if not label_r: raise CmdException('cannot find label in file %s' % label_file)
            label = label_r.group(1)
        return (label, folders[0])

    def _get_rav_path(self, product):
        ue = product.split('_')[0]
        pro = None
        if ue == 'sue':
            product = product.replace('_ulmimo', '')            # in case of 'sue_4x2_ulmimo_tdd' or 'sue_4x2_ulmimo_fdd'
            if product == 'sue_all':
                #rav_path = os.path.join(self.rav_path, 'SUE_COMBINED')
                rav_path = os.path.join(self.rav_path, 'SUE')
            else:
                pro, rat = product.split('_')[1:]
                rav_path = os.path.join(self.rav_path, rat, ue)
        elif ue == 'mue':
            #if True: # always enable MUE combined
            if product == 'mue_all':
                #rav_path = os.path.join(self.rav_path, 'MUE_COMBINED')
                rav_path = os.path.join(self.rav_path, 'MUE')
            else:
                pro_1, rat = product.split('_')[1:]
                if pro_1 == '2x2' or pro_1 == '8c': pro = '_8c_'
                elif pro_1 == '2x2splitdl' or pro_1 == '5c': pro = '_5c_'
                rav_path = os.path.join(self.rav_path, rat, ue)
        else:
            #rav_path = os.path.join(self.rav_path, 'LTE_CUE_COMBINED')
            rav_path = os.path.join(self.rav_path, 'CUE')
        WinCmd.check_folder_exist(rav_path)
        return (rav_path, pro)

    def _get_rav_search_folders(self, product, search_max_folder, except_folder):
        ue = product.split('_')[0]
        if ue == 'cue':
            return self._get_rav_search_folders_from_net(product, search_max_folder, except_folder)
        else:
            rav_path, pro = self._get_rav_path(product)
            if not pro: return self._get_rav_search_folders_from_net(product, search_max_folder, except_folder)
            folders = [(os.path.getmtime(os.path.join(rav_path, x)), os.path.join(rav_path, x)) for x in os.listdir(rav_path)]
            folders.sort(reverse = True)
            folders = [folder for t, folder in folders]
            search_folders = []
            folders_num = 0
            for folder in folders:
                if os.path.basename(folder).lower().find(pro) >= 0:
                    results_folder = os.path.join(folder, 'results')
                    if except_folder and WinCmd.is_subfolder(except_folder, results_folder):
                        self.debug_print('exclude search folders in %s' % results_folder)
                        continue   # do not include the analysed folder itself
                    try:
                        f = [os.path.join(results_folder, x) for x in os.listdir(results_folder) if os.path.isdir(os.path.join(results_folder, x)) and x.startswith('RAV')]
                    except:
                        continue
                    if f: folders_num += 1
                    search_folders += f
                    if folders_num >= search_max_folder: break
            return (folders_num, search_folders)

    def _get_rav_search_folders_from_net(self, product, search_max_folder, except_folder):
        folders = self._get_search_folders(product)
        results_folders = set()
        search_folders = []
        for folder in folders:
            results_folder = os.path.dirname(folder)
            if except_folder and WinCmd.is_subfolder(except_folder, results_folder):
                self.debug_print('exclude search folders in %s' % results_folder)
                continue   # do not include the analysed folder itself
            results_folders.add(results_folder)
            search_folders.append(folder)
            if len(results_folders) >= search_max_folder: break
        return (len(results_folders), search_folders)

    def gen_rav_search_folders(self, product = 'sue_4x2_fdd', search_max_folder = 20, except_folder = None, re_gen_search_folder = False):
        self.print_('start gen search folders...')
        product = product.lower()
        folders_num, search_folders = self._get_rav_search_folders(product, search_max_folder, except_folder)
        rav_cache_path = os.path.join(self.rav_cache_path, product)
        if re_gen_search_folder or not os.path.isdir(rav_cache_path): WinCmd.del_dir(rav_cache_path)
        exclude_search_folders = []
        for search_folder in search_folders:
            cache_file = os.path.join(rav_cache_path, os.path.basename(search_folder)+'.txt')
            if not os.path.isfile(cache_file):
                files = [file for file in os.listdir(search_folder) if '1'<=file[0]<='9' and file.endswith('.html')]  # do not use 0xxxx_.*.html, it's the batch
                if not files: exclude_search_folders.append(search_folder)
                with open(cache_file, 'w') as f:
                    for file in files:
                        f.write(file + '\n')
        for exclude_folder in exclude_search_folders:
            search_folders.remove(exclude_folder)
            self.debug_print('exclude empty folder: %s' % exclude_folder)
        for search_folder in search_folders:
            self.debug_print('search folder: %s' % search_folder)
        self.debug_print('search folders %d, subfolders %d.' % (folders_num, len(search_folders)))
        self.print_('gen search folders successfully!')
        return (rav_cache_path, search_folders)

    def search_case_on_rav(self, case, rav_cache_path, search_folders, max_rav_case_history = 5):
        search_result = []
        for search_folder in search_folders:
            result = self._search_case(case, rav_cache_path, search_folder)
            if result[1] != 'NA': search_result.append(result)  # remove 'NA' search result
            if max_rav_case_history and len(search_result) >= max_rav_case_history: break   # max rav case history log, for the readability
        return search_result    #[[folder, 'FAIL', [info1, info2]], [folder, 'PASS', []], ...]

    def _search_case(self, case, rav_cache_path, search_folder):
        keyword, fail_info = 'NA', []
        folder = os.path.basename(os.path.dirname(os.path.dirname(search_folder)))
        # search from cache file
        cache_file = os.path.join(rav_cache_path, os.path.basename(search_folder)+'.txt')
        with open(cache_file, 'r') as f_cache:
            for line in f_cache:
                file = line.strip()
                if file.startswith(case):   # found
                    # retrieve the keyword
                    filename = os.path.join(search_folder, file)
                    f = open(filename, 'r')
                    try:
                        f.seek(-1000, os.SEEK_END)
                        lines = f.read(1000).split('\n')
                    except:
                        lines = f.readlines()
                    for i, line in enumerate(lines[::-1]):
                        if i >= 10: break    # max search for 10 last lines
                        s_keyword = re.search(r'\d{2}:\d{2}:\d{2}\.\d{4}\s(PASS|FAIL|FATAL|CRASH):', line.rstrip())
                        if s_keyword: break
                    keyword = 'OTHER'
                    if s_keyword:
                        keyword = s_keyword.group(1)
                        if keyword in ['FAIL', 'FATAL', 'CRASH']:
                            fail_info = self.analyse_html(os.path.join(filename), keyword)
                    break
        return [folder, keyword, fail_info]  #[folder, 'FAIL', [info1, info2]] or [folder, 'NA', []]

    def gen_hde_case_cache(self):
        self.print_('start generate hde case cache file...')
        if not os.path.isdir(self.rav_cache_path): WinCmd.make_dir(self.rav_cache_path)
        if os.path.isfile(self.hde_case_cache_file):
            bak_file = '%s_bak_%s.dat' % (os.path.splitext(self.hde_case_cache_file)[0], datetime.fromtimestamp(os.stat(self.hde_case_cache_file).st_mtime).strftime('%y%m%d_%H%M%S'))
            if not os.path.isfile(bak_file): WinCmd.rename_files(self.hde_case_cache_file, bak_file)
        with open(self.hde_case_cache_file, 'w') as f_write:
            f_write.write('[Gen Cache file, start time %s]\n' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            for dir_path, subpaths, files in os.walk(self.hde_case_root_path):
                usf_files = [file for file in files if file.endswith('.usf')]
                if usf_files:
                    f_write.write(dir_path + '\n')
                    for usf_file in usf_files:
                        f_write.write(' '*4 + usf_file + '\n')
            f_write.write('[Gen Cache file, end time %s]\n' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        self.print_('generate hde case cache file successfully!')

    def search_hde_vector(self, case, dest_dir):
        if not os.path.isfile(self.hde_case_cache_file): self.gen_hde_case_cache()
        if not os.path.isdir(dest_dir): WinCmd.make_dir(dest_dir)
        add_all_following_file = False
        results = []
        with open(self.hde_case_cache_file, 'r') as f:
            for line in f:
                if line.startswith('\\\\'):
                    case_path = line.strip()
                    add_all_following_file = True if line.find(case) >= 0 else False
                elif line.startswith(' '*4):
                    if add_all_following_file or line.find(case) >= 0:
                        results.append(os.path.join(case_path, line.strip()))
                        WinCmd.copy_file(os.path.join(case_path, line.strip()), dest_dir)
        return results

    def combine_usf(self, output_usf, usf_list = [], usf_path = ''):
        tool = os.path.join(self.tool_path, 'mkusf.py')
        if usf_path:
            usf_list = [os.path.join(usf_path, u) for u in usf_list]
            output_usf = os.path.join(usf_path, output_usf)
        usf_cmd = r'python %s -m -o %s ' % (tool, output_usf)
        for usf in usf_list:
            usf_files = self.get_re_files(usf)
            if len(usf_files) != 1: raise CmdException('found usf files for %s: %d, expect 1' % (usf, len(usf_files)))
            usf_cmd += ' ' + os.path.basename(usf_files[0])
        WinCmd.cmd(usf_cmd)
        return output_usf

    def set_vumbra(self, usf_files, hde_tool_path = ''):
        if not usf_files: raise CmdException('no usf files specified.')
        if not isinstance(usf_files, list): usf_files = list(usf_files)
        for usf_file in usf_files:
            WinCmd.check_file_exist(usf_file)
        vmbra_cmd = 'vumbra.exe'
        hde_kill_cmd = 'hde_kill.exe'
        WinCmd.check_file_exist(os.path.join(hde_tool_path, vmbra_cmd) if hde_tool_path else vmbra_cmd)
        WinCmd.check_file_exist(os.path.join(hde_tool_path, hde_kill_cmd) if hde_tool_path else hde_kill_cmd)

        for index, usf_file in enumerate(usf_files):
            vumbra_file = 'vumbra%s.opts' % ('' if index == 0 else str(index))
            vumbra_file = os.path.join(hde_tool_path, vumbra_file) if hde_tool_path else vumbra_file
            if not os.path.isfile(vumbra_file):
                WinCmd.cmd('%s -n %d %s' % (vmbra_cmd, index, usf_file), hde_tool_path, showcmdwin = True, wait = False)
                time.sleep(0.5)
                WinCmd.cmd('%s vumbra' % hde_kill_cmd, hde_tool_path)
            WinCmd.check_file_exist(vumbra_file)
            data = open(vumbra_file, 'r').read()
            input_string = 'InputVector=string(%s)' % os.path.abspath(usf_file)
            input_string = input_string.replace('\\', '\\\\\\\\')
            if re.search(r'InputVector=string', data):
                data = re.sub(r'InputVector=string\(.*\)', input_string, data)
            else:
                data += input_string + '\n'
            open(vumbra_file, 'w').write(data)

    def find_traceviewer_path(self, html_file):
        def _find_traceviewer_path(folder):
            parent_folder = os.path.dirname(folder)
            if parent_folder == folder or not parent_folder: return ''
            target_folder = os.path.join(folder, 'traceviewer')
            if os.path.isdir(target_folder): return target_folder
            return _find_traceviewer_path(parent_folder)
        return _find_traceviewer_path(os.path.dirname(html_file))

    def get_trc_file_from_html(self, html_file):
        # <h2>23:49:24.3740 <a href = 'dump_17-2348.trc'>23:49:24.3740 Dump Trace File: dump_17-2348.trc</a></h2>
        content = open(html_file, 'r').read()
        s = re.search(r"<a href\s*=\s*'([^>]*\.trc)'>[^<]+</a>", content)
        trc_file = os.path.join(os.path.dirname(html_file), s.group(1)) if s else ''
        return trc_file

    def get_case_file_from_html(self, html_file):
        # <h1><a href = '83004_3GPP_20MHz_PRACH-Config-52_Frmt-4_RootSI-79_Ncs-6_Preamble-Idx-4_TDD-CFG-0_8.txt'>Test: 83004_3GPP_20MHz_PRACH-Config-52_Frmt-4_RootSI-79_Ncs-6_Preamble-Idx-4_TDD-CFG-0_8.txt</a></h1>
        content = open(html_file, 'r').read()
        s = re.search(r"<h1><a href\s*=\s*'([^>\.]+.txt)'>Test:\s*[^>\.]+.txt</a></h1>", content)
        case_file = os.path.join(os.path.dirname(html_file), s.group(1)) if s else ''
        return case_file

    def gen_script_from_html(self, html_file, script_file = '', first_dcch_msg_after_switch_vector = False):
        def _parse_load_vector(line):
            ### NR5G
            # USRP_SYSTEM : USRP [0], SERVER [0], antenna [0] >>> e:\pxi_tv\lte_enb_0_cell_0_msg2_msg4_mo_sig_b1.dat Load OK
            # USRP_SYSTEM : USRP [1], SERVER [1], antenna [0] >>> c:\rav99-2_auto_test\teamcityrav\vectors\98853_nr_msg2_ulgrant_ant0.dat Load OK
            s = re.search(r'USRP_SYSTEM\s*:.*\\([^\\\.]+\.dat).*', line)  # vector
            if s:
                total_line, aiq_file = s.group(0), s.group(1)
                return [total_line, aiq_file, '']
            ### LTE
            # PXI: Loading test vector, filename: E:\PXI_TV\LTE_MUE_32637_ant0.aiq, Carrier frequency: 2140000000, Transmission power: -32
            s = re.search(r'PXI:.*PXI_TV\\(\D*(\d{5})?.*\.aiq).*', line)  # vector
            if s:
                total_line, aiq_file, vec_number = s.group(0), s.group(1), s.group(2)
                return [total_line, aiq_file, vec_number]
            # SIG GEN: pxi_slave.S[2] .[0] [ LTEA40114_Cell13_3020] 07/02/2012 12:31:02 19661.146Kb -20 dBm 2155.0000 MHz
            # SIG GEN: pxi.S[0]M .[0] [ LTEA40114_Cell1_3020] 07/02/2012 12:29:35 19661.146Kb -20 dBm 2125.0000 MHz
            # SIG GEN: pxi.S[1] .[0] [ LTEA40114_Cell1_3020] 07/02/2012 12:29:35 19661.146Kb -20 dBm 2125.0000 MHz
            s = re.search(r'SIG GEN: *pxi(_[\d\w]+)?\.S\[(\d)\](M)? *\.\[(\d)\] *\[ *(\D*(\d{5}).*)\].*', line)
            if s:
                total_line, pxi_ant, vector_index, aiq_file, vec_number = s.group(0), s.group(2), s.group(4), s.group(5)+'.aiq', s.group(6)
                return [total_line, aiq_file, vec_number]
            # SIG GEN: pxi_3.S[0] .[0] [LTE_eNB_13_Cell_132_Msg2_Msg4_MO_Sig_B1_Ant0] 26/07/2014 02:25:30 80 TTI -20 dBm 2120.0000 MHz
            # SIG GEN: pxi_3.S[0] .[1] [ Cell_132_RLC_AM_32UE_DL_Ant0] 19/08/2015 15:27:01 640 TTI -20 dBm 2120.0000 MHz
            # SIG GEN: pxi_3.S[1] .[0] [LTE_eNB_13_Cell_132_Msg2_Msg4_MO_Sig_B1_Ant1] 26/07/2014 02:25:33 80 TTI -20 dBm 2120.0000 MHz
            # SIG GEN: pxi_3.S[1] .[1] [ Cell_132_RLC_AM_32UE_DL_Ant1] 19/08/2015 15:27:32 640 TTI -20 dBm 2120.0000 MHz
            s = re.search(r'SIG GEN: *pxi(_[\d\w]+)?\.S\[(\d)\](M)? *\.\[(\d)\] *\[ *([_\w\d]+)\].*', line)
            if s:
                total_line, pxi_ant, vector_index, aiq_file = s.group(0), s.group(2), s.group(4), s.group(5)+'.aiq'
                return [total_line, aiq_file, '']
            return []
        def _parse_switch_vector(line):
            ## NR5G
            # USRP_SYSTEM : All USRPs [[0, 1]] Change TV vector_number: 0  delay: 1.78 TV length 0.08 secs
            # USRP_SYSTEM : USRP [0] SERVER [0] antenna (0,1) Change TV num: 1  delay: 0 TV 0.0133333333333 secs
            # USRP_SYSTEM : This siggen 0 is grouped with [0, 1] , group id 0, therfore all siggens were sync to  tv number 1
            s = re.search(r'USRP_SYSTEM\s*:.*?USRP\s*\[(\d)\].*Change TV\D+(\d)\s.*', line)  # vector
            if s:
                total_line, pxi_ant, vector_index = s.group(0), s.group(1), s.group(2)
                return [total_line, pxi_ant, vector_index]
            ## LTE
            # SIG GEN: pxi.S[0]: TV changed to [1] LTEA40056_Cell1_1CC_3020
            # SIG GEN: pxi_slave.S[2]: TV changed to [0] LTEA40114_Cell13_3020
            s = re.search(r'SIG GEN: *pxi(_slave)?.S\[(\d)\]: *TV changed to *\[(\d)\].*', line)  # vector
            if s:
                total_line, pxi_ant, vector_index = s.group(0), s.group(2), s.group(3)
                return [total_line, pxi_ant, vector_index]
            # PXI: PASS: Siggen 1 switched to channel 0.
            s = re.search(r'PXI:\s*PASS:\s*Siggen (\d) switched to channel (\d)', line)
            if s:
                total_line, pxi_ant, vector_index = s.group(0), str(int(s.group(1))-1), s.group(2)
                return [total_line, pxi_ant, vector_index]
            return []
        def _parse_wait_cmd(line):
            s = re.search(r'Waiting for (\d+) secs', line)
            return s.group(1) if s else None
        def _parse_wait_ind_cmd(line):
            # Waiting for indication containing 'ACTIVATE IND' in 30 secs
            s = re.search(r'Waiting for indication containing \'([\w\s]+)\' in (\d+) secs', line)
            return [s.group(1), s.group(2)] if s else []
        def _parse_dl_dcch_msg(line):
            def _dataind(msg):
                dataind_msg = ' '.join([msg[2*i:2*i+2] for i in range(len(msg)/2)])
                return 'FORW RRC DATAIND 0 1 01 %s' % dataind_msg
            # MCI : I: CMPI RRC PCO_IND: UE Id 0, DL-DCCH-Message 220B9C00504CD39FE0F4ABD9...
            s = re.search(r'MCI.*DL-DCCH-Message (\w+)\W.*', line)
            return [s.group(0), _dataind(s.group(1))] if s else []
        start_comment = False
        check_first_dcch_msg = False
        vec_numbers = []
        aiq_files = []
        no_vec_aiq_files = []  # such as  Cell_132_RLC_AM_32UE_DL_Ant1
        with open(html_file, 'r') as f:
            f_write = open(script_file, 'w') if script_file else None
            if f_write: f_write.write('###From: %s\n\n' % html_file)
            for line in f:
                line = line.strip()
                pos = line.find('MCI: Running command:')
                if pos > 0:
                    pos = pos + len('MCI: Running command:')
                    command = self._remove_html_tag(line[pos:].strip())
                    if start_comment: command = '#' + command
                    elif command.find('Delete') >= 0 or command.find('Deregister') >= 0 or command.startswith('GUMS') or command.startswith('gsen'):
                        command = '#' + command
                        start_comment = True
                    elif command.lower().find('lcfg dsp ') >= 0 or command.lower().find('lcfg hlc ') >= 0 or command.lower().find('lcfg umb ') >= 0:
                        command = '#' + command
                    elif command.lower().find('activate -1') >= 0:
                        command += '\nwait for "ACTIVATE" timeout 30\n'
                    if f_write: f_write.write(command + '\n')
                    continue
                result = _parse_load_vector(line)
                if result:
                    total_line, aiq_file, vec_number = result
                    if f_write: f_write.write('###' + self._remove_html_tag(total_line) + '\n')
                    if aiq_file and aiq_file not in aiq_files: aiq_files.append(aiq_file)
                    if not vec_number and aiq_file and aiq_file not in no_vec_aiq_files: no_vec_aiq_files.append(aiq_file)
                    if vec_number and vec_number not in vec_numbers: vec_numbers.append(vec_number)
                    continue
                result = _parse_switch_vector(line)
                if result:
                    total_line, pxi_ant, vector_index = result
                    if f_write:
                        f_write.write('\n###' + self._remove_html_tag(total_line) + '\n')
                        f_write.write('#swiv %d %s\n\n' % (0 if pxi_ant == '0' else 1, vector_index))
                    if first_dcch_msg_after_switch_vector: check_first_dcch_msg = True
                    continue
                result = _parse_wait_cmd(line)
                if result:
                    seconds = result
                    if f_write: f_write.write('#wait %s\n' % seconds)
                    continue
                result = _parse_wait_ind_cmd(line)
                if result:
                    ind_cmd, seconds = result
                    command = '#wait for "%s" timeout %s\n' % (ind_cmd, seconds)
                    if start_comment: command = '#' + command
                    if f_write: f_write.write(command + '\n')
                    continue
                if check_first_dcch_msg:
                    result = _parse_dl_dcch_msg(line)
                    if result:
                        total_line, dataind_msg = result
                        if f_write:
                            f_write.write('\n#' + self._remove_html_tag(total_line) + '\n')
                            f_write.write('#%s\n\n' % dataind_msg)
                        check_first_dcch_msg = False
                        continue
            if f_write: f_write.close()
        return vec_numbers, aiq_files, no_vec_aiq_files

    def update_file_to_change_file(self, update_file, change_list_file):
        with open(update_file, 'r') as f:
            with open(change_list_file, 'w') as f_write:
                for line in f:
                    if line.startswith('Updated:'):
                        f_write.write('...\\' + line.split()[1] + '\n')

    def copy_change_files(self, change_list_file):
        dest_dir = os.path.dirname(change_list_file)
        src_dirs, dest_dirs = [], []
        with open(change_list_file, 'r') as f:
            while True:
                src_dir_line = f.readline().strip().split(',')
                src_dir, dest_dir_name = src_dir_line[0], src_dir_line[1] if len(src_dir_line) > 1 else os.path.basename(src_dir_line[0])
                if not src_dir: break
                WinCmd.check_folder_exist(src_dir)
                src_dirs.append(src_dir)
                dest_dirs.append(os.path.join(dest_dir, dest_dir_name))
            for line in f:
                logic_file = line.strip()
                if not logic_file: continue
                if logic_file.find('...') < 0: raise CmdException('line err: do not have ... in %s.' % logic_file)
                for src_dir, dest_dir in zip(src_dirs, dest_dirs):
                    src_file = logic_file.replace('...', src_dir)
                    if os.path.isfile(src_file):
                        dest_path = os.path.dirname(logic_file.replace('...', dest_dir))
                        if not os.path.isdir(dest_path): WinCmd.make_dir(dest_path)
                        WinCmd.copy_file(src_file, dest_path)

    def check_change_files(self, cc_cmd, change_list_file, project_dir = ''):
        with open(change_list_file, 'r') as f:
            if not project_dir: project_dir = f.readline().strip()
            while f.readline().strip(): pass    # until a blank line
            for line in f:
                logic_file = line.strip()
                if not logic_file: continue
                if logic_file.find('...') < 0: raise CmdException('line err: do not have ... in %s.' % logic_file)
                project_file = logic_file.replace('...', project_dir)
                if os.path.isfile(project_file):
                    if cc_cmd == 'checkout': CcTool.checkout(project_file)
                    elif cc_cmd == 'checkin': CcTool.checkin(project_file)
                    elif cc_cmd == 'undo_checkout': CcTool.undo_checkout(project_file)

    def code_check_files(self, file_list, output_file, project_dir = ''):
        with open(file_list, 'r') as f:
            if not project_dir: project_dir = f.readline().strip()
            while f.readline().strip(): pass    # until a blank line
            files = []
            for line in f:
                logic_file = line.strip()
                if not logic_file: continue
                if logic_file.find('...') < 0: raise CmdException('line err: do not have ... in %s.' % logic_file)
                project_file = logic_file.replace('...', project_dir)
                if os.path.isfile(project_file): files.append(project_file)
        if not hasattr(self, 'code_check'): self.code_check = CodeCheck()
        self.code_check.check(files, output_file)

    def _copy_teamcity_folder(self, project_path):
        teamcity_path = os.path.join(project_path, self.teamcity_rel_paths[0])
        teamcity_copy_path = os.path.join(os.path.dirname(teamcity_path), 'teamcity_copy')
        self.print_('copy folder and run: %s...' % teamcity_path)
        WinCmd.copy_dir(teamcity_path, teamcity_copy_path, empty_dest_first = True)
        return teamcity_copy_path

    def teamcity_remote_run(self, project_path, select_batches_key = '', cell_1_batch_one_run = False, rav = '', debug_output = False):
        teamcity_copy_path = self._copy_teamcity_folder(project_path)
        remote_run_tool = os.path.join(teamcity_copy_path, 'remote_run.pyw')
        teamcity_ini_file = os.path.join(os.path.dirname(remote_run_tool), 'settings.ini')
        teamcity_ini = TeamcityIni(teamcity_ini_file)
        if select_batches_key:
            select_keys = []
            for key in select_batches_key:
                if key not in self.sanity_batches_dict.keys(): raise CmdException('invalid select batches %s' % key)
                select_keys.append(key)
        else:
            select_keys = self.sanity_batches_dict.keys()
        runs = []
        config_keys = self.sanity_batches_config.keys()
        config_keys.remove('default')
        for key in config_keys:
            if key in select_keys:
                runs.append((self.sanity_batches_dict[key], self.sanity_batches_config[key]))
                select_keys.remove(key)
        if not cell_1_batch_one_run and 'basic' in select_keys:
            runs.append((self.sanity_batches_dict['basic'], self.sanity_batches_config['default']))
            select_keys.remove('basic')
        if select_keys: runs.append((reduce(list.__add__, [self.sanity_batches_dict[k] for k in select_keys], []), self.sanity_batches_config['default']))
        self.print_('Total %d runs.' % len(runs))
        for i, (run, config) in enumerate(runs):
            self.print_('Start to run %d: (%s) %s ...' % (i+1, config, run))
            batches = [os.path.join(self.sanity_batch_path, r) for r in run]
            teamcity_ini.set_batches(batches, config, rav)
            hook_tool = HookToolCacheManager(remote_run_tool, debug_output = debug_output)
            hook_tool.run()
            #raw_input(r'press any key to continue...')
            self.print_('End submit running %d.' % (i+1))

    def presub(self, project_path, dynamic_view_path, manual = False, debug_output = False):
        temp_file = self.get_temp_filename()
        if os.path.isfile(temp_file): WinCmd.del_file(temp_file)
        WinCmd.cmd('cleartool catcs > %s' % temp_file, project_path, showcmdwin = False, wait = True)
        if not os.path.isfile(temp_file): raise CmdException('cannot export configspec of view: %s' % project_path)
        WinCmd.cmd('cleartool setcs %s' % temp_file, dynamic_view_path, showcmdwin = False, wait = True)
        if manual:
            tool_path, tool_name = os.path.split(self.get_presub(dynamic_view_path))
            WinCmd.cmd(r'python "%s"' % tool_name, tool_path, showcmdwin = False)
        else:
            teamcity_copy_path = self._copy_teamcity_folder(dynamic_view_path)
            presub_tool = os.path.join(teamcity_copy_path, 'presub.pyw')
            hook_tool = HookToolCacheManager(presub_tool, debug_output = debug_output)
            hook_tool.run()

    def obsolete_branches(self, branches, username, days_ago = 200):
        time_now = datetime.now()
        time_delta = timedelta(days = days_ago)
        number = 0
        for b in branches:
            result, time, _, _ = self.check_branch(b, username)
            if not result: continue
            if (time_now - time_delta) > time:
                result = self.obsolete_branch(b)
                if result: number += 1
        self.print_('obsolete %d branches totally!' % number)

    def extract_branches(self, branches_file, username):
        WinCmd.check_file_exist(branches_file)
        branches = []
        with open(branches_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and line.split(':')[0].lower() == username:
                    branches.append(line.split(':')[1])
        return branches

    def check_branch(self, branch, username = ''):
        branch_time_user, reason = CcTool.branch_info(branch)
        result = True
        if not branch_time_user:
            self.print_('FAIL: cannot read branch info, %s: %s' % (branch, str(reason)))
            result = False
            time = None
        else:
            b, time, user, obsoleted = branch_time_user
            assert branch == b and (not username or user == username), 'branch or user name mismatch. %s != %s or %s != %s' % (branch, b, user, username)
            if obsoleted:
                result = False
                self.print_('branch %s already under obsoleted' % branch)
        return result, time, user, obsoleted

    def obsolete_branch(self, branch):
        result, reason = CcTool.obsolete_branch(branch)
        if not result:
            self.print_('FAIL: cannot obsolete branch %s, %s' % (branch, reason))
        else:
            self.print_('obsolete branch %s successfully.' % branch)
        return result

    def set_remote_proxy(self, proxy_enable):
        #remote_proxy = '10.239.145.10:8080'   # use this http proxy in shanghai
        remote_proxy = '10.120.0.111:80'   # use this http proxy in shanghai
        bypass = r'*.extranet.aeroflex.corp;*.aeroflex.corp'
        WinCmd.check_file_exist(self.proxy_tool_file)
        if proxy_enable:
            WinCmd.cmd(r'python "%s" start remote %s %s' % (self.proxy_tool_file, remote_proxy, bypass))
        else:
            WinCmd.cmd(r'python "%s" stop' % self.proxy_tool_file)

    def start_proxy_server(self, port, no_hack = False):
        WinCmd.check_file_exist(self.proxy_tool_file)
        title = 'proxy_server_localhost_%d' % port
        WinCmd.cmd(r'python "%s" start local %d %s' % (self.proxy_tool_file, port, 'nohack' if no_hack else ''), showcmdwin = True, minwin = True, wait = False, retaincmdwin = True, title = title)

    def stop_proxy_server(self):
        WinCmd.cmd(r'taskkill /fi "IMAGENAME eq cmd.exe" /fi "WindowTitle eq Administrator:  proxy_server*" > nul')
        WinCmd.check_file_exist(self.proxy_tool_file)
        WinCmd.cmd(r'python "%s" stop' % self.proxy_tool_file)

    def find_tool_path(self, project_path):
        build_tool_path = [os.path.join(project_path, p) for p in self.rel_build_tool_path if os.path.isdir(os.path.join(project_path, p))]
        if not build_tool_path: raise CmdException('cannot find the build tool path.')
        return build_tool_path[0]

    def start_hde_log(self, project_path, log_path, dsps = []):
        project_name = os.path.basename(project_path)
        log_tool_path = self.find_tool_path(project_path)
        if not os.path.isdir(log_path): raise CmdException('no path found: %s' % log_path)
        titles = []
        for dspno in dsps:
            if dspno.lower() == 'server':
                title = 'hde_log_%s_dsp_%s_%s' % (project_name, dspno, datetime.now().strftime('%y%m%d_%H%M%S'))
                port_num = 25700
            else:
                title = 'hde_log_%s_dsp%s_%s' % (project_name, dspno, datetime.now().strftime('%y%m%d_%H%M%S'))
                # core 0: port_num = 5750 + iDspNum;
                # other core: port_num = 1e4 + 1e3 * iCoreNum + iDspNum + 50;
                if dspno.find('.') < 0: dspno = dspno + '.0'
                dspnum, corenum = [int(x) for x in dspno.split('.')]
                port_num = (5750 + dspnum) if corenum == 0 else (10050 + 1000*corenum + dspnum)
            command = r'loganalyse.exe -i127.0.0.1:%d > %s\%s.txt' % (port_num, log_path, title)
            titles.append(title)
            WinCmd.cmd(command, log_tool_path, showcmdwin = True, wait = False, retaincmdwin = True, title = title)
        return titles

    def kill_hde_log(self):
        WinCmd.cmd(r'taskkill /fi "IMAGENAME eq cmd.exe" /fi "WindowTitle eq Administrator:  hde_log*"')
        WinCmd.cmd(r'taskkill /fi "IMAGENAME eq cmd.exe" /fi "WindowTitle eq loganalyse.exe*"')

    def kill_run_batch_window(self):
        WinCmd.cmd(r'taskkill /fi "IMAGENAME eq cmd.exe" /fi "WindowTitle eq Administrator:*Shouliang*"')

    def kill_other_process(self, cmd_win = False, python_exe = False):
        def _kill_process_with_filter(process, regex_filter):
            cmd = 'for /f "tokens=2 delims=," %%a in (\' tasklist /fi "imagename eq %s" /v /fo:csv /nh ^| findstr /r /c:"%s" \') do taskkill /F /pid %%a > nul' % (process, regex_filter)
            WinCmd.cmd(cmd)
        # for /f "tokens=2 delims=," %a in (' tasklist /fi "imagename eq cmd.exe" /v /fo:csv /nh ^| findstr /r /c:"[^!].$" ') do taskkill /F /pid %a
        # for /f "tokens=2 delims=," %a in (' tasklist /fi "imagename eq python.exe" /v /fo:csv /nh ^| findstr /r /c:"(python.exe.$|WndName.$)" ') do taskkill /F /pid %a
        if cmd_win: _kill_process_with_filter('cmd.exe', '[^!].$')          # kill other command window, rely on the changed title
        if python_exe:
            _kill_process_with_filter('python.exe', 'python.exe.$')  # kill other python.exe
            _kill_process_with_filter('python.exe', 'WndName.$')  # kill other python.exe
            _kill_process_with_filter('python.exe', '"Services"')  # kill other python.exe

    def update_result(self):
        command_path = 'C:\\'
        command_file = 'Update_Results.bat'
        WinCmd.check_file_exist(os.path.join(command_path, command_file))
        WinCmd.cmd(command_file, path = command_path, showcmdwin = True, wait = True)

    def retrieve_log_pattern(self, src_file, to_file, pattern, start_number, end_number_offset = 20, remove_time = True):
        start_line_text = (pattern % start_number).replace('%', ' ')
        end_line_text = (pattern % (start_number + end_number_offset)).replace('%', ' ')
        self.print_('search start text: "%s", end text: "%s"' % (start_line_text, end_line_text))
        self.retrieve_log(src_file, to_file, start_line_text, end_line_text, remove_time)

    def retrieve_log(self, src_file, to_file, start_line_text, end_line_text, remove_time = True):
        def _remove_time(line):
            if remove_time:
                pos = line.find(':')
                if pos >= 0: return line[pos+1:].strip()
            return line

        start_log = False
        with open(src_file, 'r') as f:
            with open(to_file, 'w') as f_write:
                for line in f:
                    if not start_log and line.find(start_line_text) >= 0:
                        start_log = True
                        f_write.write(_remove_time(line) + '\n')
                    elif start_log:
                        f_write.write(_remove_time(line) + '\n')
                        if line.find(end_line_text) >= 0: break

    def retrieve_folders(self, base_folder, folders = []):
        WinCmd.check_folder_exist(base_folder)
        out_folders = []
        for f in [os.path.join(base_folder, x) for x in os.listdir(base_folder) if os.path.isdir(os.path.join(base_folder, x))]:
            if os.path.basename(f) in folders:
                out_folders.append(f)
            else:
                subfolders = self.retrieve_folders(f, folders)
                if subfolders: out_folders += subfolders
        return out_folders

    def _get_file_list_from_clearquest(self, url):
        if not url.endswith('/'): url += '/'
        try:
            html = urllib2.urlopen(url, timeout = 5).read()
        except Exception as e:
            raise CmdException('open html error! "%s", %s' % (url, e))
        temp_list = re.findall(r'<a href[^>]+>[^<]+</a>\s*\d{2}-\w+-\d{4}', html)
        file_list = []
        for temp in temp_list:
            r = re.search(r'<a href[^>]+>([^<]+)</a>', temp)
            name = r.group(1)
            if name.endswith('/'):  # folder
                file_list_from_folder = self._get_file_list_from_clearquest(url + urllib.quote(name))
                file_list.append((name[:-1], file_list_from_folder))
            else:  # file
                file_list.append(name)
        return file_list

    def _download_folder_list_from_clearquest(self, base_url, base_folder, folder_list, folder_name = ()):
        total_files_num = download_files_num = files_num_already_exist = 0
        folder = os.path.join(base_folder, reduce(os.path.join, folder_name, ''))
        for f in folder_list:
            if isinstance(f, tuple):  # folder
                sub_folder_name, sub_folder_list = f
                n1, n2, n3 = self._download_folder_list_from_clearquest(base_url, base_folder, sub_folder_list, folder_name + (sub_folder_name,))
                total_files_num += n1
                download_files_num += n2
                files_num_already_exist += n3
            else: # file
                total_files_num += 1
                target_file = os.path.join(folder, f)
                if not os.path.isdir(folder): WinCmd.make_dir(folder)
                if os.path.isfile(target_file):
                    files_num_already_exist += 1
                    continue
                f_url = '%s/%s' % (base_url, '/'.join(map(urllib.quote, (folder_name + (f,)))))
                content = None
                block_size = 10*1024*1024  # read 10M bytes at a time
                try:
                    response = urllib2.urlopen(f_url, timeout = 5)
                    content = response.read(block_size)
                except Exception as e:
                    #raise CmdException('open html error! "%s", %s' % (f_url, e))
                    self.print_('open html error! "%s", %s' % (f_url, e))
                if not content is None:
                    with open(target_file, "wb") as f_write:
                        while content:
                            f_write.write(content)
                            content = response.read(block_size)
                    download_files_num += 1
        return (total_files_num, download_files_num, files_num_already_exist)

    def get_files_from_clearquest(self, ubi, output_path):
        # http://emea-clearquest/attachments/ubi00098472
        # <a href="TM500_ExtCp_ssp5_issue.zip">TM500_ExtCp_ssp5_issue.zip</a> 07-Apr-2015 12:45   16K  ZIP archive
        ubi_str = 'ubi' + '0' * (8-len(ubi)) + '%s' % ubi
        assert len(ubi) in [5, 6] and int(ubi) > 0, 'error ubi number ' % ubi_str
        WinCmd.check_folder_exist(output_path)
        folder = os.path.join(output_path, 'ubi%s' % ubi)
        if not os.path.isdir(folder): WinCmd.make_dir(folder)
        #url = 'http://emea-clearquest/attachments/%s' % ubi_str
        url = 'https://emea-clearquest.aeroflex.corp/attachments/%s' % ubi_str
        file_list = self._get_file_list_from_clearquest(url)
        total_files_num, download_files_num, files_num_already_exist = self._download_folder_list_from_clearquest(url, folder, file_list)
        self.print_('total %d (already exist %d, total %d) files downloaded to %s.' % (download_files_num, files_num_already_exist, total_files_num, folder))
        remain_files_num = total_files_num - download_files_num - files_num_already_exist
        if remain_files_num: self.print_('Caution: %d files cannot be downloaded!!!' % remain_files_num)

    def _download_file(self, file_url, target_file):
        content = None
        block_size = 10*1024*1024  # read 10M bytes at a time
        try:
            self.print_('get: %s' % file_url)
            response = urllib2.urlopen(file_url, timeout = 10)
            content = response.read(block_size)
        except Exception as e:
            self.print_('open html error! "%s", %s' % (file_url, e))
            return False
        if not content is None:
            with open(target_file, "wb") as f_write:
                while content:
                    f_write.write(content)
                    content = response.read(block_size)
        return True

    def get_files_from_teamcity(self, run_number, output_path):
        # https://emea-teamcity.aeroflex.corp/repository/download/RemoteRun_BinariesTestNr5g_BinariesRun/1264919:id/Run1.zip
        file_url = r'https://emea-teamcity.aeroflex.corp/repository/download/RemoteRun_BinariesTestNr5g_BinariesRun/%s:id/Run1.zip' % run_number
        filename = os.path.splitext(os.path.basename(file_url))
        target_file = os.path.join(output_path, '%s_%s%s' % (filename[0], run_number, filename[1]))
        status = self._download_file(file_url, target_file)
        if status:
            WinCmd.check_file_exist(target_file)
            dest_dir = os.path.splitext(target_file)[0]
            if not os.path.isdir(dest_dir): os.makedirs(dest_dir)
            ZipUtil.unzip(target_file, dest_dir)
            self.print_('download run1.zip (%d) to folder: %s' % (run_number, dest_dir))

    def _rrc_file(self, file_name_id):
        return self.get_temp_filename(suffix = '_rrc_%s' % file_name_id)

    def rrc_encode(self, project_path, clipboard = False, file_name_id = '0'):
        tool_path = self.find_tool_path(project_path)
        rrc_tool = os.path.join(tool_path, 'rrc_encoder.exe')
        WinCmd.check_file_exist(rrc_tool)
        if clipboard:
            data_in = WinCmd.get_clip_text()
            rrc_file = self.get_temp_filename(suffix = '_rrc')
            open(rrc_file, 'wb').write(data_in)
            self.print_('load data from clipboard and save to file: %s' % rrc_file)
        else:
            rrc_file = self._rrc_file(file_name_id)
            WinCmd.check_file_exist(rrc_file)
        temp_file = self.get_temp_filename(suffix = '_rrc_encode')
        if os.path.isfile(temp_file): os.remove(temp_file)
        WinCmd.cmd('%s %s > %s' % (rrc_tool, rrc_file, temp_file), showcmdwin = True, minwin = True, wait = True)
        if os.path.isfile(temp_file):
            self.print_('encode file %s to %s successfully!' % (rrc_file, temp_file))
            output_data = open(temp_file).read()
            output_data = ' '.join([output_data[2*i:2*i+2] for i in range(len(output_data)/2)])
            text = '%s\n%s\n\n%s\n%s\n' % ('[SUE]', 'FORW RRC DATAIND 1 00 %s 00 00 00 00' % (output_data), '[MUE/CUE]', 'FORW RRC DATAIND 0 1 00 %s 00 00 00 00' % (output_data))
            open(temp_file, 'a').write('\n\n'+text)
            WinCmd.explorer(temp_file)
        else:
            self.print_('[Error] cannot encode file %s. Please check.' % rrc_file)

    def rrc_decode(self, project_path, file_name_id = '0', message_name = ''):
        tool_path = self.find_tool_path(project_path)
        rrc_tool = os.path.join(tool_path, 'rrc_decoder.exe')
        WinCmd.check_file_exist(rrc_tool)
        data_in = WinCmd.get_clip_text()
        self.print_(data_in)
        r = re.search('dataind\s+(\d\s)?1\s+00\s+((\w{2}\s+)+\w{2})$', data_in.lower())
        if r:
            pdu_value = ''.join(r.group(2).split())
            pdu_name = message_name
        else:
            pdu = data_in.strip().split()
            if len(pdu) > 1:
                pdu_name, pdu_value = pdu
            else:
                pdu_value = pdu[0]
                pdu_name = message_name
        self.print_('[pdu value/pdu name] %s / %s' % (pdu_name, pdu_value))
        if pdu_name not in ['DL-DCCH-Message', 'UL-DCCH-Message', 'UE-EUTRA-Capability']:
            raise CmdException('message name %s invalid!' % pdu_name)
        rrc_file = self._rrc_file(file_name_id)
        if os.path.isfile(rrc_file): os.remove(rrc_file)
        WinCmd.cmd('%s %s %s > %s' % (rrc_tool, pdu_value, pdu_name, rrc_file), showcmdwin = True, minwin = True, wait = True)
        if os.path.isfile(rrc_file):
            self.print_('decode the string to file %s successfully!' % rrc_file)
            WinCmd.explorer(rrc_file)
        else:
            self.print_('[Error] cannot decode the string. Please check.')

    def update_batch(self, git_path, batch_path, backup = False):
        WinCmd.cmd('git pull', git_path, showcmdwin = True, wait = True, retaincmdwin = False)
        if backup:
            bak_dir = os.path.join(os.path.dirname(batch_path), 'batch_bak')
            WinCmd.copy_dir(batch_path, bak_dir, empty_dest_first = True, include_src_dir = False)
            self.print_('backup batches to folder: %s' % bak_dir)
        sanity_dir = os.path.join(batch_path, 'sanity')
        source_batches = [os.path.join(git_path, b) for b in self.all_batches]
        WinCmd.copy_files(source_batches, batch_path, empty_dir_first = False)
        sanity_source_batches = [os.path.join(batch_path, b) for b in self.sanity_batches]
        WinCmd.copy_files(sanity_source_batches, sanity_dir, empty_dir_first = False)
        return self.all_batches

    @use_system32_on_64bit_system
    def fix_remote_copy_paste(self):
        # restart the process 'rdpclip.exe'
        tool_file = r'C:\Windows\System32\rdpclip.exe'
        filename = os.path.basename(tool_file)
        WinCmd.check_file_exist(tool_file)
        WinCmd.kill(filename)
        WinCmd.process(tool_file)

    def clean_build_files(self, project_path):
        WinCmd.check_folder_exist(os.path.join(project_path, 'tm_build_system'))
        build_dirs = []
        for root, dirs, files in os.walk(project_path):
            if 'build' in dirs:
                build_dirs.append(os.path.join(root, 'build'))
        for times in range(2):  # clean 2 times
            for build_dir in build_dirs:
                #self.print_('folder: %s' % build_dir)
                WinCmd.del_dir(build_dir, include_dir = True, show_error_msg = False)
        self.print_('removed %d build folders' % len(build_dirs))

    def parse_build_logs(self, build_file):
        WinCmd.check_file_exist(build_file)
        build_start_str = 'scons: Building targets'
        build_success_str = 'scons: done building targets'
        build_error_str = 'scons: building terminated because of errors'
        logs = open(build_file, 'r').read()
        lines = open(build_file, 'r').readlines()
        error_lines = [line.strip() for line in lines if line.find('error:') > 0 or line.find('warning:') > 0 or line.find('remark:') > 0]
        error_lines = list(set(error_lines))
        if logs.find(build_error_str) > 0:
            return False, build_error_str, error_lines
        elif logs.find(build_success_str) > 0:
            return True, build_success_str
        elif logs.find(build_start_str) < 0:
            r = re.search(r'(AssertionError.*?)\n', logs)
            if r:
                return False, r.group(1)
            else:
                return False, 'Build not start for unknown reason'
        else:
            return False, 'Build fails for unknown reason'

    def _tsms_ip(self, machine):
        return [self.tsms.name_to_ip(m) for m in machine]

    def tsms_param(self, debug_log = False, reload = False):
        self.tsms.set_debug_log(debug_log)
        if reload: self.tsms.reload_station_info()

    def tsms_info(self, machine_or_ip = [], only_show_ip = False):
        if not machine_or_ip:  # means all machines
            machine_or_ip = self.tsms.get_all_stations()
        if only_show_ip:
            machine_ip = zip(machine_or_ip, self._tsms_ip(machine_or_ip))
            for m, ip in machine_ip:
                self.print_('%s : %s' % (m, ip))
        else:
            print_blank_line = False
            for m in machine_or_ip:
                record = self.tsms.find_machine_record(m)
                if record:
                    if print_blank_line: self.print_('')
                    for column in self.tsms.info_column:
                        self.print_('%s : %s : %s' % (m, column, record[column]))
                    print_blank_line = True

    def _tsms_unlimited_machine(self, machine):
        return machine.upper().startswith('PFC') and not machine.upper() in ['PFC19', 'PFC20']

    def _time_sgh_to_stevenage(self, floattime):
        TIMEZONE_OFFSET = 8     # 8 or 7
        return floattime - TIMEZONE_OFFSET

    def tsms_book(self, machines, book_time):
        RAV_START_TIME = 8    # RAV machine after 8:00
        SGH_OFF_WORK_TIME = 18.5 # off work time, 18:30
        MAX_DURATION = 7   # max 7 hour booking
        # book_time format: start,end,duration, e.g. 8,11.5, or 8,,3.5 or 8,,
        book_time = [float(t) if t else None for t in book_time.split(',')]
        if len(book_time) == 2:
            start_time, end_time, duration = book_time[0], book_time[1], None
        elif len(book_time) == 3:
            start_time, end_time, duration = book_time
        else:
            raise Exception('invalid book time %s' % book_time)
        if duration: duration = min(duration, MAX_DURATION)
        now = self.tsms.datetime_to_floattime(datetime.now())
        for m in machines:
            if start_time is None:
                if end_time and duration:
                    start_time = end_time - duration
                    start_time = max(start_time, now)
                else:
                    start_time = now if self._tsms_unlimited_machine(m) else RAV_START_TIME
                    if end_time: start_time = max(start_time, end_time - MAX_DURATION)
            if end_time is None:
                if start_time and duration:
                    end_time = start_time + duration
                else:
                    end_time = self._time_sgh_to_stevenage(SGH_OFF_WORK_TIME)
                    end_time = min(start_time + MAX_DURATION, end_time)
            if start_time < now: start_time = now
            if not self._tsms_unlimited_machine(m) and start_time < RAV_START_TIME: start_time = RAV_START_TIME
            start_datetime = self.tsms.floattime_to_datetime(start_time)
            end_datetime = self.tsms.floattime_to_datetime(end_time)
            self.print_('trying to book %s from %s to %s...' % (m, start_datetime.strftime('%H:%M'), end_datetime.strftime('%H:%M')))
            result = self.tsms.book(m, start_datetime, end_datetime)

    def vnc_connect(self, machines, debug_log = False):
        vnc_path = [r'C:\Program Files\RealVNC\VNC Viewer', r'C:\Program Files (x86)\RealVNC\VNC4']
        vnc_tools = [os.path.join(p, 'vncviewer.exe') for p in vnc_path if os.path.isfile(os.path.join(p, 'vncviewer.exe'))]
        if not vnc_tools: raise CmdException('cannot find vncviewer.exe')
        vnc_tool = vnc_tools[0]
        self.tsms.set_debug_log(debug_log)
        if not isinstance(machines, list): machines = [machines]
        machine_ip = zip(machines, self._tsms_ip(machines))
        for m, ip in machine_ip:
            WinCmd.process('%s %s' % (vnc_tool, ip))
            self.vnc_login(timeout = 10)

    @thread_func()
    def clear_signals(self):
        if not os.path.isdir(self.signal_folder): return
        ip, ip_str = self.get_ip_addr()
        WinCmd.del_pattern_files(os.path.join(self.signal_folder, '%s_%s*' % (ip_str, ip)))

    @thread_func()
    def report_finish(self, msg = ''):
        self._set_signal('Finished', msg)

    @thread_func()
    def set_remote_clip_text(self, msg):
        self._set_signal('RClip', msg)

    @thread_func()
    def monitor_signal_deamon(self, flag = [], timeout = 0, monitor_matlab_flag = False):
        local_ip, local_ip_str = self.get_ip_addr()
        count = 0
        while True:
            if monitor_matlab_flag: self.monitor_matlab()
            # signal_file, machine name, ip addr, signal, dest_pc, datetime, msg
            signals = self._get_signal()
            if signals:
                msgbox_output = False
                s = ''
                for sig in signals:
                    clear_signal = False
                    file_abs, machine, ip, signal, dest_pc, dtime, msg = sig
                    if signal == 'RClip':
                        if msg and ip != local_ip:
                            WinCmd.set_clip_text(msg)
                            self.print_('receive clip text %d characters from %s(%s)' % (len(msg), machine, ip))
                            clear_signal = True
                    elif local_ip_str.lower().startswith('sgh'):
                        t = '%s-%s-%s %s:%s:%s' % (dtime[:4], dtime[4:6], dtime[6:8], dtime[8:10], dtime[10:12], dtime[12:])
                        s += '[%s (%s) @ %s]\n' % (machine, ip, t)
                        s += '%s!\n' % signal
                        s += '(Cmd)%s\n\n' % msg.strip()
                        msgbox_output = True
                        clear_signal = True
                    if clear_signal: WinCmd.force_del_file(file_abs)
                if msgbox_output: WinCmd.MessageBox(s)
            count += 1
            if (timeout and count >= timeout) or len(flag): break
            time.sleep(0.5)

    def monitor_signal(self, monitor_matlab_flag = False):
        ip, ip_str = self.get_ip_addr()
        self.print_('the current PC is %s (%s)' % (ip_str, ip))
        flag = []
        self.monitor_signal_deamon(flag, monitor_matlab_flag = monitor_matlab_flag)
        input = raw_input('the monitor is running! press any key to close the monitor...\n')
        flag.append(1)
        self.print_('the monitor has been closed.')

    def _set_signal(self, signal, msg = '', dest_pc = 0):
        if not os.path.isdir(self.signal_folder): WinCmd.make_dir(self.signal_folder)
        ip, ip_str = self.get_ip_addr()
        filename = '%s_%s_%s_to%d_%s.txt' % (ip_str, ip, signal, dest_pc, datetime.now().strftime('%Y%m%d%H%M%S'))
        with open(os.path.join(self.signal_folder, filename), 'w') as f_write:
            if msg: f_write.write(msg)

    def _get_signal(self):
        if not os.path.isdir(self.signal_folder): return ''
        signals = []
        for f in os.listdir(self.signal_folder):
            if f.endswith('.txt'):
                f_abs = os.path.join(self.signal_folder, f)
                try:
                    with open(f_abs) as fid:
                        data = fid.read()
                        signals.append([f_abs] + os.path.splitext(f)[0].split('_') + [data])
                except:
                    pass
                #WinCmd.del_file(f_abs)
        # signal_file, machine name, ip addr, signal, dest_pc, datetime, msg
        return signals

    def reminder(self, time = None):  # here????
        if time:
            pass

    def monitor_matlab(self):
        if not hasattr(self, 'matlab_user'): self.matlab_user = 'NotAvailable'
        user, start_time = self.check_matlab_user()
        if user != 'NotAvailable':
            if self.matlab_user == 'NotAvailable': self.matlab_user = user
            if user != self.matlab_user:
                if user:
                    s = '[%s] start to use matlab at [%s] !' % (user, start_time)
                else:
                    s = '[%s] stop using matlab !' % (self.matlab_user)
                self.matlab_user = user
                WinCmd.MessageBox(s)

    def check_matlab_user(self):
        path_candidate = [r'D:\Program Files\MATLAB\R2012b\etc\win64', r'C:\Program Files (x86)\MATLAB\R2009a\bin\win32']
        tools_name = 'lmutil.exe'
        tools = [os.path.join(p, tools_name) for p in path_candidate if os.path.isfile(os.path.join(p, tools_name))]
        if not tools: raise CmdException('no files found for: %s' % tools_name)
        tool = tools[0]
        temp_file = self.get_temp_filename(suffix = '_monitor')
        #WinCmd.cmd(r'%s lmstat -c ..\..\licenses\network.lic -a > "%s"' % (tools_name, temp_file), os.path.split(tool)[0], showcmdwin = True, minwin = True, wait = True)
        WinCmd.cmd(r'%s lmstat -c ..\..\licenses\network.lic -a > "%s"' % (tools_name, temp_file), os.path.split(tool)[0])
        time.sleep(1)
        start_time = ''
        if os.path.isfile(temp_file):
            user = ''
            with open(temp_file, 'r') as f:
                for line in f:
                    r = re.search(r'^([\w.]+)\b.*?start\s+(.*)$', line.strip())
                    if r:
                        user, start_time = r.group(1), r.group(2)
                        break
        else:
            self.tool.print_('run command in checking matlab user fail!')
            user = 'NotAvailable'
        return user, start_time

    def _session_deamon(self):
        if not hasattr(self, '_session_add_cursor'): self._session_add_cursor = True
        cursor = win32api.GetCursorPos()
        offset = 100
        new_cursor = (cursor[0] + offset, cursor[1] + offset) if self._session_add_cursor else (cursor[0] - offset, cursor[1] - offset)
        self._session_add_cursor = not self._session_add_cursor
        win32api.SetCursorPos(new_cursor)
        self.print_('set new cursor %s' % str(new_cursor))

    def _vnc_deamon(self):
        handles = self._get_vnc_handle()
        #key = win32con.VK_F9   #win32con.VK_DOWN
        key = win32con.VK_SNAPSHOT
        for h in handles: self.send_vnc_msg(h, key, 'key')

    def _add_deamon_config(self, func, time_wait):
        if not hasattr(self, 'deamon_config'):
            self.deamon_config = []
        self.deamon_config.append((func, time_wait))

    @thread_func()
    def _deamon(self, stop_flag = []):
        # self.deamon_config: [(func, time_wait), ...]
        self._deamon_time_cnt = {}
        while True:
            for _func, _time_wait in self.deamon_config:
                if not _func in self._deamon_time_cnt: self._deamon_time_cnt[_func] = -1
                self._deamon_time_cnt[_func] = self._deamon_time_cnt[_func] + 1
                if self._deamon_time_cnt[_func] >= _time_wait:
                    _func()
                    self._deamon_time_cnt[_func] = 0
            if len(stop_flag): break
            time.sleep(1)

    def _find_windows(self, parent = None, window_class = None, window_name = None):
        handles = []
        h = None
        while True:
            h = win32gui.FindWindowEx(parent, h, window_class, window_name)
            if h:
                handles.append(h)
            else:
                break
        return handles

    def _get_vnc_handle(self, type = 'normal'):
        handles = []
        # type: 'authentication', 'login', 'normal'
        if type == 'authentication':
            window_name = 'VNC Viewer : Authentication [No Encryption]'
            handles = self._find_windows(window_name = window_name)
        elif type == 'login':
            pass
        elif type == 'normal':
            window_class = 'rfb::win32::DesktopWindowClass'
            handles = self._find_windows(window_class = window_class)
            self.print_('found %d vnc viewer running.' % len(handles))
        else:
            raise CmdException('invalid type %s' % type)
        return handles

    def send_vnc_msg(self, handle, msg, type = 'text'):
        if type == 'text':
            for c in msg:
                #win32api.SendMessage(handle, win32con.WM_CHAR, ord(c), 0)
                win32api.PostMessage(handle, win32con.WM_KEYDOWN, ord(c), 0)
                win32api.PostMessage(handle, win32con.WM_KEYUP, ord(c), 0)
                time.sleep(0.1)
        elif type == 'key':
            win32api.PostMessage(handle, win32con.WM_KEYDOWN, msg, 0)
            win32api.PostMessage(handle, win32con.WM_KEYUP, msg, 0)

    def vnc_login(self, timeout = 10):
        while timeout:
            handles = self._get_vnc_handle(type = 'authentication')
            if handles: break
            timeout -= 1
            time.sleep(1)
        if not len(handles) == 1:
            self.print_('found vnc handles %d, invalid operation.' % len(handles))
            return
        h = handles[0]
        edit_handles = self._find_windows(parent = h, window_class = 'Edit')
        if not len(edit_handles) == 2:
            self.print_('invalid edit handles, number %d' % len(edit_handles))
            return
        edit = edit_handles[1]
        win32gui.SendMessage(edit, win32con.WM_SETTEXT, 0, '123')
        self.send_vnc_msg(h, win32con.VK_RETURN, 'key')

    def keep(self, keep_vnc = False, keep_session = False):
        if not keep_vnc and not keep_session: return
        ip, ip_str = self.get_ip_addr()
        self.print_('the current PC is %s (%s)' % (ip_str, ip))
        stop_flag = []
        if keep_vnc: self._add_deamon_config(self._vnc_deamon, time_wait = 60*3)
        if keep_session: self._add_deamon_config(self._session_deamon, time_wait = 60)
        self._deamon(stop_flag)
        input = raw_input('keep deamon running! press any key to terminate...\n')
        stop_flag.append(1)
        self.print_('the deamon has been closed.')

    def update_self(self):
        args = sys.argv[:]
        args.insert(0, sys.executable)
        sys.stdout.flush()
        self.print_('begin updating: %s, %s' % (sys.executable, args))
        os.execv(sys.executable, args)

if __name__ == '__main__':
    Test = False
    if Test:
        tool = TestTool()
        #a = tool._load_file_rav(r'test\3.txt')
        tool._gen_result_4(r'test\4.txt', r'test\4_auto.txt', r'test\4_remove.txt')
        #import pprint
        #pprint.pprint(a)
    else:
        start_index = 1
        if start_index == 0:
            CmdLine().cmdloop()
        elif start_index == 1:
            if len(sys.argv) > 1 and sys.argv[1] == 'remote':
                remote_call = True
            else:
                remote_call = False
            CmdLine(remote_call = remote_call).cmdloop()
        elif start_index == 2:
            if len(sys.argv) > 1 and sys.argv[1] == 'remote':
                remote_call = True
            else:
                remote_call = False
            c = CmdLine(remote_call = remote_call, stdout = open('temp/stdout.txt', 'w'))
            #c.use_rawinput = False
            c.cmdloop()
        else:
            if len(sys.argv) < 2:
                file_path = os.path.dirname(os.path.abspath(__file__))
                if file_path.startswith(r'\\'):
                    # map network device
                    map_path = r'\\' + '\\'.join(file_path[2:].split('\\')[:2])
                    map_drive = 'B:'
                    os.system('net use %s /delete' % map_drive)
                    os.system('net use %s %s' % (map_drive, map_path))
                    filename = __file__.replace(map_path, map_drive)
                    file_path = os.path.dirname(filename)
                    os.system('explorer %s' % file_path)
                else:
                    filename = __file__
                # restart program in command shell, do not wait or retain the cmd win
                WinCmd.cmd('python "%s" start' % filename, file_path, showcmdwin = True, wait = False)
            else:
                if sys.argv[1] == 'remote':
                    # command: python *.py remote directory file_index
                    directory = sys.argv[2] if len(sys.argv) >= 3 else None
                    file_index = sys.argv[3] if len(sys.argv) >= 4 else None
                    remote = Remote(directory, file_index)
                    remote_call = True
                else:
                    remote_call = False
                print '%s>python %s start' % (os.path.split(os.path.abspath(__file__)))
                CmdLine(remote_call = remote_call).cmdloop()
