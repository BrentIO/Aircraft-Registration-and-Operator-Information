#!/usr/bin/env python3
from datetime import datetime, timedelta
import http.server
import socketserver
from urllib import parse
import json
import sys
import os
import logging
import logging.handlers as handlers
import signal
import mysql.connector #pip3 install mysql-connector-python
from enum import Enum
import hashlib


def handle_interrupt(signal, frame):
    raise sigKill("SIGKILL Requested")


def setLogLevel(logLevel):

    logLevel = logLevel.lower()

    if logLevel == "debug":
        logger.setLevel(logging.DEBUG)
        logger.debug("Logging set to DEBUG.")
        return

    if logLevel == "error":
        logger.setLevel(logging.ERROR)
        logger.error("Logging set to ERROR.")
        return

    if logLevel == "warning":
        logger.setLevel(logging.WARNING)
        logger.warning("Logging set to WARNING.")
        return

    if logLevel == "critical":
        logger.setLevel(logging.CRITICAL)
        logger.critical("Logging set to CRITICAL.")
        return


def responseHandler(requestHandler, status, headers=[], body=None, contentType="application/json"):

    #Send the HTTP status code requested
    requestHandler.send_response(status)

    if status == 404:
        contentType = None

    if contentType != None:
        tmpHeader = {}
        tmpHeader['key'] = "Content-Type"
        tmpHeader['value'] = contentType
        headers.append(tmpHeader)

    tmpHeader = {}
    tmpHeader['key'] = 'Access-Control-Allow-Origin'
    tmpHeader['value'] = "*"
    headers.append(tmpHeader)

    #Send each header to the caller
    for header in headers:
        requestHandler.send_header(header['key'], header['value'])

    #Send a blank line to the caller
    requestHandler.end_headers()

    #Empty the headers
    headers.clear()

    #Write the response body to the caller
    if body:
        if contentType == "application/json":
            requestHandler.wfile.write(json.dumps(body).encode("utf8"))
        else:
            requestHandler.wfile.write(body)


def authenticate(requestHandler):

    #Ensure the header exists
    if "x-api-key" not in requestHandler.headers:
        raise HTTPUnauthorizedResponse(status=401)

    #Ensure the header matches
    if requestHandler.headers['x-api-key'] != settings['api']['x-api-key']:
        raise HTTPUnauthorizedResponse(status=401)


def parseURL(path):

    #Get the operation requested by the user
    returnValue = parse.urlsplit(path).path.split("/")

    #Remove the first element in the array, it's going to be empty
    returnValue.pop(0)

    #Clean up each element in the array
    position = 0
    
    for element in returnValue:
        returnValue[position] = parse.unquote(element).strip()
        position = position + 1

    return returnValue


def parseBody(requestHandler):

    #Ensure the data is JSON
    if requestHandler.headers.get('Content-Type') != "application/json":
        raise HTTPErrorResponse(status=415, message="Unexpected Content-Type; Send application/json")

    content_len = int(requestHandler.headers.get('Content-Length'))
    return json.loads(requestHandler.rfile.read(content_len))


def registration_get(requestHandler, urlPath):

    if len(urlPath) < 3:
        raise HTTPErrorResponse(status=400, message="Parameter type (icao_hex|registration) and value is required")

    if urlPath[1] not in ['icao_hex', 'registration']:
        raise HTTPErrorResponse(status=400, message="Parameter type (icao_hex or registration) is required")

    if len(urlPath[2]) == 0:
        raise HTTPErrorResponse(status=400, message="Search criteria is required")

    #See if the user specified the type, default to "simple"
    if len(urlPath) == 4:
        if urlPath[3] in ['simple', 'detailed']:
            data_type = urlPath[3]
        else:
            raise HTTPErrorResponse(status=400, message="Parameter " + urlPath[3] + " is invalid")
    else:
        data_type = None

    if urlPath[1] == "registration":
        tmpRegistration = registration(registration=urlPath[2], data_type=data_type)

    if urlPath[1] == "icao_hex":
        tmpRegistration = registration(icao_hex=urlPath[2], data_type=data_type)

    getResult = tmpRegistration.get()

    #Ensure we have a result
    if getResult['status'] == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 200, body=getResult['data'])
        return

    if getResult['status'] == ENUM_RESULT.INVALID_REQUEST:
        raise HTTPErrorResponse(status=400, message=getResult['message'])

    if getResult['status'] == ENUM_RESULT.NOT_FOUND:

        #Auto redirect to the opposite if possible
        if requestHandler.headers.get('referer') is None and data_type == None:

            tmpHeaders = []
            tmpHeader = {}
            tmpHeader['key'] = "referer"
            tmpHeader['value'] = "http://" + requestHandler.headers['Host'] + requestHandler.path
            tmpHeaders.append(tmpHeader)
            tmpHeader = {}

            tmpHeader['key'] = "location"
            tmpHeader['value'] = "http://" + requestHandler.headers['Host'] + "/registration/" + str(urlPath[1]) + "/" +  str(urlPath[2])

            if data_type == "detailed":
                tmpHeader['value'] = tmpHeader['value'] + "/simple"
                tmpHeaders.append(tmpHeader)

                responseHandler(requestHandler, 303, headers=tmpHeaders)
                return

            else:
                tmpHeader['value'] = tmpHeader['value'] + "/detailed"
                tmpHeaders.append(tmpHeader)

                responseHandler(requestHandler, 303, headers=tmpHeaders)
                return
        
        responseHandler(requestHandler, 404)
        return
    
    if getResult['status'] == ENUM_RESULT.UNEXPECTED_RESULT:
        raise HTTPErrorResponse(status=409, message=getResult['message'])

    #Default to a 500
    raise HTTPErrorResponse()


def operator_get(requestHandler, urlPath):

    if len(urlPath) < 2 or len(urlPath[1]) == 0:
        logger.debug("Parameter 'airline_designator' is required" + str(urlPath))
        raise HTTPErrorResponse(status=400, message="Parameter 'airline_designator' is required")

    tmpOperator = operator()

    tmpOperator.airline_designator = parse.unquote(urlPath[1]).strip()

    getResult = tmpOperator.get()

    #Ensure we have a result
    if getResult == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 200, body=tmpOperator.toDict())
        return

    if getResult == ENUM_RESULT.NOT_FOUND:
        responseHandler(requestHandler, 404)
        return
    
    if getResult == ENUM_RESULT.UNEXPECTED_RESULT:
        responseHandler(requestHandler, 409)
        return

    #Default
    logger.debug("Unhandled response in operator_get for data" + str(urlPath))
    raise HTTPErrorResponse()


