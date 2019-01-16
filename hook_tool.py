#!/usr/bin/python
# -*- coding: utf-8 -*-

import re, os, sys
from wincmd import WinCmd


class HookTool:
    def __init__(self, rules = None, debug_output = False):
        # [target_file, pattern to search, target line after pattern, string to replace]
        self.rules = rules
        self.changed_files = []
        self.debug_output = debug_output

    def replace_files_with_rules(self, rules = None):
        rules = rules or self.rules
        for rule in rules:
            self.replace_str_in_file(*rule)

    def replace_str_in_file(self, target_file, pattern_mark, pattern_to_replace, replace_str):
        WinCmd.check_file_exist(target_file)
        tmp_file = '%s.tmp' % target_file
        mark_found = True if not pattern_mark else False
        replace_line = False
        have_changed = False
        with open(target_file, 'r') as f:
            with open(tmp_file, 'w') as f_write:
                for line in f:
                    if not mark_found:
                        #r = re.search(pattern_mark, line, flags = re.IGNORECASE)
                        #if r: mark_found = True
                        if line.find(pattern_mark) >= 0: mark_found = True
                    else:
                        #r = re.search(pattern_to_replace, line, flags = re.IGNORECASE)
                        #if r: replace_line = True
                        if line.find(pattern_to_replace) >= 0: replace_line = True
                    if replace_line:
                        leading_spaces = len(line) - len(line.lstrip(' '))
                        f_write.write('%s%s\n' % (leading_spaces * ' ', replace_str))
                        have_changed = True
                        mark_found = True if not pattern_mark else False
                        replace_line = False
                    else:
                        f_write.write(line)
        if have_changed:
            bak_file = '%s.bak' % target_file
            if not os.path.isfile(bak_file): WinCmd.rename_files(target_file, bak_file)
            WinCmd.rename_files(tmp_file, target_file, remove_dest_first = True)
            self.changed_files.append(target_file)
            self.print_('Changed file successfully: %s' % target_file)
        else:
            WinCmd.del_file(tmp_file)
            self.print_('Warning: file %s no change.' % target_file, force_output = True)

    def restore_changed_files(self):
        for changed_file in self.changed_files:
            bak_file = '%s.bak' % changed_file
            WinCmd.check_file_exist(changed_file)
            if os.path.isfile(bak_file):
                WinCmd.rename_files(bak_file, changed_file, remove_dest_first = True)
                self.print_('Restore file successfully: %s' % changed_file)
        self.changed_files = []

    def print_(self, msg, force_output = False):
        if self.debug_output or force_output:
            WinCmd.print_(msg)


if __name__ == '__main__':
    h = HookTool()
    rules = [[r'temp/remote_run.pyw', '', 'frame.Show(True)', "frame.Show(True); from Hook import Hook; Hook().hook(frame)"],
             [r'temp/main_frame.py', 'Build has been scheduled', 'msgDlg.ShowModal()', 'msgDlg.ShowModal(); from Hook import Hook; Hook().hook_schedule_end()']]
    h.replace_files_with_rules(rules)

