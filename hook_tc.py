#!/usr/bin/python
# -*- coding: utf-8 -*-

import wx
import os, sys, traceback
from decorator import thread_func, hook_func
from hook_tool import HookTool
from wincmd import WinCmd


class HookToolCacheManager(HookTool):
    def __init__(self, remote_run_tool, debug_output = False):
        self.remote_run_tool = remote_run_tool
        path = os.path.dirname(os.path.abspath(__file__))
        self.rules = [[self.remote_run_tool, '', 'CacheManager().run(__file__)', "c = CacheManager(); import sys; sys.path.append(r'%s'); from hook_tc import hook; import os; hook.hook_cache_manager(c, os.path.abspath(__file__), %s); c.run(__file__)" % (path, debug_output)]];
        HookTool.__init__(self, self.rules)

    def run(self):
        try:
            self.replace_files_with_rules()
            tool_path, tool_name = os.path.split(self.remote_run_tool)
            WinCmd.cmd(r'python "%s"' % tool_name, tool_path, showcmdwin = True, wait = False)
        except Exception as e:
            print('EXCEPTION: %s\n' % (e))
            print(traceback.format_exc())
        finally:
            #self.restore_changed_files()
            pass

class HookToolRemoteRun(HookTool):
    def __init__(self, teamcity_folder):
        self.teamcity_folder = teamcity_folder
        self.rules = [[os.path.join(self.teamcity_folder, '.cache', 'remote_run.pyw'), '', 'frame.Show(True)', "frame.Show(True); from hook_tc import hook; import os; hook.hook_frame(frame, os.path.abspath(__file__))"],
                      [os.path.join(self.teamcity_folder, '.cache', 'remote_run_internals', 'main_frame.py'), 'Build has been scheduled', 'msgDlg.ShowModal()', 'from hook_tc import hook; hook.hook_schedule_end()']]
        HookTool.__init__(self, self.rules)

    def run(self):
        try:
            self.replace_files_with_rules()
        except Exception as e:
            print('EXCEPTION: %s\n' % (e))
            print(traceback.format_exc())
            self.restore_changed_files()

class HookTc:
    def __init__(self):
        self.batches = [r'C:\wang\03.Batch\sanity\batch_CUE_PDCP_NR5G_1CELL_15kHz_Basic.txt',
                        r'C:\wang\03.Batch\batch_CUE_PDCP_NR5G_1CELL_15kHz_Basic.txt'];
        self.ftp_folder = r'tm_build_system\build\ftp'
        self.debug_output = False

    def change_ftp_folder(self, ftp_folder):
        self.ftp_folder = ftp_folder

    def hook_cache_manager(self, cache_manager, target_file, debug_output = False):
        self.debug_output = debug_output
        self.teamcity_folder = os.path.dirname(target_file)
        self.hook_remote_run = HookToolRemoteRun(self.teamcity_folder)
        self._cache_manager = cache_manager
        self._cache_manager.run = hook_func(self._cache_manager.run, before_func = self._hook_func_cache_manager)

    def _hook_func_cache_manager(self, scriptName):
        if os.path.basename(scriptName) == 'remote_run.pyw':
            self.print_('Before run cache manager, start to replace files...')
            self.hook_remote_run.run()

    def hook_frame(self, frame, frame_file):
        self._frame = frame
        self._panel = frame._panel
        self.run()

    @thread_func(1)
    def run(self):
        self.print_('After the window opens, start to hook functions...')
        try:
            self._frame.Destroy = hook_func(self._frame.Destroy, before_func = self._hook_func_destroy)
            self._panel.panelAddBatchDialog.onok = hook_func(self._panel.panelAddBatchDialog.onok, after_func = self._hook_func_add_batches)
            #self._panel.panelSelectPath.get_ftp_folder = hook_func(self._panel.panelSelectPath.get_ftp_folder, after_func = self._hook_func_get_ftp_folder)
            self._panel.resetWindow = hook_func(self._panel.resetWindow, after_func = self._hook_func_reset_window)
            self._panel.oncontinue(event = None)
        except Exception as e:
            self.print_('Exception: %s' % e, force_output = True)
            self._frame.Destroy()

    def _hook_func_destroy(self):
        self.print_('Before destroy the window, start to restore the changed files.')
        self.hook_remote_run.restore_changed_files()

    def _hook_func_add_batches(self):
        self.print_('before load batches, start to change the batches and folders.')
        sys.path.append(os.path.join(self.teamcity_folder, '.cache', 'remote_run_internals', 'add_batch_dialog'))
        self.print_('DEBUG: sys.path is %s' % str(sys.path))
        from batch_info import BatchInfo
        self._panel.panelAddBatchDialog.selectedBatchInfo = []
        self._panel.panelAddBatchDialog.selectedFolders = []
        for batch in self.batches:
            batch_path, batch_name = os.path.dirname(batch), os.path.basename(batch)
            self._panel.panelAddBatchDialog.selectedBatchInfo.append(BatchInfo(batch_name, 'MK4.X', 'RemoteRun_BinariesTestNr5g_BinariesRun', '2CELL4G5G'))
            self._panel.panelAddBatchDialog.selectedFolders.append(batch_path)
        self.print_('finish to change the batches and folders.')

    def _hook_func_get_ftp_folder(self):
        self.print_('before get ftp folder, start to change the ftp folder.')
        return self.ftp_folder

    def hook_schedule_end(self):
        self.print_('scheduling have been finished. replace the Modal dialog.')

    def _hook_func_reset_window(self):
        self.print_('after reset window, start to destroy the window.')
        self._frame.Destroy()

    def print_(self, s, force_output = False):
        if self.debug_output or force_output:
            WinCmd.MessageBox(s)
            #self.message(s)

    def message(self, msg):
        dlg = wx.MessageDialog(
                self._frame,
                msg,
                "Hook",
                wx.OK | wx.CANCEL | wx.ICON_QUESTION)
        result = dlg.ShowModal()
        dlg.Destroy()

# python only import once, so use the method for singleton
hook = HookTc()



