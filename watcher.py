#!/usr/bin/env python

"""
Watcher in the water

This program will connect to a slack channel that is publishing pokemon and read those reports.
It will then compute distances and potentially send you an alert.  This can be done on a per-user basis
using "crow" flies logic computed in the web browser using JS to compute distances.  Crazier, there is
a solution where it can server-side compute driving distance using the Google Driving distance API.
This alert could be a message to your scratch pad in slack.  It could use IOS's iCloud system.
It could even just be an email->SMS gateway based email message.

Anyway, the slack channel is no longer posting updates, so this is just a collection of examples
on how to connect to Slack, Google Maps, iCLoud and bottle.
"""

import datetime
import json
import os
import Queue
import re
import smtplib
import sqlite3
import string
import sys
import threading
import time
import traceback
import urllib
import uuid

import bottle
from bottle import static_file, redirect, post, route, request, template
from math import radians, cos, sin, asin, sqrt
from operator import methodcaller
from pyicloud import PyiCloudService
from pprint import pprint
from slackclient import SlackClient
from urlparse import parse_qs
from urlparse import urlparse

# Load below values from JSON
global configuration
configuration = {}

global apiKey, token, dbname, icloudUser, icloudPassword, mailname, mailpass, vtext, textAlways
dbname = "poke_events.db" # the SQLite DB filename
apiKey = "" # google driving api key
staticMapApiKey = "" # google static map api key
token  = "" # Slack API token found at https://api.slack.com/web#authentication
icloudUser = ""
icloudPassword = ""
icloudDevice = u'' # the device ID of your apple device that you want to alert
mailname = "" # your sms username
mailpass = "" # your sms password
vtext    = "" # The vtext address you want to send the message to

# Texting configuration
criticalTextMaxDistance = 2 # miles as the crow flies
perfectTextMaxDistance  = 3 # miles as the crow flies
alwaysTextMaxDistance   = 4 # miles as the crow flies
textEarly = 9  # military time
textLate  = 23 # military time
textAlways = False

global populateDB, criticalList, notifyList, alwaysTextList, webserverPort, managerRefreshTime
# text me these at any hour of the day, as long as they are within a ce
alwaysTextList  = [ "gyrados", "muk" ]

# Text me any time BUT ONLY if it is PERFECT
alwaysTextIfPerfectList = [ "dragonite", "lapras", "venasaur", "dratini", "dragonair" ]

# text me these during normal hours, but only if they are perfect
perfectTextList = [ "oddish", "gloom", "slowpoke" ]

# text me these during normal hours, and highlight them
criticalList    = [ "snorlax", "dragonite", "lapras", "venasaur", "slowbro", "grimer" ]

# Add to active but do not text me
noTextList      = [ "charmander", "slowpoke", "squirtle", "bulbasaur", "poliwag", "magikarp", "victreebel", "machamp", "vileplume" ]

# Nearby limit (in miles)
global NEARBY_LIMIT
NEARBY_LIMIT = 1.0

populateDB         = True
webserverPort      = 9432
managerRefreshTime = 30

class Current(object):
    testing = False
    debug = True
    phoneCoord = None
    enableSlack = True
    enableGoogleAndICloud = True
    enableTextMessages = False

    @staticmethod
    def getIphoneCoordStr():
        if Current.phoneCoord is None:
            if Current.debug:
                print "phoneCoord is none, returning blank"
            return ""
        else:
            return "%f,%f" % ( Current.phoneCoord[0], Current.phoneCoord[1] )

    @staticmethod
    def getTesting():
        return Current.testing

    @staticmethod
    def getDebug():
        return Current.debug

def sendTextMessageViaEmail(subject, message, link):

    # The URI here is bizarre.  This allows you to open google maps directly from a link in chrome (and safari I think)
    myLink = link.replace("|Open in Google Maps>", "").replace("<http://maps.google.com/maps?q=", "comgooglemaps://?q=")

    msg = """From: %s
To: %s
Subject: %s

%s
""" % (mailname, vtext, message, myLink)

    print "SENDING: %s" % msg

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(mailname,mailpass)
    server.sendmail(mailname, vtext, msg)
    server.quit()

