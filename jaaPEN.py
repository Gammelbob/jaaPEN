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
# 0.0.6 - better performance by reducing sql-queries and rewritten linkhandling
# 0.0.5 - added project table to store data for more than one site
# 0.0.4 - switched over to sqlite. some local vars are still in use.
# 0.0.3 - added GET detection
# 0.0.2 - added basic crawling and blacklisting
# 0.0.1 - initial commit
#
#2do: remove all general exceptions
#2do: db-qry replace % with ?
#more at grep -Hirn "2do:" .
#issues:
# - try: tmp = storage[baselink][key][value] except KeyError: is bad in many ways.
# if not storage[baselink][key][value]: would be nicer but i did not get it to work
# - 'myID' in local dict storage[..] could be a key or val at the target site
######################################################################################

import sys
import re
import urllib2
import urlparse
import time
from collections import defaultdict
try:
    from pysqlite2 import dbapi2 as sqlite
except ImportError:
    import sqlite3 as sqlite

version = '0.0.6'
showResults = False
saveResults = False
filterExternal = True
projectID = 1
dbfile = ':memory:'
#dbfile = '/tmp/jaaPEN'

try:
    if sys.argv[1] == 'version' or sys.argv[1] == '-version' or sys.argv[1] == '--version':
        print 'jaaPEN version %s' % version
        exit()
    tocrawl = set([sys.argv[1]])
except:
    print 'Usage: jaaPEN url [show|save] [file]'
    print '# Example 1: jaaPEN http://localhost'
    print '# Example 2: jaaPEN http://localhost show'
    print '# Example 3: jaaPEN http://localhost save'
    print '# Example 4: jaaPEN http://localhost save results.log\n'
    print "# Example 1 will display the results as a tree."
    print "# Example 2 will display the results as a tree."
    print "# Example 3 will display nothing but errors."
    print "# Example 4 will display nothing but errors. The results will be saved in the given file as a tree."
    print "# Runtime stats will be displayed on all examples."
    exit()

try:
    if sys.argv[2] == 'show':
        showResults = True
    elif sys.argv[2] == 'save':
        showResults = False
        #2do: if iswritable(sys.argv[3]): set saveResults = True, remove showResults here as it is set to False on init
except:
    showResults = True


