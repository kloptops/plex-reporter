# -*- coding: utf-8 -*-
# -*- python -*-

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

import re
import json
import gzip
import datetime
import itertools
import collections


EVENT_MORE      = 0
EVENT_DONE      = 1
EVENT_DONE_REDO = 2


def startswith_list(text, items):
    for item in items:
        if text.startswith(item):
            return item
    return None


def event_categorize(event_line):
    """Categorizes an event_line suitable for the EventParserController."""
    result = []
    # Doesn't work if event_line starts over new day
    # result.append("{0:04}-{1:02}-{2:02}".format(*event_line['datetime']))
    seen = []

    url_collators = (
        '/video/:/transcode/segmented',
        '/video/:/transcode/universal',
        '/video/:/transcode/session',
        )

    # Session info is only useful if we have a ratingKey or key
    if 'session_info' in event_line and (
            'ratingKey' in event_line['session_info'] or
            'key' in event_line['session_info']):

        seen.append('url')
        result.append('/:/session_info')
        session_info = event_line['session_info']
        seen.append('session')
        result.append(session_info['session'])

    if 'url_path' in event_line:
        seen.append('url')
        startswith = startswith_list(event_line['url_path'], url_collators)
        if startswith:
            result.append(startswith)
        else:
            result.append(event_line['url_path'])

        if 'request_ip' in event_line:
            seen.append('ip')
            result.append(event_line['request_ip'])

        if (event_line['url_path'].startswith(
                '/video/:/transcode/segmented/session') or
            event_line['url_path'].startswith(
                '/video/:/transcode/universal/session')):
            seen.append('session')
            result.append(event_line['url_path'].split('/')[6])
        elif (event_line['url_path'].startswith('/video/:/transcode/session')):
            seen.append('session')
            result.append(event_line['url_path'].split('/')[5])

    if 'ip' not in seen and 'request_ip' in event_line:
        seen.append('ip')
        result.append(event_line['request_ip'])

    if 'session' not in seen and 'url_query' in event_line:
        url_query = event_line['url_query']
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
    re.compile(r'progress of (?P<time>\d+)/(?P<total>\d+)ms'),
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

    def to_dict(self):
        return {
            'session_key':   self.session_key,
            'media_key':     self.media_key,
            'device_name':   self.device_name,
            'device_ip':     self.device_ip,
            'device_client': self.device_client,
            'start':         self.start,
            'end':           self.end,
            'resumed':       self.resumed,
            'stopped':       self.stopped,
            }

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

    def _parse_first_line(self, event_line, previous_lines, next_lines):
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
            session_id = '@'.join([
                '/video/:/transcode',
                event_line['request_ip']])

            if session_id in self.controller.sessions:
                session = self.controller.sessions[session_id]
                assert self.event.media_key == session['media_key']

                if 'session_key' in session:
                    self.event.session_key = session['session_key']
                if 'device_name' in session:
                    self.event.device_name = session['device_name']
                if 'device_client' in session:
                    self.event.device_client = session['device_client']

        ## Seems to be a Plex Media Center thing...
        if (self.event_category[0] == '/:/progress' and
                self.event.session_key == '' and
                self.event.device_name == '' and
                'identifier' in event_line['url_query']):

            if (event_line['url_query']['identifier'] ==
                    'com.plexapp.plugins.library'):

                self.event.device_name = (
                    'Plex Media Center @ ({0})'.format(
                        self.event.device_ip))
                self.event.device_client = 'Plex Media Center'
                self.event.session_key = (
                    '-'.join(['pms', self.event.device_ip]))

        ## So far my DLNA clients give me this... :D
        if self.event.device_client == 'DLNA':
            for z_category, z_line in itertools.chain(
                    reversed(previous_lines), next_lines):
                if len(z_category) == 0:
                    continue
                if (z_category[0] == "/:/session_info" and 
                        'ratingKey' in z_line['session_info'] and
                        z_line['session_info']['ratingKey'] ==
                            self.event.media_key):
                    self.event.session_key = z_category[1]
                    break

        ## Somehow Chrome on windows vista 32bit did this?! O_o
        if (self.event.device_client == 'Unknown' and
                self.event.session_key == '' and
                self.event.device_name == ''):

            for z_category, z_line in itertools.chain(
                    reversed(previous_lines), next_lines):

                if len(z_category) == 0:
                    continue

                if (z_category[0] == "/:/session_info" and
                        'ratingKey' in z_line['session_info'] and
                        z_line['session_info']['ratingKey'] ==
                            self.event.media_key):
                    self.event.session_key = z_category[1]
                    break

        ## Still no session_key, it used to be just for sessions, now we use it
        ## for a unique identifier... probably should fix this :/
        if (self.event.session_key == '' and
                    self.controller.debug_stream is not None):

            debug_stream = self.controller.debug_stream
            print("#" * 80, file=debug_stream)
            for previous_line in previous_lines:
                print("< ", json.dumps(previous_line, sort_keys=True),
                    file=debug_stream)
            print("=", json.dumps(event_line, sort_keys=True),
                file=debug_stream)
            print(self.event)
            for next_line in next_lines:
                print("> ", json.dumps(next_line, sort_keys=True),
                    file=debug_stream)
            print("#" * 80, file=debug_stream)

        self.first_line = False
        self.last = event_line
        self.debug_info.append(event_line)
        return EVENT_MORE

    def parse(self, event_line, previous_lines, next_lines):
        if self.first_line:
            return self._parse_first_line(event_line, previous_lines, next_lines)

        if event_line["url_query"]["state"] == "playing":
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