def shouldSendText(pm, distance, hr=datetime.datetime.now().hour):
    if pm.getName() in alwaysTextList and distance < alwaysTextMaxDistance:
        return True

    # if critical and perfect, text at any time
    if pm.getCritical() and pm.getPerfect():
        return True

    elif hr >= textEarly and hr <= textLate:
        #print "Inside early/late! isPerfect=%s, isCritical=%s" % ( pm.getPerfect(), pm.getCritical() )
        if pm.getPerfect() and distance < perfectTextMaxDistance:
            return True
        elif pm.getCritical() and distance < criticalTextMaxDistance:
            return True
    return False

def haversine(lat1, lat2, lon1, lon2):
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    miles = ( 6367 * c ) * 0.62137 # convert to miles, because 'merica
    return miles

def uniqify(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]

class PokemonWebServer(threading.Thread):
    webToManagerQueue = None
    managerToWebQueue = None
    mgr = None

    def __init__(self, manager, webToManagerQueue, managerToWebQueue):
        PokemonWebServer.mgr = manager
        PokemonWebServer.webToManagerQueue = webToManagerQueue
        PokemonWebServer.managerToWebQueue = managerToWebQueue
        threading.Thread.__init__(self)

    @route('/')
    def index():
        return ""

    @route('/current.png')
    def server_static():
        return static_file("current.png", root='.')

    # 1. Expose a way to send all hits to slackbot
    @route('/pokemon')
    def pokemon():
        # 1. send request
        # 2. block on response
        dt = datetime.datetime.now()
        ts = dt.strftime("%I:%M:%S%p")
        html = [
            "<head><style>",
            "table, th, td {",
            "   border: 1px solid black;",
            "}",
            "input {",
            "   font-size: 24px",
            "}",
            "</style>",
            "<meta http-equiv=\"refresh\" content=\"30\">",
            "<script>",
            "function getLocation() {",
            "    if (navigator.geolocation) {",
            "        navigator.geolocation.getCurrentPosition(showPosition);",
            "    } else {",
            "        x.innerHTML = \"Geolocation is not supported by this browser.\";",
            "    }",
            "}",
            "function showPosition(position) {",
            "    var x = document.getElementById('demo');",
            "    x.innerHTML = \"Latitude: \" + position.coords.latitude + \"<br>Longitude: \" + position.coords.longitude;",
            "}",
            "</script>",
            "</head>",
            "<div id='demo'>DEMO</div>",
            "<p><img src=\"/current.png\"></p>",
            "<h2>Active pokemon %s, update in %d</h2>" % ( str(ts), PokemonWebServer.mgr.getSecondsUntilNextUpdate() ),
            "<br/>",
            "<table>",
            "<tr><th>Map Label</th><th>Remove 'Mon</th><th>Name</th><th>Time To</th><th>Distance To</th><th>Time to Despawn</th><th>Map to 'Mon</th><th>Computed</th></tr>"
        ]
        active = PokemonWebServer.mgr.buildSortedActive()
        totalPct   = 0
        totalCount = 0
        for mon in active:
            totalCount = totalCount + 1
            removeLink = "<a href='/remove/%s'>Remove</a>" % mon.getId()
            mapLink = mon.getLink().replace("<", "<a href=\"").replace("|Open in Google Maps", "\" target=\"_blank\">Map</a").replace("\n", " ")
            bgColor = ""

            try:
                mtch = re.match("^.*\(([0-9][0-9]\.?[0-9]?)%\)", mapLink)
                pctValue = float(mtch.group(1))
                totalPct = totalPct + pctValue

                if mon.getCritical():
                    bgColor = " bgcolor=\"yellow\""
                elif pctValue > 95:
                    bgColor = " bgcolor=\"lime\""
                elif pctValue > 90:
                    bgColor = " bgcolor=\"aqua\""
                elif pctValue > 80:
                    bgColor = " bgcolor=\"silver\""
            except Exception as ex:
                traceback.print_exc()

            computedBy = ""
            if mon.haversineOnly:
                computedBy = "haversine"
            else:
                computedBy = "google"

            html.append(template("<tr%s><td>{{label}}</td><td>%s<td><b>{{name}}</b</td><td>{{timeTo}}</td><td>{{distanceTo}}</td><td>{{remaining}}</td><td>%s</td><td>{{computed}}</td></tr>" % ( bgColor, removeLink, mapLink ), label=mon.getLabel(), name=mon.getName(), timeTo=mon.getTimeToTarget(), distanceTo=mon.getDistanceToTarget(), remaining=int(mon.getTimeLeftToDespawn() / 60), computed=computedBy))
        html.append("</table>")

        if totalCount > 0:
            html.append("<p>Current IV average: %f</p>" % (totalPct/totalCount))

        html.append("<br/>")
        html.append("<h2>Nearby Pokemon</h2>")
        html.append("<table style='border:1px solid black'>")
        html.append("<tr><th>Remove 'Mon</th><th>Name</th><th>Distance To</th><th>Time to Despawn</th><th>Map to 'Mon</th></tr>")
        nearby = PokemonWebServer.mgr.buildSortedNearby()
        for mon in nearby:
            try:
                if Current.debug:
                    print "Nearby: %s, %s" % ( str(mon), str(type(mon)) )

                removeLink = "<a href='/remove/%s'>Remove</a>" % mon.getId()
                mapLink = mon.getLink().replace("<", "<a href=\"").replace("|Open in Google Maps", "\" target=\"_blank\">Map</a")
                html.append(template("<tr><td>%s<td><b>{{name}}</b></td><td>{{distanceTo}}</td><td>{{remaining}}</td><td>%s</td></tr>" % ( removeLink, mapLink ), remove=removeLink, name=mon.getName(), distanceTo="{0:.3f}".format(mon.getDistanceToTarget()), remaining=int(mon.getTimeLeftToDespawn() / 60)))
            except Exception as ex:
                print "Error processing nearby pokemon! mon=%s" % str(mon)
                traceback.print_exc()

        html.append("</table>")

        html.append("<br/><br/>")
        html.append("<p><input type='button' onclick=\"location.href='/slack?tm=' + (new Date).getTime();\" value='Send to Slack' /></p>")
        html.append("<p><input type='button' onclick=\"location.href='/toggleLocation?tm' + (new Date).getTime();\" value='Toggle Google/iCloud, current=%s' />&nbsp;&nbsp;Current Coordinates: %s</p>" % ( str(Current.enableGoogleAndICloud), Current.getIphoneCoordStr() ) )
        html.append("<p>Always text (at any time!) %s" % str(alwaysTextList))
        html.append("<p>Always Text if Perfect: %s</p>" % str(alwaysTextIfPerfectList))
        html.append("<p>Text if perfect only: %s</p>" % str(perfectTextList))
        html.append("<p>Critical: %s</p>" % str(criticalList))
        html.append("<p>No text list: %s</p>" % str(noTextList))
        html.append("<p>Notify list: %s</p>" % str(notifyList))
        html.append("<p>Texting Hours: %d to %d</p>" % ( textEarly, textLate ))
        html.append("<br/>")
        html.append("<p><input type='button' onClick='getLocation();' value='Show Position'></p>")
        html.append("<br/>")
        html.append("<p><input type='button' onclick=\"location.href='/toggleText?tm=' + (new Date).getTime();\" value='Toggle Text %s' /></p>" % ( Current.enableTextMessages ))

        return "\n".join(html)

    # 2. Expose a way to send to slackbot
    @route('/slack')
    def sendToSlack():
        PokemonWebServer.mgr.reportAndSendToSlack()
        redirect('/pokemon?tm=' + str(time.time()))

    # 3. Expose a way to remove a Pokemon from the active list
    @route('/remove/:idVal')
    def remove(idVal):
        print "Looking to remove idVal = %s" % idVal
        active = manager.getActive()
        for idx, val in enumerate(active):
            print "(Active) Checking: %d - %s" % ( idx, val )
            if val.getId() == idVal:
                del active[idx]

        nearby = manager.getNearby()
        for idx, val in enumerate(nearby):
            print "(Nearby) Checking: %d - %s" % ( idx, val )
            if val.getId() == idVal:
                del nearby[idx]
        redirect('/pokemon?tm=' + str(time.time()))

    # 4. Expose a way to toggle google location on and off services
    @route('/toggleLocation')
    def toggleLocation():
        Current.enableGoogleAndICloud = not Current.enableGoogleAndICloud
        print "Toggled enableGoogleAndICloud, new value=%s" % str(Current.enableGoogleAndICloud)
        if Current.enableGoogleAndICloud:
            manager.connectIcloud()
        redirect('/pokemon?tm=' + str(time.time()))

    def run(self):
        bottle.run(host="0.0.0.0", port=webserverPort)

    #@route('/sendText'):

    @route('/toggleText')
    def toggleText():
        Current.enableTextMessages = not Current.enableTextMessages
        print "Toggled enableTextMessages, new value=%s" % str(Current.enableTextMessages)
        redirect('/pokemon?tm=' + str(time.time()))

