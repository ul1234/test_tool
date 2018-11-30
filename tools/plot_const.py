#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, re, sys
import numpy as np
import matplotlib.pyplot as plt


#filename = r'E:\03.Matlab\NR\data\nokia_10.txt'
#data_log_keyword = 'LOG_NR_L0_DL_SRP_PDCCH_PHASE_COMP_FFT_DATA'

def load_data_dsp_log(filename, data_log_keyword):
    data_all = [];
    with open(filename, 'r') as f:
        for line in f:
            s = re.search(r'%s\(' % data_log_keyword, line.strip())
            if s:
                data = re.findall(r'\s*([-+\d\.]+)(?:,|\))', line.strip())
                data_all += [float(x) for x in data[1:]]
    complex_data = {}
    complex_data['real'] = data_all[::2]
    complex_data['imag'] = data_all[1::2]
    return complex_data

def plot_data(filename, data_log_keyword):
    data = load_data_dsp_log(filename, data_log_keyword)
    #print data['real']
    #print data['imag']

    data_power = [data['real'][i]*data['real'][i] + data['imag'][i]*data['imag'][i] for i in range(0,len(data['real']))]

    plt.figure(1)
    plt.plot(range(0, len(data_power)), data_power, '*-')
    plt.grid()

    plt.figure(2)
    plt.plot(data['real'], data['imag'], '*')
    plt.grid()

    plt.show()

def print_usage():
    print 'Usage: plot_const {filename} {keyword}'

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print_usage()
    else:
        try:
            filename = sys.argv[1]
            keyword = sys.argv[2]
            plot_data(filename, keyword)
        except Exception as e:
            print(str(e) + '\n')
            print traceback.format_exc()
            print_usage()
