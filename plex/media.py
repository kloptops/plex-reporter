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

import logging
import requests
from plex.util import PlexException, get_content_rating, RATING_UNKNOWN
from bs4 import BeautifulSoup


class PlexServerException(PlexException):
    pass


class PlexMediaException(PlexException):
    pass


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
        logger = logging.getLogger(self.__class__.__name__ + '.check_connection')
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
        logger = logging.getLogger(self.__class__.__name__ + '.fetch_metadata')

        if not self.enabled:
            raise PlexServerException(
                'Unable to query metadata, media connection disabled')

        if key in self.metadata_cache:
            return self.metadata_cache[key]

        metadata_req = requests.get(
            'http://{host}:{port}/library/metadata/{key}'.format(
            host=self.host, port=self.port, key=key))

        if metadata_req.status_code != 200:
            raise PlexServerException((
                'Unable to query metadata for {key}:'
                ' [{status_code}] - {reason}'
                ).format(
                    key=key,
                    status_code=metadata_req.status_code,
                    reason=metadata_req.reason))

        self.metadata_cache[key] = metadata_req.text
        return self.metadata_cache[key]

    def fetch(self, path):
        logger = logging.getLogger(self.__class__.__name__ + '.fetch')

        if not self.enabled:
            raise PlexServerException(
                'Unable to fetch data, media connection disabled')

        if path in self.page_cache:
            return self.page_cache[path]

        page_req = requests.get('http://{host}:{port}/{path}'.format(
            host=self.host, port=self.port, path=path))

        if page_req.status_code != 200:
            raise PlexServerException(
                ('Unable to query path {path}:'
                ' [{status_code}] - {reason}').format(
                path=path, status_code=page_req.status_code,
                reason=page_req.reason))

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
        ## TODO: not sure if content ratings should be in the base object?
        ##   I store audio or pictures on plex so I have no idea if they have
        ##   contentratings... :(
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
        self.rating_code = get_content_rating(self.rating)

        self.duration = int(video_tag.get('duration', 0))
        self.year = video_tag.get('year', '1900')
        self.title = video_tag.get('title', '')
        self.summary = video_tag.get('summary', '')

        ## TODO: Make this better, but I haven't really needed this yet,
        ## so I haven't decided how it needs to be laid out.
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
        return (
            '<{us.__class__.__name__}'
            ' key={us.key}, series_title={us.series_title!r},'
            ' season={us.season}, episode={us.episode},'
            ' title={us.title!r}>').format(
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
        return (
            '<{us.__class__.__name__}'
            ' key={us.key}, title={us.title!r}'
            ' year={us.year}>').format(
            us=self)


def plex_media_object(conn, key, xml=None, soup=None):
    """
    passing: conn, key -- will retrieve the xml from the server
    passing: key, xml[, soup] -- will just parse the possibly cached xml
    """
    if key is None and xml is None:
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


## TODO: allow PlexServerConnection to cache something like this...
def plex_media_object_batch(conn, keys, batch_size=20):
    """
    Batch fetch metadata from media server. :)
    """
    if not isinstance(keys, (list, tuple)):
        raise TypeError("Required argument 'keys' must be a list or tuple.")

    if conn is None:
        raise TypeError("Argument 'conn' must not be None")

    logger = logging.getLogger('plex_media_object_batch')
    logger.debug("Fetching {0} media objects".format(len(keys)))

    results = {}
    all_keys = keys[:]

    while len(all_keys) > 0:
        working_keys = all_keys[:batch_size]
        all_keys = all_keys[batch_size:]
        req = 'library/metadata/' + ','.join(map(str, working_keys))

        logger.debug("-> {0}".format(', '.join(map(str, working_keys))))

        xml = conn.fetch(req)
        soup = BeautifulSoup(xml)

        for container_tag in soup.find_all(ratingkey=True):
            container_key = container_tag['ratingkey']
            if container_key in results:
                continue

            ## TODO: Extract the soup object, suitable for passing down
            ##   to plex_media_object
            results[container_key] = plex_media_object(
                conn, int(container_key), str(container_tag))

    logger.debug("Fetched {0} media objects".format(len(results)))

    return results