class Pokemon(object):
    __slots__ = "id timeReceived name link coords text coordStr lastCoordCheck distanceToTarget timeToTarget lastUpdated critical perfect notify noText label haversineOnly".split()
    def __init__(self, timeReceived, name, coords, text, link):
        self.id = str(uuid.uuid4())
        self.timeReceived = timeReceived
        self.name = name.lower()
        self.coords = coords
        self.text = text
        self.link = link
        self.coordStr = "%f,%f" % ( coords[0], coords[1] )
        self.timeToTarget = None
        self.distanceToTarget = None
        self.lastCoordCheck = None
        self.lastUpdated = time.time()
        self.haversineOnly = False
        self.label = ""

        self.computeStatus()

    def computeStatus(self):
        self.perfect = False
        self.critical = False
        self.noText = False
        self.notify = False

        if "100%" in self.getLink() or re.match("^.*\(9[0-9].[0-9]%.*$", self.getLink()):
            print "%s - critical? %s" % ( self.getName(), self.getLink() )
            self.setPerfect(True)

        if self.name in criticalList:
            self.setCritical(True)

        if self.name in noTextList:
            self.setNoText(True)

        if self.name in notifyList:
            self.setNotify(True)

    def setName(self, name):
        self.name = name.lower()
        self.computeStatus()

    def shouldAddToActive(self):
        return self.notify

    def isNearby(self):
        # If it is nearby (less than 1.5 miles) from here, add to the nearby list
        return Current.phoneCoord is not None and self.updateDistanceUsingHaversine() < NEARBY_LIMIT

    def getId(self):
        return self.id

    def getName(self):
        return self.name

    def getLink(self):
        return self.link

    def getCritical(self):
        return self.critical

    def getText(self):
        return self.text

    def setNoText(self, value):
        self.noText = value

    def setNotify(self, value):
        self.notify = value

    def getNoText(self):
        return self.noText

    def getNotify(self):
        return self.notify

    def setCritical(self, critical):
        #print "Setting %s to critical!" % self.name
        self.critical = critical

    def getPerfect(self):
        return self.perfect

    def setPerfect(self, perfect):
        self.perfect = perfect

    def getLabel(self):
        return self.label

    def setLabel(self, label):
        self.label = label

    def getTimeLeftToDespawn(self):
        return ( self.timeReceived + 900 ) - time.time()

    def getCoords(self):
        return self.coords

    def isStillValid(self):
        secondsLeft = self.getTimeLeftToDespawn()
        if secondsLeft <= 0:
            # If it is past the despawn time, remove!
            return False
        elif self.timeToTarget is not None and secondsLeft / 60 < self.timeToTarget:
            # If we don't have enough time to get there before it despawns, remove!
            return False
        else:
            # Good to go
            return True

    def generateDistanceMessage(self):
        return "`%s` time=%s(min) distance=%s(mi)\n%s" % ( self.text, self.timeToTarget, self.distanceToTarget, self.link  )

    def shouldUpdateDistance(self):
        # 1. Compute the distance of the last time we checked
        if self.lastCoordCheck is None:
            return True

        if Current.phoneCoord is None:
            if Current.debug:
                print "(ShouldUpdateDistance) Current phone coord is none, returning!"
            return

        distance = haversine(Current.phoneCoord[0], self.lastCoordCheck[0], Current.phoneCoord[1], self.lastCoordCheck[1])
        if Current.debug:
            print "(%s) phone distance from last check.  distance=%f" % ( self.name, distance )
        # 2. If distance is greater than a mile (or if the only computation we have done is haversine based), re-compute distance
        if distance > .25 or self.haversineOnly:
            return True

        return False

    def updateDistanceUsingHaversine(self):
        if Current.phoneCoord is None:
            if Current.debug:
                print "(updateHaversine) phoneCoord is none"
            return
        self.distanceToTarget = haversine(Current.phoneCoord[0], self.coords[0], Current.phoneCoord[1], self.coords[1])
        self.haversineOnly = True
        self.label = ""
        return self.distanceToTarget

    def updateDistanceBetweenPoints(self):
        if not Current.enableGoogleAndICloud:
            self.updateDistanceUsingHaversine()
            self.timeToTarget = self.distanceToTarget * 3
            return

        if Current.phoneCoord is None:
            if Current.debug:
                print "phoneCoord is none, returning!"
            return
        originStr = Current.getIphoneCoordStr()

        url = "https://maps.googleapis.com/maps/api/distancematrix/json?origins=%s&destinations=%s&mode=driving&units=imperial&key=%s" % ( originStr, self.coordStr, apiKey )
        try:
            jsonRes = urllib.urlopen(url).read()
            self.handleDistanceResult(jsonRes)
            self.lastCoordCheck = list(Current.phoneCoord)
            self.haversineOnly = False
        except Exception as ex:
            traceback.print_exc()
            print "Error processing JSON from google distance API! %s" % str(ex)

    def getFormattedCoordStr(self):
        return "%s,%s" % ( "{0:.6f}".format(self.coords[0]), "{0:.6f}".format(self.coords[1]) )

    def handleDistanceResult(self, jsonData):
        jsonRes = json.loads(jsonData)
        self.distanceToTarget = float(jsonRes["rows"][0]["elements"][0]["distance"]["text"].strip(string.ascii_letters).strip(" "))
        self.timeToTarget     = float(jsonRes["rows"][0]["elements"][0]["duration"]["text"].strip(string.ascii_letters).strip(" "))

        if Current.debug:
            print "%s : distance=%s timeToTarget=%s" % ( self.name, self.distanceToTarget, self.timeToTarget )

    def getDistanceToTarget(self):
        return self.distanceToTarget

    def getTimeToTarget(self):
        return self.timeToTarget

    def __str__(self):
        return "(%s) coordStr=%s, d=%s, t=%s, id=%s" % ( str(self.name), str(self.coordStr), str(self.distanceToTarget), str(self.timeToTarget), self.getId() )

