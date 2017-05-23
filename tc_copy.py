#!/usr/bin/python
# -*- coding: utf-8 -*-

from cache_manager import CacheManager
import shutil, os

base_dir = os.path.dirname(os.path.abspath(__file__))
__file__ = os.path.join(base_dir, 'remote_run.pyw')

class TCCopy:
    def __init__(self):
        self.temp_filename = 'remote_run_temp.pyw'
        self.cache_folder = '.cache'
        self.temp_file = os.path.join(base_dir, self.temp_filename)
        self.dest_temp_file = os.path.join(base_dir, self.cache_folder, self.temp_filename)
        self.cm = CacheManager()
        self.copy_temp_file()

    def copy_temp_file(self):
        if not os.path.isdir(self.cache_folder): raise 'no .cache folder found!'
        if not os.path.isfile(self.temp_file): raise 'no %s file found!' % self.temp_file
        if os.path.isfile(self.dest_temp_file): os.remove(self.dest_temp_file)
        shutil.copyfile(self.temp_file, self.dest_temp_file)

    def run(self):
        self.cm.run(self.temp_file)
        print 'remote run finished, deleting the temp file.'
        if os.path.isfile(self.dest_temp_file): os.remove(self.dest_temp_file)

if __name__ == '__main__':
    tc_copy = TCCopy()
    tc_copy.run()
