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
from collections import deque


EVENT_MORE      = 0
EVENT_DONE      = 1
EVENT_DONE_REDO = 2


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
            seen.append('name')
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


def decode_content_session_info(event_line):
    result = {}
    content = event_line['content']

    for regex in _content_session_info_re:
        match = regex.search(content)
        if match is not None:
            result.update(match.groupdict())

    if 'session' in result:
        del event_line['content']
        event_line['session_info'] = result


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
        self.device_client = kwargs.get('device_client', 'Unknown')

        self.start = kwargs.get('start', None)
        self.end = kwargs.get('end', None)

        self.media_object = kwargs.get('media_object', None)


        self.resumed = kwargs.get('resumed', False)
        # True stopped, False paused, None if we have no idea... :)
        self.stopped = kwargs.get('stopped', None)

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

    def get_duration(self):
        if self.end is None or self.start is None:
            return None
        return datetime_diff(self.end, self.start)
    duration = property(get_duration)

    def __repr__(self):
        return (
            '<PlexEvent\n'
            '    media_key={us.media_key},\n'
            '    session_key={us.session_key!r},\n'
            '    device_name={us.device_name!r},\n'
            '    device_ip={us.device_ip},\n'
            '    device_client={us.device_client!r}\n'
            '    start={start!r},\n'
            '    end={end!r},\n'
            '    duration={us.duration},\n'
            '    resumed={us.resumed},\n'
            '    stopped={us.stopped},\n'
            '    media_object={us.media_object}>'
            ).format(
                us=self,
                start=(
                    format_date(self.start) 
                        if self.start is not None
                        else None),
                end=(
                    format_date(self.end) 
                        if self.end is not None
                        else None))


class EventParser(object):
    # For now we only parse '/:/timeline' events
    def __init__(self, controller, event_category):
        self.controller = controller
        self.event_category = event_category

        event_dict = {
            'device_ip': event_category[1],
            'media_key': event_category[2],
            }

        self.event = PlexEvent(**event_dict)
        self.first_line = False
        self.last_line = None

    def parse(self, event_line, previous_lines, next_lines):
        if not self.first_line:
            if (event_line['url_query']['time'] >
                    event_line['url_query']['duration']):
                # I don't get why these events even occur... :/
                return EVENT_MORE

            self.event.start = event_line['datetime']

            if 'X-Plex-Product' in event_line['url_query']:
                self.event.device_client = (
                    event_line['url_query']['X-Plex-Product'])

            if 'X-Plex-Device-Name' in event_line['url_query']:
                self.event.device_name = (
                    event_line['url_query']['X-Plex-Device-Name'])

            if 'X-Plex-Client-Identifier' in event_line['url_query']:
                self.event.session_key = (
                    event_line['url_query']['X-Plex-Client-Identifier'])

            if int(event_line['url_query']['time']) > 10000:
                self.event.resumed = True

            if self.event.session_key == '' and self.event.device_name == '':
                # Detect session information from controller... :D
                session_id = ('/video/:/transcode', event_line['request_ip'])
                if session_id in self.controller.sessions:
                    session = self.controller.sessions[session_id]
                    assert self.event.media_key == session['media_key']

                    if 'session_key' in session:
                        self.event.session_key = session['session_key']
                    if 'device_name' in session:
                        self.event.device_name = session['device_name']
                    if 'device_client' in session:
                        self.event.device_client = session['device_client']

                print("#" * 80)
                for previous_line in previous_lines:
                    print("-", json.dumps(previous_line, sort_keys=True))
                print(self.event)
                for next_line in next_lines:
                    print("-", json.dumps(next_line, sort_keys=True))
                print("#" * 80)

            self.first_line = True
            self.last = event_line
            return EVENT_MORE

        if event_line["url_query"]["state"] == "playing":
            ## Detect weird time differencees...
            # if (abs(event_line['url_query']['time'] - 
            #        last['url_query']['time']) > 600000):
            #     return EVENT_DONE_REDO
            if datetime_diff(event_line['datetime'], self.last['datetime']) > 600:
                # Too much of a time difference, making this a different event.
                return EVENT_DONE_REDO

            self.last = event_line
            return EVENT_MORE

        elif event_line["url_query"]["state"] == "paused":
            self.last = event_line
            return EVENT_MORE

        else:
            self.last = event_line
            return EVENT_DONE

    def finish(self):
        if self.last["url_query"]["state"] == "stopped":
            self.event.stopped = True
        elif self.last["url_query"]["state"] == "paused":
            self.event.stopped = False

        self.event.end = self.last['datetime']