class Manager(threading.Thread):
    __slots__ = "active nearby iCloud slack userId userName lastUpdated previousURL webToManagerQueue managerToWebQueue slackToManagerQueue".split()

    def __init__(self, slack, webToManagerQueue, managerToWebQueue, slackToManagerQueue):
        threading.Thread.__init__(self)
        self.slack = slack
        self.webToManagerQueue = webToManagerQueue
        self.managerToWebQueue = managerToWebQueue
        self.slackToManagerQueue = slackToManagerQueue
        self.active = []
        self.nearby = []
        self.lastUpdated = 0
        self.previousURL = ""
        if Current.enableGoogleAndICloud:
            self.connectIcloud()

        if Current.enableSlack:
            self.getSlackUserInfo()
        else:
            if not Current.getTesting():
                print "Messaging disabled"

    def getSecondsUntilNextUpdate(self):
        return ( self.lastUpdated + managerRefreshTime ) - time.time()

    def getSlackUserInfo(self):
        userInfo      = self.slack.api_call("auth.test")
        self.userId   = userInfo["user_id"]
        self.userName = userInfo["user"]
        print "Got username from slack: userName=%s, userId=%s" % ( str(self.userName), str(self.userId) )

    def addActivePokemon(self, pokemon):
        if Current.debug:
            print "Adding ACTIVE pokemon: %s" % str(pokemon)
        self.active.append(pokemon)
        self.potentiallySendTextForPokemon(pokemon)

        if pokemon.getTimeToTarget() is None:
            pokemon.updateDistanceBetweenPoints()

    def potentiallySendTextForPokemon(self, pm):
        if not Current.enableTextMessages:
            return

        if pm.getText() is None: # text is not saved in the DB, so it will be None on restarts
            return

        if shouldSendText(pm, pm.getDistanceToTarget()):
            sendTextMessageViaEmail(pm.getName(), pm.getText(), pm.getLink())

    def addNearbyPokemon(self, pokemon):
        if Current.debug:
            print "Adding NEARBY pokemon: %s" % str(pokemon)
        self.nearby.append(pokemon)

    def getActiveCount(self):
        return len(self.active)

    def updateAllDistances(self):
        # Iterate over each active record, update distance if needed
        updateCount = 0
        for elem in self.active:
            if elem.shouldUpdateDistance():
                elem.updateDistanceBetweenPoints()
                updateCount = updateCount + 1

        for elem in self.nearby:
            elem.updateDistanceUsingHaversine()

        return updateCount

    def removeInvalidPokemon(self):
        # Remove any element that needs to be removed
        tmp = []
        for elem in self.active:
            if elem.isStillValid():
                tmp.append(elem)
        self.active = tmp

        tmp = []
        for elem in self.nearby:
            if elem.isStillValid():
                tmp.append(elem)
        self.nearby = tmp

    def getActive(self):
        return self.active

    def getNearby(self):
        return self.nearby

    def buildSortedActive(self):
        # Sort by distance
        return sorted(self.active, key=methodcaller('getTimeToTarget'))

    def buildSortedNearby(self):
        # Sort by distance
        return sorted(self.nearby, key=methodcaller('getDistanceToTarget'))

    def report(self):
        # 1. Get the sorted active list
        sortedActive = self.buildSortedActive()

        # 2. Build outbound string
        outbound = []
        for elem in sortedActive:
            outbound.append(elem.generateDistanceMessage())
        if len(outbound) > 0:
            dt = datetime.datetime.now()
            ts = dt.strftime("%I:%M:%S%p")
            outbound.append("```-=-=-%s-=-=-```" % ts)
            return "\n".join(outbound)
        return None

    @staticmethod
    def getNextStringOrNumber(val):
        if val == 'Z':
            return 0

        if type(val) is str:
            return chr(ord(val) + 1)
        else:
            return val + 1

    def generateStaticMap(self, execute=True):
        if Current.phoneCoord is None:
            return

        if not Current.enableGoogleAndICloud:
            if os.path.exists("current.png"): # delete the image if location is not enabled
                os.remove("current.png")
            return

        markers = [ "&markers=color:black|%s" % Current.getIphoneCoordStr() ]
        pos = 'A'
        for mon in self.buildSortedActive():
            mon.setLabel(pos)
            pos = Manager.getNextStringOrNumber(pos)
            markers.append("&markers=label:%s|%s" % ( mon.getLabel(), mon.getFormattedCoordStr() ))

        if len(markers) > 1:
            url = "https://maps.googleapis.com/maps/api/staticmap?size=640x640&center=%s&maptype=roadmap&key=%s%s" % ( Current.getIphoneCoordStr(), staticMapApiKey, "".join(markers) )
            if Current.debug:
                print "Generating static map: url=%s" % url
            if execute:
                if self.previousURL == url:
                    return url
                urllib.urlretrieve(url, "new.png")
                os.rename("new.png", "current.png")
                previousURL = url
            return url
        return None

    def connectIcloud(self):
        """ Connects to iCloud, or throws an exception """
        print "Connecting to iCloud"
        self.iCloud = PyiCloudService(icloudUser, icloudPassword)
        if icloudDevice in self.iCloud.devices.keys():
            print "iCloud is connected"
        else:
            raise Exception("Could not find device in iCloud! %s" % str(self.iCloud.devices.keys()) )

    def updateIphoneLocation(self):
        """ Retrieves the location from iCloud for your phone """
        if not Current.enableGoogleAndICloud:
            return

        res = None
        try:
            res = self.iCloud.devices[icloudDevice].location()
            Current.phoneCoord = [ res["latitude"], res["longitude"] ]
            if Current.debug:
                print "Got iPhone result! %s" % str(Current.phoneCoord)
            return Current.phoneCoord
        except Exception as ex:
            print "Res = %s" % str(res)
            traceback.print_exc()
            print "Reconnect to iCloud!"
            self.connectIcloud()

    def playIphoneSound(self):
        """ Plays a sound on your phone, as slack isn't terribly reliable :( """
        if Current.enableGoogleAndICloud:
            self.iCloud.devices[icloudDevice].play_sound()

    def sendToSlack(self, msg):
        if not Current.enableSlack:
            return

        self.slack.api_call(
            "chat.postMessage", channel="@" + self.userName, text=msg,
            username='watcher', icon_emoji=':robot_face:'
        )

    def updateAll(self):
        print "Updating iphoneLocation"
        self.updateIphoneLocation()
        print "iPhoneLocation updated, coords = %s" % Current.getIphoneCoordStr()
        updateCount = self.updateAllDistances()
        print "Updated all distances"
        self.removeInvalidPokemon()
        print "Removed all invalid pokemon"
        self.generateStaticMap()
        print "Generated static map"

    def reportAndSendToSlack(self):
        outbound = self.report()
        if outbound is not None:
            self.sendToSlack(outbound)

    def repopulateDB(self, conn):
        cur = conn.cursor()
        cur.execute("select time, type, lat, long, link, notes from event order by time desc limit 50")
        elems = cur.fetchall()
        for elem in elems:
            if time.time() < elem[0] + 700:
                print "Reloading: %s" % str(elem)
                pm = Pokemon(elem[0], elem[1], [ elem[2], elem[3] ], None, elem[4])
                self.potentiallyAddPokemonToManager(pm)

    def potentiallyAddPokemonToManager(self, pm):
        if pm.shouldAddToActive():
            self.addActivePokemon(pm)
        elif pm.isNearby():
            self.addNearbyPokemon(pm)

    def run(self):
        """ The manager thread main loop.  This will loop over our pokemon, update their distances, and then produce a message to send to slackbot """
        while True:
            try:
                if time.time() - self.lastUpdated > managerRefreshTime:
                    self.updateAll()
                    self.lastUpdated = time.time()

                    if Current.debug:
                        for pokemon in self.active:
                            print "Active: %s" % str(pokemon)
                        print "-=-=-=-=-=-=-=-"

            except Exception as ex:
                print "Error in Manager loop!"
                traceback.print_exc()
            time.sleep(.1)

