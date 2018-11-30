#!/usr/bin/python
# -*- coding: utf-8 -*-

import hashlib, re, os, sys, traceback
import pprint
from datetime import datetime, timedelta
import cPickle as pickle
import base64, zlib
import zipfile, base64

class WinCmd:
    SHOW_CMD_STRING = False;

    @staticmethod
    def del_dir(dest_dir, include_dir = False, show_error_msg = True):
        if os.path.isdir(dest_dir):
            output = '> nul 2>&1' if not show_error_msg else ''
            WinCmd.cmd(r'rmdir /s /q "%s" %s' % (dest_dir, output))
        if not include_dir:
            WinCmd.make_dir(dest_dir)

    @staticmethod
    def del_file(file):
        if os.path.isfile(file): os.remove(file)
        if os.path.isfile(file): raise Exception('cannot delete file %s' % file)

    @staticmethod
    def is_folder_empty(dest_dir):
        return len(os.listdir(dest_dir)) == 0

    @staticmethod
    def make_dir(dest_dir):
        for try_times in range(5):
            if os.path.isdir(dest_dir): break
            try:
                os.makedirs(dest_dir)
            except:
                time.sleep(1)
        if not os.path.isdir(dest_dir): raise Exception('cannot create directory in %d times: %s' % (try_times, dest_dir))

    @staticmethod
    def copy_file(src_file, dest, dest_is_dir = True):
        if not os.path.isfile(src_file):
            raise Exception('no such file: %s' % src_file)
        if dest_is_dir and not os.path.isdir(dest):
            raise Exception('no such directory: %s' % dest)
        WinCmd.cmd(r'copy /y "%s" "%s" > nul' % (src_file, dest))  # no output info
        dest_file = dest if not dest_is_dir else os.path.join(dest, os.path.basename(src_file))
        if not os.path.isfile(dest_file) or os.path.getmtime(src_file) != os.path.getmtime(dest_file):
            raise Exception('cannot copy file to %s' % dest_file)

    @staticmethod
    def cmd(command, path = None, showcmdwin = False, minwin = False, wait = True, retaincmdwin = False, title = ''):
        path_str = r'cd /d "%s" & ' % path if path else ''
        if showcmdwin:
            min_str = r'/min' if minwin else ''
            title_str = r'title %s & ' % title if title else ''
            wait_str = '/wait' if wait else ''
            retain_str = '/k' if retaincmdwin else '/c'
            cmd_str = r'start %s %s cmd.exe %s "%s%s%s"' % (min_str, wait_str, retain_str, title_str, path_str, command)
        else:
            cmd_str = r'%s%s' % (path_str, command)
        if WinCmd.SHOW_CMD_STRING: print '[RUN CMD] %s' % cmd_str
        os.system(cmd_str)


class ZipUtil:
    @staticmethod
    def zip(src_files, zip_file, base_path = None, compress = True):
        filelist = []
        for src_file in src_files:
            if not os.path.exists(src_file): raise Exception('%s not exists.' % src_file)
            if os.path.isfile(src_file):
                filelist.append(src_file)
            else:
                for root, dirs, files in os.walk(src_file):
                    for name in files:
                        filelist.append(os.path.join(root, name))
        if compress:
            zf = zipfile.ZipFile(zip_file, "w", zipfile.zlib.DEFLATED)
        else:
            zf = zipfile.ZipFile(zip_file, "w", zipfile.ZIP_STORED)
        if not base_path:
            if len(src_files) == 1:
                base_path = os.path.dirname(src_files[0])
            else:
                base_path = os.path.dirname(os.path.commonprefix([p + os.path.sep if os.path.isdir(p) else p for p in src_files]))
        for file in filelist:
            if not os.path.commonprefix([file, base_path]) == base_path:
                file_in_zip = os.path.basename(file)
            else:
                file_in_zip = os.path.relpath(file, base_path)
            zf.write(file, file_in_zip)
        zf.close()

    @staticmethod
    def unzip(zip_file, dest_dir):
        if not os.path.exists(dest_dir): os.makedirs(dest_dir)
        zfobj = zipfile.ZipFile(zip_file)
        for name in zfobj.namelist():
            name = name.replace('\\','/')
            if name.endswith('/'):
                os.makedirs(os.path.join(dest_dir, name))
            else:
                ext_filename = os.path.join(dest_dir, name)
                ext_dir = os.path.dirname(ext_filename)
                if not os.path.exists(ext_dir) : os.makedirs(ext_dir)
                with open(ext_filename, 'wb') as f:
                    f.write(zfobj.read(name))

    @staticmethod
    def b64enc(src_file, dest_file):
        with open(src_file, 'rb') as src:
            with open(dest_file, 'w') as dest:
                base64.encode(src, dest)

    @staticmethod
    def b64dec(src_file, dest_file):
        with open(src_file, 'r') as src:
            with open(dest_file, 'wb') as dest:
                base64.decode(src, dest)


