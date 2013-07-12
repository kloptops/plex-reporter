#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

"""
tool-toggle-gz.py

Created by Jacob Smith on 2013-07-12.
Copyright (c) 2013 Jacob Smith. All rights reserved.
"""

import os
import gzip
import json
from glob import glob as file_glob
from lockfile import LockFile


def read_from_write_to(in_stream, out_stream):
    while True:
        data = in_stream.read(4096)
        if len(data) == 0:
            break
        out_stream.write(data)
    return

def main():
    if not os.path.isdir('logs'):
        os.mkdir('logs')

    config_file = os.path.join('logs', 'state.cfg')

    if os.path.isfile(config_file):
        with open(config_file, 'rU') as file_handle:
            config = json.load(file_handle)
    else:
        config = {
            'mode': 'text',
            'last_datetime': '2000-1-1-0-0-0-0',
            'log_filename': 'plex-media-server-{datetime[0]:04d}-{datetime[1]:02d}-{datetime[2]:02d}.log',
            'log_match': 'plex-media-server-*.log*',
            }

    log_match = os.path.join('logs', config['log_match'])

    total_before = 0
    total_after = 0

    if config['mode'] == 'text':
        print('Enabling compression...')
        config['mode'] = 'gzip'
        config['log_filename'] = config['log_filename'] + '.gz'

        for log_name in file_glob(log_match):
            # Shouldn't happen, but it might?
            if log_name.endswith('.gz'):
                continue

            new_log_name = log_name + '.gz'

            print('  Compressing {0} ...'.format(log_name))
            with gzip.open(new_log_name, 'wt') as out_fh, open(log_name, 'rt') as in_fh:
                read_from_write_to(in_fh, out_fh)

            new_log_size = os.stat(new_log_name).st_size
            log_size = os.stat(log_name).st_size

            total_before += log_size
            total_after += new_log_size

            print('  Original size {0} bytes'.format(log_size))
            print('  New size {0} bytes ({1:0.02f}% of original file)'.format(
                new_log_size, (new_log_size / float(log_size) * 100)))

            os.unlink(log_name)
    elif config['mode'] == 'gzip':
        print('Disabling compression...')
        config['mode'] = 'text'
        if config['log_filename'].endswith('.gz'):
            config['log_filename'] = config['log_filename'][:-3]

        for log_name in file_glob(log_match):
            # Shouldn't happen, but it might?
            if not log_name.endswith('.gz'):
                continue

            new_log_name = log_name[:-3]

            print('  Decompressing {0} ...'.format(log_name))
            with open(new_log_name, 'wt') as out_fh, gzip.open(log_name, 'rt') as in_fh:
                read_from_write_to(in_fh, out_fh)

            new_log_size = os.stat(new_log_name).st_size
            log_size = os.stat(log_name).st_size

            total_before += log_size
            total_after += new_log_size

            print('  Original size {0} bytes'.format(log_size))
            print('  New size {0} bytes ({1:0.02f}% of original file)'.format(
                new_log_size, (new_log_size / float(log_size) * 100)))

            os.unlink(log_name)

    with open(config_file, 'w') as file_handle:
        json.dump(config, file_handle, sort_keys=True, indent=4)

    print('Logs size:')
    print(' Before: {0}'.format(total_before))
    print('  After: {0}'.format(total_after))

if __name__ == '__main__':
    with LockFile() as lf:
        main()
