import csv
import os
import json
import requests
import shutil
from urllib.parse import urlparse
import zipfile
import sqlite3
import logging
import logging.handlers as handlers
import sys
from datetime import datetime
from progress.bar import Bar
import time
import hashlib
from yaspin import yaspin
from bson.objectid import ObjectId
import mysql.connector #pip3 install mysql-connector-python
import argparse
import re

#https://www.mictronics.de/aircraft-database/indexedDB.php


def setup(args):
    global logger
    global applicationName
    global settings
    global import_sql

    settings = {}

    try:

        filePath = os.path.dirname(os.path.realpath(__file__)) + "/"

        applicationName = "Mictronics IndexedDB"

        #Setup the logger, 10MB maximum log size
        logger = logging.getLogger(applicationName)
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] - %(message)s')
        logHandler = handlers.RotatingFileHandler(filePath + 'events.log', maxBytes=10485760, backupCount=1)
        logHandler.setFormatter(formatter)
        logger.addHandler(logHandler)
        logger.setLevel(logging.INFO)

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
        settings['download_url'] = args.download_url

        #By default, do not skip the download
        if "skip_download" not in settings:
            settings['skip_download'] = False

        if settings['skip_download'] != False:

            settings['skip_download'] = True
            print("Skipping file download; Will use the cached copy.")
            logger.warning("Skipping file download; Will use the cached copy.")

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
        cursor.execute("CREATE TABLE aircraft (icao_hex text, registration text, type_designator text, military integer, interesting integer)")
        cursor.execute("CREATE TABLE operators (airline_designator text, name text, country text, callsign text)")
        cursor.execute("CREATE TABLE types (type_designator text, manufacturer_model text, powerplant text, category text, wake_turbulence_category text)")
    
    except Exception as ex:
        logger.error(ex)
        print(ex)
        exitApp(1)


def main():

    try:

        #Get the files
        if settings['skip_download'] != True:
            download()

        #Import the operators file
        import_operators()

        #Import the types file
        import_types()

        #Import the aircraft file
        import_aircraft()

        #Export the aircraft data
        export_aircraft()

        #Export the operator data
        export_operators()

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

    #Delete the temp folder if it exists
    if os.path.exists(settings['tempPath']) and exitCode == 0:

        logger.info("Deleting temporary folder.")

        #Delete the old temp directory
        shutil.rmtree(settings['tempPath'])

    if exitCode == 0:
        print(applicationName + " application finished successfully.")
        logger.info(applicationName + " application finished successfully.")

    if exitCode != 0:
        logger.info("Error; Exiting with code " + str(exitCode))

    sys.exit(exitCode)


def download():

    if os.path.exists(settings['tempPath']):

        #Delete the old temp directory
        shutil.rmtree(settings['tempPath'])

    if os.path.exists(settings['tempPath']) == False: 

        #Create a new, empty temp directory
        os.mkdir(settings['tempPath'])

    #Set the files' name
    downloadFileName = os.path.basename(urlparse(settings['download_url']).path)
    downloadFileDestination = os.path.join(settings['tempPath'], downloadFileName)

    #Get the file
    logger.info("Beginning file download.  File: " + settings['download_url'])

    with yaspin(text="Downloading file...") as spinner:
        response = requests.get(settings['download_url'])

        spinner.text = "Completed file download.\n"
        spinner.ok()
   
    if response.status_code != 200:
        raise Exception("Response code from download was " + str(response.status_code) + ".")

    #Write the file to disk
    with open(downloadFileDestination, 'wb') as downloadedFile:
        downloadedFile.write(response.content)

    logger.info("Completed file download.")

    #Extract the file
    logger.info("Extracting ZIP file.")

    with zipfile.ZipFile(downloadFileDestination, 'r') as downloadedFile:

        with yaspin(text="Extracting files...") as spinner:
            downloadedFile.extractall(settings['tempPath'])

            spinner.text = "Files extracted.\n"
            spinner.ok()

    logger.info("ZIP file extracted.")

    #Delete the original zip file
    os.remove(downloadFileDestination)

    #Rename the files to be lower case
    for extractedFile in os.listdir(settings['tempPath']):
        os.rename(os.path.join(settings['tempPath'], extractedFile), os.path.join(settings['tempPath'], extractedFile.lower()))


