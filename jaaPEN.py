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
# 0.1.1 - rewritten var type evaluating
# 0.1.0 - some small fixes
# 0.0.9 - added basic var type (integer, boolean, string) evaluating
# 0.0.8 - added COOKIE detection
# 0.0.7 - added POST detection
# 0.0.6 - better performance by reducing sql-queries and rewritten linkhandling
# 0.0.5 - added project table to store data for more than one site
# 0.0.4 - switched over to sqlite. some local vars are still in use.
# 0.0.3 - added GET detection
# 0.0.2 - added basic crawling and blacklisting
# 0.0.1 - initial commit
#
#2do: remove all general exceptions
#2do: db-qry replace % with ?
#2do: crawl, scanform, scancookies are almost identical. should be merged.
#2do: castType checks for boolean and integer are almost identical. should be merged.
#2do: castCheckMinResults > 1|2 will be a problem at boolean casting. add if block.
#2do: get PHPSESSID value at first crawl and use it for all later requests.
#2do: merge all those sql stuff in var type evaluation
#more at grep -Hirn "2do:" .
#issues:
# - try: tmp = storage[baselink][key][value] except KeyError: is bad and just ugly
# if not storage[baselink][key][value]: would be nicer but i did not get it to work
# - 'myID' in local dict storage[..] could be a key or val at the remote host
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

version = '0.1.1'
showResults = True
saveResults = False

scanID = 1                  # for future gui implementation. could be a base for scan diffs
dbfile = ':memory:'         # use in-memory database. database is lost after runtime.
#dbfile = '/tmp/jaaPEN'     # this database is saved after runtime. performance should equal :memory:
openURL = True              # enable web requests
crawl = True                # enable link crawling
scanForms = True            # enable form scanning
scanCookies = True          # enable cookie scanning
ignoreSessionID = True      # ignore PHPSESSID as in most cases you get a different one for each site while crawling.
castCheck = True            # try to determine value types
castCheckMinResults = 1     # castCheck is successful if at least castCheckMinResults could be casted.
                            # change this to 2 or even more to show only reliable results.
filterExternal = True       # you should _really_ not disable this setting !

try:
    if sys.argv[1] == 'version' or sys.argv[1] == '-version' or sys.argv[1] == '--version':
        print 'jaaPEN version %s' % version
        print 'update @ https://github.com/Gammelbob/jaaPEN'
        exit()
    firstCrawl = sys.argv[1]

    #2do: this is way to general and should be removed
    if not firstCrawl.endswith('/'):
        firstCrawl = '%s/' % firstCrawl
    tocrawl = set([firstCrawl])
except IndexError:
    print 'Usage: jaaPEN url [show|save] [file]'
    print '# Example 1: jaaPEN http://localhost'
    print '# Example 2: jaaPEN http://localhost show'
    print '# Example 3: jaaPEN http://localhost save'
    print '# Example 4: jaaPEN http://localhost save results.log\n'
    print "# Example 1 will display the results as a tree."
    print "# Example 2 will display the results as a tree."
    print "# Example 3 will display nothing but errors."
    #print "# Example 4 will display nothing but errors. The results will be saved in the given file as a tree."
    print "# Example 4 will result in termination."
    print "# Runtime stats will be displayed on all examples."
    exit()

try:
    if sys.argv[2] == 'show':
        saveResults = False
    elif sys.argv[2] == 'save':
        print '#\n#\t* results will not be saved.\n#\t* nothing but errors and simple statistics will be displayed.\n#\t* use jaaPEN url > file instead\n#'
        showResults = False
        try:
            argFile = sys.argv[3]
            out_file = open(argFile,"r") #2do: replace r with w or a. add a users choice var.
            out_file.close()
            print 'could open "%s" for reading but i am not in the mood to write so much' % argFile #2do: replace reading with writing
            exit()
            saveResults = True
        except IOError:
            print 'could not open "%s" for reading' % argFile #2do: replace reading with writing
            exit()
            saveResults = False
except IndexError:
    saveResults = False