class EventParserController(object):
    """EventParserController(buffer_size=20)

    Controls the creation and destruction of EventParser objects. Suitable for
    serializing with pickle, infact its recommended.
    """
    def __init__(self, buffer_size=20, debug_stream=None):
        self.event_parsers = {}
        self.done_events = []
        self.sessions = {}
        self.debug_stream = debug_stream

        # Buffer contains the last/next buffer_size lines
        self.buffer_size = buffer_size
        self.next_lines = collections.deque([])
        self.previous_lines = collections.deque([], buffer_size)

    def _parse_session_event(self, event_category, event_line):
        if event_line['url_path'].rsplit('/', 1)[-1].startswith("start."):
            ## Start transcoding session...
            session_id = '@'.join(['/video/:/transcode', event_category[1]])
            session = {'session_key': event_category[2]}

            if 'X-Plex-Device-Name' in event_line['url_query']:
                session['device_name'] = (
                    event_line['url_query']['X-Plex-Device-Name'])

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
            session_id = (
                event_category[0].rsplit('/', 1)[0], event_category[1])
            if session_id in self.sessions:
                del self.sessions[session_id]

        return True

    def _parse_timeline_event(self, event_category, event_line):
        event_id = '@'.join(event_category)
        if event_id not in self.event_parsers:
            event_parser = self.event_parsers[event_id] = (
                EventParser(self, event_category))
        else:
            event_parser = self.event_parsers[event_id]

        parse_result = event_parser.parse(
            event_line, self.previous_lines, self.next_lines)

        if parse_result == EVENT_DONE_REDO:
            del self.event_parsers[event_id]
            event_parser.finish()
            self.done_events.append(event_parser.event)
            # Return false to push the event back onto the queue and it'll be
            # reparsed with a new EventParser
            return False

        elif parse_result == EVENT_DONE:
            del self.event_parsers[event_id]
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

            return self._parse_session_event(event_category, event_line)

        elif event_category[0] == '/:/progress':
            return self._parse_timeline_event(event_category, event_line)

        elif event_category[0] == '/:/timeline':
            return self._parse_timeline_event(event_category, event_line)

        elif event_category[0] == '/:/session_info':
            # print("-", event_category, json.dumps(event_line, sort_keys=True))
            return True

        else:
            return True

    def parse_reset(self):
        """Totally resets the controller and its parsers, leaves the done_events
        alone in place.
        """
        self.event_parsers.clear()
        self.previous_lines.clear()
        self.next_lines.clear()
        self.sessions.clear()

    def parse_line(self, event_line):
        """Parse an event_line."""
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

    def parse_finish(self):
        """Finish off the parser.

        This can be called when you're done, but it can result in malformed
        events due to lines missing. You're better off serializing this object
        between runs with pickle, like so::

            done_events = controller.parse_dump()

            pickle.dump(controller, file_handle, pickle.HIGHEST_PROTOCOL)

            live_events = controller.parse_flush()

        This will mean only properly formed (but possibly incomplete) events
        will be returned, but at the same time you're safe to use these events
        as the event_id should not change.
        """
        while len(self.next_lines) > self.buffer_size:
            event_category, event_line = self.next_lines.popleft()
            if len(event_category) == 0:
                self.previous_lines.append((event_category, event_line))
                continue

            if self.parse_event(event_category, event_line):
                self.previous_lines.append((event_category, event_line))
            else:
                self.next_lines.appendleft((event_category, event_line))

    def parse_dump(self, last_datetime):
        """Clear out null events, returns done_events.
        
        Call this before you serialize this object. Events returned here are
        stable, and shouldn't change.
        """
        done_events = self.done_events
        self.done_events = []

        for event_key in self.event_parsers.keys():
            event_parser = self.event_parsers[event_key]
            if event_parser.first_line:
                del self.event_parsers[event_key]

            elif (datetime_diff(
                    last_datetime, event_parser.last['datetime']) > 600):
                event_parser.finish()
                done_events.append(event_parser.event)
                del self.event_parsers[event_key]

        self.debug_stream = None
        return done_events

    def parse_flush(self):
        """Flush out unfinished events, returns more done_events.

        Call this after you've serialized this object. Events returned here
        maybe mid playback, and thus may change, but the event_id should be
        stable. Therefore you can just update events based on their event_id if
        they change.
        """
        done_events = []
        for event_key in self.event_parsers.keys():
            event_parser = self.event_parsers[event_key]
            if not event_parser.first_line:
                event_parser.finish()
                done_events.append(event_parser.event)
                del self.event_parsers[event_key]

        return done_events


