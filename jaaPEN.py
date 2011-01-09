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
# 0.0.3 - added GET detection
# 0.0.2 - added basic crawling and blacklisting
# 0.0.1 - initial commit
############################################

import sys
import re
import urllib2
import urlparse

version = '0.0.3'

try:
    if sys.argv[1] == 'version' or sys.argv[1] == '-version' or sys.argv[1] == '--version':
        print 'jaaPEN version %s' % version
        exit()
    tocrawl = set([sys.argv[1]])
except:
    print 'Usage: jaaPEN http://localhost [show|save] [file]'
    exit()
try:
    if sys.argv[2] == 'show':
        showResults = True
    elif sys.argv[2] == 'save':
        showResults = False
        #2do: if iswritable(sys.argv[3]): set showResults = False, set saveResults = True
except:
    showResults = True
    saveResults = False

crawled = set([])
blacklist = set([])
external = set([])
baselinks = set([])
dynlinks = set([])
getKeys = set([])
getValues = set([])
getParameter =set([]) 
linkregex = re.compile('<a\s*href=[\'|"](.*?)[\'"].*?>')
filterExternal = True
jobtime = ''
while True:
    try:
        crawling = tocrawl.pop()
    except KeyError:
        if showResults:
            print '\nBlacklist:'
            for value in blacklist:
                print value
            print '\nexternal:'
            for value in external:
                print value
            print '\nbaselinks:'
            for value in baselinks:
                print value
            print '\nget-parameter:'
            for value in getParameter:
                print value
            print '\nget-keys:'
            for value in getKeys:
                print value
            #print 'dynlinks:'
            #for value in dynlinks:
            #    print value
            #print 'crawled:'
            #for value in crawled:
            #    print value
        print '==========================================='
        print ' crawled pages: %s%s' % (len(crawled), ' in'.join(jobtime))
        print ' links in blacklist: %s' % len(blacklist)
        print ' found external links: %s' % len(external)
        print ' found baselinks: %s' % len(baselinks)
        print ' found dynlinks: %s' % len(dynlinks)
        print ' found get-parameter: %s' % len(getParameter)
        print ' found get-keys: %s' % len(getKeys)
        print ' found get-values: %s' % len(getValues)
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
            elif not link.startswith('http') and ':' in link:
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
    for dynlink in dynlinks:
        parameters = dynlink.split('&')
        for parameter in parameters:
            try:
                key = parameter.split('=')[0]
                value = parameter.split('=')[1]
                getParameter.add(parameter)
                getKeys.add(key)
                getValues.add(value)
                #2do: store values in relation to the key like getKeys[key].add(value)
            except:
                print 'error while splitting key. parameter="%s" key="%s"' % (parameter, parameter.split('=')[0])

