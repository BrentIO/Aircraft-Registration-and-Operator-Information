import os
import json
import requests
from urllib.parse import urlparse
import sqlite3
import logging
import logging.handlers as handlers
import sys
from datetime import datetime
import time
from progress.bar import Bar
import hashlib
from yaspin import yaspin
import mysql.connector #pip3 install mysql-connector-python
import argparse

#https://aeroapi.flightaware.com/aeroapi/airports/{AIRPORT_ICAO}/flights/arrivals?type=Airline

#Note, FlightAware's max_pages does not operate as expected.  A "page" of data is 15 records, and it sends it
#  all in one response.  so, if request is .../flights/arrivals?type=Airline&max_pages=10, we're requesting
#  FlightAware to return 150 records (10 pages * 15 results per page).  Pricing is based on per-page results, 
#  so that request would cost $0.005 * 10 = $0.05.


def setup(args):
    global logger
    global applicationName
    global settings
    global import_sql

    settings = {}

    try:

        filePath = os.path.dirname(os.path.realpath(__file__)) + "/"

        applicationName = "FlightAware AeroAPI Airport Flight Arrivals"

        #Setup the logger, 10MB maximum log size
        logger = logging.getLogger(applicationName)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
        logHandler = handlers.RotatingFileHandler(filePath + 'events.log', maxBytes=10485760, backupCount=1)
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)
        logger.setLevel(logging.DEBUG)

        logger.info(applicationName + " application started.")
        
        #Make sure the settings file exists
        if os.path.exists(filePath + 'settings.json') == False:
            raise Exception("Settings file does not exist.  Expected file " + filePath + 'settings.json')

        #Get the settings file
        if os.path.exists(filePath + 'settings.json.private') == True:
            with open(filePath + 'settings.json.private') as settingsFile:
                settings = json.load(settingsFile)
        else:   
            with open(filePath + 'settings.json') as settingsFile:
                settings = json.load(settingsFile)

        settings['filePath'] = filePath
        settings['tempPath']  = os.path.join(settings['filePath'] , "tmp")
        settings['download_url'] = "https://aeroapi.flightaware.com/"
        settings['airport'] = str(args.icao_airport_code).strip()

        #By default, do not skip the download
        if "skip_download" not in settings:
            settings['skip_download'] = False

        if settings['skip_download'] != False:

            settings['skip_download'] = True
            print("Skipping file download not supported for this integration.")
            logger.warning("Skipping file download not supported for this integration.")

        if "mySQL" not in settings:
            raise Exception("The MySQL database information (mySQL) is not populated in the settings.json file.")

        if "uri" not in settings['mySQL']:
            raise Exception("The database uri (mySQL -> uri) is not populated in the settings.json file.")

        if "username" not in settings['mySQL']:
            raise Exception("The database username (mySQL -> username) is not populated in the settings.json file.")

        if "password" not in settings['mySQL']:
            raise Exception("The database password (mySQL -> password) is not populated in the settings.json file.")

        if "database" not in settings['mySQL']:
            raise Exception("The database name (mySQL -> database) is not populated in the settings.json file.")

        if "flightAware" not in settings:
            raise Exception("The FlightAware information (flightAware) is not populated in the settings.json file.")

        if "x-apikey" not in settings['flightAware']:
            raise Exception("The FlightAware API key (x-apikey) is not populated in the settings.json file.")

        if settings['flightAware']['x-apikey'] == "":
            raise Exception("The FlightAware API key (x-apikey) in the settings.json file is empty.")

        if "max_pages" not in settings['flightAware']:
            logger.warning("Setting flightAware -> max_pages is not defined in settings.json file; Defaulting to 5.")
            settings['flightAware']['max_pages'] = 5

        if str(settings['flightAware']['max_pages']).isnumeric() != True:
            raise Exception ("Invalid flightAware -> max_pages in settings.json")

        if "page_depth" not in settings['flightAware']:
            logger.warning("Setting flightAware -> page_depth is not defined in settings.json file; Defaulting to 1.")
            settings['flightAware']['page_depth'] = 1

        if str(settings['flightAware']['page_depth']).isnumeric() != True:
            raise Exception ("Invalid flightAware -> page_depth in settings.json")

        if "ttl_days" not in settings['flightAware']:
            logger.warning("Setting flightAware -> ttl_days is not defined in settings.json file; Defaulting to 30.")
            settings['flightAware']['ttl_days'] = 30

        if str(settings['flightAware']['ttl_days']).isnumeric() != True:
            raise Exception ("Invalid flightAware -> ttl_days in settings.json")

        if "sleep_duration_seconds" not in settings['flightAware']:
            logger.warning("Setting flightAware -> sleep_duration_seconds is not defined in settings.json file; Defaulting to 65.")
            settings['flightAware']['sleep_duration_seconds'] = 65

        if str(settings['flightAware']['sleep_duration_seconds']).isnumeric() != True:
            raise Exception ("Invalid flightAware -> sleep_duration_seconds in settings.json")

        #Get the SQL mode, defaulting to "memory"
        if 'local_database_mode' not in settings:
            settings['local_database_mode'] = "memory"

        if str(settings['local_database_mode']).lower() == "memory":

            import_sql = sqlite3.connect(":memory:")
        else:
            settings['local_database_mode'] = "disk"
            databaseFile = os.path.join(filePath, applicationName.lower().replace(" ", "-") + ".db")

            if os.path.exists(databaseFile):
                
                #Delete the old database
                os.remove(databaseFile)

            if os.path.exists(databaseFile + "-journal"):

                #Delete the old database journal
                os.remove(databaseFile + "-journal")

            import_sql = sqlite3.connect(databaseFile)
        
        cursor = import_sql.cursor()

        #Create the temporary tables in memory
        cursor.execute("CREATE TABLE flight_numbers (airline_designator text, flight_number text, ident text, origin text, destination text)")
    
    except Exception as ex:
        logger.error(ex)
        print(ex)
        exitApp(1)