class FileZipTool(object):
    def __init__(self):
        #self.change_rules = {'^firmware.pkg$': [(48, 30), (-1, 4)],
        #                     '^c.*.out$': [('Build time', 30), (-1, 4)]}
        self.change_rules = {}
        self.local_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)))
        self.local_temp_folder = os.path.join(self.local_folder, 'temp')
        if not os.path.isdir(self.local_temp_folder): WinCmd.make_dir(self.local_temp_folder)
        self.tmp_info_file = os.path.join(self.local_temp_folder, 'temp_info_file.txt')

    def check_file_exist(self, filename, can_be_empty = False):
        if not can_be_empty and not filename: raise Exception('file can not be empty: %s' % filename)
        if filename and not os.path.isfile(filename): raise Exception('file not found: %s' % filename)

    def check_folder_exist(self, folder, can_be_empty = False):
        if not can_be_empty and not folder: raise Exception('folder can not be empty: %s' % folder)
        if folder and not os.path.isdir(folder): raise Exception('folder not found: %s' % folder)

    def print_(self, str):
        #pprint.pprint(str)
        print('[%s]%s' % (datetime.now().strftime('%I:%M:%S'), str))

    def _hash_block(self, filename, hash_handle = None):
        block_len = 100000000  # 100K bytes
        with open(filename, 'rb') as f:
            if hash_handle is None: hash_handle = hashlib.md5()
            while True:
                data = f.read(block_len)
                if not data: break
                hash_handle.update(data)
            return (hash_handle.hexdigest(), hash_handle)

    def hash_folder(self, folder):
        hash_handle = hashlib.md5()
        for dir_path, subpaths, files in os.walk(folder):
            for file in files:
                filename = os.path.join(dir_path, file)
                _, hash_handle = self._hash_block(filename, hash_handle)
        return hash_handle.hexdigest()

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
        else:
            return 'not_equal'

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

    def check_7z_tool_exist(self):
        file_7z_tool = ['7z.exe', '7z.dll']
        for f in file_7z_tool:
            filename = os.path.join(self.local_folder, f)
            self.check_file_exist(filename)

    def zip_7z_folder(self, folder, ref_folder, zip_file):
        self.check_7z_tool_exist()
        file_zip = '%s.zip' % os.path.splitext(zip_file)[0]
        md5 = self.zip_folder(folder, ref_folder, file_zip, compress = False)
        file_7z = '%s.7z' % os.path.splitext(zip_file)[0]
        if os.path.isfile(file_7z): WinCmd.del_file(file_7z)
        WinCmd.cmd(r'7z a %s %s' % (file_7z, file_zip), showcmdwin = True, wait = True)
        WinCmd.del_file(file_zip)
        self.print_('zip files to %s successfully!, folder MD5: %s' % (file_7z, md5))

    def unzip_7z_folder(self, file_7z, ref_folder, dest_folder = ''):
        self.check_7z_tool_exist()
        self.check_file_exist(file_7z)
        self.check_folder_exist(ref_folder)
        dest_folder = dest_folder or os.path.splitext(file_7z)[0]
        if os.path.isdir(dest_folder): raise Exception('output folder %s already exist, please delete the folder!' % dest_folder)
        WinCmd.make_dir(dest_folder)

        file_zip = '%s.zip' % os.path.splitext(file_7z)[0]
        if os.path.isfile(file_zip): WinCmd.del_file(file_zip)
        WinCmd.cmd(r'7z e %s' % file_7z, showcmdwin = True, wait = True)
        if not os.path.isfile(file_zip): raise Exception('unzip 7z file fail. %s not found!' % file_zip)
        self.unzip_folder(file_zip, ref_folder, dest_folder)
        WinCmd.del_file(file_zip)

    def zip_folder(self, folder, ref_folder, zip_file, compress = True):
        self.check_folder_exist(folder)
        self.check_folder_exist(ref_folder)
        if os.path.isdir(zip_file): raise Exception('zip file cannot be a folder.')
        if os.path.isfile(zip_file): WinCmd.del_file(zip_file)

        not_equal_files = []
        folder_info = {}
        folder_info['md5'] = self.hash_folder(folder)
        for dir_path, subpaths, files in os.walk(folder):
            for file in files:
                filename = os.path.join(dir_path, file)
                ref_file = os.path.join(ref_folder, os.path.relpath(filename, folder))
                file_info = self.get_file_info(filename)
                if os.path.isfile(ref_file):
                    file_info['cmp_result'] = self.cmp_file(ref_file, file_info)
                else:
                    file_info['cmp_result'] = 'not_equal'
                if file_info['cmp_result'] == 'not_equal':
                    not_equal_files.append(filename)
                folder_info[os.path.relpath(filename, folder)] = file_info
        folder_info_str = self.object_to_string(folder_info)
        if os.path.isfile(self.tmp_info_file): WinCmd.del_file(self.tmp_info_file)
        open(self.tmp_info_file, 'w').write(folder_info_str)
        not_equal_files.append(self.tmp_info_file)
        ZipUtil.zip(not_equal_files, zip_file, base_path = folder, compress = compress)
        #self.print_('zip file successfully! MD5: %s' % folder_info['md5'])
        return folder_info['md5']

    def unzip_folder(self, zip_file, ref_folder, dest_folder):
        self.check_file_exist(zip_file)
        self.check_folder_exist(ref_folder)
        self.check_folder_exist(dest_folder)
        if not WinCmd.is_folder_empty(dest_folder): raise Exception('the dest folder is not empty!')
        ZipUtil.unzip(zip_file, dest_folder)
        folder_info_file = os.path.join(dest_folder, os.path.basename(self.tmp_info_file))
        folder_info_str = open(folder_info_file, 'r').read()
        folder_info = self.string_to_object(folder_info_str)

        for filename, file_info in folder_info.items():
            ref_file = os.path.join(ref_folder, filename)
            dest_file_folder = os.path.join(dest_folder, os.path.dirname(filename))
            if not os.path.isdir(dest_file_folder): os.makedirs(dest_file_folder)
            if os.path.isfile(ref_file):
                result = self.cmp_file(ref_file, file_info)
                if result != file_info['cmp_result'] and result == 'not_equal':
                    raise Exception('check file %s not match!' %  filename)
                if result == 'equal':
                    WinCmd.copy_file(ref_file, dest_file_folder)
                elif result == 'partial_equal':
                    self.copy_file_with_info(file_info, ref_file, dest_file_folder)
        WinCmd.del_file(folder_info_file)
        md5 = self.hash_folder(dest_folder)
        if folder_info['md5'] == md5:
            self.print_('Unzip files to %s successfully! MD5 check pass! MD5: %s' % (dest_folder, md5))
        else:
            self.print_('Unzip files to %s fail! MD5 check fail! send MD5: %s, rebuilt MD5: %s' % (dest_folder, folder_info['md5'], md5))