def import_operators():

    #Ensure the file exists
    operatorsFilePath = os.path.join(settings['tempPath'], 'operators.json')

    if os.path.exists(operatorsFilePath) == False:
        raise Exception ("Operators file not found, expected " + operatorsFilePath)

    logger.info("Beginning to import operators file.")

    with open(operatorsFilePath) as operatorsFile:
        fileContents = json.load(operatorsFile)

    count = 0

    for operator in fileContents:

        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO operators (airline_designator, name, country, callsign) VALUES (?,?,?,?)"
        parameters = (str(operator).strip(), str(fileContents[operator][0]).strip(), str(fileContents[operator][1]).strip(), str(fileContents[operator][2]).strip())

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        count = count + 1

        #Close the cursor
        dbCursor.close()

    logger.info("Completed importing " + str(count) + " operators.")
   
    return


def import_types():

    #Ensure the file exists
    typesFilePath = os.path.join(settings['tempPath'], 'types.json')

    if os.path.exists(typesFilePath) == False:
        raise Exception ("Types file not found, expected " + typesFilePath)
    
    logger.info("Beginning to read aircraft types file.")

    count = 0

    with open(typesFilePath) as aircraftTypeFile:
        fileContents = json.load(aircraftTypeFile)

    for entry in fileContents:

        dbCursor = import_sql.cursor()

        #Correct incorrect WTC for the A388
        if str(entry).strip() == "A388":
            fileContents[entry][2] = "J"

        tmpObj = {}
        tmpObj['designator'] = str(entry).strip()
        tmpObj['manufacturer_model'] = str(fileContents[entry][0]).strip()
        tmpDecodedDescription = decode_description(str(fileContents[entry][1]).strip())
        tmpObj['powerplant'] = tmpDecodedDescription['powerplant']
        tmpObj['category'] = tmpDecodedDescription['category']
        tmpObj['wake_turbulence_category'] = decode_wtc(str(fileContents[entry][2]).strip())

        insert_statement = "INSERT INTO types (type_designator, manufacturer_model, powerplant, category, wake_turbulence_category) VALUES (?,?,?,?,?)"
        parameters = (tmpObj['designator'], tmpObj['manufacturer_model'], json.dumps(tmpObj['powerplant']), tmpObj['category'], tmpObj['wake_turbulence_category'])

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        count = count + 1

        #Close the cursor
        dbCursor.close()

    logger.info("Finished reading aircraft types, created " + str(count) + " total entries.")


def import_aircraft():

    #Ensure the file exists
    aircraftsFilePath = os.path.join(settings['tempPath'], 'aircrafts.json')

    if os.path.exists(aircraftsFilePath) == False:
        raise Exception ("Aircraft file not found, expected " + aircraftsFilePath)
    
    logger.info("Beginning to read aircraft file.")

    count = 0

    with open(aircraftsFilePath) as aircraftFile:
        fileContents = json.load(aircraftFile)

    for entry in fileContents:

        dbCursor = import_sql.cursor()
        tmpObject = {}
        tmpObject['icao_hex'] = str(entry).strip()
        tmpObject['registration'] = str(fileContents[entry][0]).strip()
        tmpObject['type_designator'] = str(fileContents[entry][1]).strip()
        tmpObject['military'] = str(fileContents[entry][2][0]).strip()
        tmpObject['interesting'] = str(fileContents[entry][2][1]).strip()

        if tmpObject['type_designator'] == "":
            tmpObject['type_designator'] = None

        insert_statement = "INSERT INTO aircraft (icao_hex, registration, type_designator, military, interesting) VALUES (?,?,?,?,?)"
        parameters = (tmpObject['icao_hex'], tmpObject['registration'], tmpObject['type_designator'] , tmpObject['military'], tmpObject['interesting'])

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        count = count + 1

        #Close the cursor
        dbCursor.close()

    logger.info("Finished reading aircraft, created " + str(count) + " total entries.")