def operator_post(requestHandler):

    #Get the body from the post
    body = parseBody(requestHandler)

    #Verify the object passed has the correct parameters
    if "airline_designator" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'airline_designator' is required")

    if "name" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'name' is required")

    if "callsign" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'callsign' is required")

    if "country" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'country' is required")

    if "source" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'source' is required")

    tmpOperator = operator()

    tmpOperator.airline_designator = body['airline_designator']
    tmpOperator.name = body['name']
    tmpOperator.callsign = body['callsign']
    tmpOperator.country = body['country']
    tmpOperator.source = body['source']

    operator_postResponse = tmpOperator.post()

    if operator_postResponse['status'] == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 204)
        return

    if operator_postResponse['status'] == ENUM_RESULT.SUCCESS_NOT_MODIFIED:
        raise HTTPErrorResponse(status=409, message=operator_postResponse['message'])

    if operator_postResponse['status'] == ENUM_RESULT.UNEXPECTED_RESULT:
        raise HTTPErrorResponse(status=400, message=operator_postResponse['message'])

    if operator_postResponse['status'] == ENUM_RESULT.UNKNOWN_FAILURE:
        raise HTTPErrorResponse(status=500, message=operator_postResponse['message'])

    #Default
    logger.debug("Unhandled response in operator_post")
    raise HTTPErrorResponse()


def operator_patch(requestHandler, urlPath):

    if len(urlPath) < 2 or len(urlPath[1]) == 0:
        logger.debug("Parameter 'airline_designator' is required" + str(urlPath))
        raise HTTPErrorResponse(status=400, message="Parameter 'airline_designator' is required")

    #Get the body from the post
    body = parseBody(requestHandler)

    #Verify the object passed has the correct parameters
    if "airline_designator" in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'airline_designator' is not allowed in request body for this operation")

    if "name" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'name' is required")

    if "callsign" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'callsign' is required")

    if "country" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'country' is required")

    if "source" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'source' is required")

    tmpOperator = operator(urlPath[1], body['name'], body['callsign'], body['country'], body['source'])

    operator_patchResponse = tmpOperator.patch()

    if operator_patchResponse['status'] == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 204)
        return

    if operator_patchResponse['status'] == ENUM_RESULT.UNEXPECTED_RESULT or operator_patchResponse['status'] == ENUM_RESULT.INVALID_REQUEST:
        raise HTTPErrorResponse(status=400, message=operator_patchResponse['message'])

    if operator_patchResponse['status'] == ENUM_RESULT.NOT_FOUND:
        responseHandler(requestHandler, 404)
        return

    if operator_patchResponse['status'] == ENUM_RESULT.SUCCESS_NOT_MODIFIED:
        raise HTTPErrorResponse(status=409, message=operator_patchResponse['message'])

    if operator_patchResponse['status'] == ENUM_RESULT.UNKNOWN_FAILURE:
        raise HTTPErrorResponse(status=500, message=operator_patchResponse['message'])

    #Default
    logger.debug("Unhandled response in operator_patch")
    raise HTTPErrorResponse()


def operator_delete(requestHandler, urlPath):

    if len(urlPath) < 2 or len(urlPath[1]) == 0:
        logger.debug("Parameter 'airline_designator' is required" + str(urlPath))
        raise HTTPErrorResponse(status=400, message="Parameter 'airline_designator' is required")

    tmpOperator = operator(urlPath[1])

    operator_deleteResponse = tmpOperator.delete()

    if operator_deleteResponse['status'] == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 204)
        return

    if operator_deleteResponse['status'] == ENUM_RESULT.UNEXPECTED_RESULT:
        raise HTTPErrorResponse(status=400, message=operator_deleteResponse['message'])

    if operator_deleteResponse['status'] == ENUM_RESULT.NOT_FOUND:
        responseHandler(requestHandler, 404)
        return

    if operator_deleteResponse['status'] == ENUM_RESULT.SUCCESS_NOT_MODIFIED:
        raise HTTPErrorResponse(status=409, message=operator_deleteResponse['message'])

    if operator_deleteResponse['status'] == ENUM_RESULT.UNKNOWN_FAILURE:
        raise HTTPErrorResponse(status=500, message=operator_deleteResponse['message'])

    #Default
    logger.debug("Unhandled response in operator_delete")
    raise HTTPErrorResponse()


def flight_info_get(requestHandler, urlPath):

    if len(urlPath) < 2 or len(urlPath[1]) == 0:
        logger.debug("Parameter 'ident' is required" + str(urlPath))
        raise HTTPErrorResponse(status=400, message="Parameter 'ident' is required")

    #Parse the query string
    queryString = parse.parse_qs(parse.urlsplit(requestHandler.path).query)
    airport_icao = None

    #Ensure we only have 1 instance of each hint
    if "airport_icao" in queryString:
        if len(queryString['airport_icao']) != 1:
            raise HTTPErrorResponse(status=400, message="Exactly 1 airport_icao hint must be supplied")

        airport_icao = queryString['airport_icao'][0]

    tmpFlightInfo = flight_info(urlPath[1], focus_airport_icao_code=airport_icao)

    getResult = tmpFlightInfo.get()
    
    #Ensure we have a result
    if getResult == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 200, body=tmpFlightInfo.toDict())
        return

    if getResult == ENUM_RESULT.NOT_FOUND:
        responseHandler(requestHandler, 404)
        return
    
    if getResult == ENUM_RESULT.UNEXPECTED_RESULT:
        responseHandler(requestHandler, 409)
        return

    #Default
    logger.debug("Unhandled response in flight_info_get for data" + str(urlPath))
    raise HTTPErrorResponse()