class EventParserController(object):
    def __init__(self, buffer_size=20):
        self.events = {}

        # Buffer contains the last/next buffer_size lines
        self.buffer_size = buffer_size
        self.next_lines = deque([])
        self.previous_lines = deque([], buffer_size)

        self.events = {}
        self.done_events = []

        self.sessions = {}

    def parse_session_event(self, event_category, event_line):
        if event_line['url_path'].rsplit('/', 1)[-1].startswith("start."):
            ## Start transcoding session...
            session_id = ('/video/:/transcode', event_category[1])
            session = {'session_key': event_category[2]}

            if 'X-Plex-Device-Name' in event_line['url_query']:
                session['device_name'] = event_line['url_query']['X-Plex-Device-Name']

            if 'X-Plex-Product' in event_line['url_query']:
                session['device_client'] = (
                    event_line['url_query']['X-Plex-Product'])

            if 'X-Plex-Device-Name' in event_line['url_query']:
                session['device_name'] = (
                    event_line['url_query']['X-Plex-Device-Name'])

            if 'ratingKey' in event_line['url_query']:
                session['media_key'] = (
                    event_line['url_query']['ratingKey'])
            elif 'path' in event_line['url_query']:
                session['media_key'] = (
                    event_line['url_query']['path'].rsplit('/', 1)[-1])

            self.sessions[session_id] = session

        elif event_line['url_path'].endswith('stop'):
            ## End transcoding sesssion...
            session_id = (event_category[0].rsplit('/', 1)[0], event_category[1])
            if session_id in self.sessions:
                del self.sessions[session_id]

        return True

    def parse_timeline_event(self, event_category, event_line):
        # We only respond to timeline events for now...
        if event_category not in self.events:
            event = self.events[event_category] = EventParser(self, event_category)
        else:
            event = self.events[event_category]

        parse_result = event.parse(event_line, self.previous_lines, self.next_lines)

        if parse_result == EVENT_DONE_REDO:
            del self.events[event_category]
            event.finish()
            self.done_events.append(event)
            # Return false to push the event back onto the queue and it'll be
            # reparsed with a new EventParser
            return False

        elif parse_result == EVENT_DONE:
            del self.events[event_category]
            event.finish()
            self.done_events.append(event)
            return False

        else: # parse_result = EVENT_MORE
            return True

    def parse_event(self, event_category, event_line):
        if event_category[0] in (
                "/video/:/transcode/segmented",
                "/video/:/transcode/universal"):

            return self.parse_session_event(event_category, event_line)

        elif event_category[0] == '/:/timeline':
            return self.parse_timeline_event(event_category, event_line)

        else:
            return True

    def parse_begin(self):
        self.events.clear()
        self.previous_lines.clear()
        self.next_lines.clear()

        while True:
            event_line = (yield None)
            if event_line is None:
                break

            # print("Parsing", event_line)
            event_category = event_categorize(event_line)
            self.next_lines.append((event_category, event_line))
            while len(self.next_lines) > self.buffer_size:
                event_category, event_line = self.next_lines.popleft()
                if len(event_category) == 0:
                    self.previous_lines.append((event_category, event_line))
                    continue

                if self.parse_event(event_category, event_line):
                    self.previous_lines.append((event_category, event_line))
                else:
                    self.next_lines.append((event_category, event_line))

        while len(self.next_lines) > self.buffer_size:
            event_category, event_line = self.next_lines.popleft()
            if len(event_category) == 0:
                self.previous_lines.append((event_category, event_line))
                continue

            if self.parse_event(event_category, event_line):
                self.previous_lines.append((event_category, event_line))
            else:
                self.next_lines.append((event_category, event_line))

    def parse(self):
        parser = self.parse_begin()
        parser.next()

        return parser


## TODO: Support minimum datetime...
class LogLoader(object):
    def __init__(self, controller):
        self.controller = controller
        self.started = False
        self.parser = None

    def load_file(self, log_file):
        if not self.started:
            raise RuntimeError("LogLoader not started parser")

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
                event_line = json.loads(line)

                if ('content' in event_line and
                        event_line['content'].startswith('Client [')):
                    decode_content_session_info(event_line)

                if 'url_path' in event_line:
                    if event_line['url_path'] == '/':
                        continue
                    if (startswith_list(event_line['url_path'], paths_wanted)
                            is None):
                        continue

                # if 'url_path' not in event_line and 'session_info' not in event_line:
                #     continue

                self.parser.send(event_line)


    def start(self):
        if self.started:
            raise RuntimeError("LogLoader parser already started")
        self.started = True
        self.parser = self.controller.parse()

    def finish(self):
        if not self.started:
            raise RuntimeError("LogLoader not started parser")
        self.started = False
        self.parser = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.finish()


def main():
    if os.path.isfile('plex-reporter.log'):
        os.remove('plex-reporter.log')

    import resource

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

    log_file_match = os.path.join('logs', config['log_file_match'])

    controller = EventParserController(30)

    with LogLoader(controller) as loader:
        for log_file in file_glob(log_file_match):
            print("Log - {}".format(log_file))
            loader.load_file(log_file)
            #break

    for event_parser in controller.done_events:
        if event_parser.event.duration is not None and event_parser.event.duration > 6:
            print(event_parser.event)

if __name__ == '__main__':
    with LockFile() as lock_file:
        main()
