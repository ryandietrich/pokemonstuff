#!/usr/bin/env python

import dbm
import json
import os
from pprint import pprint
import requests
import sys
import time
import traceback

# Get your (free) API key from: https://ocr.space/ocrapi
my_api_key = ""

def ocr_space_file(filename, overlay=False, api_key=my_api_key, language='eng'):
    """ OCR.space API request with local file.
        Python3.5 - not tested on 2.7
    :param filename: Your file path & name.
    :param overlay: Is OCR.space overlay required in your response.
                    Defaults to False.
    :param api_key: OCR.space API key.
                    Defaults to 'helloworld'.
    :param language: Language code to be used in OCR.
                    List of available language codes can be found on https://ocr.space/OCRAPI
                    Defaults to 'en'.
    :return: Result in JSON format.
    """

    payload = {'isOverlayRequired': overlay,
               'apikey': api_key,
               'language': language,
               }
    with open(filename, 'rb') as f:
        r = requests.post('https://api.ocr.space/parse/image',
                          files={filename: f},
                          data=payload,
                          )

    if r.status_code == 200:
        return r.content
    return None

def process_res(result):
    if "ParsedResults" in result and type(result["ParsedResults"]) is list and len(result['ParsedResults']) > 0:
        if "ParsedText" in result['ParsedResults'][0]:
            elems = result['ParsedResults'][0]['ParsedText'].split("\r\n")
            if len(elems) > 1:
                return elems[1].strip()
            else:
                return None
    return None

""" Example result from ocr service
fakeres = {
    "ParsedResults" : [
        {
            "TextOverlay":{
                "Lines":[],
                "HasOverlay":False,
                "Message":"Text overlay is not provided as it is not requested"
            },
            "FileParseExitCode":1,
            "ParsedText" : "You got a Heart fra \r\nCameron \r\n",
            "ErrorMessage":"",
            "ErrorDetails":""
        }
    ],
    "OCRExitCode" : 1,
    "IsErroredOnProcessing":False,
    "ErrorMessage":None,
    "ErrorDetails":None,
    "ProcessingTimeInMilliseconds":"1850",
    "SearchablePDFURL":"Searchable PDF not generated as it was not requested."
}
"""

def updateOutboundData(outbound, recordFileJson, png, name):
    if name is None or name == "":
        print "    Unable to determine: %s" % png
        return

    if name not in outbound:
        outbound["%s,%s" % (name,png)] = 0

    print "png=%s name=%s" % ( png, name )

    elem = recordFileJson[png]
    if not elem:
        print "    Unable to find heart data for: %s (%s)" % ( name, png )
        return

    for ee in elem['receiveCounts']:
        outbound["%s,%s" % (name, png)] += int(elem['receiveCounts'][ee])

def _removeNonAscii(s):
    return "".join(i for i in s if ord(i)<128)

def determine_datadir():
    if len(sys.argv) == 2:
        if not os.path.exists(sys.argv[1]):
            raise Exception("Path: %s not found" % sys.argv[1])
        datadir = sys.argv[1]
    else:
        datadir = os.path.abspath(os.path.dirname(__file__))
    return datadir

def load_record_data(datadir):
    recordFileObj  = open("%s/record.txt" % datadir, 'r')
    recordFileTxt  = recordFileObj.read()
    recordFileJson = json.loads(recordFileTxt)
    return recordFileJson

def generate_files_to_process(datadir):
    allFiles = os.listdir(datadir)
    for af in allFiles:
        if not af.endswith(".png"):
            allFiles.remove(af)
    return allFiles

def main():
    db = dbm.open("ocr", 'c')
    outbound = {}

    datadir        = determine_datadir()
    recordFileJson = load_record_data(datadir)
    allFiles       = generate_files_to_process(datadir)

    for pos in range(0, len(allFiles)):
        print "%d of %d" % ( pos, len(allFiles) )
        ff = allFiles[pos]

        if ff in db:
            name = db[ff]
            updateOutboundData(outbound, recordFileJson, ff, name)
        else:
            try:
                decodeRes = ocr_space_file(filename="%s/%s" % (datadir, ff), language='eng')
                if decodeRes is None:
                    print "    Unable to determine name for: %s" % ff

                jsonData  = json.loads(decodeRes)
                decodeTxt = process_res(jsonData)

                if decodeTxt is None or decodeTxt == "":
                    print "    Unable to determine name for: %s" % ff

                name = _removeNonAscii(decodeTxt)
                db[ff] = name
                updateOutboundData(outbound, recordFileJson, ff, name)

            except Exception as ex:
                print traceback.format_exc(ex)
                print "Error processing: %s!" % ff

    # Print the sorted data
    for kk in sorted(outbound, key=outbound.get):
        print "%d,%s" % ( int(outbound[kk]), kk )

if __name__ == "__main__":
    if my_api_key == "":
        print "Please get an api key from https://ocr.space/ocrapi and update 'my_api_key' at the top of this script"
        sys.exit(2)
    main()
