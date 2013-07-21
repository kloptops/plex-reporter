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
import json
import zlib
import logging
import datetime


def get_logger(*args):
    return logging.getLogger('.'.join([
        arg.__class__.__name__
        if not isinstance(arg, str) else str(arg)
        for arg in args]))


RATING_ANYONE  = 0
RATING_CHILD   = 1
RATING_TEEN    = 2
RATING_ADULT   = 3
RATING_UNKNOWN = 4
RATING_NAMES   = ['Anyone', 'Child', 'Teen', 'Adult', 'Unknown']

content_ratings = {
    # TV ratings, obvious by the TV- prefix... o_o
    'TV-Y':    RATING_ANYONE,
    'TV-Y7':   RATING_ANYONE,
    'TV-G':    RATING_CHILD,
    'TV-PG':   RATING_CHILD,
    'TV-14':   RATING_TEEN,
    'TV-MA':   RATING_ADULT,
    'NC-17':   RATING_ADULT,

    # Movie ratings
    'G':       RATING_ANYONE,
    'PG':      RATING_CHILD,
    'PG-13':   RATING_TEEN,
    'R':       RATING_ADULT,

    # Our ratings
    'Anyone':  RATING_ANYONE,
    'Child':   RATING_CHILD,
    'Teen':    RATING_TEEN,
    'Adult':   RATING_ADULT,
    'Unknown': RATING_UNKNOWN,
    }


def get_content_rating(rating):
    if rating in content_ratings:
        return content_ratings[rating]
    return RATING_UNKNOWN


def get_content_rating_name(content_rating):
    if content_rating in (0, 1, 2, 3, 4):
        return RATING_NAMES
    return 'Unknown'


def compress(data):
    return zlib.compress(data.encode('utf-8'))


def decompress(data):
    return zlib.decompress(data).decode('utf-8')


class PlexException(Exception):
    pass


CONFIG_VERSION = '0.1'


def config_update(config):
    if config['config_version'] == '0.0':
        # Renamed: mode -> log_save_mode
        config['log_save_mode'] = config['mode']
        del config['mode']

        # Renamed: log_match -> log_file_match
        config['log_file_match'] = config['log_match']
        del config['log_match']

        # Renamed: log_file_name -> log_filename
        config['log_file_name'] = config['log_filename']
        del config['log_filename']

        # Renamed: last_datetime -> plex_last_datetime
        config['plex_last_datetime'] = config['last_datetime']
        del config['last_datetime']

        # Added: 'plex_log_dir', 'plex_server_host', 'plex_server_port'
        config.setdefault('plex_log_dir', '')
        config.setdefault('plex_server_host', 'localhost')
        config.setdefault('plex_server_port', 32400)

        # Now 0.1
        config['config_version'] = '0.1'
    # Add new updates here... :)


def config_load(config_file, no_save=False):
    if os.path.isfile(config_file):
        with open(config_file, 'rU') as file_handle:
            config = json.load(file_handle)
    else:
        config = {
            'config_version': CONFIG_VERSION,
            'log_file_name': (
                'plex-media-server-'
                '{datetime[0]:04d}-'
                '{datetime[1]:02d}-'
                '{datetime[2]:02d}.log'),
            'log_file_match': 'plex-media-server-*.log*',
            'log_save_mode': 'text',
            'plex_last_datetime': '2000-1-1-0-0-0-0',
            'plex_log_dir': '',
            'plex_server_host': 'localhost',
            'plex_server_port': 32400,
            }

        if not no_save:
            config_save(config_file, config)

    config.setdefault('config_version', '0.0')
    if config['config_version'] != CONFIG_VERSION:
        config_update(config)
        if not no_save:
            config_save(config_file, config)

    return config


def config_save(config_file, config):
    config_file_temp = config_file + '.tmp'
    with open(config_file_temp, 'w') as file_handle:
        json.dump(config, file_handle, sort_keys=True, indent=4)

    if os.path.isfile(config_file):
        os.remove(config_file)
    os.rename(config_file_temp, config_file)


def datetime_diff(date_a, date_b):
    a = datetime.datetime(*date_a)
    b = datetime.datetime(*date_b)
    return (a - b).seconds


class BasketOfHandles(object):
    """
    Allows multiple files to be opened by name, but really only keeps
    max_handles open at a time.

    Not the greatest piece of code, but it helped simplify plex-log-saver's
    code and performance wise its OK.
    """
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

        logger = logging.getLogger(self.__class__.__name__ + '.open')

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
        logger = logging.getLogger(self.__class__.__name__ + '.__enter__')
        if self.in_state is True:
            logger.error(
                'Unable to enter state multiple times with single object')
            raise RuntimeError(
                'Unable to enter state multiple times with single object')
        self.in_state = True
        logger.debug("Entering state")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        logger = logging.getLogger(self.__class__.__name__ + '.__exit__')
        if self.in_state is False:
            logger.error('Exit state called multiple times...')

        self.in_state = False
        logger.debug("Exiting state")
        for key, value in self.handles.items():
            logger.debug(" - closing: '{0}'".format(key))
            value.close()

        self.handles.clear()
        self.handle_queue[:] = []
