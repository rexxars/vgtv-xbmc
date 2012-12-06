#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.


# This module contains helper functions that interact with the VGTV.no JSON API

import simplejson
import urllib2
from utils import unescape
from datetime import datetime
from datetime import timedelta
from urllib import urlencode

class VgtvApi():

    API_URL = 'http://api.vgtv.no/api/actions'
    PER_PAGE = 21
    plugin = None
    categories = None

    def __init__(self, plugin):
        self.plugin = plugin;

    def get_api_url(self, url, params={}):
        defaults = {'formats': 'http', 'meta': 1}
        params = dict(defaults.items() + params.items())
        return self.API_URL + url + '?' + urlencode(params)


    def get_default_video_list(self, url, page, raw=False, params={}):
        if raw is False:
            offset = self.calculate_offset(page)
            params.update({'limit': self.PER_PAGE, 'offset': offset})
            url = self.get_api_url(url=url, params=params)

        response = urllib2.urlopen(url)
        return self.parse_video_response(response)

    def get_category_tree(self):
        if self.categories is not None:
            return self.categories

        url = 'http://cmsapi.vgtv.no/categories/drvideo-list'
        response = urllib2.urlopen(url)
        data = simplejson.loads(response.read())
        self.categories = data
        return data

    def get_categories(self, root_id=0):
        categories = self.get_category_tree()

        matches = [];
        for id in categories:

            if int(id) < 0:
                continue

            category = categories.get(id)
            if (int(category.get('parentId')) == int(root_id)):
                matches.append({
                    'label': unescape(category.get('name')),
                    'path' : self.plugin.url_for('show_category', id=str(id)),
                    'id'   : id
                })

        return matches

    def resolve_video_url(self, video_id):
        url = self.get_api_url(url='/video/', params={'id': video_id});
        response = urllib2.urlopen(url)
        data = simplejson.loads(response.read())
        return self.get_video_urls(data, allow_resolve=False)

    def parse_video_response(self, response):
        data  = simplejson.loads(response.read())
        items = list()
        count = 0
        for video in data['videos']:
            video_url, thumbnail_url = self.get_video_urls(video)
            count += 1

            if video_url is None:
                continue

            meta = video.get('meta')
            items.append({
                'label': unescape(meta.get('title')),
                'thumbnail': thumbnail_url,
                'info': {
                    'plot': unescape(meta.get('preamble') or ''),
                    'originaltitle': unescape(meta.get('title') or '???'),
                    'tagline': unescape(meta.get('preamble') or ''),
                    'aired': self.get_date(meta.get('timePublished')),
                    'duration': self.get_duration(meta.get('duration'))
                },
                'path': video_url,
                'is_playable': True,
            })

        return items, (count < self.PER_PAGE)


    def get_video_urls(self, video, allow_resolve=True):
        highest_bitrate = 0
        best_thumb  = {'width': 10000}
        best_format = None

        # Some videos do not have a formats array
        if 'formats' not in video and allow_resolve:
            video_url = self.plugin.url_for('play_video', id=str(video['id']))
            thumb_url = self.build_thumbnail_url({
                'width': 354,
                'height': 199
            }, video['id'])

            return video_url, thumb_url
        elif 'formats' not in video:
            self.plugin.log.warning('Formats not in video-response')
            return None, None

        # MP4 or m3u8?
        if (allow_resolve):
            # Use MP4 by default
            format = 'mp4'
            if ('mp4' not in video['formats']['http'] and
                'm3u8' in video['formats']['http']):
                format = 'm3u8'
        else:
            # Reverse order for stuff we have to resolve
            # Had some trouble getting mp4 stream to work
            format = 'm3u8'
            if ('m3u8' not in video['formats']['http'] and
                'mp4' in video['formats']['http']):
                format = 'mp4'

        # Loop through the formats to find the best one
        for format in video['formats']['http'][format]:
            # Find the highest bitrate available
            if format['bitrate'] > highest_bitrate:
                highest_bitrate = format['bitrate']
                best_format = format

            # Thumbs seem to be around ~300px in general
            if format['width'] > 310 and format['width'] < best_thumb['width']:
                best_thumb = format

        # Fall back if something failed
        if best_format is None:
            self.plugin.log.error('No format found for video %s' % video['id'])
            return None, None

        # If we didn't find a fitting thumb, use thumb from the highest bitrate
        if 'height' not in best_thumb:
            best_thumb = best_format

        video_url = self.build_video_url(best_format['paths'][0])
        thumb_url = self.build_thumbnail_url(best_thumb, video['id'])
        return video_url, thumb_url


    def build_video_url(self, p):
        # p = parts
        url = 'http://%s/%s/%s' % (p['address'], p['path'], p['filename'])
        return url


    def build_thumbnail_url(self, d, id):
        # d = dimensions
        url = 'http://api.vgtv.no/images/id/' + str(id / 1000) + 'xxx/'
        url += '%s/w%dh%dc.jpg' % (id % 1000, d['width'], d['height'])
        return url


    def calculate_offset(self, page):
        return self.PER_PAGE * (int(page) - 1)


    def get_date(self, timestamp):
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')


    def get_duration(self, secs):
        return timedelta(seconds=secs)