connection = sqlite.connect(dbfile)
cursor = connection.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS `projects` (projectID INTEGER PRIMARY KEY AUTOINCREMENT, description VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `baselinks` (baseID INTEGER PRIMARY KEY AUTOINCREMENT, projectID INTEGER, baselink VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `keys` (keyID INTEGER PRIMARY KEY AUTOINCREMENT, baseID INTEGER, type VARCHAR(20), key VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `valuaes` (valueID INTEGER PRIMARY KEY AUTOINCREMENT, keyID INTEGER, value VARCHAR(255))")
# valuaes is not a typo. you cant have something like values as a table name in sqlite. 2 hours gone to realise it :o

crawled = set([])
blacklist = set([])
external = set([])
storage = dict()

linkregex = re.compile('<a\s*href=[\'|"](.*?)[\'"].*?>')

try:
    print '# loading previous results from db'
    # refresh our local vars [baselink][..doh. type is missing..][key][value]['myID']
    for baselinkRow in cursor.execute("SELECT baseID, baselink FROM `baselinks` WHERE projectID = %i" % projectID).fetchall():
        storage[baselinkRow[1]] = dict()
        storage[baselinkRow[1]]['myID'] = baselinkRow[0]
        for typeRow in cursor.execute("SELECT type FROM `keys` WHERE baseID = %i GROUP BY `keys`.type" % baselinkRow[0]).fetchall():
            for keyRow in cursor.execute("SELECT keyID, key  FROM `keys` WHERE baseID = %i AND type='%s'" % (baselinkRow[0], typeRow[0])).fetchall():
                storage[baselinkRow[1]][keyRow[1]] = dict()
                storage[baselinkRow[1]][keyRow[1]]['myID'] = keyRow[0]
                for valueRow in cursor.execute("SELECT valueID, value FROM `valuaes` WHERE keyID = %i" % keyRow[0]).fetchall():
                    storage[baselinkRow[1]][keyRow[1]][valueRow[1]] = dict()
                    storage[baselinkRow[1]][keyRow[1]][valueRow[1]]['myID'] = valueRow[0]
except:
    print '# loading previous results from DB failed. guessing new table or in-memory DB'

print '# started crawling for projectID %i' % projectID
jobtime = time.time()
while True:
    try:
        crawling = tocrawl.pop()
        if crawling in blacklist:
            print "this should really not happen"
            continue
    except KeyError:
        # job done, presenting the results
        jobtime = time.time() - jobtime
        pagesPerSec = len(crawled) / jobtime
        jobtime = int(jobtime)
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
        print '######'
        print '#  crawled pages\t%i in ~%s seconds' % (len(crawled),jobtime)
        print '#  which means\t\t%f pages/s' % pagesPerSec
        print '#  blacklisted links\t%i' % (len(blacklist) - len(external))
        print '#  external links\t%i' % len(external)
        print '#  found baselinks\t%i' % cntBaseLinks
        print '#  found get-keys\t%i' % cntGetKeys
        print '#  found get-values\t%i' % cntGetValues
        print '######'
        # commit our changes which is only needed at a physical file, not at an in-memory database.
        connection.commit()
        connection.close()
        exit()

    #2do: switch to threads with blocking sockets (could be a problem with sqlite because of missing multiconnections) or:
    #2do: switch to multiple non blocking sockets (which would cause the same problem). should be solved by 0.0.6 (reduced SELECTs).
    url = urlparse.urlparse(crawling)
    try:
        response = urllib2.urlopen(crawling)
    except:
        print '# we got an error while requesting "%s"' % crawling
        blacklist.add(crawling)
        continue
    msg = response.read()
    links = linkregex.findall(msg)
    crawled.add(crawling)

    for link in (links.pop(0) for _ in xrange(len(links))):
        if link in crawled or link in blacklist:
            continue
        # lets do some path fixing and blacklisting
        if not link.startswith('http'):
            if link.startswith('/'):
                link = 'http://' + url[1] + link
            elif link.startswith('#'):
                link = 'http://' + url[1] + url[2] + link
            elif ':' in link:
                print '# found a weird link: ' + link
                blacklist.add(link)
                continue
            else:
                link = 'http://' + url[1] + '/' + link
            # recheck due linkfixing
            if link in crawled or link in blacklist:
                continue
        if not link.startswith(sys.argv[1]):
            if filterExternal:
                print '# found an external link: ' + link
                blacklist.add(link)
                external.add(link)
                continue
        # we finally found a new link to crawl, lets get the attributes
        # baselink
        if '?' in link:
            baselink = link.split('?')[0]
            dynlink = link.split('?')[1]
        else:
            baselink = link
            dynlink = ''

        # lets check if we already know this baselink
        try:
            tmp = storage[baselink]['myID']
        except KeyError:
            cursor.execute("INSERT INTO `baselinks` VALUES(NULL,%i,'%s')" % (projectID,baselink))
            storage[baselink] = dict()
            storage[baselink]['myID'] = cursor.lastrowid
            #print "\tnew baselink"
        # get our GET parameter
        if '&' in dynlink or '=' in dynlink:
            parameters = dynlink.split('&')
        else:
            # we got an empty or weird dynlink
            parameters = dynlink
        for parameter in parameters:
            if '=' in parameter:
                key = parameter.split('=')[0]
                value = parameter.split('=')[1]
                # lets check if we already know this key in relation to our baselink
                try:
                    tmp = storage[baselink][key]['myID']
                except KeyError:
                    cursor.execute("INSERT INTO `keys` VALUES(NULL,%i,'%s','%s')" % (storage[baselink]['myID'],'GET',key))
                    storage[baselink][key] = dict()
                    storage[baselink][key]['myID'] = cursor.lastrowid
                    #print "\t\tnew key"
                # lets check if we already know this value in relation to our key
                try:
                    tmp = storage[baselink][key][value]['myID']
                except KeyError:
                    cursor.execute("INSERT INTO `valuaes` VALUES (NULL,%i,'%s')" % (storage[baselink][key]['myID'],value))
                    storage[baselink][key][value] = dict()
                    storage[baselink][key][value]['myID'] = cursor.lastrowid
                    #print "\t\t\tnew value"
            else:
                print '# found a weird parameter: %s' % parameter
        #connection.commit()
        tocrawl.add(link)