def flight_info_post(requestHandler):

    #Get the body from the post
    body = parseBody(requestHandler)

    #Verify the object passed has the correct parameters
    if "ident" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'ident' is required")

    if "airline_designator" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'airline_designator' is required")

    if "flight_number" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'flight_number' is required")

    if "origin" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'origin' is required")

    if "destination" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'destination' is required")

    if "source" not in body:
        raise HTTPErrorResponse(status=400, message="Parameter 'source' is required")

    tmpFlight = flight_info(ident=body['ident'])

    tmpFlight.airline_designator = body['airline_designator']
    tmpFlight.flight_number = body['flight_number']
    tmpFlight.origin['icao_code'] = str(body['origin'])
    tmpFlight.destination['icao_code'] = str(body['destination'])
    tmpFlight.source = body['source']

    if 'expires' in body:
        tmpFlight.expires = datetime.fromisoformat(body['expires'])
        
    flight_postResponse = tmpFlight.post()

    if flight_postResponse['status'] == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 204)
        return

    if flight_postResponse['status'] == ENUM_RESULT.SUCCESS_NOT_MODIFIED:
        raise HTTPErrorResponse(status=409, message=flight_postResponse['message'])

    if flight_postResponse['status'] == ENUM_RESULT.UNEXPECTED_RESULT:
        raise HTTPErrorResponse(status=400, message=flight_postResponse['message'])

    if flight_postResponse['status'] == ENUM_RESULT.UNKNOWN_FAILURE:
        raise HTTPErrorResponse(status=500, message=flight_postResponse['message'])

    #Default
    logger.debug("Unhandled response in flight_post")
    raise HTTPErrorResponse()


def flight_info_delete(requestHandler, urlPath):

    #/flights/{ident}/{origin_airport_icao_code}/{destination_airport_icao_code}

    if len(urlPath) < 4:
        raise HTTPErrorResponse(status=400, message="Insufficient number of parameters provided")

    if len(urlPath[1]) == 0:
        logger.debug("Parameter 'ident' is required" + str(urlPath))
        raise HTTPErrorResponse(status=400, message="Parameter 'ident' is required")

    if len(urlPath[2]) == 0:
        logger.debug("Parameter 'origin_airport_icao_code' is required" + str(urlPath))
        raise HTTPErrorResponse(status=400, message="Parameter 'origin_airport_icao_code' is required")

    if len(urlPath[3]) == 0:
        logger.debug("Parameter 'destination_airport_icao_code' is required" + str(urlPath))
        raise HTTPErrorResponse(status=400, message="Parameter 'destination_airport_icao_code' is required")

    tmpFlight = flight_info(urlPath[1])
    tmpFlight.origin['icao_code'] = urlPath[2]
    tmpFlight.destination['icao_code'] = urlPath[3]

    flight_deleteResponse = tmpFlight.delete()

    if flight_deleteResponse['status'] == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 204)
        return

    if flight_deleteResponse['status'] == ENUM_RESULT.UNEXPECTED_RESULT:
        raise HTTPErrorResponse(status=400, message=flight_deleteResponse['message'])

    if flight_deleteResponse['status'] == ENUM_RESULT.NOT_FOUND:
        responseHandler(requestHandler, 404)
        return

    if flight_deleteResponse['status'] == ENUM_RESULT.SUCCESS_NOT_MODIFIED:
        raise HTTPErrorResponse(status=409, message=flight_deleteResponse['message'])

    if flight_deleteResponse['status'] == ENUM_RESULT.UNKNOWN_FAILURE:
        raise HTTPErrorResponse(status=500, message=flight_deleteResponse['message'])

    #Default
    logger.debug("Unhandled response in flight_info_delete")
    raise HTTPErrorResponse()


def flight_info_conflicts_get(requestHandler):

    tmpFlightInfo = flight_info(None)

    getResult = tmpFlightInfo.get_conflicts()
    
    #Ensure we have a result
    if getResult == ENUM_RESULT.SUCCESS:
        responseHandler(requestHandler, 200, body=tmpFlightInfo.conflicts())
        return

    if getResult == ENUM_RESULT.NOT_FOUND:
        responseHandler(requestHandler, 404)
        return
    
    if getResult == ENUM_RESULT.UNEXPECTED_RESULT:
        responseHandler(requestHandler, 409)
        return

    #Default
    logger.debug("Unhandled response in flight_info_conflicts_get")
    raise HTTPErrorResponse()


class sigKill(Exception):
    pass