connection = sqlite.connect(dbfile)
cursor = connection.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS `castTypes` (castTypeID INTEGER PRIMARY KEY AUTOINCREMENT, castTypeValue VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `scans` (scanID INTEGER PRIMARY KEY AUTOINCREMENT, description VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `baselinks` (baseID INTEGER PRIMARY KEY AUTOINCREMENT, scanID INTEGER, baselink VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `keys` (keyID INTEGER PRIMARY KEY AUTOINCREMENT, baseID INTEGER, type VARCHAR(20), key VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `keyCastResults` (keyID INTEGER PRIMARY KEY, castTypeID INTEGER, castSuccess INTEGER, castErrors INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS `castErrors` (castErrorID INTEGER PRIMARY KEY AUTOINCREMENT, keyID INTEGER, castTypeID INTEGER, castErrorValue VARCHAR(255))")
cursor.execute("CREATE TABLE IF NOT EXISTS `valuaes` (valueID INTEGER PRIMARY KEY AUTOINCREMENT, keyID INTEGER, value VARCHAR(255))")
# valuaes is not a typo. you cant have something like values as a table name in sqlite. 2 hours gone to realise it :o
#2do: castErrors should be keyCastErrors

crawled = set([])
blacklist = set([])
external = set([])
storage = dict()

linkregex = re.compile('<a\s*href=[\'|"](.*?)[\'"].*?>')
if scanForms:
    #2do: i guess there is no need for * as ? covers all but nothing
    formRegex = re.compile('<form.*?</form>',re.DOTALL)
    formActionRegex = re.compile('action=[\'|"](.*?)[\'|"]')
    formMethodRegex = re.compile('method=[\'|"](.*?)[\'|"]')
    inputRegex = re.compile('<input.*?>')
    inputNameRegex = re.compile('name=[\'|"](.*?)[\'"]')
    inputValueRegex = re.compile('value=[\'|"](.*?)[\'"]')

if scanCookies:
    cookieRegex = re.compile('Set-Cookie: (.*?);')

try:
    print '# loading previous results from db'
    # refresh our local vars [baselink][type][key][value]['myID']
    for baselinkRow in cursor.execute("SELECT baseID, baselink FROM `baselinks` WHERE scanID = %i" % scanID).fetchall():
        storage[baselinkRow[1]] = dict()
        storage[baselinkRow[1]]['myID'] = baselinkRow[0]
        for typeRow in cursor.execute("SELECT type FROM `keys` WHERE baseID = %i GROUP BY `keys`.type" % baselinkRow[0]).fetchall():
            storage[baselinkRow[1]][typeRow[0]] = dict()
            for keyRow in cursor.execute("SELECT keyID, key  FROM `keys` WHERE baseID = %i AND type='%s'" % (baselinkRow[0], typeRow[0])).fetchall():
                storage[baselinkRow[1]][typeRow[0]][keyRow[1]] = dict()
                storage[baselinkRow[1]][typeRow[0]][keyRow[1]]['myID'] = keyRow[0]
                for valueRow in cursor.execute("SELECT valueID, value FROM `valuaes` WHERE keyID = %i" % keyRow[0]).fetchall():
                    storage[baselinkRow[1]][typeRow[0]][keyRow[1]][valueRow[1]] = dict()
                    storage[baselinkRow[1]][typeRow[0]][keyRow[1]][valueRow[1]]['myID'] = valueRow[0]
except:
    print '# loading previous results from DB failed. guessing new table or in-memory DB'

print '# started crawling for scanID %i' % scanID
jobtime = time.time()
while True:
    try:
        crawling = tocrawl.pop()
        if crawling in blacklist:
            print 'this should really not happen: "%s" is in blacklist but should be crawled.' % crawling
            continue
    except KeyboardInterrupt:
        print '\nI got killed :o'
        print 'saving database..'
        connection.commit()
        print 'closing connection..'
        connection.close()
        print 'please report bugs and issues @ https://github.com/Gammelbob/jaaPEN'
        exit()
    except KeyError:
        jobtime = time.time() - jobtime
        pagesPerSec = float(len(crawled) / jobtime)
        jobtime = int(jobtime)
        # job done, presenting the results
        cntBaseLinks = int(cursor.execute('SELECT count(baseID) FROM baselinks WHERE scanID = %i' % scanID).fetchone()[0])
        cntGetKeys = int(cursor.execute('SELECT count(keyID) FROM keys WHERE type = \'%s\' AND baseID IN (SELECT baseID FROM baselinks WHERE scanID = %i)' % ('GET',scanID)).fetchone()[0])
        cntGetValues = int(cursor.execute('SELECT count(valueID) FROM valuaes WHERE keyID IN (SELECT keyID FROM keys WHERE type = \'%s\' AND baseID IN (SELECT baseID FROM baselinks WHERE scanID = %i))' % ('GET',scanID)).fetchone()[0])
        cntPostKeys = int(cursor.execute('SELECT count(keyID) FROM keys WHERE type = \'%s\' AND baseID IN (SELECT baseID FROM baselinks WHERE scanID = %i)' % ('POST',scanID)).fetchone()[0])
        cntPostValues = int(cursor.execute('SELECT count(valueID) FROM valuaes WHERE keyID IN (SELECT keyID FROM keys WHERE type = \'%s\' AND baseID IN (SELECT baseID FROM baselinks WHERE scanID = %i))' % ('POST',scanID)).fetchone()[0])
        cntCookieKeys = int(cursor.execute('SELECT count(keyID) FROM keys WHERE type = \'%s\' AND baseID IN (SELECT baseID FROM baselinks WHERE scanID = %i)' % ('COOKIE',scanID)).fetchone()[0])
        cntCookieValues = int(cursor.execute('SELECT count(valueID) FROM valuaes WHERE keyID IN (SELECT keyID FROM keys WHERE type = \'%s\' AND baseID IN (SELECT baseID FROM baselinks WHERE scanID = %i))' % ('COOKIE',scanID)).fetchone()[0])
        if showResults:
            for baselinkRow in cursor.execute("SELECT baseID, baselink FROM `baselinks` WHERE scanID = %i" % scanID).fetchall():
                print '%s' % baselinkRow[1]
                for typeRow in cursor.execute("SELECT type FROM `keys` WHERE baseID = %i GROUP BY `keys`.type" % baselinkRow[0]).fetchall():
                    print '\t%s' % typeRow[0]
                    for keyRow in cursor.execute("SELECT keyID, key  FROM `keys` WHERE baseID = %i AND type='%s'" % (baselinkRow[0], typeRow[0])).fetchall():
                        print '\t\t%s' % keyRow[1]
                        for valueRow in cursor.execute("SELECT value FROM `valuaes` WHERE keyID = %i" % keyRow[0]).fetchall():
                            print '\t\t\t%s' % valueRow[0]
        if castCheck:
            castCheckOut = dict()
            print '#\n# trying to determine var types'
            print '# deleting old keyCast results'
            cursor.execute("DELETE FROM `keyCastResults`")
            cursor.execute("DELETE FROM `castErrors`")
            for baselink in storage:
                for varType in storage[baselink]:
                    if varType == 'myID':
                        continue
                    for key in storage[baselink][varType]:
                        if key == 'myID':
                            continue
                        # check for 1)boolean 2)integer 3)assume string
                        # castCheck for boolean
                        castType = 'boolean'
                        castErrors = 0
                        castSuccess = 0
                        castErrorlist = set([])
                        notSure = False
                        for value in storage[baselink][varType][key]:
                            if value == 'myID':
                                continue
                            if value == '1' or value == '0':
                                notSure = True
                                castSuccess +=1
                            elif value.upper() == 'TRUE' or value.upper() == 'FALSE':
                                notSure = False
                                castSuccess +=1
                            else:
                                castErrors +=1
                                castErrorlist.add(value)
                        if int(castSuccess + castErrors) < castCheckMinResults:
                            continue
                        if castSuccess > 0:
                            keyID = storage[baselink][varType][key]['myID']
                            successRate = float(float(castSuccess) / float(castErrors+castSuccess)*100)
                            if notSure and int(castSuccess + castErrors) == 1:
                                castType = 'bool or int'
                                try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                                except TypeError:
                                    cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                                    castTypeID = cursor.lastrowid
                                cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, castSuccess, castErrors))
                                continue
                            if castErrors == 0:
                                # we got a boolean
                                castType = 'boolean'
                                try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                                except TypeError:
                                    cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                                    castTypeID = cursor.lastrowid
                                cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, castSuccess, castErrors))
                                continue
                            elif successRate >= float(99.9):
                                # uhm.. ya, seems we got a boolean
                                castType = 'boolean'
                                try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                                except TypeError:
                                    cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                                    castTypeID = cursor.lastrowid
                                cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, castSuccess, castErrors))
                                for castErrorValue in castErrorlist:
                                    cursor.execute("INSERT INTO castErrors VALUES (NULL,%i,%i,'%s')" % (keyID, castTypeID, castErrorValue))
                                continue
                            elif successRate >= float(90.0):
                                # uhm.. ya, could be a boolean
                                castType = 'bool or int'
                                try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                                except TypeError:
                                    cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                                    castTypeID = cursor.lastrowid
                                cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, castSuccess, castErrors))
                                for castErrorValue in castErrorlist:
                                    cursor.execute("INSERT INTO castErrors VALUES (NULL,%i,%i,'%s')" % (keyID, castTypeID, castErrorValue))
                                continue
                        # castSuccess is 0 or successRate is above limits:
                        # no boolean - lets check for int
                        castType = 'integer'
                        castErrors = 0
                        castSuccess = 0
                        castErrorlist = set([])
                        for value in storage[baselink][varType][key]:
                            if value == 'myID':
                                continue
                            try:
                                tmp = int(value)
                                castSuccess +=1
                            except ValueError:
                                castErrors +=1
                                castErrorlist.add(value)
                        if castSuccess > 0:
                            keyID = storage[baselink][varType][key]['myID']
                            successRate = float(float(castSuccess) / float(castErrors+castSuccess)*100)
                            if castErrors == 0:
                                # we got an integer
                                castType = 'integer'
                                try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                                except TypeError:
                                    cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                                    castTypeID = cursor.lastrowid
                                cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, castSuccess, castErrors))
                                continue
                            elif successRate >= float(99.9):
                                # uhm.. ya, seems we got an integer
                                castType = 'integer'
                                try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                                except TypeError:
                                    cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                                    castTypeID = cursor.lastrowid
                                cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, castSuccess, castErrors))
                                for castErrorValue in castErrorlist:
                                    cursor.execute("INSERT INTO castErrors VALUES (NULL,%i,%i,'%s')" % (keyID, castTypeID, castErrorValue))
                                continue
                            elif successRate >= float(90.0):
                                # uhm.. ya, could be an integer
                                castType = 'could be integer'
                                try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                                except TypeError:
                                    cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                                    castTypeID = cursor.lastrowid
                                cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, castSuccess, castErrors))
                                for castErrorValue in castErrorlist:
                                    cursor.execute("INSERT INTO castErrors VALUES (NULL,%i,%i,'%s')" % (keyID, castTypeID, castErrorValue))
                                continue

                        # castSuccess is 0 or successRate is above limits:
                        # no boolean - no int - should be a string
                        castType = 'string'
                        keyID = storage[baselink][varType][key]['myID']
                        try: castTypeID = cursor.execute("SELECT castTypeID FROM castTypes WHERE castTypeValue = '%s'" % castType).fetchone()[0]
                        except TypeError:
                            cursor.execute("INSERT INTO castTypes VALUES (NULL,'%s')" % castType)
                            castTypeID = cursor.lastrowid
                        cursor.execute("INSERT INTO keyCastResults VALUES (%i,%i,%i,%i)" % (keyID, castTypeID, 0, int(castSuccess+castErrors)))
                        
            for castTypeRow in cursor.execute("SELECT castTypeID, castTypeValue FROM `castTypes` ORDER BY castTypeValue ASC").fetchall():
                print '\n%s' % castTypeRow[1]
                for baselinkRow in cursor.execute("SELECT baseID, baselink FROM `baselinks` WHERE scanID = %i" % scanID).fetchall():
                    for typeRow in cursor.execute("SELECT type FROM `keys` WHERE baseID = %i GROUP BY `keys`.type" % baselinkRow[0]).fetchall():
                        for keyRow in cursor.execute("SELECT `keys`.keyID, key, `keyCastResults`.castSuccess, `keyCastResults`.castErrors FROM `keys`, `keyCastResults` WHERE baseID = %i AND type='%s' AND `keyCastResults`.castTypeID = %i AND `keyCastResults`.keyID = `keys`.keyID" % (baselinkRow[0], typeRow[0], castTypeRow[0])).fetchall():
                            count = int(keyRow[2] + keyRow[3])
                            if not castTypeRow[1] == 'string':
                                successCount = int(keyRow[2])
                                successRate = float(successCount) / float(count) * 100
                                if int(successRate) < 100:
                                    filler = ' '
                                    if int(successRate) < 10: filler = ' %s' % filler
                                else: filler = ''
                                if count > 99:
                                    print '\t%s%.2f%s (%i/%i)\t[%s][%s][%s]' % (filler, successRate, '%', successCount, count, baselinkRow[1], typeRow[0], keyRow[1])
                                else:
                                    print '\t%s%.2f%s (%i/%i)\t\t[%s][%s][%s]' % (filler, successRate, '%', successCount, count, baselinkRow[1], typeRow[0], keyRow[1])
                            else:
                                print '\tchecked: %i\t\t[%s][%s][%s]' % (count, baselinkRow[1], typeRow[0], keyRow[1])
                            for castErrorRow in cursor.execute("SELECT castErrorValue FROM `castErrors` WHERE keyID = %i" % keyRow[0]).fetchall():
                                print '\t\t\t\t=> could not cast "%s" to %s' % (castErrorRow[0], castTypeRow[1]) 

        print '######'
        print '#  crawled pages\t%i in ~%s seconds' % (len(crawled),jobtime)
        print '#  which means\t\t%f pages/s' % pagesPerSec
        print '#  blacklisted links\t%i' % int(len(blacklist) - len(external))
        print '#  external links\t%i' % len(external)
        print '#  found baselinks\t%i' % cntBaseLinks
        print '#  found get-keys\t%i' % cntGetKeys
        print '#  found get-values\t%i' % cntGetValues
        print '#  found post-keys\t%i' % cntPostKeys
        print '#  found post-values\t%i' % cntPostValues
        print '#  found cookie-keys\t%i' % cntCookieKeys
        print '#  found cookie-values\t%i' % cntCookieValues
        print '######'
        # commit our changes which is only needed at a physical file, not at an in-memory database.
        connection.commit()
        connection.close()
        exit()

    # lets do the job
    if openURL:
        #2do: switch to threads with blocking sockets (could be a problem with sqlite because of missing multiconnections) or:
        #2do: switch to non blocking sockets (which would cause the same problem). should be solved by 0.0.6 (reduced SELECTs).
        url = urlparse.urlparse(crawling)
        try: response = urllib2.urlopen(crawling)
        except KeyboardInterrupt:
            print '\nI got killed :o'
            print 'saving database..'
            connection.commit()
            print 'closing connection..'
            connection.close()
            print 'please report bugs and issues @ https://github.com/Gammelbob/jaaPEN'
            exit()
        except: #2do: this needs to be changed to remove except KeyboardInterrupt above
            print '# we got an error while requesting "%s"' % crawling
            blacklist.add(crawling)
            continue
        msg = response.read()

    if crawl:
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
                else: link = 'http://' + url[1] + '/' + link
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
            try: tmp = storage[baselink]['myID']
            except KeyError:
                cursor.execute("INSERT INTO `baselinks` VALUES(NULL,%i,'%s')" % (scanID,baselink))
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
                    # do we have an GET dict for current baselink
                    try: tmp = storage[baselink]['GET']
                    except KeyError:
                        storage[baselink]['GET'] = dict()
                    # lets check if we already know this key in relation to our baselink
                    try: tmp = storage[baselink]['GET'][key]['myID']
                    except KeyError:
                        cursor.execute("INSERT INTO `keys` VALUES(NULL,%i,'%s','%s')" % (storage[baselink]['myID'],'GET',key))
                        storage[baselink]['GET'][key] = dict()
                        storage[baselink]['GET'][key]['myID'] = cursor.lastrowid
                        #print "\t\tnew key"
                    # lets check if we already know this value in relation to our key
                    try: tmp = storage[baselink]['GET'][key][value]['myID']
                    except KeyError:
                        cursor.execute("INSERT INTO `valuaes` VALUES (NULL,%i,'%s')" % (storage[baselink]['GET'][key]['myID'],value))
                        storage[baselink]['GET'][key][value] = dict()
                        storage[baselink]['GET'][key][value]['myID'] = cursor.lastrowid
                        #print "\t\t\tnew value"
                else:
                    print '# found a weird parameter: %s' % parameter
            #connection.commit()
            tocrawl.add(link)

    if scanForms:
        forms = formRegex.findall(msg)
        for form in (forms.pop(0) for _ in xrange(len(forms))):
            formAction = formActionRegex.findall(form)[0]
            formMethod = formMethodRegex.findall(form)[0].upper()
            # lets do some path fixing and blacklisting
            if not formAction.startswith('http'):
                if formAction.startswith('/'):
                    formAction = 'http://' + url[1] + formAction
                elif formAction.startswith('#'):
                    formAction = 'http://' + url[1] + url[2] + formAction
                elif ':' in formAction:
                    print '# found a weird formAction: ' + formAction
                    print '# nevertheless, we turn on'
                    #blacklist.add(formAction)
                    #continue
                else:
                    formAction = 'http://' + url[1] + '/' + formAction
            if not formAction.startswith(sys.argv[1]):
                if filterExternal:
                    print '# found an external form target: ' + formAction
                    print '# breaking up here!'
                    blacklist.add(formAction)
                    external.add(formAction)
                    continue
            if formAction in blacklist:
                continue
            if formAction not in crawled and formAction not in tocrawl:
                # lets have a look what do we get if we request the forms target without any parameters
                tocrawl.add(formAction)
            # lets check if we already know the forms target/baselink
            try: tmp = storage[formAction]['myID']
            except KeyError:
                cursor.execute("INSERT INTO `baselinks` VALUES(NULL,%i,'%s')" % (scanID,formAction))
                storage[formAction] = dict()
                storage[formAction]['myID'] = cursor.lastrowid
            # do we have an [POST/GET/WHATEVER] dict for current form target
            try: tmp = storage[formAction][formMethod]
            except KeyError:
                storage[formAction][formMethod] = dict()
            # finally get parameters
            inputs = inputRegex.findall(form)
            for inputelement in (inputs.pop(0) for _ in xrange(len(inputs))):
                try: inputName = inputNameRegex.findall(inputelement)[0]
                except IndexError:
                    inputName = 'not/set' 
                try: inputValue = inputValueRegex.findall(inputelement)[0]
                except IndexError:
                    inputValue = 'not/set'
                # lets check if we know the key in relation to our formAction/baselink
                try: tmp = storage[formAction][formMethod][inputName]['myID']
                except KeyError:
                    cursor.execute("INSERT INTO `keys` VALUES(NULL,%i,'%s','%s')" % (storage[formAction]['myID'],formMethod,inputName))
                    storage[formAction][formMethod][inputName] = dict()
                    storage[formAction][formMethod][inputName]['myID'] = cursor.lastrowid
                # lets check if we know the value in relation to the key
                try: tmp = storage[formAction][formMethod][inputName][inputValue]['myID']
                except KeyError:
                    cursor.execute("INSERT INTO `valuaes` VALUES (NULL,%i,'%s')" % (storage[formAction][formMethod][inputName]['myID'],inputValue))
                    storage[formAction][formMethod][inputName][inputValue] = dict()
                    storage[formAction][formMethod][inputName][inputValue]['myID'] = cursor.lastrowid

    if scanCookies:
        # response.info() returns the header
        header = str(response.info())
        cookies = cookieRegex.findall(header)
        try: baselink = response.geturl().split('?')[0]
        except IndexError:
            baselink = response.geturl()

        for cookie in (cookies.pop(0) for _ in xrange(len(cookies))):
            try:
                key = cookie.split('=')[0]
                if ignoreSessionID and key == 'PHPSESSID':
                    continue
            except IndexError:
                key = 'not/set' 
            try: value = cookie.split('=')[1]
            except IndexError:
                value = 'not/set'
            try: tmp = storage[baselink]['myID']
            except KeyError:
                cursor.execute("INSERT INTO `baselinks` VALUES(NULL,%i,'%s')" % (scanID,baselink))
                storage[baselink] = dict()
                storage[baselink]['myID'] = cursor.lastrowid
            # do we have an COOKIE dict for current baselink
            try: tmp = storage[baselink]['COOKIE']
            except KeyError:
                storage[baselink]['COOKIE'] = dict()
            # lets check if we know the key in relation to our baselink
            try: tmp = storage[baselink]['COOKIE'][key]['myID']
            except KeyError:
                cursor.execute("INSERT INTO `keys` VALUES(NULL,%i,'%s','%s')" % (storage[baselink]['myID'],'COOKIE',key))
                storage[baselink]['COOKIE'][key] = dict()
                storage[baselink]['COOKIE'][key]['myID'] = cursor.lastrowid
            # lets check if we know the value in relation to the key
            try: tmp = storage[baselink]['COOKIE'][key][value]['myID']
            except KeyError:
                cursor.execute("INSERT INTO `valuaes` VALUES (NULL,%i,'%s')" % (storage[baselink]['COOKIE'][key]['myID'],value))
                storage[baselink]['COOKIE'][key][value] = dict()
                storage[baselink]['COOKIE'][key][value]['myID'] = cursor.lastrowid