##########################################################################

# Lowercase everything in case people mess up capitalization
alwaysTextList          = [x.lower() for x in alwaysTextList]
alwaysTextIfPerfectList = [x.lower() for x in alwaysTextIfPerfectList]
perfectTextList         = [x.lower() for x in perfectTextList]
noTextList              = [x.lower() for x in noTextList]
criticalList            = [x.lower() for x in criticalList]
notifyList              = uniqify(alwaysTextList + alwaysTextIfPerfectList + perfectTextList + noTextList + criticalList)

global sqlStatement, userId, userName
sqlStatement = "insert into event ( time, type, link, lat, long, notes ) values ( ?, ?, ?, ?, ?, ? )"
# Slack user info retrieved after connection
userId   = None
userName = None

def parseCoordinates(val):
    parsed    = urlparse(val)
    elems     = parsed[4].split("|")
    coordObj  = parse_qs(elems[0])
    coords    = coordObj["q"][0].split(",")
    latitude  = float(coords[0])
    longitude = float(coords[1])
    return [ latitude, longitude ]

def connectDatabase():
    print "Connecting to database"
    createDB = False
    # If the database does not exist, mark that we should create the schema
    if not os.path.isfile(dbname):
        createDB = True

    conn = sqlite3.connect(dbname) # make our connection to the database "file"

    if createDB:
        # Get a cursor, and create our single table
        cur = conn.cursor()
        cur.execute("create table event ( time integer, type text, lat real, long real, link text, notes text )")
        conn.commit()
    print "Connected to database"
    return conn