class RequestHandler(http.server.SimpleHTTPRequestHandler):

    #Create a conversation tracker for this request
    def __init__(self, request, client_address, server):

        http.server.SimpleHTTPRequestHandler.__init__(self, request, client_address, server)

    def log_message(self, format, *args):
        #Quiet the logs
        return

    def do_PATCH(self):

        try:

            #Ensure the correct key was sent
            authenticate(self)

            #Get the operation requested by the user
            urlPath = parseURL(self.path)

            if urlPath[0] == "operator":

                operator_patch(self, urlPath)
                return
                         
            #All other requests get 405
            responseHandler(self, 405)

        except HTTPErrorResponse as ex:
            responseHandler(self, ex.status, body={"error": ex.message})

        except HTTPUnauthorizedResponse as ex:
            responseHandler(self, ex.status)

        except Exception as ex:
            logger.error({"exception": ex})
            responseHandler(self, 500, body={"error": "Unknown Error"})

    def do_DELETE(self):

        try:

            #Ensure the correct key was sent
            authenticate(self)

            #Get the operation requested by the user
            urlPath = parseURL(self.path)

            if urlPath[0] == "operator":
                operator_delete(self, urlPath)
                return

            if urlPath[0] == "flight":
                flight_info_delete(self, urlPath)
                return
                         
            #All other requests get 405
            responseHandler(self, 405)

        except HTTPErrorResponse as ex:
            responseHandler(self, ex.status, body={"error": ex.message})

        except HTTPUnauthorizedResponse as ex:
            responseHandler(self, ex.status)

        except Exception as ex:
            logger.error({"exception": ex})
            responseHandler(self, 500, body={"error": "Unknown Error"})

    def do_POST(self):
        
        try:

            #Ensure the correct key was sent
            authenticate(self)

            #Get the operation requested by the user
            urlPath = parseURL(self.path)

            if urlPath[0] == "operator":
                if len(urlPath) > 1:
                    raise HTTPErrorResponse(status=400, message="Airline designator should not be provided in path when performing POST")

                operator_post(self)
                return

            if urlPath[0] == "flight":
                if len(urlPath) > 1:
                    raise HTTPErrorResponse(status=400, message="Flight ident should not be provided in path when performing POST")

                flight_info_post(self)
                return
             
            #All other requests get 405
            responseHandler(self, 405)

        except HTTPErrorResponse as ex:
            responseHandler(self, ex.status, body={"error": ex.message})

        except HTTPUnauthorizedResponse as ex:
            responseHandler(self, ex.status)

        except Exception as ex:
            logger.error({"exception": ex})
            responseHandler(self, 500, body={"error": "Unknown Error"})

    def do_OPTIONS(self):

        tmpHeaders = []

        tmpHeader = {}
        tmpHeader['key'] = 'Access-Control-Allow-Methods'
        tmpHeader['value'] = "*"
        tmpHeaders.append(tmpHeader)

        tmpHeader = {}
        tmpHeader['key'] = 'Access-Control-Allow-Headers'
        tmpHeader['value'] = "*"
        tmpHeaders.append(tmpHeader)

        responseHandler(self, 200, headers=tmpHeaders)

    def do_GET(self):

        try:

            #Get the operation requested by the user
            urlPath = parseURL(self.path)

            if urlPath[0] == "manage":
                self.handleStaticFile(urlPath)
                return

            if urlPath[0] == "favicon.ico":
                self.sendStaticFile("manage/favicon.ico")
                return

            #Ensure the correct key was sent
            authenticate(self)

            if urlPath[0] == "registration":
                registration_get(self, urlPath)
                return

            if urlPath[0] == "operator":
                operator_get(self, urlPath)
                return

            if urlPath[0] == "flight" and urlPath[1] != "conflicts":
                flight_info_get(self, urlPath)
                return

            if urlPath[0] == "flight" and urlPath[1] == "conflicts":
                flight_info_conflicts_get(self)
                return

            #All other requests get 404
            responseHandler(self, 404)

        except HTTPErrorResponse as ex:
            responseHandler(self, ex.status, body={"error": ex.message})

        except HTTPUnauthorizedResponse as ex:
            responseHandler(self, ex.status)

        except Exception as ex:
            logger.error({"exception": ex})
            responseHandler(self, 500, body={"error": "Unknown Error"})


    def sendStaticFile(self, fileName):

        rootDirectory = os.path.dirname(os.path.realpath(__file__))
        fileName = os.path.join(rootDirectory,fileName)

        if os.path.exists(fileName) == False:
            responseHandler(self, 404)
            return

        if os.path.isfile(fileName) == False:
            if os.path.exists(os.path.join(fileName, "index.html")):
                fileName = os.path.join(fileName, "index.html")
            else:
                responseHandler(self, 404)
                return

        data = None
        contentType = None

        with open(fileName, "rb") as f:
            contentType = self.getContentType(fileName)
            data = f.read()
            f.close()

            responseHandler(self, 200, body=data, contentType=contentType)


    def handleStaticFile(self, fileName:list):

        if "common.js" in fileName:
            self.sendStaticFile("manage/common.js")
            return

        if "common.html" in fileName:
            self.sendStaticFile("manage/common.html")
            return
    
        strFileName = ""

        for entry in fileName:
            strFileName = os.path.join(strFileName, entry)

        self.sendStaticFile(strFileName)


    def getContentType(self, fileName:str):

        if fileName.endswith(".html"):
            return "text/html"

        if fileName.endswith(".ico"):
            return "image/x-icon"

        if fileName.endswith(".js"):
            return "text/javascript"
          
        return None


class HTTPErrorResponse(Exception):

    #Custom error message wrapper

    def __init__(self, status=500, message="Unknown Error"):
        self.status = status
        self.message = message
        super().__init__(self.status, self.message)


class HTTPUnauthorizedResponse(Exception):

    #Custom unauthorized message wrapper

    def __init__(self, status=401):
        self.status = status
        super().__init__(self.status)


