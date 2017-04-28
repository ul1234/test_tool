#!/usr/bin/python
# -*- coding: utf-8 -*-

import hashlib, re, os
import pprint
import cPickle as pickle
import base64, zlib
from wincmd import WinCmd

class FileTool(object):
    def __init__(self):
        self.change_rules = {'^firmware.pkg$': [(48, 30), (-1, 4)],
                             '^c.*.out$': [('Build time', 30), (-1, 4)]}

    def print_(self, str):
        #pprint.pprint(str)
        print('[%s]%s' % (datetime.now().strftime('%I:%M:%S'), str))

    def _hash_block(filename):
        block_len = 1000000000  # 1M bytes
        with open(filename, 'rb') as f:
            h = hashlib.md5()
            while True:
                data = f.read(block_len)
                if not data: break
                h.update(data)
            return h.hexdigest()

    def _hash(self, buf, info = []):
        h = hashlib.md5()
        if not info: h.update(buf)
        for start, len in info:
            h.update(buf[start:start+len])
        return h.hexdigest()

    def _split_buf(self, src_buf, drop_buf):
        src_start, src_end = src_buf[0], src_buf[0] + src_buf[1]
        drop_start, drop_end = drop_buf[0], drop_buf[0] + drop_buf[1]
        if drop_start <= src_start:
            if drop_end <= src_start: return [src_buf]
            elif drop_end >= src_end: return []
            else: return [(drop_end, src_end - drop_end)]
        elif drop_start >= src_end:
            return [src_buf]
        else:
            if drop_end >= src_end: return [(src_start, drop_start - src_start)]
            else: return [(src_start, drop_start - src_start), (drop_end, src_end - drop_end)]

    def _get_split_buf_info(self, buf_len, rules_info):
        return reduce(lambda src_buf_info, rule_info: sum([self._split_buf(src, rule_info) for src in src_buf_info], []), rules_info, [(0, buf_len)])

    def _get_file_rules(self, filename):
        for name, rules in self.change_rules.items():
            if re.search(name, os.path.basename(filename)):
                return rules
        return []

    def get_file_info(self, filename):
        buf = open(filename, 'rb').read()
        rules_info, rules_data = [], []
        
        for start, length in self._get_file_rules(filename):
            if isinstance(start, basestring):
                pos = buf.find(start)
                if pos < 0: continue
                rules_info.append((pos, length))
                rules_data.append(buf[pos + len(start):pos + len(start)+length])
            elif start == -1:
                rules_info.append((len(buf)-length, length))
                rules_data.append(buf[-length:])
            else:
                rules_info.append((start, length))
                rules_data.append(buf[start:start+length])

        file_info = {}
        file_info['file_hash'] = self._hash(buf)
        file_info['file_len'] = len(buf)
        if rules_info:
            src_buf_info = self._get_split_buf_info(len(buf), rules_info)
            file_info['rules_data'] = rules_data
            file_info['rules_info'] = rules_info
            file_info['rules_hash'] = self._hash(buf, src_buf_info)
        return file_info

    def cmp_file(self, filename, file_info):
        buf = open(filename, 'rb').read()
        hash = self._hash(buf)
        file_len = len(buf)
        if file_len != file_info['file_len']: return 'not_equal'
        if hash == file_info['file_hash']: return 'equal'
        if 'rules_info' in file_info:
            src_buf_info = self._get_split_buf_info(file_len, file_info['rules_info'])
            if file_info['rules_hash'] != self._hash(buf, src_buf_info): return 'not_equal'
            return 'partial_equal'

    def copy_file_with_info(self, file_info, ref_file, dest_folder):
        if not 'rules_info' in file_info or not 'rules_data' in file_info: raise Exception('%s should should have rules!' % ref_file)
        buf = open(ref_file, 'rb').read()
        rules_info, rules_data = file_info['rules_info'], file_info['rules_data']
        src_buf_info = self._get_split_buf_info(len(buf), rules_info)
        src_buf = [buf[start:start+length] for start, length in src_buf_info]
        first_buf, second_buf = (src_buf, rules_data) if src_buf_info[0][0] == 0 else (rules_data, src_buf)
        if len(second_buf) < len(first_buf): second_buf.append('')
        result_buf = reduce(lambda x,(i,j): x+i+j, zip(first_buf, second_buf), '')

        with open(os.path.join(dest_folder, os.path.basename(ref_file)), 'wb') as f:
            f.write(result_buf)

    def copy_folder_with_info(self, folder_info, ref_folder, dest_folder):
        WinCmd.del_dir(dest_folder)
        not_equal_files = []
        for filename, file_info in folder_info.items():
            ref_file = os.path.join(ref_folder, filename)
            dest_file_folder = os.path.join(dest_folder, os.path.dirname(filename))
            if not os.path.isdir(dest_file_folder): os.makedirs(dest_file_folder)
            if os.path.isfile(ref_file):
                result = self.cmp_file(ref_file, file_info)
                if result == 'equal':
                    WinCmd.copy_file(ref_file, dest_file_folder)
                elif result == 'partial_equal':
                    self.copy_file_with_info(file_info, ref_file, dest_file_folder)
                else:  # 'not_equal'
                    not_equal_files.append(filename)
            else:
                not_equal_files.append(filename)
        return not_equal_files

    def gen_folder_info(self, folder):
        folder_info = {}
        for dir_path, subpaths, files in os.walk(folder):
            for file in files:
                filename = os.path.join(dir_path, file)
                folder_info[os.path.relpath(filename, folder)] = self.get_file_info(filename)
        return folder_info

    def object_to_string(self, info):
        return base64.b64encode(zlib.compress(pickle.dumps(info), zlib.Z_BEST_COMPRESSION))

    def string_to_object(self, s):
        return pickle.loads(zlib.decompress(base64.b64decode(s)))

if __name__ == '__main__':
    tool = FileTool()
    #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_\fw\firmware.pkg')
    #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_\cpu16.out')
    #pprint.pprint(info)
    #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_\cpu16.out')
    #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_1\fw\firmware.pkg')
    #pprint.pprint(info)
    info = tool.gen_folder_info(r'E:\tool\test\trans\swang2_view_mue_ul_harm_int_2x2_FDD')
    s = tool.object_to_string(info)
    print len(s)
    #pprint.pprint(s)
    i = tool.string_to_object(s)
    #pprint.pprint(i)
    
    remain_files = tool.copy_folder_with_info(i, r'E:\tool\test\trans\swang2_view_mue_ul_harm_int_2x2_FDD_1', r'E:\tool\test\trans\test_folder')
    print remain_files
    print 'done'

