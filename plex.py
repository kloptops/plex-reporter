#!/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-
from __future__ import print_function

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


RATING_ANYONE = 0
RATING_CHILD  = 1
RATING_TEEN   = 2
RATING_ADULT  = 3
RATING_UNKNOWN= 4
RATING_NAMES = ['Anyone', 'Child', 'Teen', 'Adult', 'Unknown']

content_ratings = {
    # TV ratings, obvious by the TV- prefix... o_o
    'TV-Y':  RATING_ANYONE,
    'TV-Y7': RATING_ANYONE,
    'TV-G':  RATING_CHILD,
    'TV-PG': RATING_CHILD,
    'TV-14': RATING_TEEN,
    'TV-MA': RATING_ADULT,
    'NC-17': RATING_ADULT,

    # Movie ratings
    'G':     RATING_ANYONE,
    'PG':    RATING_CHILD,
    'PG-13': RATING_TEEN,
    'R':     RATING_ADULT,

    # Hack
    '':      RATING_UNKNOWN,
    }



class PlexException(Exception): pass
class PlexServerException(PlexException): pass
class PlexMediaException(PlexException): pass


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


class PlexServerConnection(object):
    def __init__(self, host='localhost', port=32400):
        self.host = host
        self.port = port
        self.enabled = False
        self.server_info = {}
        self.metadata_cache = {}
        self.page_cache = {}

        self.check_connection()

    def check_connection(self):
        # Check if medialookup is enabled, and test the connection if so
        logger = logging.getLogger(self.__class__.__name__ + '.' + 'check_connection')
        logger.debug("Called check_connection")
        try:
            check_req=requests.get('http://{host}:{port}/servers'.format(
                host=self.host, port=self.port))

            check_soup = BeautifulSoup(check_req.text)

            server_info = check_soup('server')[0]

            self.server_info = {}
            self.server_info['name'] = server_info['name']
            self.server_info['host'] = server_info['host']
            self.server_info['port'] = server_info['port']
            self.server_info['address'] = server_info['address']
            self.server_info['id'] = server_info['machineidentifier']
            self.server_info['version'] = server_info['version']

            self.enabled = True

            logger.info("Media connection enabled!")

        except requests.ConnectionError as err:
            logger.error('Error checking media server: ' + str(err))
            self.enabled = False
            logger.warning("Media connection disabled!")

    def fetch_metadata(self, key):
        assert isinstance(key, int)
        logger = logging.getLogger(self.__class__.__name__ + '.' + 'fetch_metadata')

        if not self.enabled:
            raise PlexServerException(
                'Unable to query metadata, media connection disabled')

        if key in self.metadata_cache:
            return self.metadata_cache[key]

        metadata_req = requests.get('http://{host}:{port}/library/metadata/{key}'.format(
            host=self.host, port=self.port, key=key))

        if metadata_req.status_code != 200:
            raise PlexServerException(
                'Unable to query metadata for {key}: [{status_code}] - {reason}'.format(
                key=key, status_code=metadata_req.status_code, reason=metadata_req.reason))

        self.metadata_cache[key] = metadata_req.text
        return self.metadata_cache[key]


    def fetch(self, path):
        logger = logging.getLogger(self.__class__.__name__ + '.' + 'fetch')

        if not self.enabled:
            raise PlexServerException(
                'Unable to fetch data, media connection disabled')

        if path in self.page_cache:
            return self.page_cache[path]

        page_req = requests.get('http://{host}:{port}/{path}'.format(
            host=self.host, port=self.port, path=path))

        if page_req.status_code != 200:
            raise PlexServerException(
                'Unable to query path {path}: [{status_code}] - {reason}'.format(
                path=path, status_code=page_req.status_code, reason=page_req.reason))

        self.page_cache[path] = page_req.text
        return self.page_cache[path]



class PlexMediaLibraryObject(object):
    def __init__(self, key=0, xml=None, soup=None):
        assert isinstance(key, int)
        self._key = key
        self.set_xml(xml, soup)

    def get_key(self):
        return self._key
    key = property(get_key)

    def clear(self):
        if hasattr(self, '_xml'):
            self._xml = None

    def set_xml(self, xml, soup=None):
        self.clear()
        if xml is None:
            self._xml = None
        else:
            self._parse_xml(xml, soup)
    def get_xml(self):
        return self._xml
    xml = property(get_xml, set_xml)

    def _parse_xml(self, xml, soup=None):
        if soup is None:
            soup = BeautifulSoup(xml)

        tag = soup.find(ratingkey=True)
        if int(tag['ratingkey']) != self.key:
            raise PlexMediaException(
                'Incorrect xml metadata, passed key {0}, xml key {1}'.format(
                self.key, int(tag['ratingkey'])))


