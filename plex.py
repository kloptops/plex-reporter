#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

"""
plex.py

Created by Jacob Smith on 2013-07-10.
Copyright (c) 2013 Jacob Smith. All rights reserved.
"""
import os
import re
import requests
from bs4 import BeautifulSoup
import logging
from glob import glob as file_glob

try:
    from urlparse import urlparse, parse_qs
except ImportError:
    from urllib.parse import urlparse, parse_qs


class BasketOfHandles(object):
    def __init__(self, creator, max_handles=10):
        self.creator = creator
        self.max_handles = max_handles
        self.handles = {}
        self.handle_queue = []
        self.in_state = False

    def open(self, key, *args, **kwargs):
        if key in self.handles:
            if self.handle_queue[0] != key:
                self.handle_queue.remove(key)
                self.handle_queue.insert(0, key)
            return self.handles[key]

        logger = logging.getLogger(self.__class__.__name__ + '.' + 'open')

        # Make sure we only have at most max_handles open!
        while len(self.handle_queue) >= self.max_handles:
            old_key = self.handle_queue.pop()
            logger.debug("Closing '{0}'".format(old_key))
            self.handles[old_key].close()
            del self.handles[old_key]

        logger.debug("Opening '{0}'".format(key))
        self.handles[key] = self.creator(key, *args, **kwargs)
        self.handle_queue.insert(0, key)
        return self.handles[key]

    def __enter__(self):
        logger = logging.getLogger(self.__class__.__name__ + '.' + '__enter__')
        if self.in_state is True:
            logger.error('Unable to enter state multiple times with single object')
            raise Exception('Unable to enter state multiple times with single object')
        self.in_state = True
        logger.debug("Entering state")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logger = logging.getLogger(self.__class__.__name__ + '.' + '__exit__')
        if self.in_state is False:
            logger.error('Exit state called multiple times...')

        self.in_state = False
        logger.debug("Exiting state")
        for key, value in self.handles.items():
            logger.debug(" - closing: '{0}'".format(key))
            value.close()

        self.handles.clear()
        self.handle_queue[:] = []



class PlexSimpleLogParser(object):
    def __init__(self):
        pass

    def _re_search(self, regex, text):
        match = re.search(regex, text)
        if match:
            self._last = match.groupdict()
        else:
            self._last = None
        return self._last

    def _re_match(self, regex, text):
        match = re.search(regex, text)
        if match:
            self._last = match.groupdict()
        else:
            self._last = None
        return self._last

    def _parse_datetime(self, in_dict):
        # give us a nice sortable time :)
        month_index = {
            'jan':  1, 'feb':  2, 'mar':  3,
            'apr':  4, 'may':  5, 'jun':  6,
            'jul':  7, 'aug':  8, 'sep':  9,
            'oct': 10, 'nov': 11, 'dec': 12,
            }

        in_date = [
            int(in_dict['year']),
            int(month_index[in_dict['month'].lower()]),
            int(in_dict['day']),
            ]
        in_time = list(map(int, in_dict['time'].split(':')))

        in_dict['datetime'] = tuple(in_date + in_time)

        del in_dict['year']
        del in_dict['month']
        del in_dict['day']
        del in_dict['time']



    def _parse_base(self, real_file_name, file_handle):
        file_name = os.path.basename(real_file_name)
        for line_no, line_text in enumerate(file_handle, 1):

            # Jul 03, 2013 02:13:16:353 [4600] DEBUG - .* ([127.0.0.1:57601])?
            if not self._re_match(r'(?P<month>\w+) (?P<day>\d+), (?P<year>\d{4}) (?P<time>\d+:\d+:\d+:\d+) \[\d+\] (?P<debug_level>\w+) - (?P<content>.*)', line_text):
                continue

            line_body = {}
            line_body['file_name'] = file_name
            line_body['file_line_no'] = line_no
            line_body.update(self._last)

            self._parse_datetime(line_body)
            
            yield line_body


    def line_body_filter(self, line_body):
        return True


    def parse_file(self, real_file_name):
        logger = logging.getLogger(self.__class__.__name__ + '.' + 'parse_file')

        logger.debug("Called parse_file with: {0}".format(real_file_name))

        lines = []
        with open(real_file_name, 'rU') as file_handle:
            for line_body in self._parse_base(real_file_name, file_handle):
                if not self.line_body_filter(line_body):
                    continue

                lines.append(line_body)
        
        return lines


class PlexLogParser(PlexSimpleLogParser):

    def __init__(self, strict=True, *args, **kwargs):
        super(PlexLogParser, self).__init__(*args, **kwargs)
        self.strict = strict

        # We call str.startswith(wanted_url)
        # Set to [] if you want all urls to be saved! :)
        self.wanted_urls = [
            '/:/timeline',
            '/video/:/transcode/universal/start',
            '/video/:/transcode/universal/stop',
            ]
        

    #
    def _squish_dict(self, in_dict):
        for key, value in in_dict.items():
            if isinstance(value, list) and len(value) == 1:
                in_dict[key] = value[0]


    def line_body_filter(self, line_body):
        if self._re_match(r'Request: (?P<method>\w+) (?P<url>.*) \[(?:::ffff:)?(?P<request_ip>[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)(?::(?P<request_port>[0-9]+))?\] .*', line_body['content']):
            line_body.update(self._last)
            del line_body['content']

            line_url = urlparse(line_body['url'])
            del line_body['url']

            line_body['url_path'] = line_url.path
            line_body['url_query'] = parse_qs(line_url.query, keep_blank_values=True)
            self._squish_dict(line_body['url_query'])

            if len(self.wanted_urls) == 0:
                return True

            for wanted_url in self.wanted_urls:
                if line_body['url_path'].startswith(wanted_url):
                    return True
            else:
                return False

        if self.strict:
            return False

        return super(PlexLogParser, self).line_body_filter(line_body)

