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





log_files = (
    r'C:\Users\Norti\AppData\Local\Plex Media Server\Logs\Plex Media Server*',
    'Plex Media Server/Plex Media Server*'
    )

if __name__ == '__main__':
    import json
    if os.path.isfile('plex-reporter.log'):
        os.remove('plex-reporter.log')

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename='plex-reporter.log',
        level=logging.DEBUG)

    logging.info('{0:#^40}'.format('[ Plex Reporter Log ]'))

    log_parser = PlexLogParser(strict=True)

    all_lines = []
    for log_file_glob in log_files:
        for log_file in file_glob(log_file_glob):
            all_lines += log_parser.parse_file(log_file)

    all_lines.sort(key=lambda x: (x['aa'], x['datetime']))
    
    condensed_lines = []
    
    last_line = all_lines[0]
    for line in all_lines[1:]:
        if last_line['aa'] == line['aa']:
            diff = event_difference(line, last_line)

    for line in all_lines:
        json.dump(line, sort_keys=True, indent=4))


"""

{"datetime": [2013, 7, 4, 19, 33, 11, 386], "debug_level": "DEBUG", "file_line_no": 39693, "file_name": "Plex Media Server.log", "method": "GET", "request_ip": "10.0.0.11", "request_port": "59285", "url_path": "/:/timeline", "url_query": {"X-Plex-Client-Capabilities": "protocols=http-live-streaming,http-mp4-streaming,http-streaming-video,http-streaming-video-720p,http-mp4-video,http-mp4-video-720p;videoDecoders=h264{profile:high&resolution:1080&level:41};audioDecoders=mp3,aac{bitrate:160000}", "X-Plex-Client-Identifier": "C5B092C3-B261-4344-A09F-A6939E10A468", "X-Plex-Client-Platform": "iOS", "X-Plex-Device": "iPhone", "X-Plex-Device-Name": "\u5927\u962a", "X-Plex-Model": "5,2", "X-Plex-Platform": "iOS", "X-Plex-Platform-Version": "6.1.2", "X-Plex-Product": "Plex/iOS", "X-Plex-Version": "3.2.2", "duration": "1278048", "identifier": "com.plexapp.plugins.library", "key": "/library/metadata/5422", "ratingKey": "5422", "state": "playing", "time": "69932"}}
{"datetime": [2013, 7, 4, 11, 54, 44, 838], "debug_level": "DEBUG", "file_line_no": 34218, "file_name": "Plex Media Server.log", "method": "GET", "request_ip": "127.0.0.1", "request_port": "50478", "url_path": "/:/timeline", "url_query": {"X-Plex-Device": "Western Digital TV Live", "X-Plex-Device-Name": "Western Digital TV Live", "X-Plex-Product": "DLNA", "containerKey": "/library/metadata/10898", "duration": "1212002", "guid": "com.plexapp.agents.thetvdb://80379/6/24?lang=en", "key": "/library/metadata/10898", "ratingKey": "10898", "report": "1", "state": "playing", "time": "1179000"}}

{"datetime": [2013, 7, 4, 19, 34, 28, 773], "debug_level": "DEBUG", "file_line_no": 39913, "file_name": "Plex Media Server.log", "method": "GET", "request_ip": "127.0.0.1", "request_port": "62201", "url_path": "/video/:/transcode/universal/start.m3u8", "url_query": {"X-Plex-Client-Identifier": "xk4kbse0xxadzpvi", "X-Plex-Device": "Windows", "X-Plex-Device-Name": "Plex/Web (Chrome)", "X-Plex-Platform": "Chrome", "X-Plex-Platform-Version": "27", "X-Plex-Product": "Web Client", "X-Plex-Version": "1.2.2", "audioBoost": "100", "directPlay": "0", "directStream": "1", "fastSeek": "1", "maxVideoBitrate": "3000", "mediaIndex": "0", "offset": "0", "partIndex": "0", "path": "http://127.0.0.1:32400/library/metadata/321", "protocol": "hls", "session": "xk4kbse0xxadzpvi", "subtitleSize": "100", "videoQuality": "75", "videoResolution": "1280x720"}}
{"datetime": [2013, 7, 4, 19, 34, 30, 655], "debug_level": "DEBUG", "file_line_no": 39971, "file_name": "Plex Media Server.log", "method": "GET", "request_ip": "127.0.0.1", "request_port": "62216", "url_path": "/:/timeline", "url_query": {"duration": "2582880", "key": "/library/metadata/321", "ratingKey": "321", "state": "playing", "time": "0"}}
{"datetime": [2013, 7, 4, 19, 35, 29, 135], "debug_level": "DEBUG", "file_line_no": 40242, "file_name": "Plex Media Server.log", "method": "GET", "request_ip": "127.0.0.1", "request_port": "62298", "url_path": "/:/timeline", "url_query": {"duration": "2582880", "key": "/library/metadata/321", "ratingKey": "321", "state": "stopped", "time": "2582880"}}
{"datetime": [2013, 7, 4, 19, 35, 31, 977], "debug_level": "DEBUG", "file_line_no": 40263, "file_name": "Plex Media Server.log", "method": "GET", "request_ip": "127.0.0.1", "request_port": "62302", "url_path": "/video/:/transcode/universal/stop", "url_query": {"session": "xk4kbse0xxadzpvi"}}

"""