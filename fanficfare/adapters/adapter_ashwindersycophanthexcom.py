# -*- coding: utf-8 -*-

# Copyright 2011 Fanficdownloader team, 2018 FanFicFare team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

# Software: eFiction
from __future__ import absolute_import
import logging
logger = logging.getLogger(__name__)
import re
from ..htmlcleanup import stripHTML
from .. import exceptions as exceptions

# py2 vs py3 transition
from ..six import text_type as unicode

from .base_adapter import BaseSiteAdapter,  makeDate

def getClass():
    return AshwinderSycophantHexComAdapter

# Class name has to be unique.  Our convention is camel case the
# sitename with Adapter at the end.  www is skipped.
class AshwinderSycophantHexComAdapter(BaseSiteAdapter):

    def __init__(self, config, url):
        BaseSiteAdapter.__init__(self, config, url)

        self.username = "NoneGiven" # if left empty, site doesn't return any message at all.
        self.password = ""
        self.is_adult=False

        # get storyId from url--url validation guarantees query is only sid=1234
        self.story.setMetadata('storyId',self.parsedUrl.query.split('=',)[1])



        # normalized story URL.
        self._setURL('https://' + self.getSiteDomain() + '/viewstory.php?sid='+self.story.getMetadata('storyId'))

        # Each adapter needs to have a unique site abbreviation.
        self.story.setMetadata('siteabbrev','asph')

        # The date format will vary from site to site.
        # http://docs.python.org/library/datetime.html#strftime-strptime-behavior
        self.dateformat = "%m/%d/%Y"

    @staticmethod # must be @staticmethod, don't remove it.
    def getSiteDomain():
        # The site domain.  Does have www here, if it uses it.
        return 'ashwinder.sycophanthex.com'

    @classmethod
    def getSiteExampleURLs(cls):
        return "https://"+cls.getSiteDomain()+"/viewstory.php?sid=1234"

    def getSiteURLPattern(self):
        return r"https?://"+re.escape(self.getSiteDomain()+"/viewstory.php?sid=")+r"\d+$"

    ## Login seems to be reasonably standard across eFiction sites.
    def needToLoginCheck(self, data):
        if 'This story contains adult content and/or themes.' in data \
                or "That password doesn't match the one in our database" in data \
                or "Member Login" in data:
            return True
        else:
            return False

    def performLogin(self, url):
        params = {}

        if self.password:
            params['penname'] = self.username
            params['password'] = self.password
        else:
            params['penname'] = self.getConfig("username")
            params['password'] = self.getConfig("password")
        params['rememberme'] = '1'
        params['sid'] = ''
        params['intent'] = ''
        params['submit'] = 'Submit'

        loginUrl = 'https://' + self.getSiteDomain() + '/user.php'
        logger.debug("Will now login to URL (%s) as (%s)" % (loginUrl,
                                                              params['penname']))

        d = self.post_request(loginUrl, params)

        if "Logout" not in d : #Member Account
            logger.info("Failed to login to URL %s as %s" % (loginUrl,
                                                              params['penname']))
            raise exceptions.FailedToLogin(url,params['penname'])
            return False
        else:
            return True

    ## Getting the chapter list and the meta data, plus 'is adult' checking.
    def extractChapterUrlsAndMetadata(self):
        # index=1 makes sure we see the story chapter index.  Some
        # sites skip that for one-chapter stories.
        url = self.url
        logger.debug("URL: "+url)

        data = self.get_request(url)

        if self.needToLoginCheck(data):
            # need to log in for this one.
            self.performLogin(url)
            data = self.get_request(url)

        if "Access denied. This story has not been validated by the adminstrators of this site." in data:
            raise exceptions.AccessDenied(self.getSiteDomain() +" says: Access denied. This story has not been validated by the adminstrators of this site.")

        soup = self.make_soup(data)
        # print data


        # Find authorid and URL from... author url.
        a = soup.find('a', href=re.compile(r"viewuser.php\?uid=\d+"))
        self.story.setMetadata('authorId',a['href'].split('=')[1])
        self.story.setMetadata('authorUrl','https://'+self.host+'/'+a['href'])
        self.story.setMetadata('author',a.string)
        asoup = self.make_soup(self.get_request(self.story.getMetadata('authorUrl')))

        try:
            # in case link points somewhere other than the first chapter
            a = soup.find_all('option')[1]['value']
            self.story.setMetadata('storyId',a.split('=',)[1])
            url = 'https://'+self.host+'/'+a
            soup = self.make_soup(self.get_request(url))
        except:
            pass

        for info in asoup.find_all('table', {'width' : '100%', 'bordercolor' : re.compile(r'#')}):
            a = info.find('a', href=re.compile(r'viewstory.php\?sid='+self.story.getMetadata('storyId')+"$"))
            if a != None:
                self.story.setMetadata('title',stripHTML(a))
                break


        # Find the chapters:
        chapters=soup.find_all('a', href=re.compile(r'viewstory.php\?sid=\d+&i=1$'))
        if len(chapters) == 0:
            self.add_chapter(self.story.getMetadata('title'),url)
        else:
            for chapter in chapters:
                # just in case there's tags, like <i> in chapter titles.
                self.add_chapter(chapter,'https://'+self.host+'/'+chapter['href'])


        # eFiction sites don't help us out a lot with their meta data
        # formating, so it's a little ugly.

        # utility method
        def defaultGetattr(d):
            try:
                return d.name
            except:
                return ""

        cats = info.find_all('a',href=re.compile('categories.php'))
        for cat in cats:
            self.story.addToList('category',cat.string)

        a = info.find('a', href=re.compile(r'reviews.php\?sid='+self.story.getMetadata('storyId')))
        val = a.nextSibling
        svalue = ""
        while not defaultGetattr(val) == 'br':
            val = val.nextSibling
        val = val.nextSibling
        while not defaultGetattr(val) == 'table':
            svalue += unicode(val)
            val = val.nextSibling
        self.setDescription(url,svalue)

        ## <td><span class="sb"><b>Published:</b> 04/08/2007</td>

        ## one story had <b>Updated...</b> in the description. Restrict to sub-table
        labels = info.find('table').find_all('b')
        for labelspan in labels:
            value = labelspan.nextSibling
            label = stripHTML(labelspan)

            if 'Rating' in label:
                self.story.setMetadata('rating', value)

            if 'Word Count' in label:
                self.story.setMetadata('numWords', value)

            if 'Genres' in label:
                genres = value.string.split(', ')
                for genre in genres:
                    if genre != 'none':
                        self.story.addToList('genre',genre)

            if 'Warnings' in label:
                warnings = value.string.split(', ')
                for warning in warnings:
                    if warning != ' none':
                        self.story.addToList('warnings',warning)

            if 'Completed' in label:
                if 'Yes' in value:
                    self.story.setMetadata('status', 'Completed')
                else:
                    self.story.setMetadata('status', 'In-Progress')

            if 'Published' in label:
                self.story.setMetadata('datePublished', makeDate(stripHTML(value), self.dateformat))

            if 'Updated' in label:
                # there's a stray [ at the end.
                #value = value[0:-1]
                self.story.setMetadata('dateUpdated', makeDate(stripHTML(value), self.dateformat))


    # grab the text for an individual chapter.
    def getChapterText(self, url):

        logger.debug('Getting chapter text from: %s' % url)

        data = self.get_request(url)

        soup = self.make_soup(data) # some chapters seem to be hanging up on those tags, so it is safer to close them

        story = soup.find('div', {"align" : "left"})

        if None == story:
            raise exceptions.FailedToDownload("Error downloading Chapter: %s!  Missing required element!" % url)

        return self.utf8FromSoup(url,story)
