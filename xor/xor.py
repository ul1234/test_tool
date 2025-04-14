#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys

header_file = 'header.iq'
header_num = 256
key = b'\x08\xla\xf1\xfd\x0l\x00\xlc\xl7\xff\x05\x09\xle\x00'

def xor(data, key):
    key_length = len(key)
    result = bytearray()
    for i in range(len(data)):
        result.append(data[i] ^ key[i % key_length])
    return bytes(result)

def enc_file(input_file, out_file):
    byte_array = bytearray(os.path.basename(input_file).encode('utf-8'))

    assert len(byte_array) < 200, "invalid input_file %s" % input_file
    byte_array.extend(b'\x00' * (200 - len(byte_array)))

    with open(input_file, 'rb') as f_read:
        byte_array.extend(f_read.read())

    data_out = xor(byte_array, key)

    with open(header_file, 'rb') as f_read:
        header = bytearray(f_read.read())

    with open(out_file, 'wb') as output_file:
        output_file.write(header)
        output_file.write(data_out)

    print(f"write to {out_file}")

def dec_file(input_file, out_path):
    with open(input_file, 'rb') as f_read:
        byte_array = bytearray(f_read.read())

    data_out = xor(byte_array[header_num:], key)

    dec_filename = data_out[0:200].rstrip(b'\x00').decode('utf-8')
    out_file = os.path.join(out_path, dec_filename)

    with open(out_file, 'wb') as output_file:
        output_file.write(data_out[200:])

    print(f"write to {out_file}")

def get_header(input_file = 'y1_UL1_1.iq'):
    with open(input_file, 'rb') as f_read:
        byte_array = bytearray(f_read.read())

    with open(header_file, 'wb') as output_file:
        output_file.write(byte_array[:header_num])

def enc_files(data_folder, regex_pattern):
    output_id = 0
    for file in os.listdir(data_folder):
        file_path = os.path.join(data_folder, file)
        if os.path.isfile (file_path):
            if re.search(regex_pattern, file):
                enc_file(file_path, os.path.join(data_folder,'yl_UL1_%d.iq' % output_id))
                output_id = output_id + 1

def dec_files(data_folder, regex_pattern, out_path):
    for file in os.listdir(data_folder):
        file_path = os.path.join(data_folder, file)
        if os.path.isfile (file_path):
            if re.search(regex_pattern, file):
                dec_file(file_path, out_path)


if __name__ == "__main__":
    output_file = 'y1_UL1.iq'
    if len(sys.argv) < 2:
        #get_header()
        enc_file('test.txt', 'data.dat')
        dec_file('data.dat', 'output')
    elif len(sys.argv) == 3:
        # python xor.py ./ rar
        enc_files(sys.argv[1], sys.argv[2])
    else:
        # python xor.py ./ iq ./output/
        dec_files(sys.argv[1], sys.argv[2], sys.argv[3])



