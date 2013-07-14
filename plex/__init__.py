# -*- coding: utf-8 -*-
# -*- python -*-

__license__ = """

The MIT License (MIT)
Copyright (c) 2013 Jacob Smith <kloptops@gmail.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the “Software”), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""
__author__ = "Jacob Smith"
__version__ = "0.1.0"

from plex.util import (
	RATING_ANYONE, RATING_CHILD, RATING_TEEN, RATING_ADULT,
	RATING_UNKNOWN, RATING_NAMES, get_content_rating, content_ratings,
	PlexException,
	CONFIG_VERSION, config_load, config_save,
	BasketOfHandles,
	)

from plex.media import (
	PlexMediaException, PlexServerException,
	PlexServerConnection,
	PlexMediaLibraryObject, PlexMediaVideoObject, PlexMediaEpisodeObject,
	PlexMediaMovieObject, plex_media_object
	)

from plex.parser import (
	PlexLogParser,
	)

from plex.lockfile import LockFile, TimeOutError
