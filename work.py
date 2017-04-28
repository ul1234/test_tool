#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys

try:
    import work_log
except:
    work_log = None

class Log:
    def __init__(self, project_path = ''):
        if project_path: self.load_project(project_path)

    def load_project(self, project_path):
        self.project_path = project_path
        self.log_tool_path = os.path.join(self.project_path, 'tm_build_system', 'build', 'win32')
        self.log_domain_file = os.path.join(self.project_path, 'lte_common', 'interface', 'log', 'dsp_logging_domain.h')

        sys.path.append(self.log_tool_path)
        os.chdir(self.log_tool_path)
        
        import pyloganalyse
        self.loganalyse = pyloganalyse.LogAnalyse()
        self.base_set_nums = pyloganalyse.LA_NUM_BASE_SETS
        self.base_in_set_shift = pyloganalyse.LA_BASE_IN_SET_SHIFT
        
        if self.loganalyse.get_rat_name() != 'LTE': raise Exception('LogAnalyse rat name err: %s' % self.loganalyse.get_rat_name())
        
        self.loganalyse.parse_header(self.log_domain_file)
        self.all_bases = self.loganalyse.base_names()

    def gen_log_masks(self, selected_bases):
        masks = [0] * self.base_set_nums
        non_exist_bases = []
        for base in selected_bases:
            if base in self.all_bases:
                base_set_id, base_id = self.loganalyse.get_base_id(base)
                masks[base_set_id] |= base_id
                #base_name = self.loganalyse.get_base_set_name(base_set_id)
            else:
                non_exist_bases.append(base)
        log_mask_string = ' '.join(['0x%08x' % (mask << self.base_in_set_shift) if mask else '0' for mask in masks])
        return (log_mask_string, non_exist_bases)
        
    def get_work_log(self, log_name):
        if not hasattr(work_log, log_name): return []
        logs = getattr(work_log, log_name)
        log_bases = reduce(lambda x, y: x+y, [log if isinstance(log, list) else [log] for log in logs], [])
        return self.gen_log_masks(log_bases)

if __name__ == '__main__':
    project_path = r'E:\cc_projects\swang2_cue_tot'
    #project_path = r'E:\cc_projects\swang2_view_mue_harm_dev_int2'
    log = Log(project_path)
    #test_bases = ['LOG_DL_SRP_PD_CONFIG_BASE']
    #log_mask, non_exist_bases = log.gen_log_masks(test_bases)
    log_mask, non_exist_bases = log.get_work_log('ul_crc')
    #log_mask, non_exist_bases = log.get_work_log('ul_cqi')
    if non_exist_bases: print '[Warning]Non-Exist bases: %s' % non_exist_bases
    print 'mask is: %s' % log_mask
