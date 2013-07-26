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
from bs4 import BeautifulSoup
from plex.event import PlexEvent
from plex.media import plex_media_object
from plex.util import get_content_rating, get_content_rating_name


_client_restriction_types = {}
_restriction_action_types = {}


def client_restriction(**kwargs):
    if 'type' not in kwargs:
        raise ValueError("argument 'type' is required!")

    if kwargs['type'] not in _client_restriction_types:
        raise ValueError("argument 'type' is not a known restriction!")

    return _client_restriction_types[kwargs['type']](**kwargs)


def restriction_action(**kwargs):
    if 'type' not in kwargs:
        raise ValueError("argument 'type' is required!")

    if kwargs['type'] not in _restriction_action_types:
        raise ValueError("argument 'type' is not a known action!")

    return _restriction_action_types[kwargs['type']](**kwargs)


class ClientRestriction(object):
    def __init__(self, **kwargs):
        self.type = kwargs.get('type')
        self.action = kwargs.get('action', None)

    def requires_media_object(self):
        return False

    def match(self, event):
        return False

    def to_dict(self, result=None):
        if result is None:
            result = {}
        result['type'] = self.type
        return result

    def __repr__(self):
        return (
            '<{us.__class__.__name__}'
            '>').format(us=self)


class LogicalRestriction(ClientRestriction):
    def __init__(self, **kwargs):
        super(LogicalRestriction, self).__init__(**kwargs)
        if 'ops' not in kwargs:
            raise ValueError("argument 'ops' is required!")
        ops = kwargs.get('ops', [])
        self.ops = []
        for op in ops:
            self.ops.append(client_restriction(**op))

    def match(self, event):
        for op in self.ops:
            if op.match(event):
                return True
        return False

    def to_dict(self, result=None):
        if result is None:
            result = {}
        super(LogicalRestriction, self).to_dict(result)
        result['ops'] = []
        for op in self.ops:
            result['ops'].append(op.to_dict())
        return result

    def requires_media_object(self):
        for op in self.ops:
            if self.requires_media_object():
                return True

    __op_repr__ = property(lambda self: ', '.join(map(str, self.ops)))

    def __repr__(self):
        return (
            '<{us.__class__.__name__}'
            ' ops=[{us.__op_repr__}]'
            '>').format(us=self)


class OrRestriction(LogicalRestriction):
    def match(self, event):
        for op in self.ops:
            if op.match(event):
                return True
        return False


class AndRestriction(LogicalRestriction):
    def match(self, event):
        for op in self.ops:
            if not op.match(event):
                return False
        return True


class NotRestriction(ClientRestriction):
    def __init__(self, **kwargs):
        super(NotRestriction, self).__init__(**kwargs)
        if 'op' not in kwargs:
            raise ValueError("argument 'op' is required!")
        op = kwargs.get('op')
        self.op = client_restriction(**op)

    def match(self, event):
        return not self.op.match(event)

    def to_dict(self, result=None):
        if result is None:
            result = {}
        super(NotRestriction, self).to_dict(result)
        result['op'] = self.op.to_dict()
        return result

    def requires_media_object(self):
        return self.op.requires_media_object()

    def __repr__(self):
        return (
            '<{us.__class__.__name__}'
            ' op={us.op}'
            '>').format(us=self)


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
        'everyday':  [1, 2, 3, 4, 5, 6, 7],
        'weekday':   [1, 2, 3, 4, 5],
        'weekend':   [6, 7],
        'weeknight': [1, 2, 3, 4, 7],
        'monday':    [1], 'mon': [1],
        'tuesday':   [2], 'tue': [2],
        'wednesday': [3], 'wed': [3],
        'thursday':  [4], 'thu': [4],
        'friday':    [5], 'fri': [5],
        'saturday':  [6], 'sat': [6],
        'sunday':    [7], 'sun': [7],
        '1': [1], '2': [2], '3': [3],
        '4': [4], '5': [5], '6': [6],
        '7': [7],
        }

    _day_to_days[None]         = _day_to_days['everyday']
    _day_to_days['weeknights'] = _day_to_days['weeknight']
    _day_to_days['weekends']   = _day_to_days['weekend']
    _day_to_days['weekdays']   = _day_to_days['weekday']

    _day_to_days_cache = {None: [1, 2, 3, 4, 5, 6, 7]}

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
        return self._days if self._days is not None else 'everyday'
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
        return self._end
    end = property(get_end, set_end)

    def to_dict(self, result=None):
        if result is None:
            result = {}
        super(TimeRestriction, self).to_dict(result)
        if self._days is not None:
            result['days'] = self.days
        result['start'] = self.start
        result['end'] = self.end

        return result

    def _inner_match(self):
        return self._start_match < self._end_match

    def match(self, event):
        start = datetime.datetime(*event.start)
        end   = datetime.datetime(*event.end)
        start_time = start.time()
        end_time = end.time()

        if start.isoweekday() in self._days_match:
            start_time = start.time()

            if (self._inner_match() and
                    self._start_match < start_time and
                    start_time < self._end_match):
                return True

            if (not self._inner_match() and (
                    self._start_match < start_time or
                    start_time < self._end_match)):
                return True

        if end.isoweekday() in self._days_match:
            end_time = end.time()

            if (self._inner_match() and
                    self._start_match < end_time and
                    end_time < self._end_match):
                return True

            if (not self._inner_match() and (
                    self._start_match < end_time or
                    end_time < self._end_match)):
                return True

        return False

    def __repr__(self):
        return (
            '<{us.__class__.__name__}'
            ' days={us.days!r},'
            ' start={us.start!r},'
            ' end={us.end!r}'
            '>').format(us=self)