class flight_info():

    def __init__(self, ident, focus_airport_icao_code = None):
        self.ident = ""
        self.airline_designator = ""
        self.flight_number = ""
        self.origin = {}
        self.destination = {}
        self.expires = None
        self.source = ""
        self.hash = ""

        self.focus_airport_icao_code = focus_airport_icao_code
        self.ident = ident
        self._conflicts = []

    class conflict():

        def __init__(self):
            self.ident = ""
            self.airline_designator = ""
            self.flight_number = ""
            self.source = ""
            self.expires = ""
            self.origin = {}
            self.destination = {}


    def get(self):

        operatorsDb = mysql.connector.connect(
            host=settings['mySQL']['uri'],
            user=settings['mySQL']['username'],
            password=settings['mySQL']['password'],
            database=settings['mySQL']['database'])

        mysqlCur = operatorsDb.cursor(dictionary=True)

        sqlQuery = "SELECT "\
                "flight_numbers.airline_designator, "\
                "flight_numbers.flight_number, "\
                "flight_numbers.expires, "\
                "origin_airport.icao_code AS origin_airport_icao_code, "\
                "origin_airport.name AS origin_airport_name, "\
                "origin_airport.city AS origin_airport_city, "\
                "origin_airport.region AS origin_airport_region, "\
                "origin_airport.country AS origin_airport_country, "\
                "origin_airport.phonic AS origin_airport_phonic, "\
                "destination_airport.icao_code AS destination_airport_icao_code, "\
                "destination_airport.name AS destination_airport_name, "\
                "destination_airport.city AS destination_airport_city, "\
                "destination_airport.region AS destination_airport_region, "\
                "destination_airport.country AS destination_airport_country, "\
                "destination_airport.phonic AS destination_airport_phonic, "\
                "flight_numbers.hash, "\
                "sources.agency AS source "\
            "FROM flight_numbers "\
            "LEFT OUTER JOIN airports AS origin_airport ON origin_airport.icao_code = flight_numbers.origin "\
            "LEFT OUTER JOIN airports AS destination_airport ON destination_airport.icao_code = flight_numbers.destination "\
            "LEFT OUTER JOIN sources ON sources.unique_id = flight_numbers.source "\
            "WHERE "\
                "flight_numbers.expires >= now() AND "\
                "flight_numbers.ident='" + self.ident + "'"

        if self.focus_airport_icao_code is not None:
            sqlQuery = sqlQuery + " AND (origin_airport.icao_code = '" + self.focus_airport_icao_code + "' OR destination_airport.icao_code = '" + self.focus_airport_icao_code + "')"

        mysqlCur.execute(sqlQuery)

        result = mysqlCur.fetchall()

        mysqlCur.close()
        operatorsDb.close()

        #Ensure we have have exactly 1 row
        if len(result) == 1:
            self.airline_designator = result[0]['airline_designator']
            self.flight_number = result[0]['flight_number']
            self.expires = result[0]['expires']
            self.origin['icao_code'] = result[0]['origin_airport_icao_code']
            self.origin['name'] = result[0]['origin_airport_name']
            self.origin['city'] = result[0]['origin_airport_city']
            self.origin['region'] = result[0]['origin_airport_region']
            self.origin['country'] = result[0]['origin_airport_country']
            self.origin['phonic'] = result[0]['origin_airport_phonic']
            self.destination['icao_code'] = result[0]['destination_airport_icao_code']
            self.destination['name'] = result[0]['destination_airport_name']
            self.destination['city'] = result[0]['destination_airport_city']
            self.destination['region'] = result[0]['destination_airport_region']
            self.destination['country'] = result[0]['destination_airport_country']
            self.destination['phonic'] = result[0]['destination_airport_phonic']
            self.source = result[0]['source']
            self.hash = result[0]['hash']
            return ENUM_RESULT.SUCCESS

        if len(result) == 0:
            return ENUM_RESULT.NOT_FOUND

        if len(result) > 1:
            logger.warning("Retrieved " + str(len(result)) + " records from MySQL when querying " + json.dumps(self.__dict__, default=str) + ".  Expected 0 or 1.")
            return ENUM_RESULT.UNEXPECTED_RESULT
            
        #Return unknown failure
        return {"status" : ENUM_RESULT.UNKNOWN_FAILURE}

    def post(self):

        try:

            returnValue = { 
                "status" : ENUM_RESULT.UNKNOWN_FAILURE,
                "message" : ""
            }

            if self.ident.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "ident is empty"}

            if self.airline_designator.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "airline_designator is empty"}

            if self.flight_number.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "flight_number is empty"}

            if "icao_code" not in self.origin:
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "origin icao_code is missing"}

            if self.origin['icao_code'].strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "origin icao_code is empty"}

            if "icao_code" not in self.destination:
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "destination icao_code is missing"}

            if self.destination['icao_code'].strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "destination icao_code is empty"}

            if self.source.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "source is empty"}

            #If no expiration is provided, default to 30 days
            if self.expires == None:
                self.expires = datetime.now() + timedelta(days=30)               

            self.ident = self.ident.strip().upper()
            self.airline_designator = self.airline_designator.strip().upper()
            self.flight_number = self.flight_number.strip().upper()
            self.origin['icao_code'] = self.origin['icao_code'].strip().upper()
            self.destination['icao_code'] = self.destination['icao_code'].strip().upper()
            self.source = self.source.strip()
            self.compute_hash()

            operatorsDb = mysql.connector.connect(
                host=settings['mySQL']['uri'],
                user=settings['mySQL']['username'],
                password=settings['mySQL']['password'],
                database=settings['mySQL']['database'])

            mysqlCur = operatorsDb.cursor()

            #Ensure the source exists
            mysqlCur.execute("INSERT INTO sources (agency) \
                                SELECT * FROM (SELECT '" + self.source + "') AS tmp \
                                WHERE NOT EXISTS ( \
                                    SELECT agency FROM sources WHERE agency = '" + self.source + "' \
                                ) LIMIT 1;")
            
            #Insert the data
            mysqlCur.execute("INSERT INTO flight_numbers (airline_designator, flight_number, ident, origin, destination, expires, hash, source) \
                                (SELECT '" + self.airline_designator + "','" + self.flight_number + "','" + self.ident + "','" + self.origin['icao_code'] + "','" + self.destination['icao_code'] + "','" + self.expires.strftime('%Y-%m-%d %H:%M:%S') + "','" + self.hash + "', sources.unique_id FROM sources \
                                WHERE sources.agency = '" + self.source + "') ON DUPLICATE KEY UPDATE expires = '" + self.expires.strftime('%Y-%m-%d %H:%M:%S') + "';")

            if mysqlCur.rowcount > 0:
                returnValue = {"status" : ENUM_RESULT.SUCCESS, "message" : ""}
            else:
                if mysqlCur.rowcount == 0:
                    returnValue = {"status" : ENUM_RESULT.SUCCESS_NOT_MODIFIED, "message" : "Resource exists and was not updated"}
                if mysqlCur.rowcount < 0:
                    returnValue = {"status" : ENUM_RESULT.UNEXPECTED_RESULT, "message" : "Unexpected row count"}
                
            operatorsDb.commit()
            mysqlCur.close()
            operatorsDb.close()

            logger.info("POST flight numbers ident " + self.ident + " hash " + self.hash)

            return returnValue

        except Exception as ex:
            logger.error(ex)
            return {"status" : ENUM_RESULT.UNKNOWN_FAILURE, "message" : "Unknown failure, see log"}

    def delete(self):

        try:

            returnValue = { 
                "status" : ENUM_RESULT.UNKNOWN_FAILURE,
                "message" : ""
            }

            if self.ident.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "ident is empty"}

            self.airline_designator = self.airline_designator.strip().upper()

            operatorsDb = mysql.connector.connect(
                host=settings['mySQL']['uri'],
                user=settings['mySQL']['username'],
                password=settings['mySQL']['password'],
                database=settings['mySQL']['database'])

            mysqlCur = operatorsDb.cursor()

            #Insert the data
            mysqlCur.execute("UPDATE flight_numbers SET expires = now() WHERE ident = '" + self.ident + "' AND origin = '" + self.origin['icao_code'] + "' AND destination = '" + self.destination['icao_code'] + "' AND expires > now()")

            if mysqlCur.rowcount > 0:
                returnValue = {"status" : ENUM_RESULT.SUCCESS}
            else:
                returnValue = {"status" : ENUM_RESULT.NOT_FOUND, "message" : "Resource not found"}
                
            operatorsDb.commit()
            mysqlCur.close()
            operatorsDb.close()

            logger.info("DELETE flight " + self.ident + " (" + str(mysqlCur.rowcount) + ")")

            return returnValue

        except Exception as ex:
            logger.error(ex)
            return {"status" : ENUM_RESULT.UNKNOWN_FAILURE, "message" : "Unknown failure, see log"}
    
    def conflicts(self):
        return [ob.__dict__ for ob in self._conflicts]

    def get_conflicts(self):

        flightInfoDb = mysql.connector.connect(
            host=settings['mySQL']['uri'],
            user=settings['mySQL']['username'],
            password=settings['mySQL']['password'],
            database=settings['mySQL']['database'])

        mysqlCur = flightInfoDb.cursor(dictionary=True)

        sqlQuery = "SELECT flight_numbers.ident, " \
                        "flight_numbers.airline_designator, "\
                        "flight_numbers.flight_number, "\
                        "flight_numbers.expires, "\
                        "origin_airport.icao_code AS origin_airport_icao_code, "\
                        "origin_airport.name AS origin_airport_name, "\
                        "origin_airport.city AS origin_airport_city, "\
                        "origin_airport.region AS origin_airport_region, "\
                        "origin_airport.country AS origin_airport_country, "\
                        "origin_airport.phonic AS origin_airport_phonic, "\
                        "destination_airport.icao_code AS destination_airport_icao_code, "\
                        "destination_airport.name AS destination_airport_name, "\
                        "destination_airport.city AS destination_airport_city, "\
                        "destination_airport.region AS destination_airport_region, "\
                        "destination_airport.country AS destination_airport_country, "\
                        "destination_airport.phonic AS destination_airport_phonic, "\
                        "flight_numbers.hash, "\
                        "sources.agency AS source "\
                    "FROM flight_numbers " \
                    "LEFT OUTER JOIN airports AS origin_airport ON origin_airport.icao_code = flight_numbers.origin " \
                    "LEFT OUTER JOIN airports AS destination_airport ON destination_airport.icao_code = flight_numbers.destination " \
                    "LEFT OUTER JOIN sources ON sources.unique_id = flight_numbers.source " \
                    "WHERE flight_numbers.ident IN " \
                            "(SELECT ident " \
                                "FROM flight_numbers " \
                                "WHERE expires > now() " \
                                "GROUP BY ident " \
                                "HAVING count(ident) > 1)  " \
                        "AND flight_numbers.expires > now() " \
                        "ORDER BY flight_numbers.ident, flight_numbers.expires;"

        mysqlCur.execute(sqlQuery)

        result = mysqlCur.fetchall()

        mysqlCur.close()
        flightInfoDb.close()

        #Ensure we have have exactly 1 row
        if len(result) > 0:

            for entry in result:
                tmpConflict = self.conflict()
                tmpConflict.ident = entry['ident']
                tmpConflict.airline_designator = entry['airline_designator']
                tmpConflict.flight_number = entry['flight_number']
                tmpConflict.expires = entry['expires'].isoformat()
                tmpConflict.source = entry['source']
                tmpConflict.origin['icao_code'] = entry['origin_airport_icao_code']
                tmpConflict.origin['name'] = entry['origin_airport_name']
                tmpConflict.origin['city'] = entry['origin_airport_city']
                tmpConflict.origin['region'] = entry['origin_airport_region']
                tmpConflict.origin['country'] = entry['origin_airport_country']
                tmpConflict.origin['phonic'] = entry['origin_airport_phonic']
                tmpConflict.destination['icao_code'] = entry['destination_airport_icao_code']
                tmpConflict.destination['name'] = entry['destination_airport_name']
                tmpConflict.destination['city'] = entry['destination_airport_city']
                tmpConflict.destination['region'] = entry['destination_airport_region']
                tmpConflict.destination['country'] = entry['destination_airport_country']
                tmpConflict.destination['phonic'] = entry['destination_airport_phonic']
                self._conflicts.append(tmpConflict)

            return ENUM_RESULT.SUCCESS

        if len(result) == 0:
            return ENUM_RESULT.SUCCESS
            
        #Return unknown failure
        return {"status" : ENUM_RESULT.UNKNOWN_FAILURE}
    
    def toDict(self):

        returnValue = {}

        for key in self.__dict__:
            if key in ['airline_designator', 'flight_number', 'origin', 'destination']:
                returnValue[key] = self.__dict__[key]

        return returnValue

    def compute_hash(self):

        tmpObj = {}

        tmpObj['airline_designator'] = self.airline_designator
        tmpObj['flight_number'] = self.flight_number
        tmpObj['ident'] = self.ident
        tmpObj['origin'] = self.origin['icao_code']
        tmpObj['destination'] = self.destination['icao_code']

        self.hash = hashlib.md5(json.dumps(tmpObj).encode('utf-8')).hexdigest()

