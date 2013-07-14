#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-
from __future__ import print_function

__license__ = """

The MIT License (MIT)
Copyright (c) 2013 Jacob Smith <kloptops@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the “Software”), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

import os
## Uncomment the next line if you plan on using this script in the windows
## task scheduler
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import sys
import json
import logging
import datetime

from glob import glob as file_glob

# Only import what is needed, don't need requests.
from plex.util import BasketOfHandles, config_load, config_save
from plex.lockfile import LockFile
from plex.parser import PlexLogParser


class PlexSuperLogParser(PlexLogParser):
    def __init__(self, last_datetime, *args, **kwargs):
        super(PlexSuperLogParser, self).__init__(**kwargs)
        self.last_datetime = last_datetime

    def line_body_filter(self, line_body):
        # We don't want old records
        if line_body['datetime'] <= self.last_datetime:
            return False

        # We don't want the useless lines following request lines.
        if 'content' in line_body and line_body['content'].startswith(' *'):
            return False

        return super(PlexSuperLogParser, self).line_body_filter(line_body)


def datetime_diff(date_a, date_b):
    a = datetime.datetime(*date_a)
    b = datetime.datetime(*date_b)
    return a - b


def main():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename='plex-log-saver.log',
        level=logging.DEBUG)

    logging.info('{0:#^40}'.format('[ Plex Log Saver ]'))

    if not os.path.isdir('logs'):
        os.mkdir('logs')

    config_file = os.path.join('logs', 'state.cfg')

    config = config_load(config_file)

    if config['plex_log_dir'] == '':
        logging.info('Config missing "plex_log_dir", Exiting!')
        print('Config missing "plex_log_dir", Exiting!')
        return


    log_file_template = os.path.join(
        'logs', config['log_file_name'])

    if config['log_save_mode'] == 'gzip':
        import gzip
        log_open = gzip.open
    else:
        log_open = open

    last_datetime = tuple(map(int, config['plex_last_datetime'].split('-')))

    log_parser = PlexSuperLogParser(last_datetime)

    all_lines = []

    # We're only interested in 'Plex Media Server.log' log files
    # I've been able to get 90% of the info i need from those logs
    log_file_glob = os.path.join(
        config['plex_log_dir'], 'Plex Media Server.log*')

    for log_file in file_glob(log_file_glob):
        all_lines.extend(log_parser.parse_file(log_file))

    if len(all_lines) == 0:
        logging.info('No new lines, finishing.')
        return

    # Sort the logs based on datetime
    all_lines.sort(key=lambda line_body: line_body['datetime'])

    time_diff = datetime_diff(all_lines[0]['datetime'], last_datetime)

    logging.info('    Last entry last run: {0:04d}-{1:02d}-{2:02d} {3:02d}:{4:02d}:{5:02d}'.format(
        *last_datetime))
    logging.info('Earliest entry this run: {0:04d}-{1:02d}-{2:02d} {3:02d}:{4:02d}:{5:02d}'.format(
        *all_lines[0]['datetime']))


    if time_diff.seconds > 60:
        if time_diff.days > 0:
            logging.warn('Missing {} days of log files'.format(time_diff.days))
        else:
            logging.warn('Possibly missing {} seconds of log files'.format(time_diff.seconds))


    logging.info('{} new log lines added'.format(len(all_lines)))

    # BasketOfHandles handles our open files for us, keeping only 5 open at a time.
    with BasketOfHandles(log_open, 5) as basket:
        for line_body in all_lines:
            log_file_name = log_file_template.format(**line_body)

            file_handle = basket.open(log_file_name, 'at')

            json.dump(line_body, file_handle, sort_keys=True)
            file_handle.write('\n')
            if line_body['datetime'] > last_datetime:
                last_datetime = line_body['datetime']


    config['plex_last_datetime'] = '-'.join(map(str, last_datetime))

    config_save(config_file, config)

    logging.info('Finished.')


if __name__ == '__main__':
    with LockFile() as lock_file:
        main()