class ContentRestriction(ClientRestriction):
    def __init__(self, **kwargs):
        super(ContentRestriction, self).__init__(**kwargs)

        if 'rating' not in kwargs:
            raise ValueError("argument 'rating' is required!")

        self.rating = kwargs['rating']

    def set_rating(self, rating):
        assert isinstance(rating, (int, str))
        if isinstance(rating, str):
            self._rating_code = get_content_rating(rating)
        else:
            self._rating_code = rating

        self._rating = get_content_rating_name(self._rating_code)

    def get_rating(self):
        return self._rating
    rating = property(get_rating, set_rating)

    def get_rating_code(self):
        return self._rating_code
    rating_code = property(get_rating_code)

    def requires_media_object(self):
        return True

    def match(self, event):
        ## A hack...
        if event.media_object is None:
            return True

        if event.media_object.rating_code < self.rating_code:
            return True

        return False

    def __repr__(self):
        return (
            '<{us.__class__.__name__}'
            ' rating={us.rating!r},'
            ' rating_code={us.rating_code}'
            '>').format(us=self)


class ReleaseDateRestriction(ClientRestriction):
    """
    ReleaseDateRestriction()

    Restricts shows that are recently added/released from being viewed.
    """

    def __init__(self, **kwargs):
        pass


_client_restriction_types['or']      = OrRestriction
_client_restriction_types['and']     = AndRestriction
_client_restriction_types['not']     = NotRestriction
_client_restriction_types['time']    = TimeRestriction
_client_restriction_types['content'] = ContentRestriction
_client_restriction_types['release'] = ReleaseDateRestriction


class RestrictionAction(object):
    def __init__(self, **kwargs):
        self.type = kwargs.get('type')

    def requires_live_event(self):
        return False

    def match(self, event):
        return False

    def to_dict(self, result=None):
        if result is None:
            result = {}
        result['type'] = self.type
        return result

    def __repr__(self):
        return (
            '<{us.__class__.__name__}'
            '>').format(us=self)


class ActionLiveStopPlayback(RestrictionAction):
    def requires_live_event(self):
        return True


class ActionEmail(RestrictionAction):
    pass


_restriction_action_types['stop_playback'] = ActionLiveStopPlayback
_restriction_action_types['email'] = ActionEmail


class Client(object):
    """
    This is the client. Clients contain lots of information :[
    """

    def __init__(self, **kwargs):
        self.name    = kwargs.get('name', 'Unknown')
        self.profile = kwargs.get('profile', 'default')


