#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys
from datetime import datetime
from wincmd import WinCmd


class TC:
    def __init__(self):
        self.init_folders()

    def print_(self, str, output_time = True):
        if output_time:
            print('[%s]%s' % (datetime.now().strftime('%H:%M:%S'), str))
        else:
            print(str)
        sys.stdout.flush()

    def init_folders(self, working_folder = ''):
        working_folder = working_folder or r'C:\Projects\swang2_view_cue_tot'
        self.working_folder = working_folder
        self.input_vectors_check_folder = r'\\ubimelfs.aeroflex.corp\ubinetics\Development\Projects\AAS_TM500_LTE\User_Working_Folders\WangShouliang'
        self.tc_folder = os.path.join(working_folder, r'tm_build_system\teamcity')
        self.cache_folder = os.path.join(self.tc_folder, r'.cache')
        self.dest_folder = os.path.join(self.tc_folder, r'.cache\temp')
        self.batch_folder = os.path.join(self.dest_folder, r'Batch')
        self.bat_folder = os.path.join(self.dest_folder, r'BatchFiles')
        self.bin_folder = os.path.join(self.dest_folder, r'ftp')
        self.pyd_folder = os.path.join(self.dest_folder, r'pyd')
        self.test_case_folder = os.path.join(self.dest_folder, r'TestCases')
        self.vec_folder = os.path.join(self.dest_folder, r'Vectors')
        self.output_file = os.path.join(self.cache_folder, 'upload_files.txt')
        self.comment_file = os.path.join(self.cache_folder, 'comments.txt')
        self.mapping_file = os.path.join(self.cache_folder, 'mapping.txt')

    def empty_dest_folder(self, empty_bin_folder = False):
        if empty_bin_folder:
            WinCmd.del_dir(self.dest_folder)
        else:
            if os.path.isdir(self.dest_folder):
                for d in os.listdir(self.dest_folder):
                    folder = os.path.join(self.dest_folder, d)
                    if not d in [os.path.basename(self.bin_folder), os.path.basename(self.pyd_folder)]:
                        WinCmd.del_dir(folder, include_dir = True)
        WinCmd.del_file(self.output_file)

    def copy_binary(self, bin_path, pyd_path = ''):
        self.print_('start to copy binary...')
        if not bin_path or not os.path.isdir(bin_path): raise Exception('no valid binary path: %s.' % bin_path)
        WinCmd.copy_dir(bin_path, self.bin_folder, empty_dest_first = True)
        pyd_path = pyd_path or os.path.join(bin_path, '_pyd')
        if not os.path.isdir(pyd_path): raise Exception('no valid pyd path: %s.' % pyd_path)
        WinCmd.copy_dir(pyd_path, self.pyd_folder, empty_dest_first = True)
        open(self.comment_file, 'w').write(os.path.basename(bin_path))
        self.print_('copy binary from %s successfully!' % bin_path)

    def gen_vec_list_file(self, vectors):
        # the vector must be somewhere under the folder '\\ubimelfs.aeroflex.corp\ubinetics\Development\Projects\AAS_TM500_LTE\User_Working_Folders\WangShouliang'
        checked_vectors = []
        for vec in vectors:
            vec = vec.replace(r'P:', r'\\ubimelfs.aeroflex.corp\ubinetics\Development\Projects')
            if not WinCmd.is_subfolder(vec, self.input_vectors_check_folder): raise Exception(r'vector must be under user folder(P:), %s' % vec)
            if not os.path.isfile(vec): raise Exception(r'vector not found, %s' % vec)
            checked_vectors.append(vec)
        vec_list_file = os.path.join(self.vec_folder, 'vectorList.txt')
        if checked_vectors:
            if not os.path.isdir(os.path.dirname(vec_list_file)): WinCmd.make_dir(os.path.dirname(vec_list_file))
            with open(vec_list_file, 'w') as f_write:
                for v in checked_vectors: f_write.write(v + '\n')
        self.print_('gen vectorList file (include %d vectors) successfully!' % len(checked_vectors))

    def copy_batches(self, batches, rav_config, rav_type = '', umbra_update = False, run_times = 1):
        self.copy_cases(batches)
        WinCmd.copy_files(batches, self.batch_folder, empty_dir_first = True)
        if run_times > 1:
            for batch_file in batches:
                self._change_batch_run_times(os.path.join(self.batch_folder, os.path.basename(batch_file)), run_times)
        if os.path.isdir(self.bat_folder):
            WinCmd.del_dir(self.bat_folder)
        else:
            WinCmd.make_dir(self.bat_folder)
        rav_type = rav_type or rav_config
        bat_path = os.path.join(self.bat_folder, rav_type.upper())
        self._gen_bat_file(bat_path, batches, rav_config.upper(), umbra_update)
        self.print_('copy %d batches (each case %d times) successfully!' % (len(batches), run_times))

    def _gen_bat_file(self, bat_path, batches, rav_config, umbra_update = False):
        if not os.path.isdir(bat_path): WinCmd.make_dir(bat_path)
        bat_file = os.path.join(bat_path, 'RunBatchFiles.bat')
        rav_config_str = '' if not rav_config or rav_config == 'default' else r' -s %%RAV_STATION_NAME%%-%s' % rav_config
        with open(bat_file, 'w') as f_write:
            f_write.write('cd %AUTO_TEST_HOME%\\Testing\\python\\' + '\n')
            if(umbra_update): f_write.write(r'call python ttm_runner.py %%firmwareUpdateBatch%%%s' % rav_config_str + '\n')
            for batch in batches:
                f_write.write(r'call python ttm_runner.py %s%s' % (os.path.basename(batch), rav_config_str) + '\n')

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
                    elif not line.lower().endswith('txt'): raise Exception('case error: %s, in batch %s' % (line, batch))
                    else: cases.append(line)
                else:
                    batch_head.append(line)
                    if line.startswith('tests_start'): start_flag = True
        return cases, batch_head

    def _change_batch_run_times(self, batch_file, run_times = 1):
        if not os.path.isfile(batch_file): raise Exception('no file found! %s' % batch_file)
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

    def copy_cases(self, batches, copy_case = True):
        files = []
        for batch in batches:
            folder = os.path.dirname(batch)
            files += [os.path.join(folder, c) for c in self._get_batch_cases(batch)[0] if os.path.isfile(os.path.join(folder, c))]
        if files and copy_case:
            WinCmd.copy_files(files, self.test_case_folder, empty_dir_first = True)
            self.print_('copy %d test cases successfully!' % len(files))

    def gen_all_upload_files(self, mk = 'MK3'):
        if not mk in ['MK1', 'MK3', 'MK4.x']: raise Exception('invalid mk: %s' % mk)

        files_num = 0
        with open(self.output_file, 'w') as f_write:
            f_write.write(mk + '\n')
            for dir_path, subpaths, files in os.walk(self.dest_folder):
                for f in files:
                    f = os.path.relpath(os.path.join(dir_path, f), self.working_folder)
                    f_write.write(f + '\n')
                    files_num += 1
        self.print_('gen %s (total %d files) successfully!' % (self.output_file, files_num))
        self._gen_mapping_file()

    def _gen_mapping_file(self):
        #temp\ftp=jetbrains.git://|\\stv-teamcitymas.aeroflex.corp\git_projects\remote_run|\ftp
        #temp\pyd=jetbrains.git://|\\stv-teamcitymas.aeroflex.corp\git_projects\remote_run|\ASN
        #temp\Batch=jetbrains.git://|\\stv-teamcitymas.aeroflex.corp\git_projects\remote_run|\BatchFiles
        #temp\BatchFiles\8X82CC=jetbrains.git://|\\stv-teamcitymas.aeroflex.corp\git_projects\remote_run|\BatchFiles\8X82CC
        mapping_middle_str = r'=jetbrains.git://|\\stv-teamcitymas.aeroflex.corp\git_projects\remote_run|' + '\\'
        mapping_list = [[('ftp', r'BatchFiles\*', 'TestCases', 'Vectors'), ''], ['pyd', 'ASN'], ['Batch', 'BatchFiles']]
        with open(self.mapping_file, 'w') as f_write:
            for dir_path, subpaths, files in os.walk(self.dest_folder):
                rel_temp_path = os.path.relpath(dir_path, self.dest_folder)
                if rel_temp_path == '.': continue
                check_path = rel_temp_path if not os.path.dirname(rel_temp_path) else os.path.join(os.path.dirname(rel_temp_path), '*')
                map_path = ''
                for check, map in mapping_list:
                    found = (check_path in check) if isinstance(check, tuple) else check_path == check
                    if found: map_path = map if map else rel_temp_path
                if not map_path:
                    if not rel_temp_path.startswith('ftp') and rel_temp_path != 'BatchFiles': self.print_('Warning: cannot map the path %s' % rel_temp_path)
                else:
                    f_write.write(r'temp\%s%s%s' % (rel_temp_path, mapping_middle_str, map_path) + '\n')
        self.print_('gen %s successfully!' % self.mapping_file)

    def run_tc(self):
        py_copy_file = 'tc_copy.py'
        py_files = [os.path.join(os.path.dirname(__file__), f) for f in [py_copy_file, 'remote_run_temp.pyw']]
        WinCmd.copy_files(py_files, self.tc_folder)
        WinCmd.cmd('python %s' % py_copy_file, self.tc_folder)


if __name__ == '__main__':
    pass
