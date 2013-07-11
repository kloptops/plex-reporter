#/usr/bin/env python
# -*- coding: utf-8 -*-
# -*- python -*-

import os
import re
import logging
import json
from glob import glob as file_glob

from plex import PlexLogParser, PlexServerConnection, PlexMediaObject


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




plex_sample_episode = """<?xml version="1.0" encoding="UTF-8"?>
<MediaContainer size="1" allowSync="1" identifier="com.plexapp.plugins.library" librarySectionID="1" librarySectionUUID="b0ab35c6-99b7-448b-bb0e-745ed9567909" mediaTagPrefix="/system/bundle/media/flags/" mediaTagVersion="1370244290">
<Video ratingKey="11303" key="/library/metadata/11303" parentRatingKey="11296" grandparentRatingKey="11295" guid="com.plexapp.agents.thetvdb://262026/1/7?lang=en" type="episode" title="Episode Seven" grandparentKey="/library/metadata/11295" parentKey="/library/metadata/11296" grandparentTitle="House Husbands" contentRating="TV-PG" summary="With the clock ticking on his child custody hearing, Justin learns the truth about Rodney&apos;s role in the end of his marriage and football career. Lucy has second thoughts after she and Justin decide to move in together." index="7" parentIndex="1" rating="7.5" viewOffset="1297000" lastViewedAt="1373456297" year="2012" thumb="/library/metadata/11303/thumb/1372067395" art="/library/metadata/11295/art/1372768241" parentThumb="/library/metadata/11296/thumb/1372067411" grandparentThumb="/library/metadata/11295/thumb/1372768241" duration="2496048" originallyAvailableAt="2012-10-14" addedAt="1372067259" updatedAt="1372067395">
<Media id="10526" duration="2496048" bitrate="1176" width="624" height="352" aspectRatio="1.78" audioChannels="2" audioCodec="mp3" videoCodec="mpeg4" videoResolution="sd" container="avi" videoFrameRate="PAL">
<Part id="10653" key="/library/parts/10653/file.avi" duration="2496048" file="F:\TV\House Husbands\Season 1\House Husbands - S01E07 - Episode Seven.avi" size="367028224" container="avi">
<Stream id="25134" streamType="1" codec="mpeg4" index="0" bitrate="1027" bitDepth="8" chromaSubsampling="4:2:0" colorSpace="yuv" duration="2496040" frameRate="25.000" gmc="0" height="352" level="5" profile="asp" qpel="0" scanType="progressive" width="624" />
<Stream id="25135" streamType="2" selected="1" codec="mp3" index="1" channels="2" bitrate="136" bitrateMode="vbr" duration="2496048" samplingRate="48000" />
</Part>
</Media>
</Video>
</MediaContainer>
"""

