#!/usr/bin/python
# -*- coding: utf-8 -*-

#import wx
import os, sys, traceback, ConfigParser
from decorator import thread_func, hook_func
from hook_tool import HookTool
from wincmd import WinCmd


class TeamcityIni:
    def __init__(self, ini_file):
        WinCmd.check_file_exist(ini_file)
        self.ini = ConfigParser.RawConfigParser()
        self.ini.optionxform = lambda option: option  # preserve the lower/upper case
        self.ini_file = ini_file
        self.ini.read(ini_file)
        self.set_default()

    def set_default(self):
        self.ini.set('Settings', '_selectedbuildtype', 'MK4.X')
        self.ini.set('AddBatchDialog', 'umbra-update', 'False')
        self.ini.set('ButtonPanel', 'skip-file-selection', 'True')
        self.ini.set('PathSelectPanel', 'ftp-folder', r'tm_build_system\build\ftp')
        self.write_back()

    def _rav_id_from_name(self, rav = ''):
        RAV_ID_TABLE = {'RAV99-2': '211', 'RAV99-1': '210', 'RAV98-2': '213', 'RAV98-1': '212', 'RAV95-2': '207',
                        'RAV95-1': '208', 'RAV94': '160', 'RAV100-2': '215', 'RAV100-1': '216'}
        rav = rav.upper()
        if not rav in RAV_ID_TABLE.keys():
            if rav != '':
                WinCmd.print_('cannot find RAV id for %s, use Any instead.' % rav)
            rav_id = 'Any'
        else:
            rav_id = RAV_ID_TABLE[rav]
        return rav_id
        
    def set_batches(self, batches, config = '', rav = ''):
        # batch_CUE_PDCP_NR5G_1CELL_15kHz_Basic.txt:MK4.X::RemoteRun_BinariesTestNr5g_BinariesRun:Any
        # batch_CUE_PDCP_NR5G_1CELL_15kHz_Basic.txt:MK4.X::RemoteRun_BinariesTestNr5g_BinariesRun:211
        # batch_CUE_NAS_NR5G_ENDC_2CELL_June18_Basic.txt:MK4.X:2CELL4G5G:RemoteRun_BinariesTestNr5g_BinariesRun:Any
        rav_id = self._rav_id_from_name(rav)
        selected_batches = []
        selected_folders = []
        for batch in batches:
            batch_path, batch_name = os.path.dirname(batch), os.path.basename(batch)
            selected_batches.append(':'.join([batch_name, 'MK4.X', config, 'RemoteRun_BinariesTestNr5g_BinariesRun', rav_id]))
            selected_folders.append(batch_path)
        self.ini.set('Settings', '_selectedBatchFiles', ','.join(selected_batches))
        self.ini.set('Settings', '_selectedBatchFolders', ','.join(selected_folders))
        self.write_back()

    def write_back(self):
        with open(self.ini_file, 'w+') as f_write:
            self.ini.write(f_write)


class HookToolCacheManager(HookTool):
    def __init__(self, teamcity_tool, debug_output = False):
        self.teamcity_tool = teamcity_tool
        path = os.path.dirname(os.path.abspath(__file__))
        self.rules = [[self.teamcity_tool, '', 'CacheManager().run(__file__)', "c = CacheManager(); import sys; sys.path.append(r'%s'); from hook_tc import hook; import os; hook.hook_cache_manager(c, os.path.abspath(__file__), %s); c.run(__file__)" % (path, debug_output)]];
        HookTool.__init__(self, self.rules, debug_output = debug_output)

    def run(self):
        try:
            self.replace_files_with_rules()
            tool_path, tool_name = os.path.split(self.teamcity_tool)
            WinCmd.cmd(r'python "%s"' % tool_name, tool_path, showcmdwin = True, minwin = True, wait = True, retaincmdwin = False)
        except Exception as e:
            print('EXCEPTION: %s\n' % (e))
            print(traceback.format_exc())
        finally:
            self.restore_changed_files()

class HookToolRemoteRun(HookTool):
    def __init__(self, teamcity_folder):
        self.teamcity_folder = teamcity_folder
        self.rules = [[os.path.join(self.teamcity_folder, '.cache', 'remote_run.pyw'), '', 'frame.Show(True)', 'frame.Show(True); from hook_tc import hook; import os; hook.hook_frame(frame)'],
                      [os.path.join(self.teamcity_folder, '.cache', 'remote_run_internals', 'main_frame.py'), 'Build has been scheduled', 'msgDlg.ShowModal()', 'from hook_tc import hook; hook.hook_schedule_end()'],
                      [os.path.join(self.teamcity_folder, '.cache', 'remote_run_internals', 'add_batch_dialog', 'input_panel.py'), '', 'wx.CallAfter(self._start_update)', 'wx.CallAfter(self._populate_batch_file_list, False)'],
                      [os.path.join(self.teamcity_folder, '.cache', 'remote_run_internals', 'path_select_panel.py'), '', 'self._runReasonCombo.SetSelection(0)', 'self._runReasonCombo.SetSelection(4)'],
                     ]
        HookTool.__init__(self, self.rules)

    def run(self):
        try:
            self.replace_files_with_rules()
        except Exception as e:
            print('EXCEPTION: %s\n' % (e))
            print(traceback.format_exc())
            self.restore_changed_files()