class registration():

    def __init__(self, icao_hex = None, registration = None, data_type = "simple"):
        self.icao_hex = ""
        self.registration = ""

        if icao_hex:
            self.icao_hex = icao_hex
        
        if registration:
            self.registration = registration

        if data_type is None:
            data_type = "simple"

        self.data_type = data_type

        if self.data_type not in ['simple', 'detailed']:
            raise Exception("Unknown registration data type " + self.registration)    

    def get(self):

        operatorsDb = mysql.connector.connect(
            host=settings['mySQL']['uri'],
            user=settings['mySQL']['username'],
            password=settings['mySQL']['password'],
            database=settings['mySQL']['database'])

        mysqlCur = operatorsDb.cursor(dictionary=True)

        #Set the table name based on the data type
        if self.data_type == "simple":
            table_name = "simple"
        else:
            table_name = "registrations"

        if self.registration == "" and self.icao_hex == "":
            return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "registration or icao_hex must be specified"}

        if self.registration !="":
            mysqlCur.execute("SELECT " + table_name + ".data, sources.agency FROM " + table_name + " "\
                "INNER JOIN sources ON " + table_name + ".source = sources.unique_id " \
                "WHERE registration = '" + self.registration + "' AND " + table_name + ".deleted is null;")

        if self.icao_hex != "":
            mysqlCur.execute("SELECT " + table_name + ".data, sources.agency FROM " + table_name + " "\
                "INNER JOIN sources ON " + table_name + ".source = sources.unique_id " \
                "WHERE icao_hex = '" + self.icao_hex + "' AND " + table_name + ".deleted is null;")

        result = mysqlCur.fetchall()

        mysqlCur.close()
        operatorsDb.close()

        #Ensure we have have exactly 1 row
        if len(result) == 1:
            return {"status" : ENUM_RESULT.SUCCESS, "data" : json.loads(result[0]['data'])}

        if len(result) == 0:
            return {"status" : ENUM_RESULT.NOT_FOUND}

        if len(result) > 1:
            logger.warning("Retrieved " + str(len(result)) + " records from MySQL when querying " + json.dumps(self.__dict__, default=str) + ".  Expected 0 or 1.")
            return {"status" : ENUM_RESULT.UNEXPECTED_RESULT, "message" : "Unexpected number of records returned " + str(len(result))}
            
        #Return unknown failure
        return {"status" : ENUM_RESULT.UNKNOWN_FAILURE}


