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
from plex import PlexLogParser, PlexServerConnection, PlexMediaObject


def event_categorize(event):
    # Only works with requests
    result = []
    result.append("{0:04}-{1:02}-{2:02}".format(*event['datetime']))
    
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


def LogFileLoader(log_file):
    results = []
    skip_urls = [
        '/:/plugins',
        '/library/metadata',
        '/web',
        '/system',
        ]

    wanted_urls = [
        '/:/timeline',
        '/video/:/transcode/universal/start',
        '/video/:/transcode/universal/stop',    
        ]
    if log_file.endswith('.gz'):
        open_cmd = gzip.open
    else:
        open_cmd = open

    with open_cmd(log_file, 'rt') as file_handle:
        for line in file_handle:
            line_body = json.loads(line)

            # For now we are only really interested in url requests
            if 'url_path' not in line_body:
                continue

            skip = False
            for skip_url in skip_urls:
                if line_body['url_path'].startswith(skip_url):
                    skip = True
            if skip:
                continue

            # for wanted_url in wanted_urls:
            #     if line_body['url_path'].startswith(wanted_url):
            #         break
            # else:
            #     continue

            results.append(line_body)

    return results


def diff_dict(dict_a, dict_b, ignore_list=[]):
    all_keys = list(set(dict_b.keys()) + set(dict_a.keys()))
    all_keys.sort()
    result_a = []
    result_b = []
    for key in all_keys:
        if key in ignore_list:
            continue
        if key not in dict_b:
            result_a.append((key, dict_a[key]))
        elif key not in dict_a:
            result_b.append((key, dict_b[key]))
        else:
            if dict_a[key] != dict_b[key]:
                result_a.append((key, dict_a[key]))
                result_b.append((key, dict_b[key]))
    return dict(result_a), dict(result_b)


def merge_split_events(all_events):
    all_events.sort(key=lambda event: event['datetime'])
    last_event = all_events[0]
    for event in all_events[1:]:
        diff_a, diff_b = diff_dict(last_event['url_query'], event['url_query'], ['time'])
        if len(diff_a) == 0:
            continue
        else:
            yield 
            last_event = event



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

    conn = PlexServerConnection('norti-pc.local', 32400)

    categories = {}

    log_file_match = os.path.join('logs', config['log_match'])
    for log_file in file_glob(log_file_match):
        print("Log - {}".format(log_file))
        log_lines = LogFileLoader(log_file)

        for line_body in log_lines:
            category_id = event_categorize(line_body)
            category = categories.setdefault(category_id, [])
            category.append(line_body)

    print('Found {0} unique events'.format(len(categories)))
    for category_id in sorted(categories.keys()):
        print(json.dumps(category_id))
        if '/:/timeline' in category_id:
            for event in split_events(categories[category_id]):
                print('   ', json.dumps(event, sort_keys=True))


if __name__ == '__main__':
    with LockFile() as lf:
        main()
