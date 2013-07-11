#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

import os
import re
import logging
import json
from glob import glob as file_glob

from plex import PlexLogParser

class PlexLogLoader(object):
    def __init__(self):
        pass

    def load_log(self, file_name):
        with open(file_name, 'rU') as file_handle:

def event_categorize(event):
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


log_files = (
    r'C:\Users\Norti\AppData\Local\Plex Media Server\Logs\Plex Media Server*',
    'Plex Media Server/Plex Media Server*'
    )

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




if __name__ == '__main__':
    main()