if __name__ == '__main__':
    tool = FileZipTool()
    debug = 0
    if debug == 1:
        #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_\fw\firmware.pkg')
        #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_\cpu16.out')
        #pprint.pprint(info)
        #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_\cpu16.out')
        #info = tool.get_file_info(r'E:\tool\test\trans\swang2_CUE_tot_debug_EXTMUE_1\fw\firmware.pkg')
        #pprint.pprint(info)
        #info = tool.zip_folder(r'E:\build_codes\00_binary\swang2_view_cue_8x8_checkin_1_ls2', r'E:\build_codes\00_binary\swang2_view_cue_8x8_checkin_1_ls2_bak', 'temp/test.zip')
        tool.unzip_folder('temp/test.zip', r'E:\build_codes\00_binary\swang2_view_cue_8x8_checkin_1_ls2_bak', 'temp/dest')
        #s = tool.object_to_string(info)
        #print len(s)
        ##pprint.pprint(s)
        #i = tool.string_to_object(s)
        ##pprint.pprint(i)
        #
        #remain_files = tool.copy_folder_with_info(i, r'E:\tool\test\trans\swang2_view_mue_ul_harm_int_2x2_FDD_1', r'E:\tool\test\trans\test_folder')
        #print remain_files
        print 'done'
    else:
        def print_usage():
            print 'Usage for ZIP: python fileziptool.py zip {zip_folder} {reference_folder} {zip_file}'
            print 'Usage for UNZIP: python fileziptool.py unzip {zip_file} {reference_folder}'
        # python fileziptool.py zip {zip_folder} {reference_folder} {zip_file}
        # python fileziptool.py unzip {zip_file} {reference_folder}
        if len(sys.argv) < 2:
            print_usage()
        else:
            action = sys.argv[1]
            try:
                if action.lower() == 'zip':
                    if len(sys.argv) < 5:
                        print_usage()
                    else:
                        zip_folder = sys.argv[2]
                        ref_folder = sys.argv[3]
                        zip_file = sys.argv[4]
                        tool.zip_7z_folder(zip_folder, ref_folder, zip_file)
                elif action.lower() == 'unzip':
                    if len(sys.argv) < 4:
                        print_usage()
                    else:
                        file_7z = sys.argv[2]
                        ref_folder = sys.argv[3]
                        tool.unzip_7z_folder(file_7z, ref_folder)
                else:
                    print_usage()
            except Exception as e:
                print(str(e) + '\n')
                print traceback.format_exc()
                print_usage()