def main():
    sample_xml_a = (
        '<?xml version="1.0" encoding="UTF-8"?><MediaContainer size="1"'
        ' allowSync="1" identifier="com.plexapp.plugins.library"'
        ' librarySectionID="1" librarySectionUUID=""'
        ' mediaTagPrefix="/system/bundle/media/flags/"'
        ' mediaTagVersion=""><Video ratingKey="1337"'
        ' key="/library/metadata/1337" parentRatingKey="1336"'
        ' grandparentRatingKey="1335" guid="BUTTS"'
        ' type="episode" title="Episode 1"'
        ' grandparentKey="/library/metadata/1335"'
        ' parentKey="/library/metadata/1336" grandparentTitle="Example Show"'
        ' contentRating="TV-MA" summary="This show is an example."'
        ' index="1" parentIndex="1" rating="0" year="2012" thumb="" art=""'
        ' parentThumb="" grandparentThumb="" duration="3600000"'
        ' originallyAvailableAt="2012-10-14" addedAt="1372067395"'
        ' updatedAt="1372067395"></Video>'
        '<Directory ratingKey="1335"><Genre tag="Action" />'
        '<Genre tag="Restrict New" /></Directory>'
        '</MediaContainer>'
        )
    sample_xml_b = sample_xml_a.replace('TV-MA', 'TV-14')
    sample_xml_c = sample_xml_a.replace('TV-MA', 'TV-PG')

    event_base = {
        'media_key': 1337,
        'session_key': "BLAH",
        'device_ip': "127.0.0.1",
        'device_client': "Sample",
        }

    events = [
        PlexEvent(
            start=[2013, 07, 10, 20, 30,  1,   0],
            end  =[2013, 07, 10, 21,  9, 15, 458],
            media_object=plex_media_object(None, 1337, sample_xml_a),
            **event_base),
        PlexEvent(
            start=[2013, 07, 10, 21, 30,  1,   0],
            end  =[2013, 07, 10, 22,  9, 15, 458],
            media_object=plex_media_object(None, 1337, sample_xml_a),
            **event_base),
        PlexEvent(
            start=[2013, 07, 12, 20, 30,  1,   0],
            end  =[2013, 07, 12, 21,  9, 15, 458],
            media_object=plex_media_object(None, 1337, sample_xml_b),
            **event_base),
        PlexEvent(
            start=[2013, 07, 12, 21, 30,  1,   0],
            end  =[2013, 07, 12, 22,  9, 15, 458],
            media_object=plex_media_object(None, 1337, sample_xml_b),
            **event_base),
        PlexEvent(
            start=[2013, 07, 12, 23, 59,  1,   0],
            end  =[2013, 07, 13,  0, 29, 15, 458],
            media_object=plex_media_object(None, 1337, sample_xml_c),
            **event_base),
        PlexEvent(
            start=[2013, 07, 13, 12,  6,  1,   0],
            end  =[2013, 07, 13, 12, 29, 15, 458],
            **event_base),
        ]

    raw_restrictions = [
        {'type': 'or', 'ops': [
            {'type': 'time', 'start': '9pm', 'end': '7am', 'days': 'weeknights'},
            {'type': 'time', 'start': '10pm', 'end': '7am', 'days': 'everyday'},
            ]},
        {'type': 'and', 'ops': [
            {'type': 'time', 'start': '9pm', 'end': '7am', 'days': 'weeknights'},
            {'type': 'time', 'start': '10pm', 'end': '7am', 'days': 'everyday'},
            ]},
        {'type': 'and', 'ops': [
            {'type': 'not', 'op':
                {'type': 'time', 'start': '9pm', 'end': '7am', 'days': 'weeknights'}},
            {'type': 'time', 'start': '10pm', 'end': '7am', 'days': 'everyday'},
            ]},
        {'type': 'content', 'rating': 'Teen'},
        ]

    test_restrictions = list(map(
        lambda restriction: client_restriction(**restriction),
        raw_restrictions))

    tt = {True: '\033[32mTrue\033[0m', False: '\033[31mFalse\033[0m'}

    for event in events:
        print("#" * 80)
        print(event)
        for test_restriction in test_restrictions:
            print()
            print("?", test_restriction)
            print('=', tt[test_restriction.match(event)])
        print()


if __name__ == '__main__':
    main()