plex_sample_movie = """"<?xml version="1.0" encoding="UTF-8"?>
<MediaContainer size="1" allowSync="1" identifier="com.plexapp.plugins.library" librarySectionID="3" librarySectionUUID="87fccbab-9d4c-40e7-87f9-321fb60a0d24" mediaTagPrefix="/system/bundle/media/flags/" mediaTagVersion="1370244290">
<Video ratingKey="11282" key="/library/metadata/11282" guid="com.plexapp.agents.imdb://tt0184894?lang=en" studio="Spyglass Entertainment" type="movie" title="Shanghai Noon" contentRating="PG-13" summary="Chon Wang, a clumsy imperial guard trails Princess Pei Pei when she is kidnapped from the Forbidden City and transported to America. Wang follows her captors to Nevada, where he teams up with an unlikely partner, outcast outlaw Roy O&apos;Bannon, and tries to spring the princess from her imprisonment." rating="6.5999999046325701" viewCount="1" lastViewedAt="1371906931" year="2000" tagline="The old west meets the far east." thumb="/library/metadata/11282/thumb/1371888078" art="/library/metadata/11282/art/1371888078" duration="6626286" originallyAvailableAt="2000-05-26" addedAt="1371887993" updatedAt="1371888078">
<Media id="10511" duration="6626286" bitrate="887" width="608" height="272" aspectRatio="2.20" audioChannels="2" audioCodec="mp3" videoCodec="mpeg4" videoResolution="sd" container="avi" videoFrameRate="24p">
<Part id="10638" key="/library/parts/10638/file.avi" duration="6626286" file="F:\Movies\Shanghai Noon (2000)\Shanghai Noon (2000).avi" size="735047680" container="avi">
<Stream id="25138" streamType="1" codec="mpeg4" index="0" bitrate="759" bitDepth="8" bvop="1" chromaSubsampling="4:2:0" colorSpace="yuv" duration="6626286" frameRate="23.976" gmc="0" height="272" level="5" profile="asp" qpel="0" scanType="progressive" width="608" />
<Stream id="25139" streamType="2" selected="1" codec="mp3" index="1" channels="2" bitrate="115" bitrateMode="vbr" duration="6626280" samplingRate="48000" />
</Part>
</Media>
<Genre id="20" tag="Action" />
<Genre id="21" tag="Adventure" />
<Genre id="74" tag="Comedy" />
<Genre id="4339" tag="Western" />
<Writer id="2546" tag="Alfred Gough" />
<Writer id="2547" tag="Miles Millar" />
<Director id="4053" tag="Tom Dey" />
<Producer id="7101" tag="Gary Barber" />
<Producer id="7102" tag="Roger Birnbaum" />
<Producer id="4928" tag="Jonathan Glickman" />
<Country id="2919" tag="USA" />
<Role id="5908" tag="Jackie Chan" role="Chon Wang" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/wnYZ7vml6SBdWUWw7ypXlWkH3V0.jpg" />
<Role id="4058" tag="Owen Wilson" role="Roy O&apos;Bannon" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/j7OAiUKkcckSmixWL8FoacqQnx4.jpg" />
<Role id="5920" tag="Lucy Liu" role="Princess Pei Pei" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/ziLXbVMHQIpJbaiATHCSSAEonYE.jpg" />
<Role id="5643" tag="Xander Berkeley" role="Nathan Van Cleef" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/f312V2r441CHAZS1pwMcrBUF6rd.jpg" />
<Role id="7085" tag="Brandon Merrill" role="Indian Wife" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/5xEfRbl76OV6etF5EnaWr5B4GtP.jpg" />
<Role id="7086" tag="Roger Yuan" role="Lo Fong" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/rXZGun6ZfyBQd1lvIpuAMmFx8wZ.jpg" />
<Role id="7087" tag="Yu Rong-Guang" role="Imperial Guard" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/9LxWXXXJM8R0O9LGnec3ajURVfa.jpg" />
<Role id="7088" tag="Ya Hi Cui" role="Imperial Guard" />
<Role id="7089" tag="Eric Chen" role="Imperial Guard" />
<Role id="7090" tag="Jason Connery" role="Andrews" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/9tDTxkPBFSIq57DTE40NZ9Bp4Yu.jpg" />
<Role id="7091" tag="Walton Goggins" role="Wallace" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/3ESBPeIUGxB4rptFoWvIcC9UskL.jpg" />
<Role id="6504" tag="Adrien Dorval" role="Blue" />
<Role id="7092" tag="Rafael Báez" role="Vasquez" />
<Role id="7093" tag="Stacy Grant" role="Hooker in Distress" />
<Role id="7094" tag="Kate Luyben" role="Fifi" />
<Role id="7095" tag="Henry O" role="Royal Interpreter" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/cJ7rk3cmGOc0m1T90oPgZylntcs.jpg" />
<Role id="7096" tag="Russell Badger" role="Sioux Chief" />
<Role id="7097" tag="Simon Baker" role="Little Feather" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/8LXqDu1mAZLWbTvrHKC1r3JZ3Jz.jpg" />
<Role id="7098" tag="Sam Simon" role="Chief&apos;s Sidekick" />
<Role id="7099" tag="Alan C. Peterson" role="Saddle Rock Sheriff" thumb="http://d3gtl9l2a4fn1j.cloudfront.net/t/p/original/esrNQmnKq7GYF810l3MmoKjYpsn.jpg" />
<Role id="7100" tag="Rad Daly" role="Saddle Rock Deputy" />
</Video>
</MediaContainer>
"""


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

    conn = PlexServerConnection('norti-pc.local', 32400)
    temp = PlexMediaObject(conn, None, plex_sample_episode)
    print(temp)
    print(temp.media)
    print(temp.parts)

    temp = PlexMediaObject(conn, None, plex_sample_movie)
    print(temp)
    print(temp.media)
    print(temp.parts)

    temp = PlexMediaObject(conn, 10)
    print(temp)
    print(temp.media)
    print(temp.parts)

    temp = PlexMediaObject(conn, 10000000)
    print(temp)
    print(temp.media)
    print(temp.parts)




if __name__ == '__main__':
    main()
