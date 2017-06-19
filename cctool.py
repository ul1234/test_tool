#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, re
from datetime import datetime
from wincmd import WinCmd

class CcTool:
    default_cctools = [r"C:\Program Files (x86)\IBM\RationalSDLC\ClearCase\bin\cleartool.exe",
                      r"C:\Program Files\IBM\RationalSDLC\ClearCase\bin\cleartool.exe"]
    cctool = ''
    temp_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp', 'temp_file_for_cc_tool.txt')

    @staticmethod
    def set_cctool(cctool):
        CcTool.cctool = cctool

    @staticmethod
    def get_cctool():
        if CcTool.cctool: return CcTool.cctool
        for default_cctool in CcTool.default_cctools:
            if os.path.isfile(default_cctool):
                return default_cctool
        raise Exception('no valid "cleartool.exe" found!')

    @staticmethod
    def checkout(file):
        WinCmd.cmd(r'"%s" checkout -nc "%s"' % (CcTool.get_cctool(), file), showcmdwin = True, minwin = True)

    @staticmethod
    def undo_checkout(file):
        WinCmd.cmd(r'"%s" uncheckout -rm "%s"' % (CcTool.get_cctool(), file), showcmdwin = True, minwin = True)

    @staticmethod
    def checkin(file):
        WinCmd.cmd(r'"%s" checkin -nc "%s"' % (CcTool.get_cctool(), file), showcmdwin = True, minwin = True)

    @staticmethod
    def find_checkout(path):
        WinCmd.cmd(r'"%s" lsco -graphical "%s"' % (CcTool.get_cctool(), path), showcmdwin = True, minwin = True)

    @staticmethod
    def find_all_branches(dest_file):
        WinCmd.cmd(r'cleartool lstype -fmt "%%u:%%n\n" -kind brtype -invob \lte_admin_vob > "%s"' % dest_file, showcmdwin = True, minwin = True)

    @staticmethod
    def branch_info(branch_name):
        #expected output:
        #branch type "priv_w_cue_tot_debug_150721"
        #created 2015-07-21T08:01:17+01:00 by Wang (swang2.G.STV.ClearCaseUsers@STV-27974)
        #master replica: rep_ARXX_STV01_lte_admin_vob@\lte_admin_vob
        WinCmd.cmd(r'cleartool describe brtype:%s@\lte_admin_vob > "%s" 2>&1' % (branch_name, CcTool.temp_file), showcmdwin = True, minwin = True)
        lines = []
        try:
            lines = open(CcTool.temp_file, 'r').readlines()
            branch = lines[0].split('"')[1]
            obsoleted = lines[0].find('obsolete') > 0
            r = re.search(r'(\d{4})-(\d{2})-(\d{2})T.*?\b\(?(\w+)\.', lines[1].strip())
            if r:
                time = datetime(*tuple([int(r.group(i)) for i in [1,2,3]]))
                user = r.group(4).lower()
                branch_time_user = (branch, time, user, obsoleted)
            else:
                branch_time_user = ()
        except Exception as e:
            print 'branch [%s] Exception:' % branch_name, e
            branch_time_user = ()
        return branch_time_user, lines[:min(len(lines), 2)]

    @staticmethod
    def obsolete_branch(branch_name):
        #expected output:
        #Locked branch type "priv_w_cue_tot_debug_150721".
        WinCmd.cmd(r'cleartool lock -obsolete brtype:%s@\lte_admin_vob > "%s" 2>&1' % (branch_name, CcTool.temp_file), showcmdwin = True, minwin = True)
        line = open(CcTool.temp_file, 'r').readlines()[0].strip()
        result = True if line.startswith('Locked') and line.find(branch_name) > 0 else False
        return result, line

if __name__ == '__main__':
    #CcTool.checkout(r'E:\cc_projects\swang2_cue_tot_debug\lte_dsp_app\copro_models\pcp\include\ul_srp_pucch_copro_msgs.h')
    pass
