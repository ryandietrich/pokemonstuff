#!/usr/bin/env python

"""
This script will connect to ebay, and look for items are selling below a specific "per pack" threshold.
The number of packs in an "item" on ebay is defined in the text describing it, there is no structured piece of information
that depicts that, so you can't query it directly, which is annoying, hence this script.

You'll need an ebay API key to use this, and then update the ebayAppID variable below.

I should have moved a lot of the configuration into an external JSON structure, but I didn't get around to it.
"""

import datetime
import json
import re
import sys
from pprint import pprint
from ebaysdk.exception import ConnectionError
from ebaysdk.finding import Connection

ebayAppID = "" # ebay app ID goes *here*

def runQuery(page):
    try:
        api = Connection(appid=ebayAppID, config_file=None)
        response = api.execute('findItemsAdvanced', {
            'keywords' : 'pokemon online code',
            'itemFilter' : [
                { 'name' : 'ListingType',      'value' : [ 'FixedPrice', 'AuctionWithBIN' ] },
                { 'name' : 'FreeShippingOnly', 'value' : 'true' },
                { 'name' : 'MinPrice',         'value': '5',  'paramName': 'Currency', 'paramValue': 'USD'},
                { 'name' : 'MaxPrice',         'value': '50', 'paramName': 'Currency', 'paramValue': 'USD'}
            ],
            'paginationInput': {
                'entriesPerPage' : 50,
                'pageNumber' : page
            },
            'sortOrder' : 'StartTimeNewest'
        })
    except ConnectionError as e:
        print(e)
        print(e.response.dict())
    return response.dict()

def processResults(result):
    try:
        for res in result['searchResult']['item']:
            if "code" not in res['title'].lower():
                continue

            pmtch = re.search("\d+[\-/]\d+", res['title'])
            if pmtch:
                continue

            cmtch = re.search("XY-?\d+", res['title'])
            if cmtch:
                continue

            if res['listingInfo']['listingType'] == 'FixedPrice':
                price = float(res['sellingStatus']['currentPrice']['value'])

            elif res['listingInfo']['listingType'] == 'AuctionWithBIN':
                price = float(res['listingInfo']['convertedBuyItNowPrice']['value'])

            elif res['listingInfo']['listingType'] == 'StoreInventory':
                price = float(res['sellingStatus']['currentPrice']['value'])
            else:
                pprint(res)
                sys.exit(0)

            mtch = re.search("(\d+)", res['title'])
            if mtch:
                count = float(mtch.group(1))
                costPer = price / count
                printData = False
                if "roaring" in res['title'].lower():
                    if costPer < .85:
                        printData = True
                elif "moon" in res['title'].lower():
                    if costPer < .45:
                        printData = True
                elif "break" in res['title'].lower():
                    if costPer < .24:
                        printData = True
                elif "evolutions" in res['title'].lower():
                    if costPer < .19:
                        printData = True
                elif "ancient origins" in res['title'].lower():
                    if costPer < .25:
                        printData = True
                elif "generations" in res['title'].lower():
                    if costPer < .20:
                        printData = True

                if printData:
                    print "%-3f   %-8s   %-5d   %-20s   %s" % ( costPer, price, count, "http://www.ebay.com/itm/%s" % res['itemId'], res['title'] )
            #print "price = %-8s startTime = %-30s title = %s" % ( res['listingInfo']['convertedBuyItNowPrice']['value'], res['listingInfo']['startTime'], res['title'] )

    except Exception as e:
        print("Error processing: %s" % str(ex))

result = runQuery(1)
pageCount = int(result['paginationOutput']['totalPages'])
print "Total page count: %d" % pageCount

for cc in range(1, pageCount):
    print "Page: %d" % cc
    result = runQuery(cc)
    processResults(result)
