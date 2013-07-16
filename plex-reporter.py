#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-
from __future__ import print_function

__license__ = """

The MIT License (MIT)
Copyright (c) 2013 Jacob Smith <kloptops@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
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
import codecs

from glob import glob as file_glob
from plex import (
    LockFile, PlexServerConnection, plex_media_object, config_load, config_save)


def startswith_list(text, items):
    for item in items:
        if text.startswith(item):
            return item
    return None


def event_categorize(event):
    # Currently only works with requests
    result = []
    # Doesn't work if event starts over new day
    # result.append("{0:04}-{1:02}-{2:02}".format(*event['datetime']))
    seen = []

    url_collators = (
        '/video/:/transcode/segmented',
        '/video/:/transcode/universal',
        '/video/:/transcode/session',
        )

    # Session info is only useful if we have a ratingKey or key
    if 'session_info' in event and (
            'ratingKey' in event['session_info'] or
            'key' in event['session_info']):

        seen.append('url')
        result.append('/:/session_info')
        session_info = event['session_info']
        seen.append('session')
        result.append(session_info['session'])

    if 'url_path' in event:
        seen.append('url')
        startswith = startswith_list(event['url_path'], url_collators)
        if startswith:
            result.append(startswith)
        else:
            result.append(event['url_path'])

        if 'request_ip' in event:
            seen.append('ip')
            result.append(event['request_ip'])

        if (event['url_path'].startswith(
                '/video/:/transcode/segmented/session') or
            event['url_path'].startswith(
                '/video/:/transcode/universal/session')):
            seen.append('session')
            result.append(event['url_path'].split('/')[6])
        elif (event['url_path'].startswith('/video/:/transcode/session')):
            seen.append('session')
            result.append(event['url_path'].split('/')[5])

    if 'ip' not in seen and 'request_ip' in event:
        seen.append('ip')
        result.append(event['request_ip'])

    if 'session' not in seen and 'url_query' in event:
        url_query = event['url_query']
        if 'session' in url_query:
            seen.append('session')
            result.append(url_query['session'])
        # elif 'X-Plex-Client-Identifier' in url_query:
        #     seen.append('session')
        #     result.append(url_query['X-Plex-Client-Identifier'])
        elif 'ratingKey' in url_query:
            seen.append('key')
            result.append(url_query['ratingKey'])
        elif 'key' in url_query:
            seen.append('key')
            result.append(url_query['key'].rsplit('/', 1)[-1])
        elif 'X-Plex-Device-Name' in url_query:
            seen.append('xpdn')
            result.append(url_query['X-Plex-Device-Name'])

    return tuple(result)


_content_session_info_re = (
    re.compile(r'Client \[(?P<session>[^\]]+)]'),
    re.compile(r'progress of (?P<time>\d+)/(?P<total>\d+)ms.*?'),
    re.compile(r'for guid=(?P<guid>[^,]*)'),
    re.compile(r'ratingKey=(?P<ratingKey>\d+)'),
    re.compile(r'url=(?P<url>[^,]*),'),
    re.compile(r'key=(?P<key>[^,]*),'),
    re.compile(r'containerKey=(?P<containerKey>[^,]*),'),
    re.compile(r'metadataId=(?P<metadataId>\d*)'),
    )


def decode_content_session_info(line_body):
    result = {}
    content = line_body['content']

    for regex in _content_session_info_re:
        match = regex.search(content)
        if match is not None:
            result.update(match.groupdict())

    if 'session' in result:
        del line_body['content']
        line_body['session_info'] = result


def log_file_loader(log_file, results=None):
    results = {} if results is None else results

    if log_file.endswith('.gz'):
        open_cmd = gzip.open
    else:
        open_cmd = open

    paths_wanted = (
        '/:/session_info',
        '/:/timeline',
        '/video/:/transcode',
        )

    with open_cmd(log_file, 'rt') as file_handle:
        for line in file_handle:
            line_body = json.loads(line)

            if 'content' in line_body and line_body['content'].startswith('Client ['):
                decode_content_session_info(line_body)

            if 'url_path' in line_body:
                if line_body['url_path'] == '/':
                    continue
                if startswith_list(line_body['url_path'], paths_wanted) is None:
                    continue

            # For now we are only really interested in categorized events
            line_event = event_categorize(line_body)
            if len(line_event) == 0:
                continue


            results.setdefault(line_event, []).append(line_body)

    return results


def datetime_diff(date_a, date_b):
    import datetime
    a = datetime.datetime(*date_a)
    b = datetime.datetime(*date_b)
    return (a - b).seconds


def format_date(datetime):
    year, month, day, hour, minute, seconds, microseconds = datetime
    meridian = 'am'
    if hour > 12:
        hour -= 12
        meridian = 'pm'

    return (
        "{year:04}-{month:02}-{day:02}"
        " {hour:02}:{minute:02}:{seconds:02}{meridian}").format(
        year=year, month=month, day=day,
        hour=hour, minute=minute, seconds=seconds, meridian=meridian)


class PlexEvent(object):
    def __init__(self, **kwargs):
        self.session_key = kwargs.get('session_key', '')
        self.media_key = kwargs.get('media_key', '0')

        self.device_name = kwargs.get('device_name', '')
        self.device_ip = kwargs.get('device_ip', '')

        self.start = kwargs.get('start', None)
        self.end = kwargs.get('end', None)

        self.media_object = kwargs.get('media_object', None)

    def match(self, kwargs):
        # A gauntlet of matching...
        if ('session_key' in kwargs and 
                self.session_key != '' and kwargs['session_key'] != self.session_key):
            return False

        if ('media_key' in kwargs and
                self.media_key != '0' and kwargs['media_key'] != self.media_key):
            return False

        if 'datetime' in kwargs:
            # We allow a 10 second threshold...
            if (self.start is not None and datetime_diff(kwargs['datetime'], self.start) < -30):
                return False

            if (self.end is not None and datetime_diff(self.end, kwargs['datetime']) < -30):
                return False

        if ('start' in kwargs and
                self.start is not None and self.start > kwargs['start']):
            return False

        if ('end' in kwargs and
                self.end is not None and self.end < kwargs['end']):
            return False

        if ('device_name' in kwargs and self.device_name != '' and
                self.device_name != kwargs['device_name']):
            return False

        return True

    def cmp(self, other, keys=['media_key', 'session_key', 'start', 'end'], time_diff=5):
        if 'media_key' in keys and self.media_key != other.media_key:
            return False

        if 'session_key' in keys and self.session_key != other.session_key:
            return False

        if 'start' in keys and abs(datetime_diff(self.start, other.start)) <= time_diff:
            return False

        if 'end' in keys and abs(datetime_diff(self.end, other.end)) <= time_diff:
            return False

        if 'device_name' in keys and self.device_name != other.device_name:
            return False

        if 'device_ip' in keys and self.device_ip != other.device_ip:
            return False

        return True

    duration = property(lambda self: datetime_diff(self.end, self.start))

    def __repr__(self):
        return (
            '<PlexEvent'
            ' media_key={us.media_key},'
            ' session_key={us.session_key!r},'
            ' device_name={us.device_name!r},'
            ' device_ip={us.device_ip},'
            ' start={start!r},'
            ' end={end!r},'
            ' duration={us.duration}, '
            ' media_object={us.media_object}>'
            ).format(
                us=self,
                start=format_date(self.start),
                end=format_date(self.end))


class PlexEventParser(object):
    def __init__(self, file_handle):
        self.events = []
        self.file_handle = file_handle


    def find_events(self, kwargs):
        events = []

        for event in self.events:
            if event.match(kwargs):
                events.append(event)

        return events

    def find_unique_event(self, kwargs):
        events = self.find_events(kwargs)
        if len(events) == 1:
            return events[0]
        return None

    def parse_session_info(self, event_category, line_bodies):
        session_key = event_category[1]
        # Load session info into our sessions dict
        first = line_bodies[0]
        last = first
        counter = 0
        print(json.dumps(event_category, sort_keys=True), file=self.file_handle)
        for line_body in line_bodies:
            if line_body['session_info']['ratingKey'] != first['session_info']['ratingKey']:
                temp = {
                    'session_key': event_category[1],
                    'media_key': first['session_info']['ratingKey'],
                    'start': first['datetime'],
                    'end': last['datetime'],
                    }
                match_event = self.find_unique_event(temp)
                if match_event is None:
                    event = PlexEvent(**temp)
                    print('-', event, file=self.file_handle)
                    self.events.append(event)

                counter = 0
                first = last = line_body
            else:
                counter += 1
                last = line_body

        temp = {
            'session_key': event_category[1],
            'media_key': first['session_info']['ratingKey'],
            'start': first['datetime'],
            'end': last['datetime'],
            }

        match_events = self.find_events(temp)
        if len(match_events) == 0:
            event = PlexEvent(**temp)
            print('-', event, file=self.file_handle)
            self.events.append(event)


    def parse_timeline_info(self, event_category, line_bodies):
        base_event_dict = {
            'device_ip': event_category[1],
            'media_key': event_category[2],
            }

        print(json.dumps(event_category, sort_keys=True), file=self.file_handle)
        for line_body in line_bodies[:10]:
            print('  ', json.dumps(line_body, sort_keys=True), file=self.file_handle)

        seen_matches = []

        temp_line_bodies = line_bodies[:]
        while len(temp_line_bodies) > 0:
            event_dict = dict(base_event_dict.items())

            if 'X-Plex-Device-Name' in temp_line_bodies[0]['url_query']:
               event_dict['device_name'] = temp_line_bodies[0]['url_query']['X-Plex-Device-Name']

            if 'X-Plex-Client-Identifier' in temp_line_bodies[0]['url_query']:
               event_dict['session_key'] = temp_line_bodies[0]['url_query']['X-Plex-Client-Identifier']

            event_dict['datetime'] = temp_line_bodies[0]['datetime']

            event = self.find_unique_event(event_dict)
            if event is not None:
                if event.device_ip == '':
                    event.device_ip = event_dict['device_ip']
                if event.device_name == '' and 'device_name' in event_dict:
                    event.device_name = event_dict['device_name']
                if event.session_key == '' and 'session_key' in event_dict:
                    event.session_key = event_dict['session_key']

            start = temp_line_bodies[0]
            last = start
            last_was_paused = False
            for end_counter, line_body in enumerate(temp_line_bodies):
                if line_body["url_query"]["state"] == "playing":
                    if (last_was_paused and
                            datetime_diff(line_body['datetime'], last['datetime']) > 60):
                        break
                    last = line_body
                elif line_body["url_query"]["state"] == "paused":
                    last = line_body
                    last_was_paused = True
                else:
                    break

            if last["url_query"]["state"] == "stopped":
                # We did finish! :D
                pass

            end = last

            # Get a more accurateish datetime... o_o
            event_dict['start'] = start['datetime']
            event_dict['end'] = end['datetime']
            if event is not None:
                if event.start > event_dict['start']:
                    event.start = event_dict['start']
                if event.end < event_dict['end']:
                    event.end = event_dict['end']
            else:
                del event_dict['datetime']
                event = PlexEvent(**event_dict)
                self.events.append(event)
    
            end_counter += 1
            temp_line_bodies[:] = temp_line_bodies[end_counter:]
            # Do something with the events here...

    def parse_transcode_info(self, event_category, line_bodies):
        pass

    def parse_events(self, all_events):
        processed = {}

        for event_category in sorted(all_events.keys()):
            if event_category[0] == '/:/session_info':
                self.parse_session_info(event_category, all_events[event_category])
                processed[event_category] = True

            elif event_category[0] == '/:/timeline':
                self.parse_timeline_info(event_category, all_events[event_category])
                processed[event_category] = True

            elif event_category[0] in (
                '/video/:/transcode/segmented',
                '/video/:/transcode/universal'):
                self.parse_transcode_info(event_category, all_events[event_category])
                processed[event_category] = True

        for event_category in sorted(all_events.keys()):
            if event_category not in processed:
                print(json.dumps(event_category, sort_keys=True), file=self.file_handle)
                print('- ', len(all_events[event_category]))
                for line_body in all_events[event_category][:10]:
                    print(json.dumps(line_body, sort_keys=True), file=self.file_handle)

        session_to_name_map = {}
        name_to_session_map = {}

        session_to_ip_map = {}
        ip_to_session_map = {}

        name_to_ip_map = {}
        ip_to_name_map = {}

        for event in self.events:
            if event.session_key != '' and event.device_name != '':
                session_to_name_map[event.session_key] = event.device_name
                name_to_session_map[event.device_name] = event.session_key

            if event.device_name != '' and event.device_ip != '':
                name_to_ip_map[event.device_name] = event.device_ip
                ip_to_name_map[event.device_ip] = event.device_name

            if event.device_ip != '' and event.session_key != '':
                session_to_ip_map[event.session_key] = event.device_ip
                ip_to_session_map[event.device_ip] = event.session_key

        for event in self.events:
            if event.session_key == '' and event.device_name != '':
                event.session_key = name_to_session_map.get(event.device_name, '')

            if event.session_key == '' and event.device_ip != '':
                event.session_key = ip_to_session_map.get(event.device_ip, '')

            if event.device_name == '' and event.session_key != '':
                event.device_name = session_to_name_map.get(event.session_key, '')

            if event.device_name == '' and event.device_ip != '':
                event.device_name = ip_to_name_map.get(event.device_ip, '')

            if event.device_ip == '' and event.session_key != '':
                event.device_ip = session_to_ip_map.get(event.session_key, '')

            if event.device_ip == '' and event.device_name != '':
                event.device_ip = name_to_ip_map.get(event.device_name, '')

        self.events.sort(key=lambda event: (event.start, int(event.media_key)))

        new_events = []
        skip_events = []
        for i, event in enumerate(self.events):
            if event.duration < 6:
                continue

            if event in skip_events:
                continue

            for other_event in self.events[i+1:]:
                if event.cmp(other_event):
                    skip_events.append(other_event)

            new_events.append(event)

        self.events[:] = new_events


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

    config_file = os.path.join('logs', 'config.cfg')

    config = config_load(config_file)

    conn = PlexServerConnection(
            config['plex_server_host'], config['plex_server_port'])

    all_events = {}

    log_file_match = os.path.join('logs', config['log_file_match'])
    for log_file in file_glob(log_file_match):
        print("Log - {}".format(log_file))
        log_file_loader(log_file, all_events)


    with codecs.open('output.txt', 'wt', encoding="utf-8") as file_handle:
        file_handle.write("#!/usr/bin/env python\n")
        parser = PlexEventParser(file_handle)
        parser.parse_events(all_events)

        print('#' * 80)
        for event in parser.events:
            if event.media_key != 0:
                event.media_object = plex_media_object(conn, int(event.media_key))
            print("-", event)


if __name__ == '__main__':
    with LockFile() as lock_file:
        main()
