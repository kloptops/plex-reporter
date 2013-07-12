#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-
from __future__ import print_function

"""
tool-check-plexdb.py

Created by Jacob Smith on 2013-07-11.
Copyright (c) 2013 Jacob Smith. All rights reserved.
"""

import os
import sys
import re
from bs4 import BeautifulSoup

from lockfile import LockFile
import plex
from plex import PlexServerConnection



def main():
    import json

    conn = PlexServerConnection('norti-pc.local', 32400)


    sections_page = conn.fetch('library/sections')
    sections_soup = BeautifulSoup(sections_page)

    for section_tag in sections_soup.find_all('directory'):
        key = section_tag['key']

        print('{0:#^40}'.format("[ " + section_tag['title'] + " ]"))
        items_page = conn.fetch('library/sections/{0}/all'.format(key))
        items_soup = BeautifulSoup(items_page)
        
        ratings = [[] for i in range(plex.RATING_UNKNOWN+1)]        

        for item in items_soup.find_all('directory'):
            string_rating = item.get('contentrating', '')
            if string_rating not in plex.content_ratings:
                print(u"Unknown content rating {0!r} for {1}".format(
                    string_rating, item.get('title')))
                return
            
            content_rating = plex.content_ratings[string_rating]
            ratings[content_rating].append(item.get('title'))
        for item in items_soup.find_all('video'):
            string_rating = item.get('contentrating', '')
            if string_rating not in plex.content_ratings:
                print(u"Unknown content rating {0!r} for {1}".format(
                    string_rating, item.get('title')))
                return
            
            content_rating = plex.content_ratings[string_rating]
            ratings[content_rating].append(item.get('title'))

        for rating, shows in enumerate(ratings):
            if len(shows) == 0:
                continue
            print(u"  {0}".format(plex.RATING_NAMES[rating]))
            for show in shows:
                print(u"    {0}".format(show))
            print('')

if __name__ == '__main__':
    # Probably doesn't need this...
    with LockFile() as lf:
	   main()