def main():

    try:

        #Request the data
        get_arrivals()

        logger.info("Done processing arrival data.")
        print("Done processing arrival data.")

        logger.info("Sleeping " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds prior to getting scheduled arrivals.")
        print("Sleeping " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds prior to getting scheduled arrivals.")
        time.sleep(settings['flightAware']['sleep_duration_seconds']) 

        get_scheduled_arrivals()

        logger.info("Done processing scheduled arrival data.")
        print("Done processing scheduled arrival data.")

        #Export the data
        export_data()

        #Success, exit the app
        exitApp()

    except Exception as ex:
        logger.error(ex)
        print(ex)
        exitApp(1)


def exitApp(exitCode=None):

    if exitCode is None:
        exitCode = 0

    #Commit the database if it is not memory
    if settings['local_database_mode'] == "disk":
        logger.info("Committing database to disk.")
        import_sql.commit()

    if exitCode == 0:
        print(applicationName + " application finished successfully.")
        logger.info(applicationName + " application finished successfully.")

    if exitCode != 0:
        logger.info("Error; Exiting with code " + str(exitCode))

    sys.exit(exitCode)


def get_arrivals(url = None, request_depth = 1):

    logger.info("Requesting arrival data from FlightAware (Depth = " + str(request_depth) + ").")
    print("Requesting arrival data from FlightAware (Depth = " + str(request_depth) + ").")

    if url is None:
        url = settings['download_url'] + "aeroapi/airports/" + settings['airport'] + "/flights/arrivals?type=Airline&max_pages=" + str(settings['flightAware']['max_pages'])
    
    #Get the actual arrivals
    response = get_flightaware_data(url)

    #Parse the response
    if "arrivals" not in response:
        raise Exception("'arrivals' missing from response object.")

    #Process the arrivals array
    process_flights(response['arrivals'])

    #Make this recursive after giving FlightAware a cool off period
    request_depth = request_depth + 1

    if request_depth <= settings['flightAware']['page_depth']:
        logger.info("Sleeping " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds prior to getting next page depth.")
        print("Sleeping " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds prior to getting next page depth.")
        time.sleep(settings['flightAware']['sleep_duration_seconds'])  
        get_arrivals(url = settings['download_url'] + "aeroapi/" + response['links']['next'], request_depth = request_depth)


def get_scheduled_arrivals(url = None, request_depth = 1):

    logger.info("Requesting scheduled arrival data from FlightAware (Depth = " + str(request_depth) + ").")
    print("Requesting scheduled arrival data from FlightAware (Depth = " + str(request_depth) + ").")

    if url is None:
        url = settings['download_url'] + "aeroapi/airports/" + settings['airport'] + "/flights/scheduled_arrivals?type=Airline&max_pages=" + str(settings['flightAware']['max_pages'])

    #Get the actual arrivals
    response = get_flightaware_data(url)

    #Parse the response
    if "scheduled_arrivals" not in response:
        raise Exception("'arrivals' missing from response object.")

    #Process the arrivals array
    process_flights(response['scheduled_arrivals'])

    #Make this recursive after giving FlightAware a cool off period
    request_depth = request_depth + 1

    if request_depth <= settings['flightAware']['page_depth']:
        logger.info("Sleeping " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds prior to getting next page depth.")
        print("Sleeping " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds prior to getting next page depth.")
        time.sleep(settings['flightAware']['sleep_duration_seconds'])  
        get_scheduled_arrivals(url = settings['download_url'] + "aeroapi/" + response['links']['next'], request_depth = request_depth)

    

def get_flightaware_data(url):

    headers = {
        "x-apikey" : settings['flightAware']['x-apikey'],
        "Accept" : "application/json; charset=UTF-8"
    }

    with yaspin(text="Requesting data from FlightAware...") as spinner:
        response = requests.get(url, headers=headers)

        spinner.text = "Retrieved.\n"
        spinner.ok()

    #AeroAPI is extrememly temperamental
    if response.status_code == 429:

        logger.info("FlightAware returned 429; Will retry in " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds.")
        print("FlightAware returned 429; Will retry in " + str(settings['flightAware']['sleep_duration_seconds']) + " seconds.")
        time.sleep(settings['flightAware']['sleep_duration_seconds']) 

        return get_flightaware_data(url)

   
    if response.status_code != 200:
        logger.debug(json.dumps(response, default=str))
        raise Exception("Response code from request was " + str(response.status_code) + ".")

    return response.json()



def export_data():

    import_sql.row_factory = sqlite3.Row
    curFlightNumber = import_sql.cursor()

    logger.info("Querying data from SQLite.")

    with yaspin(text="Querying data from SQLite...") as spinner:

        curFlightNumber.execute("SELECT airline_designator, flight_number, ident, origin, destination FROM flight_numbers")

        arrayFlightNumbers = curFlightNumber.fetchall()

        spinner.stop()

    logger.info("SQLite returned " + str(len(arrayFlightNumbers)) + " rows of data.")

    flightNumbersDb = mysql.connector.connect(
        host=settings['mySQL']['uri'],
        user=settings['mySQL']['username'],
        password=settings['mySQL']['password'],
        database=settings['mySQL']['database'])

    logger.info("Creating temp table in MySQL.")

    mysqlCur = flightNumbersDb.cursor()

    #Ensure the source exists
    mysqlCur.execute("INSERT INTO sources (agency) \
                        SELECT * FROM (SELECT 'FlightAware') AS tmp \
                        WHERE NOT EXISTS ( \
                            SELECT agency FROM sources WHERE agency = 'FlightAware' \
                        ) LIMIT 1;")

    flightNumbersDb.commit()
    
    mysqlCur.execute("CREATE TEMPORARY TABLE import (airline_designator char(3), flight_number varchar(10), ident varchar(10), origin char(4), destination char(4), hash char(32), KEY hash (hash));")
     
    logger.info("Exporting data to MySQL.")

    sqlInsert = "INSERT INTO import (airline_designator, flight_number, ident, origin, destination, hash) VALUES (%s,%s,%s,%s,%s,%s)"

    with Bar("Exporting Data to MySQL...", max=len(arrayFlightNumbers)) as bar:

        for objFlight in arrayFlightNumbers:

            objCompleted = {}
          
            objCompleted['airline_designator'] = objFlight['airline_designator']
            objCompleted['flight_number'] = objFlight['flight_number']
            objCompleted['ident'] = objFlight['ident']
            objCompleted['origin'] = objFlight['origin']
            objCompleted['destination'] = objFlight['destination']

            mysqlCur.execute(sqlInsert, (objCompleted['airline_designator'], objCompleted['flight_number'], objCompleted['ident'], objCompleted['origin'], objCompleted['destination'], hashlib.md5(json.dumps(objCompleted).encode('utf-8')).hexdigest(), ))

            #Increment the bar
            bar.next()

        bar.finish()

    logger.info("Committing import data to MySQL.")

    with yaspin(text="Committing import data to MySQL...") as spinner:
        flightNumbersDb.commit()

        spinner.text = "Committed import data to MySQL.\n"
        spinner.ok()

    logger.info("Committed import data to MySQL.")

    # Add the data to the database
    logger.info("Creating new new flight numbers.")

    with yaspin(text="Creating new flight numbers...") as spinner:

        mysqlCur.execute("INSERT INTO flight_numbers (airline_designator, flight_number, ident, origin, destination, expires, hash, source) \
                            (SELECT import.airline_designator, import.flight_number, import.ident, import.origin, import.destination, DATE_ADD(NOW(), INTERVAL " + str(settings['flightAware']['ttl_days']) + " DAY), import.hash, sources.unique_id FROM import \
                            LEFT OUTER JOIN sources ON sources.agency = 'FlightAware') ON DUPLICATE KEY UPDATE expires = DATE_ADD(NOW(), INTERVAL " + str(settings['flightAware']['ttl_days']) + " DAY);")

        logger.info("Committing new flight numbers to MySQL.")
        flightNumbersDb.commit()
        
        spinner.text = "Created or updated " + str(mysqlCur.rowcount) + " flight numbers.\n"
        spinner.ok("")

    logger.info("Created or updated " + str(mysqlCur.rowcount) + " flight numbers.")
    
    mysqlCur.close()
    flightNumbersDb.close()


def process_flights(arryFlights):

    for objFlight in arryFlights:

        #Ensure the expected data elements are present
        if "operator_icao" not in objFlight:
            raise Exception("'operator_icao' missing from object.")

        if "flight_number" not in objFlight:
            raise Exception("'flight_number' missing from object.")

        if "ident_icao" not in objFlight:
            raise Exception("'ident_icao' missing from object.")

        if "origin" not in objFlight:
            raise Exception("'origin' missing from object.")

        if "code_iata" not in objFlight['origin']:
            raise Exception("'code_icao' missing from origin object.")

        if "code_icao" not in objFlight['origin']:
            raise Exception("'code_icao' missing from origin object.")

        if "destination" not in objFlight:
            raise Exception("'destination' missing from object.")

        if "code_icao" not in objFlight['destination']:
            raise Exception("'code_icao' missing from destination object.")

        if "diverted" not in objFlight:
            raise Exception("'diverted' missing from object.")

        if "cancelled" not in objFlight:
            raise Exception("'cancelled' missing from object.")

        if "status" not in objFlight:
            raise Exception("'status' missing from object.")

        if "fa_flight_id" not in objFlight:
            raise Exception("'fa_flight_id' missing from object.")

        tmpFlight = flight()

        tmpFlight.airline_designator = objFlight['operator_icao']
        tmpFlight.flight_number = objFlight['flight_number']
        tmpFlight.ident = objFlight['ident_icao']
        tmpFlight.origin = objFlight['origin']['code_icao']
        tmpFlight.destination = objFlight['destination']['code_icao']

        #Don't add flights that were diverted, cancelled, or result unknown
        if objFlight['diverted'] == True:
            logger.info("Skipping flight " + objFlight['fa_flight_id'] + " because the flight was marked as diverted.")
            continue

        if objFlight['cancelled'] == True:
            logger.info("Skipping flight " + objFlight['fa_flight_id'] + " because the flight was marked as cancelled.")
            continue

        if str(objFlight['status']).lower().strip() == "result unknown":
            logger.info("Skipping flight " + objFlight['fa_flight_id'] + " because the flight status was 'Result unknown'.")
            continue

        #Don't add flights with a missing IATA code (PUJ becomes KPUJ instead of MDPC, which is PUJ)
        if objFlight['origin']['code_iata'] is None:
            logger.info("Skipping flight " + objFlight['fa_flight_id'] + " because the origin -> code_iata was NULL.")
            continue

        tmpFlight.commit()


class flight():

    def __init__(self):
        self.airline_designator = ""
        self.flight_number = ""
        self.ident = ""
        self.origin = ""
        self.destination = ""

    def toDict(self):
        return self.__dict__

    def commit(self):

        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO flight_numbers (airline_designator, flight_number, ident, origin, destination) VALUES (?,?,?,?,?)"
        parameters = (self.airline_designator, self.flight_number, self.ident, self.origin, self.destination)

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        #Close the cursor
        dbCursor.close()



if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Retrieves arrivals and scheduled arrivals for the given airport code from FlightAware.')
    parser.add_argument(dest='icao_airport_code', metavar="icao_airport_code", help='ICAO airport code for the airport to retrieve (ex: KMCO).')

    args = parser.parse_args()

    #Setup the configuration required
    setup(args)

    main()