class operator():

    def __init__(self, airline_designator = "", name = "", callsign = "", country="", source=""):
        self.airline_designator = str(airline_designator).strip().upper()
        self.name = str(name).strip()
        self.callsign = str(callsign).strip().upper()
        self.country = str(country).strip().upper()
        self.source = str(source).strip()
        self.hash = ""


    def get(self):

        operatorsDb = mysql.connector.connect(
            host=settings['mySQL']['uri'],
            user=settings['mySQL']['username'],
            password=settings['mySQL']['password'],
            database=settings['mySQL']['database'])

        mysqlCur = operatorsDb.cursor(dictionary=True)

        mysqlCur.execute("SELECT airline_designator, name, callsign, country, sources.agency AS source, hash FROM operators LEFT OUTER JOIN sources ON sources.unique_id = operators.source WHERE operators.airline_designator = '" + self.airline_designator + "' AND operators.deleted is null;")

        result = mysqlCur.fetchall()

        mysqlCur.close()
        operatorsDb.close()

        #Ensure we have have exactly 1 row
        if len(result) == 1:
            self.airline_designator = result[0]['airline_designator']
            self.name = result[0]['name']
            self.callsign = result[0]['callsign']
            self.country = result[0]['country']
            self.source = result[0]['source']
            self.hash = result[0]['hash']

            return ENUM_RESULT.SUCCESS

        if len(result) == 0:
            return ENUM_RESULT.NOT_FOUND

        if len(result) > 1:
            #Default to an error
            logger.warning("Retrieved " + str(len(result)) + " records from MySQL when querying for operator '" + self.airline_designator + "'.  Expected 0 or 1.")

        return ENUM_RESULT.FAILED


    def toDict(self):
        returnValue = {}

        for key in self.__dict__:
            if key in ['airline_designator', 'name', 'callsign', 'country']:
                returnValue[key] = self.__dict__[key]
        return returnValue


    def compute_hash(self):

        tmpObj = {}

        for key in self.__dict__:
            if key in ['airline_designator', 'name', 'callsign', 'country', 'source']:
                tmpObj[key] = self.__dict__[key]

        self.hash = hashlib.md5(json.dumps(tmpObj).encode('utf-8')).hexdigest()
    

    def post(self):

        try:

            returnValue = { 
                "status" : ENUM_RESULT.UNKNOWN_FAILURE,
                "message" : ""
            }

            if self.airline_designator.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "airline_designator is empty"}

            if self.name.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "name is empty"}

            if self.callsign.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "callsign is empty"}

            if self.country.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "country is empty"}

            if self.source.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "source is empty"}

            self.airline_designator = self.airline_designator.strip().upper()
            self.name = self.name.strip()
            self.callsign = self.callsign.strip().upper()
            self.country = self.country.strip().upper()
            self.source = self.source.strip()
            self.compute_hash()

            operatorsDb = mysql.connector.connect(
                host=settings['mySQL']['uri'],
                user=settings['mySQL']['username'],
                password=settings['mySQL']['password'],
                database=settings['mySQL']['database'])

            mysqlCur = operatorsDb.cursor()

            #Ensure the source exists
            mysqlCur.execute("INSERT INTO sources (agency) \
                                SELECT * FROM (SELECT '" + self.source + "') AS tmp \
                                WHERE NOT EXISTS ( \
                                    SELECT agency FROM sources WHERE agency = '" + self.source + "' \
                                ) LIMIT 1;")

            #Insert the data
            mysqlCur.execute("UPDATE operators SET deleted = now() WHERE source = (SELECT sources.unique_id FROM sources WHERE sources.agency = '" + self.source + "') AND airline_designator = '" + self.airline_designator + "' AND operators.deleted is NULL")
            
            #Insert the data
            mysqlCur.execute("INSERT INTO operators (airline_designator, name, callsign, country, hash, source) \
                                (SELECT '" + self.airline_designator + "','" + self.name + "','" + self.callsign + "','" + self.country + "','" + self.hash + "', sources.unique_id FROM sources \
                                WHERE sources.agency = '" + self.source + "') ON DUPLICATE KEY UPDATE deleted = NULL;")

            if mysqlCur.rowcount > 0:
                returnValue = {"status" : ENUM_RESULT.SUCCESS, "message" : ""}
            else:
                if mysqlCur.rowcount == 0:
                    returnValue = {"status" : ENUM_RESULT.SUCCESS_NOT_MODIFIED, "message" : "Resource exists and was not updated"}
                if mysqlCur.rowcount < 0:
                    returnValue = {"status" : ENUM_RESULT.UNEXPECTED_RESULT, "message" : "Unexpected row count"}
                
            operatorsDb.commit()
            mysqlCur.close()
            operatorsDb.close()

            logger.info("POST operator " + self.airline_designator + " hash " + self.hash)

            return returnValue

        except Exception as ex:
            logger.error(ex)
            return {"status" : ENUM_RESULT.UNKNOWN_FAILURE, "message" : "Unknown failure, see log"}


    def patch(self):

        try:

            returnValue = { 
                "status" : ENUM_RESULT.UNKNOWN_FAILURE,
                "message" : ""
            }

            if self.airline_designator.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "airline_designator is empty"}

            if self.name.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "name is empty"}

            if self.callsign.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "callsign is empty"}

            if self.country.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "country is empty"}

            if self.source.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "source is empty"}

            self.airline_designator = self.airline_designator.strip().upper()
            self.name = self.name.strip()
            self.callsign = self.callsign.strip().upper()
            self.country = self.country.strip().upper()
            self.source = self.source.strip()
            self.compute_hash()

            tmpCheckIfExists = operator(self.airline_designator)

            #Make sure the airline_designator already exists
            if tmpCheckIfExists.get() != ENUM_RESULT.SUCCESS:
                return {"status" : ENUM_RESULT.NOT_FOUND}

            operatorsDb = mysql.connector.connect(
                host=settings['mySQL']['uri'],
                user=settings['mySQL']['username'],
                password=settings['mySQL']['password'],
                database=settings['mySQL']['database'])

            mysqlCur = operatorsDb.cursor()

            #Ensure the source exists
            mysqlCur.execute("INSERT INTO sources (agency) \
                                SELECT * FROM (SELECT '" + self.source + "') AS tmp \
                                WHERE NOT EXISTS ( \
                                    SELECT agency FROM sources WHERE agency = '" + self.source + "' \
                                ) LIMIT 1;")

            #Insert the data
            mysqlCur.execute("UPDATE operators SET deleted = now() WHERE source = (SELECT sources.unique_id FROM sources WHERE sources.agency = '" + self.source + "') AND airline_designator = '" + self.airline_designator + "' AND hash <> '" + self.hash + "' AND operators.deleted is NULL")
            
            #Insert the data
            mysqlCur.execute("INSERT INTO operators (airline_designator, name, callsign, country, hash, source) \
                                (SELECT '" + self.airline_designator + "','" + self.name + "','" + self.callsign + "','" + self.country + "','" + self.hash + "', sources.unique_id FROM sources \
                                WHERE sources.agency = '" + self.source + "') ON DUPLICATE KEY UPDATE deleted = NULL;")

            if mysqlCur.rowcount > 0 or mysqlCur.rowcount == 0:
                returnValue = {"status" : ENUM_RESULT.SUCCESS}
            else:
                returnValue = {"status" : ENUM_RESULT.UNEXPECTED_RESULT, "message" : "Unexpected row count"}
                
            operatorsDb.commit()
            mysqlCur.close()
            operatorsDb.close()

            logger.info("PATCH operator " + self.airline_designator + " hash " + self.hash)

            return returnValue

        except Exception as ex:
            logger.error(ex)
            return {"status" : ENUM_RESULT.UNKNOWN_FAILURE, "message" : "Unknown failure, see log"}


    def delete(self):

        try:

            returnValue = { 
                "status" : ENUM_RESULT.UNKNOWN_FAILURE,
                "message" : ""
            }

            if self.airline_designator.strip() == "":
                return {"status" : ENUM_RESULT.INVALID_REQUEST, "message" : "airline_designator is empty"}

            self.airline_designator = self.airline_designator.strip().upper()

            tmpCheckIfExists = operator(self.airline_designator)

            #Make sure the airline_designator already exists
            if tmpCheckIfExists.get() != ENUM_RESULT.SUCCESS:
                return {"status" : ENUM_RESULT.NOT_FOUND}

            operatorsDb = mysql.connector.connect(
                host=settings['mySQL']['uri'],
                user=settings['mySQL']['username'],
                password=settings['mySQL']['password'],
                database=settings['mySQL']['database'])

            mysqlCur = operatorsDb.cursor()

            #Insert the data
            mysqlCur.execute("UPDATE operators SET deleted = now() WHERE airline_designator = '" + self.airline_designator + "' AND operators.deleted is NULL")

            if mysqlCur.rowcount == 1:
                returnValue = {"status" : ENUM_RESULT.SUCCESS}
            else:
                returnValue = {"status" : ENUM_RESULT.NOT_FOUND, "message" : "Resource not found"}
                
            operatorsDb.commit()
            mysqlCur.close()
            operatorsDb.close()

            logger.info("DELETE operator " + self.airline_designator)

            return returnValue

        except Exception as ex:
            logger.error(ex)
            return {"status" : ENUM_RESULT.UNKNOWN_FAILURE, "message" : "Unknown failure, see log"}