def writeToDatabase(conn, item, coords):
    cur = conn.cursor()
    cur.execute(
        sqlStatement,
        (
            int(float(item["ts"])),
            item["username"],
            item["attachments"][0]['text'],
            coords[0],
            coords[1],
            item["text"]
        )
    )
    conn.commit()

def connectSlack():
    print "Connecting to slack"
    slack = SlackClient(token)
    print "Connected to slack"
    if not slack.rtm_connect():
        raise Exception("Failed to connect to slack, invalid token? token=%s" % token)
    return slack

def mainLoop(manager, slack, conn, slackToManagerQueue):
    while True:
        dataRead = slack.rtm_read()
        for item in dataRead:
            if 'bot_id' and 'subtype' and 'attachments' not in item:
                continue
            coords = parseCoordinates(item["attachments"][0]['text'])

            if populateDB:
                writeToDatabase(conn, item, coords)

            pm = Pokemon(float(item["ts"]), item["username"], coords, item["text"], item["attachments"][0]["text"])
            manager.potentiallyAddPokemonToManager(pm)

if __name__ == "__main__":
    if token is None:
        raise Exception("Token must be defined, or no connection to slack can take place.  Generate one at: https://api.slack.com/web#authentication")
    conn = None

    if populateDB:
        conn = connectDatabase()

    slack = connectSlack()

    webToManagerQueue = Queue.Queue() # web requests to manager
    managerToWebQueue = Queue.Queue() # manager responses to web
    slackToManagerQueue = Queue.Queue() # slack to manager (adding pokemon)

    print "Starting manager thread"
    manager = Manager(slack, webToManagerQueue, managerToWebQueue, slackToManagerQueue)
    manager.setDaemon(True)
    manager.repopulateDB(conn)
    manager.start()
    print "Started manager thread"

    # XXX query db, re-load manager

    print "Starting http server"
    websvr = PokemonWebServer(manager, webToManagerQueue, managerToWebQueue)
    websvr.setDaemon(True)
    websvr.start()
    print "Started http server"

    failureCount = 0
    print "Begin main loop: %s" % datetime.datetime.now()
    while True:
        if failureCount > 5:
            print "Too many errors, shutting down!"
        try:
            mainLoop(manager, slack, conn, slackToManagerQueue)
        except Exception as ex:
            failureCount = failureCount + 1
            traceback.print_exc()
            print "Reconnecting to slack!"
            slack = connectSlack()
