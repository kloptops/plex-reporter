#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-
from __future__ import print_function

"""
plex-reporter.py

Created by Jacob Smith on 2013-07-11.
Copyright (c) 2013 Jacob Smith. All rights reserved.
"""

import os
import re
import sys
import json
import gzip
import logging
from lockfile import LockFile
from glob import glob as file_glob
from plex import PlexLogParser, PlexServerConnection, plex_media_object, \
    config_load, config_save


def event_categorize(event):
    # Currently only works with requests
    result = []
    # Doesn't work if event starts over new day
    # result.append("{0:04}-{1:02}-{2:02}".format(*event['datetime']))
    
    if 'request_ip' in event:
        result.append(event['request_ip'])

    if 'url_path' in event:
        if event['url_path'].startswith('/video/:/transcode/universal'):
            result.append('/video/:/transcode/universal')
        else:
            result.append(event['url_path'])

    if 'url_query' in event:
        url_query = event['url_query']
        if 'ratingKey' in url_query:
            result.append(url_query['ratingKey'])
        elif 'key' in url_query:
            result.append(url_query['key'].rsplit('/', 1)[-1])
        if 'session' in url_query:
            result.append(url_query['session'])
        elif 'X-Plex-Device-Name' in url_query:
            result.append(url_query['X-Plex-Device-Name'])

    return tuple(result)


def LogFileLoader(log_file, results=None):
    results = {} if results is None else results

    if log_file.endswith('.gz'):
        open_cmd = gzip.open
    else:
        open_cmd = open

    with open_cmd(log_file, 'rt') as file_handle:
        for line in file_handle:
            line_body = json.loads(line)

            # For now we are only really interested in categorized events
            line_event = event_categorize(line_body)
            if len(line_event) == 0:
                continue


            results.setdefault(line_event, []).append(line_body)

    return results


def main():
    import json

    if os.path.isfile('plex-reporter.log'):
        os.remove('plex-reporter.log')

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename='plex-reporter.log',
        level=logging.DEBUG)

    logging.info('{0:#^40}'.format('[ Plex Reporter Log ]'))

    if not os.path.isdir('logs'):
        os.mkdir('logs')

    config_file = os.path.join('logs', 'state.cfg')

    config = config_load(config_file)

    conn = PlexServerConnection(
            config['plex_server_host'], config['plex_server_port'])

    all_events = {}

    log_file_match = os.path.join('logs', config['log_file_match'])
    for log_file in file_glob(log_file_match):
        print("Log - {}".format(log_file))
        LogFileLoader(log_file, all_events)


if __name__ == '__main__':
    with LockFile() as lf:
        main()
