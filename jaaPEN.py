######################################################################################
#
#    jaaPEN - just another automatic penetration testing tool for webapplications
#
######################################################################################

######################################################################################
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
######################################################################################

######################################################################################
#
# jaaPEN - 2011 by Gammelbob
# https://github.com/Gammelbob/jaaPEN
#
# Changelog:
# 0.0.5 - added project table to store data for more than one site
# 0.0.4 - switched over to sqlite. some local vars are still in use.
# 0.0.3 - added GET detection
# 0.0.2 - added basic crawling and blacklisting
# 0.0.1 - initial commit
#
#2do: remove all general exceptions
#2do: db-qry replace % with ?
#more at grep -Hirn "2do:" .
######################################################################################

import sys
import re
import urllib2
import urlparse
import time
try:
    from pysqlite2 import dbapi2 as sqlite
except ImportError:
    import sqlite3 as sqlite

version = '0.0.5'
showResults = False
saveResults = False
filterExternal = True
projectID = 1

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
        showResults = True
        #2do: if iswritable(sys.argv[3]): set saveResults = True, remove showResults here as it is set to False on init
except:
    showResults = True

connection = sqlite.connect(':memory:')
#connection = sqlite.connect('/tmp/jaaPEN')
cursor = connection.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS `projects` (projectID INTEGER PRIMARY KEY AUTOINCREMENT, description VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `baselinks` (baseID INTEGER PRIMARY KEY AUTOINCREMENT, projectID INTEGER, baselink VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `keys` (keyID INTEGER PRIMARY KEY AUTOINCREMENT, baseID INTEGER, type VARCHAR(20), key VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `valuaes` (valueID INTEGER PRIMARY KEY AUTOINCREMENT, keyID INTEGER, value VARCHAR(255))")
# valuaes is not a typo. you cant have something like values as a table name in sqlite. 2 hours gone to realise it :o

crawled = set([])
blacklist = set([])
external = set([])
linkregex = re.compile('<a\s*href=[\'|"](.*?)[\'"].*?>')
jobtime = time.time()
print '# started crawling for projectID %i' % projectID
while True:
    try:
        crawling = tocrawl.pop()
    except KeyError:
        # job done, presenting the results
        cntBaseLinks = cursor.execute('SELECT count(baseID) FROM baselinks WHERE projectID = %i' % projectID).fetchone()[0]
        cntGetKeys = cursor.execute('SELECT count(keyID) FROM keys WHERE baseID IN (SELECT baseID FROM baselinks WHERE projectID = %i)' % projectID).fetchone()[0]
        cntGetValues = cursor.execute('SELECT count(valueID) FROM valuaes WHERE keyID IN (SELECT keyID FROM keys WHERE baseID IN (SELECT baseID FROM baselinks WHERE projectID = %i))' % projectID).fetchone()[0]
        if showResults:
            for baselinkRow in cursor.execute("SELECT baseID, baselink FROM `baselinks` WHERE projectID = %i" % projectID).fetchall():
                print '%s' % baselinkRow[1]
                for typeRow in cursor.execute("SELECT type FROM `keys` WHERE baseID = %i GROUP BY `keys`.type" % baselinkRow[0]).fetchall():
                    print '\t%s' % typeRow[0]
                    for keyRow in cursor.execute("SELECT keyID, key  FROM `keys` WHERE baseID = %i AND type='%s'" % (baselinkRow[0], typeRow[0])).fetchall():
                        print '\t\t%s' % keyRow[1]
                        for valueRow in cursor.execute("SELECT value FROM `valuaes` WHERE keyID = %i" % keyRow[0]).fetchall():
                            print '\t\t\t%s' % valueRow[0]
        jobtime = time.time() - jobtime
        pagesPerSec = len(crawled) / jobtime
        jobtime = int(jobtime)
        print '######'
        print '#  crawled pages\t%s in ~%s seconds' % (len(crawled),jobtime)
        print '#  which means\t\t%f pages/s' % pagesPerSec
        print '#  blacklisted links\t%s' % len(blacklist)
        print '#  external links\t%s' % len(external)
        print '#  found baselinks\t%s' % cntBaseLinks
        print '#  found get-keys\t%s' % cntGetKeys
        print '#  found get-values\t%s' % cntGetValues
        print '######'
        # commit our changes which is only needed at a physical file, not at an in-memory database.
        # well.. maybe not even there because of connection.close() afterwards.
        #connection.commit()
        connection.close()
        exit()

    #2do: switch to threads with blocking sockets (could be a problem with sqlite because of missing multiconnections) or:
    #2do: switch to multiple non blocking sockets (which would cause the same problem)
    url = urlparse.urlparse(crawling)
    try:
        response = urllib2.urlopen(crawling)
    except:
        print '# we got an error while requesting "%s"' % crawling
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
                print '# found a weired link: ' + link
                blacklist.add(link)
            elif not link.startswith('http'):
                link = 'http://' + url[1] + '/' + link
            if not link.startswith(sys.argv[1]) and link not in blacklist:
                print '# found an external link: ' + link
                external.add(link)
            if link not in crawled and link not in blacklist and (filterExternal and link not in external):
                # we finally found a new link to crawl, lets get the attributes
                # baselink
                if '?' in link:
                    baselink = link.split('?')[0]
                    dynlink = link.split('?')[1]
                else:
                    baselink = link
                    dynlink = ''
                baselinkResult = cursor.execute("SELECT baselink, baseID FROM `baselinks` WHERE projectID = %i AND baselink = '%s'" % (projectID,baselink)).fetchone()
                if not baselinkResult or not baselinkResult[0] == baselink:
                    cursor.execute("INSERT INTO `baselinks` VALUES(NULL,%i,'%s')" % (projectID,baselink))
                    baseindex = cursor.lastrowid
                else:
                    baseindex = baselinkResult[1]

                # get our GET parameter
                if '&' in dynlink or '=' in dynlink:
                    parameters = dynlink.split('&')
                elif dynlink == '':
                    parameters = ''
                else:
                    # we got a weired dynlink
                    print '# found a weired dynlink: %s' % dynlink
                    parameters = ''
                for parameter in parameters:
                    if '=' in parameter:
                        key = parameter.split('=')[0]
                        value = parameter.split('=')[1]
                        # lets check if we already know this key in relation to our baselink
                        keyResult = cursor.execute("SELECT key, keyID FROM `keys`,`baselinks` WHERE `keys`.baseID = `baselinks`.baseID AND projectID = %i AND baselink = '%s' AND key = '%s'" % (projectID,baselink,key)).fetchone()
                        if not keyResult or not keyResult[0] == key:
                            cursor.execute("INSERT INTO `keys` VALUES(NULL,%i,'%s','%s')" % (baseindex,'GET',key))
                            keyindex = cursor.lastrowid
                        else:
                            keyindex = keyResult[1]
                        # lets check if we already know this value in relation to our key
                        valueResult = cursor.execute("SELECT value, valueID FROM `valuaes` WHERE `valuaes`.keyID = %i AND value = '%s'" % (keyindex,value)).fetchone()
                        if not valueResult or not valueResult[0] == value:
                            cursor.execute("INSERT INTO `valuaes` VALUES (NULL,%i,'%s')" % (keyindex,value))
                    else:
                        # we got a weired parameter
                        print '# found a weired parameter: %s' % parameter
                tocrawl.add(link)