class PlexMediaVideoObject(PlexMediaLibraryObject):
    def __init__(self, key=0, xml=None, soup=None):
        super(PlexMediaVideoObject, self).__init__(key, xml, soup)

    def clear(self):
        super(PlexMediaVideoObject, self).clear()
        self.rating = ''
        self.rating_code = RATING_UNKNOWN
        self.duration = 0
        self.year = '1900'
        self.title = ''
        self.summary = ''

        self.media = {}
        self.parts = []

    def _parse_xml(self, xml, soup=None):
        if soup is None:
            soup = BeautifulSoup(xml)
        super(PlexMediaVideoObject, self)._parse_xml(xml, soup)
        video_tag = soup.find('video')

        self.rating = video_tag.get('contentrating', '')
        if self.rating in content_ratings:
            self.rating_code = content_ratings[self.rating]
        else:
            self.rating_code = RATING_UNKNOWN

        self.duration = video_tag.get('duration', 0)
        self.year = video_tag.get('year', '1900')
        self.title = video_tag.get('title', '')
        self.summary = video_tag.get('summary', '')

        ## TODO: Make this better, but I haven't really needed this yet so I'm not really worried.
        media_tags = video_tag.find_all('media', id=True)
        for media_tag in media_tags:
            media_id = media_tag['id']
            self.media[media_id] = []
            part_tags = media_tag.find_all('part', id=True)
            for part_tag in part_tags:
                part_id = part_tag['id']
                part = {'id': part_id}
                if part_tag.has_attr('file'):
                    part['file'] = part_tag['file']
                if part_tag.has_attr('key'):
                    part['key'] = part_tag['key']
                self.media[media_id].append(part)
                self.parts.append(part_id)


class PlexMediaEpisodeObject(PlexMediaVideoObject):
    def __init__(self, key=0, xml=None, soup=None):
        super(PlexMediaEpisodeObject, self).__init__(key, xml)

    def clear(self):
        super(PlexMediaEpisodeObject, self).clear()
        self.series_key = 0
        self.series_title = 'Unknown'
        self.season_key = 0
        self.season = 0
        self.episode = 0

    def _parse_xml(self, xml, soup=None):
        if soup is None:
            soup = BeautifulSoup(xml)
        super(PlexMediaEpisodeObject, self)._parse_xml(xml, soup)
        video_tag = soup.find('video')

        self.series_key = video_tag.get('grandparentratingkey', 0)
        self.series_title = video_tag.get('grandparenttitle', 'Unknown')
        self.season_key = video_tag.get('parentratingkey', 0)
        self.season = video_tag.get('parentindex', 0)
        self.episode = video_tag.get('index', 0)

    def __repr__(self):
        return '<{us.__class__.__name__} key={us.key}, series_title={us.series_title!r}, season={us.season}, episode={us.episode}, title={us.title!r}>'.format(
            us=self)


class PlexMediaMovieObject(PlexMediaVideoObject):
    def __init__(self, key=0, xml=None, soup=None):
        super(PlexMediaMovieObject, self).__init__(key, xml)

    def clear(self):
        super(PlexMediaMovieObject, self).clear()

    def _parse_xml(self, xml, soup=None):
        if soup is None:
            soup = BeautifulSoup(xml)
        super(PlexMediaMovieObject, self)._parse_xml(xml, soup)

    def __repr__(self):
        return '<{us.__class__.__name__} key={us.key}, title={us.title!r} year={us.year}>'.format(
            us=self)


def PlexMediaObject(conn, key, xml=None, soup=None):
    if key is not None and xml is not None:
        raise TypeError(
            "Require argument 'key' or 'xml' must not be None")

    if key is None:
        if soup is None:
            soup = BeautifulSoup(xml)
        container_tag = soup.find(ratingkey=True)
        if container_tag is None:
            raise PlexMediaException(
                'Invalid xml passed, ratingKey="key" missing!')
        key = int(container_tag.get('ratingkey', 0))

    elif xml is None:
        if conn is None:
            raise TypeError(
                'Argument conn required if xml is None')
        xml = conn.fetch_metadata(key)

    if soup is None:
        soup = BeautifulSoup(xml)

    container_tag = soup.find(ratingkey=True)
    if container_tag.name == 'video':
        video_type = container_tag.get('type', None)
        if video_type == 'episode':
            return PlexMediaEpisodeObject(key, xml, soup)
        elif video_type == 'movie':
            return PlexMediaMovieObject(key, xml, soup)
        else:
            raise PlexMediaException(
                'Unknown video type {0!r}'.format(video_type))
    else:
        raise PlexMediaException(
            'Unknown media type for {0}'.format(key))


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

