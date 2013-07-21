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
import datetime
from plex.event import PlexEvent
from plex.util import get_content_rating


_client_restriction_types = {}


def client_restriction(**kwargs):
    if 'type' not in kwargs:
        raise ValueError("argument 'type' is required!")

    if kwargs['type'] not in _client_restriction_types:
        raise ValueError("argument 'type' is not a known restriction!")

    return _client_restriction_types[kwargs['type']](**kwargs)


class ClientRestriction(object):

    def __init__(self, **kwargs):
        self.type = kwargs.get('type')

    def match(self, event):
        pass

    def to_dict(self, result=None):
        if result is None:
            result = {}
        result['type'] = self.type
        return result


class TimeRestriction(ClientRestriction):
    """
    client_restriction(**{
        'type': 'time', 'days': 'mon,tue,wed', 'start': '9pm', 'end': '7am'})

    days: day[, day]+

    day: mon[day] | tue[sday] | wed[nesday] | thu[rsday] | fri[day] |
        sat[urday] | sun[day] | special_day
    special_day: everyday | weekday | weekend | weeknight

    param      | Mon | Tue | Wed | Thu | Fri | Sat | Sun
    -----------+-----+-----+-----+-----+-----+-----+-----
    everyday   |  x  |  x  |  x  |  x  |  x  |  x  |  x
    weekday    |  x  |  x  |  x  |  x  |  x  |     |
    weekend    |     |     |     |     |  x  |  x  |
    weeknight  |  x  |  x  |  x  |  x  |     |     |  x

    """

    _day_to_days = {
        'everyday':  [0, 1, 2, 3, 4, 5, 6],
        'weekday':   [0, 1, 2, 3, 4],
        'weekend':   [5, 6],
        'weeknight': [0, 1, 2, 3, 6],
        'monday':    [0], 'mon': [0],
        'tuesday':   [1], 'tue': [1],
        'wednesday': [2], 'wed': [2],
        'thursday':  [3], 'thu': [3],
        'friday':    [4], 'fri': [4],
        'saturday':  [5], 'sat': [5],
        'sunday':    [6], 'sun': [6],
        '0': [0], '1': [1], '2': [2],
        '3': [3], '4': [4], '5': [5],
        '6': [6],
        }

    _day_to_days[None]         = _day_to_days['everyday']
    _day_to_days['weeknights'] = _day_to_days['weeknight']
    _day_to_days['weekends']   = _day_to_days['weekend']
    _day_to_days['weekdays']   = _day_to_days['weekday']

    _day_to_days_cache = {None: [0, 1, 2, 3, 4, 5, 6]}

    def _resolve_days(self, day_string):
        if day_string in self._day_to_days_cache:
            return self._day_to_days_cache[day_string]

        days = []
        for day in day_string.split(','):
            day = day.strip().lower()
            if day in self._day_to_days:
                days.extend(self._day_to_days[day])
            else:
                raise ValueError((
                    "unknown day {0!r} specified in 'days' parameter").format(
                        day))

        days = list(set(days))
        if len(days) == 0:
            raise ValueError((
                "No days specified in 'days' parameter: {0!}").format(
                    day_string))

        days.sort()
        self._day_to_days_cache[day_string] = days

        return days

    _resolve_time_re = re.compile((
        r'\s*'
        r'(\d{1,2})'
        r'(?::(\d{1,2}))?'
        r'\s*'
        r'(am|pm)?'
        ), re.I)

    def _resolve_time(self, time_string):
        ## Match: 12pm, 12:30am, 17:00, 23:00
        match = self._resolve_time_re.match(time_string)
        if not match:
            raise ValueError((
                "bad time string {0!r} specified").format(
                    time_string))

        hour, minute, meridiem = match.groups()
        hour     = int(hour)
        minute   = int(minute) if minute is not None else 0
        meridiem = meridiem.lower()

        if meridiem is not None:
            ## 12-hour time fix
            if hour not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12):
                raise ValueError((
                    "hour parameter '{0}'' is out of range".format(hour)))
            if meridiem == 'pm' and hour != 12:
                hour += 12
            if meridiem == 'am' and hour == 12:
                hour += 12

        if hour == 24:
            hour = 0

        return datetime.time(hour, minute)

    def __init__(self, **kwargs):
        super(TimeRestriction, self).__init__(**kwargs)

        if 'start' not in kwargs:
            raise ValueError("argument 'start' is required!")
        if 'end' not in kwargs:
            raise ValueError("argument 'end' is required!")

        self.days  = kwargs.get('days', None)
        self.start = kwargs['start']
        self.end   = kwargs['end']

    def set_days(self, days_string):
        self._days_match = self._resolve_days(days_string)
        self._days = days_string

    def get_days(self):
        return self._days
    days = property(get_days, set_days)

    def set_start(self, start_string):
        self._start_match = self._resolve_time(start_string)
        self._start = start_string

    def get_start(self):
        return self._start
    start = property(get_start, set_start)

    def set_end(self, end_string):
        self._end_match = self._resolve_time(end_string)
        self._end = end_string

    def get_end(self):
        return self._start
    end = property(get_end, set_end)

    def to_dict(self, result=None):
        if result is None:
            result = {}
        super(TimeRestriction, self).to_dict(result)
        if self.days is not None:
            result['days'] = self.days
        result['start'] = self.start
        result['end'] = self.end

        return result

    def _inner_match(self):
        return self._start_match < self._end_match

    def match(self, event):
        start = datetime.datetime(*event.start)
        end   = datetime.datetime(*event.end)

        if start.day() in self._days_match:
            start_time = start.time()

            if (self._inner_match() and
                    self._start_match < start_time and
                    start_time < self._end_match):
                return True

            if (not self._inner_match() and (
                    start_time < self._start_match or
                    self._end_match < start_time)):
                return True

        elif end.day() in self._days_match:
            end_time = end.time()

            if (self._inner_match() and
                    self._start_match < end_time and
                    end_time < self._end_match):
                return True

            if (not self._inner_match() and (
                    end_time < self._start_match or
                    self._end_match < end_time)):
                return True

        return False


class ContentRestriction(ClientRestriction):
    def __init__(self):
        pass

_client_restriction_types['time']    = TimeRestriction
_client_restriction_types['content'] = ContentRestriction


class Client(object):
    def __init__(self, **kwargs):
        self.name         = kwargs.get('name', 'Unknown')
        self.restrictions = kwargs.get('restrictions', [])


def main():
    test_dicts = [
        {'type': 'time', 'start': '12pm', 'end': '7pm', 'days': 'weeknights'},
        {'type': 'time', 'start': '12pm', 'end': '7pm', 'days': 'mon,tue,wed'},
        {'type': 'time', 'start': '12pm', 'end': '7pm'},
        ]

    for test_dict in test_dicts:
        test_restriction = client_restriction(**test_dict)

        print(test_restriction._days, test_restriction._days_match)
        print(test_restriction._start, test_restriction._start_match)
        print(test_restriction._end, test_restriction._end_match)


if __name__ == '__main__':
    main()