class LogLoader(object):
    """A simple log loader that will keep track of the last event loaded.

    It will feed event_lines automajically into the controller object.

    If you're having problems with events not showing up properly, or events
    don't have enough information, and you are trying to find more info, pass 
    this flag as true and it'll pass all log lines to the parser. This can help
    with debugging.
    """
    def __init__(self, controller, last_datetime=None, want_all=False,
            max_load=None):
        self.controller = controller
        self.last_datetime = last_datetime
        self.want_all = want_all
        self.counter = 0

        ## For debugging... :)
        self.max_load = max_load

    def load_file(self, log_file):
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

        parse_line = self.controller.parse_line
        first_line = True

        with open_cmd(log_file, 'rt') as file_handle:
            for line in file_handle:
                if self.max_load is not None and self.counter >= self.max_load:
                    break

                event_line = json.loads(line)
                if first_line:
                    first_line = False
                    ## Skip this file if the last_datetime is already set on the
                    ## first line and last_datetime[:3] is bigger than the first
                    ## lines datetime[:3].
                    if (self.last_datetime is not None and
                            self.last_datetime[:3] > event_line['datetime'][:3]):
                        break

                # Skip old events...
                if (self.last_datetime is not None and 
                        self.last_datetime > event_line['datetime']):
                    continue

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

                if (not self.want_all and
                        'url_path' not in event_line and
                        'session_info' not in event_line):
                    continue

                self.counter += 1
                parse_line(event_line)
