#!/usr/bin/env python3

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


def handle_interrupt(signal, frame):
    raise sigKill("SIGKILL Requested")


class sigKill(Exception):
    pass


class RequestHandler(http.server.SimpleHTTPRequestHandler):

    #Create a conversation tracker for this request
    def __init__(self, request, client_address, server):

        http.server.SimpleHTTPRequestHandler.__init__(self, request, client_address, server)

    def log_message(self, format, *args):
        #Quiet the logs
        return

    def do_POST(self):
        responseHandler(self, 405)

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

            #Ensure the correct key was sent
            authenticate(self)

            #Get the operation requested by the user
            operation = parse.urlsplit(self.path).path.replace("/", "")

            if operation == "registration":
                getRegistration(self)
                return

            if operation == "operator":
                getOperator(self)
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


def authenticate(requestHandler):

    #Ensure the header exists
    if "x-api-key" not in requestHandler.headers:
        raise HTTPUnauthorizedResponse(status=401)

    #Ensure the header matches
    if requestHandler.headers['x-api-key'] != settings['api']['x-api-key']:
        raise HTTPUnauthorizedResponse(status=401)


def getRegistration(requestHandler):

    #Parse the query string
    queryString = parse.parse_qs(parse.urlsplit(requestHandler.path).query)

    #Ensure we have exactly 1 registration or icao_hex in the query string but not both
    if "registration" not in queryString and "icao_hex" not in queryString:
        raise HTTPErrorResponse(status=400, message="Either 'icao_hex' or 'registration' parameter is required")

    if "registration" in queryString and "icao_hex" in queryString:
        raise HTTPErrorResponse(status=400, message="Only one of 'icao_hex' or 'registration' parameter is allowed")

    #Ensure we only have 1 instance of either the registration or icao_hex
    if "registration" in queryString:
        if len(queryString['registration']) != 1:
            raise HTTPErrorResponse(status=400, message="Exactly 1 registration must be supplied")
        column_name = "registration"
        query_value = queryString['registration'][0]

    if "icao_hex" in queryString:
        if len(queryString['icao_hex']) != 1:
            raise HTTPErrorResponse(status=400, message="Exactly 1 icao_hex must be supplied")
        column_name = "icao_hex"
        query_value = queryString['icao_hex'][0]

    #Prevent cyclical requests
    if "prohibit_redirect" in queryString:
        prohibit_redirect = True
    else:
        prohibit_redirect = False

    #Default to simple data
    data_type = "simple"

    if "detailed" in queryString:
        if str(queryString['detailed'][0]).lower() == "true":
            #Change to detailed data
            data_type = "detailed"
            
    #Set the table name based on the data type
    if data_type == "simple":
        table_name = "simple"
    else:
        table_name = "registrations"

    registrationDb = mysql.connector.connect(
        host=settings['mySQL']['uri'],
        user=settings['mySQL']['username'],
        password=settings['mySQL']['password'],
        database=settings['mySQL']['database'])

    mysqlCur = registrationDb.cursor(dictionary=True)

    mysqlCur.execute("SELECT " + table_name + ".data, sources.agency FROM " + table_name + " "\
                        "INNER JOIN sources ON " + table_name + ".source = sources.unique_id " \
                        "WHERE " + column_name + " = '" + query_value + "' AND " + table_name + ".deleted is null;")

    result = mysqlCur.fetchall()

    mysqlCur.close()
    registrationDb.close()

    #Ensure we have have exactly 1 row
    if len(result) == 1:

        #Move the agency into the result
        returnValue = json.loads(result[0]['data'])
        returnValue['source'] = result[0]['agency']
        
        responseHandler(requestHandler, 200, body=returnValue)
        return

    if len(result) == 0:

        #See if the opposite data profile will give us data
        if prohibit_redirect != True:

            #Redirect to the detailed data and see if it can return anything
            if data_type == "simple":
                tmpHeaders = []
                tmpHeader = {}
                tmpHeader['key'] = "location"
                tmpHeader['value'] = "http://" + requestHandler.headers['Host'] + "/registration?" + column_name + "=" + query_value + "&detailed=true&prohibit_redirect=true"
                tmpHeaders.append(tmpHeader)

                responseHandler(requestHandler, 303, headers=tmpHeaders)
                return

            else:
                tmpHeaders = []
                tmpHeader = {}
                tmpHeader['key'] = "location"
                tmpHeader['value'] = "http://" + requestHandler.headers['Host'] + "/registration?" + column_name + "=" + query_value + "&detailed=false&prohibit_redirect=true"
                tmpHeaders.append(tmpHeader)

                responseHandler(requestHandler, 303, headers=tmpHeaders)
                return

        responseHandler(requestHandler, 404)
        return

    #Default to an error
    logger.warning("Retrieved " + str(len(result)) + " records from MySQL when querying for registration for '" + "" + "'.  Expected 0 or 1.")
    raise HTTPErrorResponse(status=409, message="Unexpected database response") 


def getOperator(requestHandler):

    #Parse the query string
    queryString = parse.parse_qs(parse.urlsplit(requestHandler.path).query)

    #Ensure we have an airline_designator in the query string and there is exactly 1 request
    if "airline_designator" not in queryString:
        raise HTTPErrorResponse(status=400, message="Parameter 'airline_designator' is required")

    if "airline_designator" in queryString:
        if len(queryString['airline_designator']) != 1:
            raise HTTPErrorResponse(status=400, message="Exactly 1 airline_designator must be supplied")

    operatorsDb = mysql.connector.connect(
        host=settings['mySQL']['uri'],
        user=settings['mySQL']['username'],
        password=settings['mySQL']['password'],
        database=settings['mySQL']['database'])

    mysqlCur = operatorsDb.cursor(dictionary=True)

    mysqlCur.execute("SELECT airline_designator, name, callsign, country FROM operators WHERE airline_designator = '" + str(queryString['airline_designator'][0]) + "' AND deleted is null;")

    result = mysqlCur.fetchall()

    mysqlCur.close()
    operatorsDb.close()

    #Ensure we have have exactly 1 row
    if len(result) == 1:
        responseHandler(requestHandler, 200, body=result[0])
        return

    if len(result) == 0:
        responseHandler(requestHandler, 404)
        return

    #Default to an error
    logger.warning("Retrieved " + str(len(result)) + " records from MySQL when querying for operator '" + str(queryString['airline_designator'][0]) + "'.  Expected 0 or 1.")
    raise HTTPErrorResponse(status=409, message="Unexpected database response") 
       

def responseHandler(requestHandler, status, headers=[], body="", contentType="application/json"):

    #Send the HTTP status code requested
    requestHandler.send_response(status)

    if len(body) > 0:
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
    if len(body) > 0:

        if contentType == "application/json":
            requestHandler.wfile.write(json.dumps(body).encode("utf8"))
        else:
            requestHandler.wfile.write(body)


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


def main():

    #Start the HTTP server
    try:

        logger.info("Starting HTTP server on port " + str(settings['api']['port']))

        #Create the webserver
        httpd = socketserver.TCPServer(("", settings['api']['port']), RequestHandler)

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