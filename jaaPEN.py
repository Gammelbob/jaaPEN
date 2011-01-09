##############################################################################
#
#    jaaPEN - just another automatic penetration tool for webapplications
#
##############################################################################

##############################################################################
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
##############################################################################

############################################
#
# jaaPEN - 2011 by Gammelbob
#
# Changelog:
# 0.0.2 - basic crawling and blacklisting
# 0.0.1 - initial commit
############################################

import sys
import re
import urllib2
import urlparse

try:
    tocrawl = set([sys.argv[1]])
except:
    print 'first parameter has to be your URL like http://localhost'
    exit()
try:
    if sys.argv[2] == 'show':
        showResults = True
    else:
        showResults = False
except:
    showResults = False

crawled = set([])
blacklist = set([])
external = set([])
baselinks = set([])
dynlinks = set([])
linkregex = re.compile('<a\s*href=[\'|"](.*?)[\'"].*?>')
filterExternal = True

while True:
    try:
        crawling = tocrawl.pop()
    except KeyError:
        if showResults:
            print 'Blacklist:'
            for value in blacklist:
                print value
            print 'external:'
            for value in external:
                print value
            print 'baselinks:'
            for value in baselinks:
                print value
            print 'dynlinks:'
            for value in dynlinks:
                print value
            #print 'crawled:'
            #for value in crawled:
            #    print value
        print '==========================================='
        print ' crawled pages: %s' % len(crawled)
        print ' links in backlist: %s' % len(blacklist)
        print ' found baselinks: %s' % len(baselinks)
        print ' found external links: %s' % len(external)
        print ' found dynlinks: %s' % len(dynlinks)
        print '==========================================='
        exit()
    url = urlparse.urlparse(crawling)
    try:
        response = urllib2.urlopen(crawling)
        #print crawling
    except:
        continue
    msg = response.read()
    links = linkregex.findall(msg)
    crawled.add(crawling)
    for link in (links.pop(0) for _ in xrange(len(links))):
        if link not in blacklist and link not in crawled and (filterExternal and link not in external):
            if link.startswith('/'):
                link = 'http://' + url[1] + link
            elif link.startswith('#'):
                link = 'http://' + url[1] + url[2] + link
            elif not link.startswith('http') and '://' in link:
                #print 'found an malicous link: ' + link
                blacklist.add(link)
            elif not link.startswith('http'):
                link = 'http://' + url[1] + '/' + link
            if not link.startswith(sys.argv[1]) and link not in blacklist:
                #print 'found an external link: ' + link
                external.add(link)
            if link not in crawled and link not in blacklist and (filterExternal and link not in external):
                try:
                    baselinks.add(link.split('?')[0])
                    dynlinks.add(link.split('?')[1])
                except:
                    # no ? in link
                    continue
                tocrawl.add(link)
