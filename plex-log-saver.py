#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

"""
plex-log-saver.py

Created by Jacob Smith on 2013-07-10.
Copyright (c) 2013 Jacob Smith. All rights reserved.
"""

import os
## Uncomment the next line if you plan on using this script in the windows
## task scheduler
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import sys
import re
import logging
from glob import glob as file_glob
import json
import datetime

try:
    from urlparse import urlparse, parse_qs
except ImportError:
    from urllib.parse import urlparse, parse_qs

from plex import PlexLogParser, BasketOfHandles


class PlexSuperLogParser(PlexLogParser):
    def __init__(self, last_datetime, *args, **kwargs):
        super(PlexSuperLogParser, self).__init__(**kwargs)
        self.last_datetime = last_datetime

    def line_body_filter(self, line_body):
        # We don't want old records
        if line_body['datetime'] <= self.last_datetime:
            return False
        if line_body['content'].startswith(' *'):
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

    ## TODO: Move this into the config file
    # We're only interested in 'Plex Media Server.log' log files
    # I've been able to get 90% of the info i need from those logs
    log_files = (
        r'C:\Users\Norti\AppData\Local\Plex Media Server\Logs\Plex Media Server.log*',
        )

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

    log_file_template = os.path.join(
        'logs', config['log_filename'])

    if config['mode'] == 'gzip':
        import gzip
        log_open = gzip.open
    else:
        log_open = open

    last_datetime = tuple(map(int, config['last_datetime'].split('-')))

    log_parser = PlexSuperLogParser(last_datetime, strict=False)
    log_parser.wanted_urls = []

    all_lines = []

    for log_file_glob in log_files:
        for log_file in file_glob(log_file_glob):
            all_lines.extend(log_parser.parse_file(log_file))

    if len(all_lines) == 0:
        logging.info('No new lines, finishing.')
        return

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

    config['last_datetime'] = '-'.join(map(str, last_datetime))

    with open(config_file, 'w') as file_handle:
        json.dump(config, file_handle, sort_keys=True, indent=4)

    logging.info('Finished.')

if __name__ == '__main__':
    from lockfile import LockFile
    with LockFile() as lf:
        main()
