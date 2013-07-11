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


class PlexMediaConnection(object):
    def __init__(self, host='localhost', port=32400):
        self.host = host
        self.port = port
        self.enabled = False
        self.server_info = {}
        self.item_cache = {}
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

    def lookup_item(self, item_id):
        # Perform a lookup on the passed item ID
        logger = logging.getLogger(self.__class__.__name__ + '.' + 'lookup_item')
        logger.debug("Called lookup_item with: {0}".format(item_id))

        if item_id in self.item_cache:
            return self.item_cache[item_id]

        if item_id == 0 or self.enabled is False:
            result = {
                'item': item_id,
                'title': 'Item: {0}'.format(item_id),
                'img': None,
                'type': 'unknown',
                'media': None,
                }
            self.item_cache[item_id] = result
            return result

        # Connect to the plex server to retrieve the metadata
        # Lookup the video file details
        try:
            item_req=requests.get('http://{host}:{port}/library/metadata/{item_id}'.format(
                host=self.host, port=self.port, item_id=item_id))
        except requests.ConnectionError as err:
            logger.error('Error checking media server: ' + str(err))
            raise

        item_soup = BeautifulSoup(item_req.text)

        result = {'item': item_id}

        # Build up media info

        media_entries = item_soup.find_all('media')
        assert len(media_entries) > 0
        if len(media_entries) > 1:
            # Multiple versions of the video
            result['medias'] = []
            for media_entry in media_entries:
                media = {'media_id': int(media_entry.get('id', 0))}
                result['medias'].append(media)
                part_entries = media_entry.find_all('part')
                assert len(part_entries) > 0
                if len(part_entries) > 1:
                    # Multiple parts
                    media['parts'] = []
                    for part_entry in part_entries:
                        media['parts'].append({
                            'file': part_entry.get('file', None),
                            'part_id': int(part_entry.get('id', '0')),
                            })
                else:
                    # Single part
                    media['part'] = {
                        'file': part_entries[0].get('file', None),
                        'part_id': int(part_entries[0].get('id', '0')),
                        }
        else:
            # Single version of the video
            media_entry = media_entries[0]

            media = {'media_id': int(media_entry.get('id', 0))}
            result['media'] = media
            part_entries = media_entry.find_all('part')
            assert len(part_entries) > 0
            if len(part_entries) > 1:
                # Multiple parts
                media['parts'] = []
                for part_entry in part_entries:
                    media['parts'].append({
                        'file': part_entry.get('file', None),
                        'part_id': int(part_entry.get('id', '0')),
                        })
            else:
                # Single part
                media['part'] = {
                    'file': part_entries[0].get('file', None),
                    'part_id': int(part_entries[0].get('id', '0')),
                    }

        video_entry = item_soup.find('video')
        assert video_entry is not None

        if not video_entry.has_attr('title'):
            if find_first('file', result) is None:
                logger.error('No title or files found for {item}' **result)
                raise Exception('todo: better error here')
            logger.warn('No title defined for {item}'.format(**result))

        video_title = video_entry.get('title', os.path.basename(find_first('file', result)))

        if not video_entry.has_attr('type'):
            logger.warn('No type defined for {item}'.format(**result))

            result['title'] = video_title
            result['img'] = video_entry.get('thumb', None)
            result['type'] = 'unknown'

        elif video_entry['type'] == 'movie':
            result['title'] = video_title
            result['img'] = video_entry.get('thumb', None)
            result['type'] = 'movie'

        elif video_entry['type'] == 'episode':
            title = '{series_name} - S{season_number:02d}E{episode_number:02d} - {episode_title}'.format(
                series_name = video_entry.get('grandparenttitle', 'Unknown'),
                season_number = int(video_entry.get('parentindex', '0')),
                episode_number = int(video_entry.get('index', '0')),
                episode_title = video_title,
                )

            if title.startswith('Unknown - S00E00 - '):
                title = video_title

            result['title'] = title
            result['img'] = video_entry.get('thumb', None)
            result['type'] = 'tv'

        else:
            result['type'] = video_entry['type']
            logger.error('Unable to parse metadata {type} for {item}'.format(**result))
            raise Exception('cant parse {type} for {item}'.format(**result))

        self.item_cache[item_id] = result
        return result


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

