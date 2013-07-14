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
import re
import sys
import json
import gzip
import logging

from glob import glob as file_glob
from plex import (
    LockFile, PlexServerConnection, plex_media_object, config_load, config_save)


def event_categorize(event):
    # Currently only works with requests
    result = []
    # Doesn't work if event starts over new day
    # result.append("{0:04}-{1:02}-{2:02}".format(*event['datetime']))
    seen = []

    url_collators = (
        ('/video/:/transcode/segmented', '/video/:/transcode/segmented'),
        ('/video/:/transcode/universal', '/video/:/transcode/universal'),
        ('/video/:/transcode/session/', '/video/:/transcode/session/'),
        )

    if 'request_ip' in event:
        seen.append('ip')
        result.append(event['request_ip'])

    if 'url_path' in event:
        seen.append('url')
        for url_collator_match, url_collator_result in url_collators:
            if event['url_path'].startswith(url_collator_match):
                result.append(url_collator_result)
                break
        else:
            result.append(event['url_path'])

        if (event['url_path'].startswith(
                '/video/:/transcode/segmented/session') or
            event['url_path'].startswith(
                '/video/:/transcode/universal/session')):
            seen.append('session')
            result.append(event['url_path'].split('/')[6])
        elif (event['url_path'].startswith('/video/:/transcode/session/')):
            seen.append('session')
            result.append(event['url_path'].split('/')[5])

    if 'url_query' in event:
        url_query = event['url_query']
        if 'session' not in seen and 'session' in url_query:
            seen.append('session')
            result.append(url_query['session'])
        if 'session' not in seen and 'ratingKey' in url_query:
            seen.append('key')
            result.append(url_query['ratingKey'])
        elif 'session' not in seen and 'key' in url_query:
            seen.append('key')
            result.append(url_query['key'].rsplit('/', 1)[-1])
        if 'session' not in seen and 'X-Plex-Device-Name' in url_query:
            seen.append('xpdn')
            result.append(url_query['X-Plex-Device-Name'])

    return tuple(result)


def LogFileLoader(log_file, results=None):
    results = {} if results is None else results

    if log_file.endswith('.gz'):
        open_cmd = gzip.open
    else:
        open_cmd = open

    paths_not_wanted = (
        '/:/plugins/',
        '/library/metadata',
        '/library/optimize',
        '/library/section',
        '/library/onDeck',
        '/web/',
        '/system/',
        )

    with open_cmd(log_file, 'rt') as file_handle:
        for line in file_handle:
            line_body = json.loads(line)

            skip = False
            if 'url_path' in line_body:
                for path_not_wanted in paths_not_wanted:
                    if line_body['url_path'].startswith(path_not_wanted):
                        skip = True
                        break

            if skip:
                continue

            # For now we are only really interested in categorized events
            line_event = event_categorize(line_body)
            if len(line_event) == 0:
                continue


            results.setdefault(line_event, []).append(line_body)

    return results



def parse_event(line_event, line_bodies, file_handle):
    print_data = [
        ('10.0.0.4', '/video/:/transcode/universal'),
        ('10.0.0.6', '/video/:/transcode/segmented', '0C902F73-51D4-4D82-9499-E6234B305CAF'),
        ('10.0.0.11', '/video/:/transcode/segmented', 'C5B092C3-B261-4344-A09F-A6939E10A468'),
        ]

    print(line_event, file=file_handle)
    if line_event in print_data:
        for line_body in line_bodies:
            print(json.dumps(line_body, sort_keys=True), file=file_handle)


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

    with open('output.txt', 'wt', encoding="utf-8") as file_handle:
        for line_event in sorted(all_events.keys()):
            all_events[line_event].sort(key=lambda line_body: line_body['datetime'])
            parse_event(line_event, all_events[line_event], file_handle)

if __name__ == '__main__':
    with LockFile() as lock_file:
        main()
