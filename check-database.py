#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

import os
import sys
import re
from bs4 import BeautifulSoup

from plex import PlexServerConnection


def main():
    import json

    conn = PlexServerConnection('norti-pc.local', 32400)

    sections_page = conn.fetch('library/sections')
    sections_soup = BeautifulSoup(sections_page)

    for section_tag in sections_soup.find_all('directory'):
        key = section_tag['key']

        print('Checking {0}'.format(section_tag['title']))
        items_page = conn.fetch('library/sections/{0}/all'.format(key))
        items_soup = BeautifulSoup(items_page)

        for item in items_soup.find_all('directory'):
            if item.get('contentrating', '') != '':
                continue
            print('    {0} - {1}'.format(
                    item.get('title', 'WTF O_O'),
                    item.get('contentrating', '')))
        for item in items_soup.find_all('video'):
            if item.get('contentrating', '') != '':
                continue
            print('    {0} - {1}'.format(
                    item.get('title', 'WTF O_O'),
                    item.get('contentrating', '')))


if __name__ == '__main__':
	main()
