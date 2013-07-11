#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

import os
import sys
import re
import logging
import json
from glob import glob as file_glob

from plex import PlexLogParser, PlexServerConnection, PlexMediaObject


def event_categorize(event):
    # Only works with requests
    result = []
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

    with open(log_file, 'rU') as file_handle:
        for line in file_handle:
            line_body = json.loads(line)

            # For now we are only really interested in url requests
            if 'url_path' not in line_body:
                continue

            results.append(line_body)

    return results


def process_log_line(line_body):

    category = event_categorize(line_body)

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
        log_lines = LogFileLoader(log_file)

        for line_body in log_lines:
            category_id = event_categorize(line_body)
            category = categories.setdefault(category_id, [])
            category.append(line_body)

    print('Found {0} unique events'.format(len(categories)))
    for category_id, category in categories.items():
        print(repr(category_id).encode(sys.stdout.encoding, errors='replace'))


if __name__ == '__main__':
    main()
