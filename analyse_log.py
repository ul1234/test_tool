#!/usr/bin/python
# -*- coding: utf-8 -*-

import re


class Buffer(object):
    def __init__(self):
        self.data = {}
        
    def save(self, block):
        sfn_str = str(block.cur_sfn)
        block_name = block.__class__.__name__
        if not sfn_str in self.data: self.data[sfn_str] = {}
        if not block_name in self.data[sfn_str]: self.data[sfn_str][block_name] = {}
        self.data[sfn_str][block_name]['lines'] = block.lines[:]
        for param in block.params:
            self.data[sfn_str][block_name][param] = getattr(block, param)

    def write(self, out_file):
        with open(out_file, 'w') as f_write:
            for sfn, dict in self.data.items():
                f_write.write('\nSFN: %s\n' % sfn)
                for block_name, params in dict.items():
                    f_write.write('block_name: %s\n' % block_name)
                    for name, value in params.items():
                        f_write.write('%s: %s\n' % (name, value))
        
class Block(object):
    def __init__(self, buffer):
        self.buffer = buffer
        self.init()
        self.reset()
        
    def sfn(self, content):
        r = re.search(self.sfn_regex, content, flags = re.IGNORECASE)
        if r:
            sfn = [r.group(1), r.group(2), r.group(3)]
            return sfn
        return []
                    
    def start_sfn(self, keyword, content):
        return self.sfn(content) if keyword.find(self.key) >= 0 else []
        
    def finish(self, save_flag = True):
        if save_flag: self.buffer.save(self)
        self.reset()
        
    def reset(self):
        self.lines = []
        self.cur_sfn = []
        self.reset_params()
        
    def is_exclude_key(self, keyword):
        if not hasattr(self, 'exclude_keys'): return False
        for key in self.exclude_keys:
            if keyword.find(key) >= 0: return True
        return False
        
    def feed(self, line_num, keyword, content):
        start_sfn = self.start_sfn(keyword, content)
        if start_sfn:
            if not self.cur_sfn:
                self.cur_sfn = start_sfn
            elif start_sfn != self.cur_sfn:
                self.finish()
                self.cur_sfn = start_sfn
        elif self.is_exclude_key(keyword):
            self.finish()
        if content.find('FLOW_CTRL') >= 0:  # flow control
            self.finish(save_flag = False)
        else:
            self.lines.append(line_num)
            if hasattr(self, 'parse_param'):
                self.parse_param(keyword, content)
            
    def reset_params(self):
        for param in self.params:
            setattr(self, param, None)

class PdcchMsgBlock(Block):
    def init(self):
        self.key = 'LOG_NR_L0_DLC_PDCCH_BRP_MSG_TO'
        self.sfn_regex = r'Sfn: (\d+), SubframeNum: (\d+), SlotNum: (\d+)'
        self.exclude_keys = ['LOG_NR_L0_ULSRP_PUCCH_MAP_MSG_END']
        self.params = ['new_tx']
        
    def parse_param(self, keyword, content):
        # NewTx
        regex = r'bNewTx: (\w+),'
        r = re.search(regex, content, flags = re.IGNORECASE)
        if r:
            self.new_tx = True if r.group(1) == 'True' else False

class PdschDataBlock(Block):
    def init(self):
        self.key = 'LOG_NR_L0_DL_SRP_PDSCH'
        self.sfn_regex = r'Sfn: (\d+), Subframe: (\d+), Slot: (\d+), Symbol: (\d+)'
        self.params = []

class CrcBlock(Block):
    def init(self):
        self.key = 'LOG_NR_L0_PDSCH_BRP_CRC_RSLT_IND'
        self.sfn_regex = r'Sfn: (\d+), Subframe: (\d+), Slot: (\d+)'
        self.params = ['crc']

    def parse_param(self, keyword, content):
        #CrcRsltCw0: Pass
        regex = r'CrcRsltCw0: (\w+),'
        r = re.search(regex, content, flags = re.IGNORECASE)
        if r:
            self.crc = r.group(1)

class Parser(object):
    def __init__(self, buffer):
        self.blocks = [PdcchMsgBlock(buffer), PdschDataBlock(buffer), CrcBlock(buffer)]
        self.cur_block = None
        
    def feed(self, line_num, keyword, content):
        for block in self.blocks:
            if not block is self.cur_block:
                if block.start_sfn(keyword, content):
                    if self.cur_block: self.cur_block.finish()
                    self.cur_block = block
        if self.cur_block:
            is_block_end = self.cur_block.feed(line_num, keyword, content)
            if is_block_end: self.cur_block = None
        
class LogAnalyser(object):
    def __init__(self):
        self.buffer = Buffer()
        self.parser = {}
        
    def analyse_log(self, filename, output_file):
        # 62.153572685:   LTE HLC 0.3.0	LOG_NR_L0_DL_SRP_PDSCH_PHASE_COMP_FFT_HDR(
        line_regex = r'^([\d\.]+):\D+([\d\.]+)\s([\w_]+)\((.*?)\)'
        with open(filename, 'r') as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if line:
                    r = re.search(line_regex, line, flags = re.IGNORECASE)
                    if not r:
                        self.tool.print_('Invalid line: %s' % line)
                        continue
                    t, server, keyword, content = r.groups()
                    if not server in self.parser: self.parser[server] = Parser(self.buffer)
                    self.parser[server].feed(line_num+1, keyword, content)
        self.buffer.write(output_file)


if __name__ == '__main__':
    log_analyser = LogAnalyser()
    log_analyser.analyse_log('temp/log.txt', 'temp/log_analyse.txt')
    
    
                    