def decode_description(description):

    returnValue = {}
    returnValue['powerplant'] = {}
    returnValue['category'] = ""

    #Handle special codes
    if description == "B0-":
        returnValue['category'] = "Balloon"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "D0-":
        returnValue['category'] = "Drone"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "V0-":
        returnValue['category'] = "Vehicle"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "L0-":
        returnValue['category'] = "LandPlane"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "P0-":
        returnValue['category'] = "Paraglider"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "G0-":
        returnValue['category'] = "Gyrocopter"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "T0-":
        returnValue['category'] = "Tiltrotor"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "H0-":
        returnValue['category'] = "Helicopter"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    if description == "-0-":
        returnValue['category'] = "Unknown/Not Yet Assigned"
        returnValue['powerplant']['count'] = 0
        returnValue['powerplant']['type'] = "None"

        return returnValue

    #Determine if this is a 3-character code in the 'category-power plant count-power plant type' format:
    if re.match("^[A-Z][A-Z0-9][A-Z]$", description) is not None:

        if description[0].upper() == "A":
            returnValue['category'] = "Amphibian"

        if description[0].upper() == "G":
            returnValue['category'] = "Gyrocopter"

        if description[0].upper() == "H":
            returnValue['category'] = "Helicopter"

        if description[0].upper() == "L":
            returnValue['category'] = "LandPlane"
        
        if description[0].upper() == "S":
            returnValue['category'] = "SeaPlane"

        if description[0].upper() == "T":
            returnValue['category'] = "Tiltrotor"

        if str(description[1]).isnumeric() == True:
            returnValue['powerplant']['count'] = int(description[1])

        else:
            if description[1].upper() == "C":
                returnValue['powerplant']['count'] = 2
                returnValue['powerplant']['combined'] = True        

        if description[2].upper() == "E":
            returnValue['powerplant']['type'] = "Electric"

        if description[2].upper() == "J":
            returnValue['powerplant']['type'] = "Jet"

        if description[2].upper() == "P":
            returnValue['powerplant']['type'] = "Piston"

        if description[2].upper() == "R":
            returnValue['powerplant']['type'] = "Rocket"

        if description[2].upper() == "T":
            returnValue['powerplant']['type'] = "Turboprop/Turboshaft"

        return returnValue

    #Determine if this is a 3-character code in the 'category-two digit power plant count-power plant type' format:
    if re.match("^[A-Z][0-9][0-9][A-Z]$", description) is not None:

        if description[0].upper() == "A":
            returnValue['category'] = "Amphibian"

        if description[0].upper() == "G":
            returnValue['category'] = "Gyrocopter"

        if description[0].upper() == "H":
            returnValue['category'] = "Helicopter"

        if description[0].upper() == "L":
            returnValue['category'] = "LandPlane"
        
        if description[0].upper() == "S":
            returnValue['category'] = "SeaPlane"

        if description[0].upper() == "T":
            returnValue['category'] = "Tiltrotor"

        if str(description[1:1]).isnumeric():
            returnValue['powerplant']['count'] = int(description[1:1])

        if description[3].upper() == "E":
            returnValue['powerplant']['type'] = "Electric"

        if description[3].upper() == "J":
            returnValue['powerplant']['type'] = "Jet"

        if description[3].upper() == "P":
            returnValue['powerplant']['type'] = "Piston"

        if description[3].upper() == "R":
            returnValue['powerplant']['type'] = "Rocket"

        if description[3].upper() == "T":
            returnValue['powerplant']['type'] = "Turboprop/Turboshaft"

        return returnValue

    logger.warning("Unexpected description format '" + str(description) + "'")
    return None


def decode_wtc(wtc):

    if wtc == "J":
        return "Super"
    
    if wtc == "H":
        return "Heavy"

    if wtc == "M":
        return "Medium"

    if wtc == "L":
        return "Light"

    if wtc == "M/L":
        return "Medium/Light"

    if wtc == "-":
        return "Unknown/None"

    logger.warning("Unknown wake turbulence code '" + str(wtc) + "'")

    return "Unknown"


