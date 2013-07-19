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
import codecs
import logging

from collections import deque
from itertools import chain

from glob import glob as file_glob
from plex.lockfile import LockFile
from plex.media import (
    PlexServerConnection, plex_media_object, plex_media_object_batch)
from plex.util import (config_load, config_save)


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
        self.session_key   = kwargs.get('session_key', '')
        self.media_key     = kwargs.get('media_key', '0')

        self.device_name   = kwargs.get('device_name', '')
        self.device_ip     = kwargs.get('device_ip', '')
        self.device_client = kwargs.get('device_client', 'Unknown')

        self.start         = kwargs.get('start', None)
        self.end           = kwargs.get('end', None)

        self.media_object  = kwargs.get('media_object', None)

        self.resumed       = kwargs.get('resumed', False)
        # True stopped, False paused, None if we have no idea... :)
        self.stopped       = kwargs.get('stopped', None)

    def get_duration(self):
        if self.end is None or self.start is None:
            return None
        return datetime_diff(self.end, self.start)
    duration = property(get_duration)

    def get_event_id(self):
        timestamp = '-'.join(map(str, self.start))
        return '@'.join([str(self.session_key), str(self.media_key), timestamp])
    event_id = property(get_event_id)

    def __repr__(self):
        return (
            '<PlexEvent'
            ' event_id={us.event_id!r},'
            ' media_key={us.media_key},'
            ' session_key={us.session_key!r},'
            ' device_name={us.device_name!r},'
            ' device_ip={us.device_ip},'
            ' device_client={us.device_client!r},'
            ' start={start!r},'
            ' end={end!r},'
            ' duration={us.duration},'
            ' resumed={us.resumed},'
            ' stopped={us.stopped},'
            ' media_object={us.media_object}>'
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
    # For now we only parse '/:/timeline' & '/:/progress' events
    def __init__(self, controller, event_category):
        self.controller = controller
        self.event_category = event_category

        event_dict = {
            'device_ip': event_category[1],
            'media_key': event_category[2],
            }

        self.event = PlexEvent(**event_dict)
        self.first_line = True
        self.last_line = None
        self.debug_info = []
        self.debug_final = None

    def parse(self, event_line, previous_lines, next_lines):
        if self.first_line:
            # Skip first lines that are "state": "stopped"
            if event_line['url_query']['state'] == 'stopped':
                return EVENT_MORE

            # Skip start lines that have a duration that's smaller than
            # the time.
            if ('duration' in event_line['url_query'] and 
                int(event_line['url_query']['time']) >
                    int(event_line['url_query']['duration'])):
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

            if (self.event_category[0] != '/:/progress' and
                    self.event.session_key == '' and self.event.device_name == ''):
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
            if (self.event_category[0] == '/:/progress' and
                    self.event.session_key == '' and self.event.device_name == ''):
                assert 'identifier' in event_line['url_query']

                ## Anyone with any better idea's, please stand up :(
                if event_line['url_query']['identifier'] == 'com.plexapp.plugins.library':
                    self.event.device_name = 'Plex Media Center'
                    self.event.session_key = self.event.device_ip

            if self.event.session_key == '' and self.event.device_name == '':
                for previous_line in previous_lines:
                    print("< ", json.dumps(previous_line, sort_keys=True))
                print("=", json.dumps(event_line, sort_keys=True))
                print(self.event)
                for next_line in next_lines:
                    print("> ", json.dumps(next_line, sort_keys=True))
                print("#" * 80)

            if self.event.device_client == 'DLNA':
                for z_category, z_line in chain(
                        reversed(previous_lines), next_lines):
                    if len(z_category) == 0:
                        continue
                    if (z_category[0] == "/:/session_info" and 
                        'ratingKey' in z_line['session_info'] and
                        z_line['session_info']['ratingKey'] == self.event.media_key):
                        self.event.session_key = z_category[1]
                        break
                else:
                    print("{0:#^80}".format(
                        '[ DLNA No Session Key - {0} - {1} ]'.format(
                            self.event.device_ip, self.event.media_key)))

                    for previous_line in previous_lines:
                        print("< ", json.dumps(previous_line, sort_keys=True))
                    print("=", json.dumps(event_line, sort_keys=True))
                    print(self.event)
                    for next_line in next_lines:
                        print("> ", json.dumps(next_line, sort_keys=True))
                    print("#" * 80)

            self.first_line = False
            self.last = event_line
            self.debug_info.append(event_line)
            return EVENT_MORE

        if event_line["url_query"]["state"] == "playing":
            ## Detect weird time differencees...
            # if (abs(event_line['url_query']['time'] - 
            #        last['url_query']['time']) > 600000):
            #     return EVENT_DONE_REDO
            if (datetime_diff(
                    event_line['datetime'], self.last['datetime']) > 600):
                # Too much of a time difference, making this a different event.
                self.debug_final = event_line
                return EVENT_DONE_REDO

            self.debug_info.append(event_line)
            self.last = event_line
            return EVENT_MORE

        elif event_line["url_query"]["state"] == "paused":
            self.last = event_line
            self.debug_info.append(event_line)
            return EVENT_MORE

        else:
            self.last = event_line
            self.debug_info.append(event_line)
            return EVENT_DONE

    def finish(self):
        if self.last["url_query"]["state"] == "stopped":
            self.event.stopped = True
        elif self.last["url_query"]["state"] == "paused":
            self.event.stopped = False

        self.event.end = self.last['datetime']
        if (self.event.end is not None and self.event.start is not None and
                self.event.end < self.event.start):
            print("WTF ", self.event)
            for debug_line in self.debug_info:
                print("- ", json.dumps(debug_line, sort_keys=True))
            if self.debug_final is not None:
                print("! ", json.dumps(self.debug_final, sort_keys=True))


class EventParserController(object):
    def __init__(self, buffer_size=20):
        self.event_parsers = {}
        self.done_events = []
        self.sessions = {}

        # Buffer contains the last/next buffer_size lines
        self.buffer_size = buffer_size
        self.next_lines = deque([])
        self.previous_lines = deque([], buffer_size)

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
        if event_category not in self.event_parsers:
            event_parser = self.event_parsers[event_category] = EventParser(self, event_category)
        else:
            event_parser = self.event_parsers[event_category]

        parse_result = event_parser.parse(event_line, self.previous_lines, self.next_lines)

        if parse_result == EVENT_DONE_REDO:
            del self.event_parsers[event_category]
            event_parser.finish()
            self.done_events.append(event_parser.event)
            # Return false to push the event back onto the queue and it'll be
            # reparsed with a new EventParser
            return False

        elif parse_result == EVENT_DONE:
            del self.event_parsers[event_category]
            event_parser.finish()
            self.done_events.append(event_parser.event)
            return True

        else: # parse_result = EVENT_MORE
            return True

    def parse_event(self, event_category, event_line):
        if len(event_category) == 0:
            return True

        elif event_category[0] in (
                "/video/:/transcode/segmented",
                "/video/:/transcode/universal"):

            return self.parse_session_event(event_category, event_line)

        elif event_category[0] == '/:/progress':
            # ANOTHER FRIKKEN confusing thing... O_O
            return self.parse_timeline_event(event_category, event_line)

        elif event_category[0] == '/:/timeline':
            return self.parse_timeline_event(event_category, event_line)

        elif event_category[0] == '/:/session_info':
            # print("-", event_category, json.dumps(event_line, sort_keys=True))
            return True

        else:
            return True

    def parse_begin(self):
        self.event_parsers.clear()
        self.previous_lines.clear()
        self.next_lines.clear()
        self.sessions.clear()

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
                    self.next_lines.appendleft((event_category, event_line))

        while len(self.next_lines) > self.buffer_size:
            event_category, event_line = self.next_lines.popleft()
            if len(event_category) == 0:
                self.previous_lines.append((event_category, event_line))
                continue

            if self.parse_event(event_category, event_line):
                self.previous_lines.append((event_category, event_line))
            else:
                self.next_lines.appendleft((event_category, event_line))

    def parse(self):
        parser = self.parse_begin()
        parser.next()

        return parser


## TODO: Support minimum datetime...
##   will add to the handler,
##   so we can still use the previous lines from older events
class LogLoader(object):
    def __init__(self, controller):
        self.controller = controller
        self.started = False
        self.parser = None
        self.last_datetime = None

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
            '/:/progress',
            '/video/:/transcode',
            )

        with open_cmd(log_file, 'rt') as file_handle:
            for line in file_handle:
                event_line = json.loads(line)

                # Sanity check...
                if self.last_datetime is not None:
                    assert self.last_datetime <= event_line['datetime']
                self.last_datetime = event_line['datetime']

                if ('content' in event_line and
                        event_line['content'].startswith('Client [')):
                    decode_content_session_info(event_line)

                if 'url_path' in event_line:
                    if event_line['url_path'] == '/':
                        continue

                    if (startswith_list(event_line['url_path'], paths_wanted)
                            is None):
                        continue

                if 'url_path' not in event_line and 'session_info' not in event_line:
                    continue

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
    ## Begin logging
    if os.path.isfile('plex-reporter.log'):
        os.remove('plex-reporter.log')

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename='plex-reporter.log',
        level=logging.DEBUG)

    logging.info('{0:#^40}'.format('[ Plex Reporter Log ]'))

    ## Load config
    if not os.path.isdir('logs'):
        os.mkdir('logs')

    config_file = os.path.join('logs', 'config.cfg')

    config = config_load(config_file)

    conn = PlexServerConnection(
            config['plex_server_host'], config['plex_server_port'])

    log_file_match = os.path.join('logs', config['log_file_match'])

    ## -- EventParserController, keep 10 lines
    controller = EventParserController(10)

    with LogLoader(controller) as loader:
        for i, log_file in enumerate(file_glob(log_file_match)):
            print("Log - {}".format(log_file))
            loader.load_file(log_file)

    ## Figure out the earliest event still "Open"
    print("{0:#^80}".format("[ Events Open ]"))

    for event_key in controller.event_parsers.keys():
        event_parser = controller.event_parsers[event_key]
        if event_parser.first_line:
            del controller.event_parsers[event_key]
            continue
        elif len(event_parser.debug_info) > 1:
            event_parser.finish()
            controller.done_events.append(event_parser.event)
            del controller.event_parsers[event_key]
        else:
            print(event_key, event_parser.event.start)

    ## -- Load event information...
    if False:
        media_keys = list(set([event.media_key for event in controller.done_events]))
        media_keys.sort(key=lambda key: int(key))
        media_objects = plex_media_object_batch(conn, media_keys)
    else:
        media_objects = {}

    controller.done_events.sort(key=lambda event: event.start)


    print("{0:#^80}".format("[ Overlapped Events ]"))
    for i, event in enumerate(controller.done_events):
        event_uid = event.session_key
        for j, other_event in enumerate(controller.done_events[i+1:], i+1):
            other_uid = other_event.session_key
            if event_uid != other_uid:
                continue

            if event.end <= other_event.start:
                continue

            if event.media_key == other_event.media_key:
                # Merge these...
                print("Merge", event)
                print("     ", other_event)
                continue

            print("Overlapped", event)
            print("          ", other_event)

    print("{0:#^80}".format("[ Events ]"))
    for event in controller.done_events:
        if event.duration is not None and event.duration > 6:
            if event.media_key in media_objects:
                event.media_object = media_objects[event.media_key]
                if event.duration > (event.media_object.duration * 1.5):
                    print("-- LONG EVENT --")
            elif event.duration > 16200:
                # Based on a 3hours * 1.5
                print("-- LONG EVENT --")

            print(event)

if __name__ == '__main__':
    with LockFile() as lock_file:
        main()
