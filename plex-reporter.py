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
import json
import logging

from glob import glob as file_glob

from plex.lockfile import LockFile
from plex.media import PlexServerConnection, plex_media_object_batch
from plex.event import EventParserController, LogLoader
from plex.util import config_load


try:
    ## In python 3, cPickle is now _pickle
    ## and loaded automatically if available
    import cPickle as pickle
except ImportError:
    import pickle


def do_pickle(pickle_file, objs):
    temp_file = pickle_file + '.tmp'
    with open(temp_file, 'wb') as file_handle:
        pickle.dump(objs, file_handle, 2)

    if os.path.isfile(pickle_file):
        os.remove(pickle_file)
    os.rename(temp_file, pickle_file)


def do_unpickle(pickle_file):
    if os.path.isfile(pickle_file):
        with open(pickle_file, 'rb') as file_handle:
            return pickle.load(file_handle)
    return None


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
    pickle_file = os.path.join('logs', 'events.pickle')

    config = config_load(config_file)

    log_file_match = os.path.join('logs', config['log_file_match'])

    conn = PlexServerConnection(
        config['plex_server_host'], config['plex_server_port'])

    ## Setup controller to keep 10 lines
    if os.path.isfile(pickle_file):
        last_datetime, controller = do_unpickle(pickle_file)
    else:
        controller = EventParserController(10)
        last_datetime = None

    loader = LogLoader(controller, last_datetime=last_datetime, want_all=False)

    ## TODO: skip files based on last_datetime...
    for log_file in file_glob(log_file_match):
        loader.load_file(log_file)

    ## Dump state...
    done_events = controller.parse_dump(loader.last_datetime)

    do_pickle(pickle_file, (loader.last_datetime, controller))

    live_events = controller.parse_flush()

    ## Load event information...
    if False:
        media_keys = list(set([
            event.media_key for event in controller.done_events]))
        media_keys.sort(key=lambda key: int(key))
        media_objects = plex_media_object_batch(conn, media_keys)
    else:
        media_objects = {}

    done_events.sort(key=lambda event: event.start)

    if len(done_events) > 0:
        print("{0:#^80}".format("[ Done Events ]"))
        for event in done_events:
            if event.duration is not None and event.duration > 6:
                print('"' + event.event_id + '":', (
                    json.dumps(event.to_dict(), sort_keys=True)))

    if len(live_events) > 0:
        print("{0:#^80}".format("[ Live Events ]"))
        for event in live_events:
            print('"' + event.event_id + '":', (
                json.dumps(event.to_dict(), sort_keys=True)))

if __name__ == '__main__':
    with LockFile() as lock_file:
        main()