class ENUM_RESULT(Enum):
    SUCCESS = 0
    SUCCESS_NOT_MODIFIED = 1
    FAILED = 100
    UNKNOWN_FAILURE = 101
    NOT_FOUND = 102
    UNEXPECTED_RESULT = 103
    INVALID_REQUEST = 104
    UNSUPPORTED = 105


def setup():
    global applicationName
    global settings
    global logger

    #Define some constants
    applicationName = "Aircraft Registration and Operator Information API"
    settings = {}

    try:

        filePath = os.path.dirname(os.path.realpath(__file__))

        #Setup the logger, 10MB maximum log size
        logger = logging.getLogger(applicationName)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
        logHandler = handlers.RotatingFileHandler(os.path.join(filePath, 'api.log'), maxBytes=10485760, backupCount=1)
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)
        logger.setLevel(logging.INFO)

        logger.info(applicationName + " started.")

        #Make sure the settings file exists
        if os.path.exists(os.path.join(filePath, 'settings.json')) == False:
            raise Exception("Settings file does not exist.  Expected file " + os.path.join(filePath, 'settings.json'))

        #Settings file exists, read it in and verify its contents
        with open(os.path.join(filePath, 'settings.json')) as settingsFile:
            settings = json.load(settingsFile)

        if "log_level" in settings:
            setLogLevel(settings['log_level'])

        if "api" not in settings:
            raise Exception ("api object is missing from settings.json")

        if "x-api-key" not in settings['api']:
            raise Exception ("Missing api -> x-api-key in settings.json")

        if settings['api']['x-api-key'] == "":
            raise Exception ("Empty api -> x-api-key in settings.json")

        if settings['api']['x-api-key'] == "5d95bb51-64b1-4269-b812-2e20e59cb3c5":
            raise Exception ("Default x-api-key used.  Please change the value for x-api-key")

        if "port" not in settings['api']:
            raise Exception ("Missing api -> port in settings.json")

        if str(settings['api']['port']).isnumeric() != True:
            raise Exception ("Invalid api -> port in settings.json")

        if "mySQL" not in settings:
            raise Exception ("mySQL object is missing from settings.json")

        if "uri" not in settings['mySQL']:
            raise Exception ("Missing mySQL -> uri in settings.json")

        if "database" not in settings['mySQL']:
            raise Exception ("Missing mySQL -> database in settings.json")

        if "username" not in settings['mySQL']:
            raise Exception ("Missing mySQL -> username in settings.json")

        if "password" not in settings['mySQL']:
            raise Exception ("Missing mySQL -> password in settings.json")
        

    except Exception as ex:
        logger.error(ex)
        exitApp(1)


def exitApp(exitCode=None):

    #Force the log level to info
    logger.setLevel(logging.INFO)

    if exitCode is None:
        exitCode = 0

    if exitCode == 0:
        logger.info(applicationName + " finished successfully.")

    if exitCode != 0:
        logger.info("Error; Exiting with code " + str(exitCode))

    sys.exit(exitCode)

class ThreadedTCPServer(socketserver.ThreadingMixIn,socketserver.TCPServer):
    pass

def main():

    #Start the HTTP server
    try:

        logger.info("Starting HTTP server on port " + str(settings['api']['port']))

        #Create the webserver
        httpd = socketserver.ThreadingTCPServer(("", settings['api']['port']), RequestHandler)

        #Serve clients until stopped
        httpd.serve_forever()

    except sigKill:
        #Kill the http server and clean up open connections
        httpd.server_close()
        exitApp(0)       

    except KeyboardInterrupt:
        #Kill the http server and clean up open connections
        httpd.server_close()
        exitApp(0)

    except Exception as ex:
        logger.error(ex)

        
if __name__ == "__main__":

    signal.signal(signal.SIGTERM, handle_interrupt)
    setup()
    main()