class HookToolPresub(HookTool):
    def __init__(self, teamcity_folder):
        self.teamcity_folder = teamcity_folder
        self.rules = [[os.path.join(self.teamcity_folder, '.cache', 'presub.pyw'), 'dialog = RemoteRunDialog(', 'dialog.Show()', 'dialog.Show(); from hook_tc import hook; import os; hook.hook_presub_dialog(dialog)'],
                      [os.path.join(self.teamcity_folder, '.cache', 'presub.pyw'), 'Select files to include in the remote run', 'if dlg.ShowModal() == wx.ID_OK', "if True:"], # skip the select files button
                      [os.path.join(self.teamcity_folder, '.cache', 'presub.pyw'), '', 'Select builds/tests to run', 'title = "Select builds/tests to run..."; from hook_tc import hook; hook.hook_presub_select_builds(items)'],
                      [os.path.join(self.teamcity_folder, '.cache', 'presub.pyw'), 'Select builds/tests to run', 'if dlg.ShowModal() == wx.ID_OK', 'if True:'],  # skip the select builds button
                      [os.path.join(self.teamcity_folder, '.cache', 'presub.pyw'), '', 'useRecommendedDlg.ShowModal()', 'useRecommended = True'],  # skip the recommended selection button
                      [os.path.join(self.teamcity_folder, '.cache', 'presub.pyw'), '', 'Done scheduling the job on TeamCity', 'self.Destroy()'],  # close window when finish
                     ]
        HookTool.__init__(self, self.rules)

    def run(self):
        try:
            self.replace_files_with_rules()
        except Exception as e:
            print('EXCEPTION: %s\n' % (e))
            print(traceback.format_exc())
            self.restore_changed_files()


class HookTeamcity:
    def __init__(self):
        self.debug_output = False
        self.hook_tool_dict = {'remote_run.pyw': 'HookToolRemoteRun',
                               'presub.pyw': 'HookToolPresub'}

    ######### cache manager, common ##############
    def hook_cache_manager(self, cache_manager, teamcity_tool, debug_output = False):
        self.debug_output = debug_output
        self.teamcity_folder = os.path.dirname(teamcity_tool)
        self.teamcity_tool = os.path.basename(teamcity_tool)
        if not self.teamcity_tool in self.hook_tool_dict.keys():
            self.print_('Invalid teamcity tool: %s' % self.teamcity_tool, force_output = True)
            raise
        self.hook_teamcity_tool = eval(r"%s(r'%s')" % (self.hook_tool_dict[self.teamcity_tool], self.teamcity_folder))
        self._cache_manager = cache_manager
        self._cache_manager.run = hook_func(self._cache_manager.run, before_func = self._hook_func_cache_manager)

    def _hook_func_cache_manager(self, scriptName):
        self.print_('Before run cache manager for %s, start to replace files...' % scriptName)
        self.hook_teamcity_tool.run()

    def _hook_func_destroy(self):
        self.print_('Before destroy the window, start to restore the changed files.')
        self.hook_teamcity_tool.restore_changed_files()

    def print_(self, s, force_output = False):
        if self.debug_output or force_output:
            WinCmd.MessageBox(s)

    ################# remote run ##################
    def hook_frame(self, frame):
        self._frame = frame
        self._panel = frame._panel
        self.run()

    @thread_func(1)
    def run(self):
        self.print_('After the window opens, start to hook functions...')
        try:
            self._frame.Destroy = hook_func(self._frame.Destroy, before_func = self._hook_func_destroy)
            self._panel.resetWindow = hook_func(self._panel.resetWindow, after_func = self._hook_func_reset_window)
            self._panel.oncontinue(event = None)
        except Exception as e:
            self.print_('Exception: %s' % e, force_output = True)
            self._frame.Destroy()

    def hook_schedule_end(self):
        self.print_('scheduling have been finished. replace the Modal dialog.')

    def _hook_func_reset_window(self):
        self.print_('after reset window, start to destroy the window.')
        self._frame.Destroy()

    ################# presub ##################
    def hook_presub_dialog(self, dialog):
        self._presub_dialog = dialog
        self._presub_dialog.Destroy = hook_func(self._presub_dialog.Destroy, before_func = self._hook_func_destroy)

    def hook_presub_select_builds(self, items):
        self.print_('before select builds. start to check the builds.')
        sys.path.append(os.path.join(self.teamcity_folder, '.cache'))
        self.print_('DEBUG: sys.path is %s' % str(sys.path))
        from utilities.simpleCheckTree import SimpleCheckItem
        for _item in items:
            product = _item.get_text()
            if product == 'NR5G':
                _item.set_check_state(SimpleCheckItem.CHECKED)


# python only import once, so use the method for singleton
hook = HookTeamcity()



