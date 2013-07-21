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

import re
import os

from plex.util import get_logger

try:
    from urlparse import urlparse, parse_qs
except ImportError:
    from urllib.parse import urlparse, parse_qs


class PlexLogParser(object):
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

    def _squish_dict(self, in_dict):
        for key, value in in_dict.items():
            if isinstance(value, list) and len(value) == 1:
                in_dict[key] = value[0]

    def _parse_base(self, real_file_name, file_handle):
        file_name = os.path.basename(real_file_name)
        for line_no, line_text in enumerate(file_handle, 1):

            # 'Jul 03, 2013 02:13:16:353 [4600] DEBUG - .*'
            if not self._re_match((
                    r'(?P<month>\w+) (?P<day>\d+), (?P<year>\d{4})'
                    r' (?P<time>\d+:\d+:\d+:\d+) \[\d+\] (?P<debug_level>\w+)'
                    r' - (?P<content>.*)'),
                    line_text):
                continue

            line_body = {}
            line_body['file_name'] = file_name
            line_body['file_line_no'] = line_no
            line_body.update(self._last)

            self._parse_datetime(line_body)

            # Match 'Request: GET /:/timeline?URL_QUERY_HERE [127.0.0.1:48192]'
            if self._re_match((
                    r'Request: (?P<method>\w+) (?P<url>.*)'
                    r' \[(?:::ffff:)?'
                    r'(?P<request_ip>[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)'
                    r'(?::(?P<request_port>[0-9]+))?\] .*'),
                    line_body['content']):

                line_body.update(self._last)
                del line_body['content']

                line_url = urlparse(line_body['url'])
                del line_body['url']

                line_body['url_path'] = line_url.path
                line_body['url_query'] = parse_qs(
                    line_url.query, keep_blank_values=True)

                self._squish_dict(line_body['url_query'])

            yield line_body

    def line_body_filter(self, line_body):
        """
        Overload this, when parse_file is called, each line passes through
        here. If you don't want this line, return False, True if you do.

        Also you can modify the structure here.
        """
        return True

    def parse_file(self, real_file_name):
        logger = get_logger(self, 'parse_file')

        logger.debug("Called parse_file with: {0}".format(real_file_name))

        lines = []
        with open(real_file_name, 'rU') as file_handle:
            for line_body in self._parse_base(real_file_name, file_handle):
                if not self.line_body_filter(line_body):
                    continue

                lines.append(line_body)

        return lines