def export_aircraft():

    import_sql.row_factory = sqlite3.Row
    aircraftCur = import_sql.cursor()

    logger.info("Querying aircraft data from SQLite.")

    with yaspin(text="Querying aircraft data from SQLite...") as spinner:

        aircraftCur.execute("SELECT aircraft.icao_hex, aircraft.registration, aircraft.type_designator, aircraft.military, \
                                types.manufacturer_model, types.powerplant, types.category, types.wake_turbulence_category \
                            FROM aircraft \
                            LEFT JOIN types on aircraft.type_designator = types.type_designator")

        arrayAircraft = aircraftCur.fetchall()

        spinner.stop()

    logger.info("SQLite returned " + str(len(arrayAircraft)) + " rows of aircraft data.")

    registrationsDb = mysql.connector.connect(
        host=settings['mySQL']['uri'],
        user=settings['mySQL']['username'],
        password=settings['mySQL']['password'],
        database=settings['mySQL']['database'])

    logger.info("Creating temp table in MySQL.")

    mysqlCur = registrationsDb.cursor()

    #Ensure the source exists
    mysqlCur.execute("INSERT INTO sources (agency) \
                        SELECT * FROM (SELECT 'Mictronics-IndexedDB') AS tmp \
                        WHERE NOT EXISTS ( \
                            SELECT agency FROM sources WHERE agency = 'Mictronics-IndexedDB' \
                        ) LIMIT 1;")
    
    mysqlCur.execute("CREATE TEMPORARY TABLE import (icao_hex char(6) NOT NULL, registration varchar(20) NOT NULL, data json NULL, hash char(32) NOT NULL, KEY icao_hex (icao_hex), KEY hash (hash));")
     
    logger.info("Exporting simple registration data to MySQL.")

    sqlInsert = "INSERT INTO import (icao_hex, registration, data, hash) VALUES (%s,%s,%s,%s)"

    with Bar("Exporting Simple Registration Data to MySQL...", max=len(arrayAircraft)) as bar:

        for aircraft in arrayAircraft:

            objCompleted = {}
          
            objCompleted['icao_hex'] = aircraft['icao_hex']
            objCompleted['registration'] = aircraft['registration']
            objCompleted['military'] = bool(aircraft['military'])

            if aircraft['type_designator'] is not None:
                objCompleted['type_designator'] = aircraft['type_designator']

            if aircraft['manufacturer_model'] is not None:
                objCompleted['manufacturer_model'] = aircraft['manufacturer_model']

            if aircraft['powerplant'] is not None:
                objCompleted['powerplant'] = json.loads(aircraft['powerplant'])

            if aircraft['category'] is not None:
                objCompleted['category'] = aircraft['category']

            if aircraft['wake_turbulence_category'] is not None:
                objCompleted['wake_turbulence_category'] = aircraft['wake_turbulence_category']

            mysqlCur.execute(sqlInsert, (objCompleted['icao_hex'], objCompleted['registration'], json.dumps(objCompleted), hashlib.md5(json.dumps(objCompleted).encode('utf-8')).hexdigest(), ))

            #Increment the bar
            bar.next()

        bar.finish()

    logger.info("Committing simple registration import data to MySQL.")

    with yaspin(text="Committing simple registration import data to MySQL...") as spinner:
        registrationsDb.commit()

        spinner.text = "Committed " + str(mysqlCur.rowcount) + " rows of aircraft import data to MySQL.\n"
        spinner.ok()

    logger.info("Committed " + str(mysqlCur.rowcount) + " rows of aircraft import data to MySQL.")

    #Delete registrations that don't exist in the import
    logger.info("Deleting deregistered simple registrations.")

    with yaspin(text="Deleting deregistered simple registrations...") as spinner:

        mysqlCur.execute("UPDATE simple, \
                            (SELECT simple.unique_id FROM simple \
                            LEFT OUTER JOIN import ON simple.icao_hex = import.icao_hex \
                            INNER JOIN sources ON simple.source = sources.unique_id \
                            WHERE import.icao_hex IS NULL AND simple.deleted IS NULL AND sources.agency = 'Mictronics-IndexedDB') as d \
                        SET simple.deleted = CURRENT_TIMESTAMP \
                        WHERE simple.unique_id = d.unique_id;")

        logger.info("Committing deletion of deregistered simple registrations to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Marked " + str(mysqlCur.rowcount) + " missing simple registrations as deleted.\n"
        spinner.ok("")

    logger.info("Marked " + str(mysqlCur.rowcount) + " missing registrations as deleted.")

    #Delete registrations if we have a new record coming in where the hashes don't match
    logger.info("Deleting obsolete simple registrations.")

    with yaspin(text="Deleting obsolete simple registrations...") as spinner:

        mysqlCur.execute("UPDATE simple, \
                            (SELECT simple.unique_id FROM simple \
                                INNER JOIN import ON import.icao_hex = simple.icao_hex and import.hash <> simple.hash \
                                INNER JOIN sources ON simple.source = sources.unique_id \
                                WHERE simple.deleted IS NULL AND sources.agency = 'Mictronics-IndexedDB') AS d \
                        SET simple.deleted = CURRENT_TIMESTAMP \
                        WHERE simple.unique_id = d.unique_id ;")

        logger.info("Committing deletion of obsolete simple registrations to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Marked " + str(mysqlCur.rowcount) + " obsolete simple registrations as deleted.\n"
        spinner.ok("")

    logger.info("Marked " + str(mysqlCur.rowcount) + " obsolete simple registrations as deleted.")

    # Create new registrations and mark deleted registrations with a matching has as undeleted
    logger.info("Creating new simple registrations.")

    with yaspin(text="Creating new simple registrations...") as spinner:

        mysqlCur.execute("INSERT INTO simple (icao_hex, registration, data,  hash, source) \
                            (SELECT import.icao_hex, import.registration, import.data,  import.hash, sources.unique_id FROM import \
                            LEFT OUTER JOIN simple on import.icao_hex = simple.icao_hex \
                            LEFT OUTER JOIN sources ON sources.agency = 'Mictronics-IndexedDB') ON DUPLICATE KEY UPDATE deleted = NULL;")

        logger.info("Committing new simple registrations to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Created " + str(mysqlCur.rowcount) + " new simple registrations.\n"
        spinner.ok("")

    logger.info("Created " + str(mysqlCur.rowcount) + " new simple registrations.")
    
    mysqlCur.close()
    registrationsDb.close()


def export_operators():

    import_sql.row_factory = sqlite3.Row
    operatorCur = import_sql.cursor()

    logger.info("Querying operator data from SQLite.")

    with yaspin(text="Querying operator data from SQLite...") as spinner:

        operatorCur.execute("SELECT airline_designator, name, country, callsign FROM operators;")

        arrayOperators = operatorCur.fetchall()

        spinner.stop()

    logger.info("SQLite returned " + str(len(arrayOperators)) + " rows of operator data.")

    registrationsDb = mysql.connector.connect(
        host=settings['mySQL']['uri'],
        user=settings['mySQL']['username'],
        password=settings['mySQL']['password'],
        database=settings['mySQL']['database'])

    logger.info("Creating temp table in MySQL.")

    mysqlCur = registrationsDb.cursor()

    #Ensure the source exists
    mysqlCur.execute("INSERT INTO sources (agency) \
                        SELECT * FROM (SELECT 'Mictronics-IndexedDB') AS tmp \
                        WHERE NOT EXISTS ( \
                            SELECT agency FROM sources WHERE agency = 'Mictronics-IndexedDB' \
                        ) LIMIT 1;")
    
    mysqlCur.execute("CREATE TEMPORARY TABLE import_operators (airline_designator varchar(10) NOT NULL, name varchar(255) NOT NULL, callsign varchar(45) NOT NULL, country varchar(45) NOT NULL, hash char(32) NOT NULL, KEY airline_designator (airline_designator), KEY hash (hash));")
     
    logger.info("Exporting simple registration data to MySQL.")

    sqlInsert = "INSERT INTO import_operators (airline_designator, name, callsign, country, hash) VALUES (%s,%s,%s,%s,%s)"

    with Bar("Exporting Operator Data to MySQL...", max=len(arrayOperators)) as bar:

        for operator in arrayOperators:

            objCompleted = {}

            objCompleted['airline_designator'] = operator['airline_designator']
            objCompleted['name'] = operator['name']
            objCompleted['callsign'] = operator['callsign']
            objCompleted['country'] = operator['country']
            objCompleted['source'] = "Mictronics-IndexedDB"
            
            mysqlCur.execute(sqlInsert, (objCompleted['airline_designator'], objCompleted['name'], objCompleted['callsign'], objCompleted['country'], hashlib.md5(json.dumps(objCompleted).encode('utf-8')).hexdigest(), ))

            #Increment the bar
            bar.next()

    bar.finish()

    logger.info("Committing operator import data to MySQL.")

    with yaspin(text="Committing operator import data to MySQL...") as spinner:
        registrationsDb.commit()

        spinner.text = "Committed " + str(mysqlCur.rowcount) + " rows of operator data to MySQL.\n"
        spinner.ok()

    logger.info("Committed " + str(mysqlCur.rowcount) + " rows of operator data to MySQL.")

    #Delete operators that don't exist in the import (Mictronics deleted the previously imported record from the database)
    logger.info("Deleting deregistered operators.")

    with yaspin(text="Deleting deregistered operators...") as spinner:

        mysqlCur.execute("UPDATE operators, \
                    (SELECT operators.unique_id FROM operators \
                    LEFT OUTER JOIN import_operators ON operators.airline_designator = import_operators.airline_designator \
                    INNER JOIN sources ON sources.unique_id = operators.source \
                    WHERE import_operators.airline_designator IS NULL AND operators.deleted IS NULL AND sources.agency = 'Mictronics-IndexedDB') as d \
                SET operators.deleted = CURRENT_TIMESTAMP \
                WHERE operators.unique_id = d.unique_id;")

        logger.info("Committing deletion of deregistered operators to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Marked " + str(mysqlCur.rowcount) + " missing opeators as deleted.\n"
        spinner.ok("")

    logger.info("Marked " + str(mysqlCur.rowcount) + " missing operators as deleted.")


    #Mark any active operators as deleted if the hash does not match (Mictronics updated the database)
    logger.info("Deleting obsolete operators.")

    with yaspin(text="Deleting obsolete operators...") as spinner:

        mysqlCur.execute("UPDATE operators, ( \
                            SELECT operators.unique_id FROM operators \
                                    INNER JOIN import_operators ON import_operators.airline_designator = operators.airline_designator and import_operators.hash <> operators.hash \
                                    INNER JOIN sources ON sources.unique_id = operators.source  \
                                    WHERE operators.deleted IS NULL AND sources.agency = 'Mictronics-IndexedDB') \
                                    AS d \
                            SET operators.deleted = CURRENT_TIMESTAMP \
                            WHERE operators.unique_id = d.unique_id ;")

        logger.info("Committing deletion of obsolete operators to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Marked " + str(mysqlCur.rowcount) + " obsolete operators as deleted.\n"
        spinner.ok("")

    logger.info("Marked " + str(mysqlCur.rowcount) + " obsolete operators as deleted.")



    #Mark any active operators as deleted if they exist in this import but did not originate from this import (Mictronics will replace the existing record)
    logger.info("Deleting conflicting other source operators.")

    with yaspin(text="Deleting conflicting other source operators...") as spinner:

        mysqlCur.execute("UPDATE operators, ( \
                            SELECT operators.unique_id FROM operators \
                                    INNER JOIN import_operators ON import_operators.airline_designator = operators.airline_designator \
                                    INNER JOIN sources ON sources.unique_id = operators.source \
                                    WHERE operators.deleted IS NULL AND sources.agency <> 'Mictronics-IndexedDB') \
                                    AS d \
                            SET operators.deleted = CURRENT_TIMESTAMP \
                            WHERE operators.unique_id = d.unique_id ;")

        logger.info("Committing Deleting conflicting other source operators to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Marked " + str(mysqlCur.rowcount) + " conflicting other source operators as deleted.\n"
        spinner.ok("")

    logger.info("Marked " + str(mysqlCur.rowcount) + " conflicting other source operators as deleted.")


    # Create new operators and mark deleted operators with a matching has as undeleted
    logger.info("Creating operators.")

    with yaspin(text="Creating new operators...") as spinner:

        mysqlCur.execute("INSERT INTO operators (airline_designator, name, callsign, country, hash, source) \
                            (SELECT import_operators.airline_designator, import_operators.name, import_operators.callsign, import_operators.country, import_operators.hash, \
                                (SELECT unique_id FROM sources WHERE sources.agency = 'Mictronics-IndexedDB') as source \
                                FROM import_operators \
                            LEFT OUTER JOIN operators on import_operators.airline_designator = operators.airline_designator) ON DUPLICATE KEY UPDATE deleted = NULL;")

        logger.info("Committing new operators to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Created " + str(mysqlCur.rowcount) + " new operators.\n"
        spinner.ok("")

    logger.info("Created " + str(mysqlCur.rowcount) + " new operators.")
    
    mysqlCur.close()
    registrationsDb.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Imports Mictronic\'s IndexedDB, containing a registry of global registration information')
    parser.add_argument(dest='download_url', metavar="download_url", help='URL of Mictronic\'s IndexedDB (https://www.mictronics.de/aircraft-database/indexedDB.php).')

    args = parser.parse_args()

    #Setup the configuration required
    setup(args)

    main()