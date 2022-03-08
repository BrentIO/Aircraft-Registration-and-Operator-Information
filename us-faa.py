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

# Supports extracts 2017 and later.  Prior to 2017 the FAA had different column positions.
# https://registry.faa.gov/database/ReleasableAircraft.zip


def setup(args):
    global logger
    global applicationName
    global settings
    global import_sql

    settings = {}

    try:

        filePath = os.path.dirname(os.path.realpath(__file__)) + "/"

        applicationName = "FAA Registration Manager"

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
            raise Exception("The database information (mySQL) is not populated in the settings.json file.")

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
            databaseFile = os.path.join(filePath, "us-faa-registration.db")

            if os.path.exists(databaseFile):
                
                #Delete the old database
                os.remove(databaseFile)

            if os.path.exists(os.path.join(filePath, "us-faa-registration.db-journal")):

                #Delete the old database journal
                os.remove(os.path.join(filePath, "us-faa-registration.db-journal"))

            import_sql = sqlite3.connect(os.path.join(filePath, "us-faa-registration.db"))
        
        cursor = import_sql.cursor()

        #Create the temporary tables in memory
        cursor.execute("CREATE TABLE aircraft (code text, manufacturer text, model text, aircraft_type text, engine_type text, category text, builder_certification text, engine_count int, seat_count int, weight text, speed int)")
        cursor.execute("CREATE TABLE engines (code text, manufacturer text, model text, engine_type text, power_value int, power_type text)")
        cursor.execute("CREATE TABLE registrations (registration text, serial_number text, code_aircraft text, code_engine text, manufactured_year text, registrant_type text, name text, street list, city text, state text, postal_code text, region text, country text, last_action text, certificate_issue text, certification text, operations text, aircraft_type text, engine_type text, status text, icao24_octal text, fractional_ownership text, airworthiness_date text, expiration_date text, kit_manufacturer text, kit_model text, icao24_hex text)")   
    
    except Exception as ex:
        logger.error(ex)
        print(ex)
        exitApp(1)

def main():

    try:

        #Get the files
        if settings['skip_download'] != True:
            download()

        #Import the engine file
        import_engines()

        #Import the aircraft file
        import_aircraft()

        #Import the registrations
        import_registrations()

        #Export the data to disk
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

def totalLines(filename):
    with open(filename) as f:
        return (sum(1 for line in f)) - 1

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

    #Get the file from the FAA
    logger.info("Beginning file download from FAA.  File: " + settings['download_url'])

    with yaspin(text="Downloading file from FAA...") as spinner:
        response = requests.get(settings['download_url'])

        spinner.text = "Completed file download from FAA.\n"
        spinner.ok()
   
    if response.status_code != 200:
        raise Exception("Response code from download was " + str(response.status_code) + ".")

    #Write the file to disk
    with open(downloadFileDestination, 'wb') as downloadedFile:
        downloadedFile.write(response.content)

    logger.info("Completed file download from FAA.")

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

    #Rename the files to be lower case, since the FAA is sometimes inconsistent
    for extractedFile in os.listdir(settings['tempPath']):
        os.rename(os.path.join(settings['tempPath'], extractedFile), os.path.join(settings['tempPath'], extractedFile.lower()))

    #Rename the files to not have duplicate extensions, since the FAA is sometimes inconsistent
    for extractedFile in os.listdir(settings['tempPath']):
        if ".txt.txt" in extractedFile:
            os.rename(os.path.join(settings['tempPath'], extractedFile), os.path.join(settings['tempPath'], os.path.splitext(extractedFile)[0]))


def import_engines():

    engineFile = os.path.join(settings['tempPath'], "engine.txt")

    logger.info("Beginning Engine Import.")

    #Make sure the file exists
    if os.path.exists(engineFile) == False:
        raise Exception ("Engine file does not exist.  Expected " + engineFile)

    rowCount = totalLines(engineFile)

    with open(engineFile, "r") as csvfile:
        fileReader = csv.reader(csvfile)

        #Skip the headers
        fileReader.__next__()

        with Bar("Importing Engines...", max=rowCount) as bar:

            for row in fileReader:

                tmpEngine = engine()

                #Import data by address
                tmpEngine.code = str(row[0])
                tmpEngine.manufacturer = str(row[1]).strip()
                tmpEngine.model = str(row[2]).strip()
                tmpEngine.set_engine_type(str(row[3]).strip())
                tmpEngine.set_power(int(row[4]), int(row[5]))

                #Store it in the DB
                tmpEngine.commit()

                #Increment the bar
                bar.next()

            bar.message = "Done Importing Engines."

        bar.finish()

        logger.info("Completed Engine Import, total row count " + str(rowCount) + ".")

def import_aircraft():
    
    aircraftFile = os.path.join(settings['tempPath'], "acftref.txt")

    logger.info("Beginning Aircraft Import.")

    #Make sure the file exists
    if os.path.exists(aircraftFile) == False:
        raise Exception ("Aircraft file does not exist.  Expected " + aircraftFile)

    rowCount = totalLines(aircraftFile)

    with open(aircraftFile, "r") as csvfile:
        fileReader = csv.reader(csvfile)

        #Skip the headers
        fileReader.__next__()

        with Bar("Importing Aircraft...", max=rowCount) as bar:

            for row in fileReader:

                tmpAircraft = aircraft()

                #Import data by address
                tmpAircraft.code = str(row[0]).strip()
                tmpAircraft.manufacturer = str(row[1]).strip()
                tmpAircraft.model = str(row[2]).strip()
                tmpAircraft.set_aircraft_type(str(row[3]).strip())
                tmpAircraft.set_engine_type(str(int(row[4])))
                tmpAircraft.set_category(str(row[5]).strip())
                tmpAircraft.set_builder_certification(str(row[6]).strip())
                tmpAircraft.engine_count = str(int(row[7]))
                tmpAircraft.seat_count = str(int(row[8]))
                tmpAircraft.set_weight(str(row[9]).strip())
                tmpAircraft.speed = int(row[10])

                #Store it in the DB
                tmpAircraft.commit()

                #Increment the bar
                bar.next()

            bar.finish()

        logger.info("Completed Aircraft Import, total row count " + str(rowCount) + ".")

def import_registrations():

    registrationFile = os.path.join(settings['tempPath'], "master.txt")

    logger.info("Beginning Registration Import.")

    #Make sure the file exists
    if os.path.exists(registrationFile) == False:
        raise Exception ("Registration file does not exist.  Expected " + registrationFile)

    rowCount = totalLines(registrationFile)

    with open(registrationFile, "r") as csvfile:
        fileReader = csv.reader(csvfile)

        #Skip the headers
        fileReader.__next__()

        with Bar("Importing Registrations...", max=rowCount) as bar:

            for row in fileReader:

                #Limit the number of registrations if requested in the settings file (dev only)
                if "limit" in settings:
                    if settings['limit'] == True:
                        if bar.index >= 500:
                            bar.finish()
                            break

                tmpRegistration = registration()

                #Import data by address
                tmpRegistration.registration = "N" + str(row[0]).strip()
                tmpRegistration.serial_number = str(row[1]).strip()
                tmpRegistration.code_aircraft = str(row[2]).strip()
                tmpRegistration.code_engine = str(row[3]).strip()
                tmpRegistration.manufactured_year = str(row[4]).strip()
                tmpRegistration.set_type_registrant(str(row[5]).strip())
                tmpRegistration.set_name(str(row[6]).strip())
                tmpRegistration.set_street(str(row[7]).strip(), str(row[8]).strip())
                tmpRegistration.city = str(row[9]).strip()
                tmpRegistration.state = str(row[10]).strip()
                tmpRegistration.postal_code = str(row[11]).strip()
                tmpRegistration.set_region(str(row[12]).strip())
                tmpRegistration.country = str(row[14]).strip()
                tmpRegistration.last_action = parseYYYYMMDD(str(row[15]).strip())
                tmpRegistration.certificate_issue = parseYYYYMMDD(str(row[16]).strip())
                tmpRegistration.set_certification(str(row[17]).strip())
                tmpRegistration.set_aircraft_type(str(row[18]).strip())
                tmpRegistration.set_engine_type(str(row[19]).strip())
                tmpRegistration.set_status(str(row[20]).strip())
                tmpRegistration.icao24_octal = str(row[21]).strip()
                tmpRegistration.set_fractional_ownership(str(row[22]).strip())
                tmpRegistration.airworthiness_date = parseYYYYMMDD(str(row[23]).strip())
                tmpRegistration.set_name(str(row[24]).strip())
                tmpRegistration.set_name(str(row[25]).strip())
                tmpRegistration.set_name(str(row[26]).strip())
                tmpRegistration.set_name(str(row[27]).strip())
                tmpRegistration.set_name(str(row[28]).strip())
                tmpRegistration.expiration_date = parseYYYYMMDD(str(row[29]).strip())
                tmpRegistration.kit_manufacturer = str(row[31]).strip()
                tmpRegistration.kit_model = str(row[32]).strip()
                tmpRegistration.icao24_hex = str(row[33]).strip()

                #Store it in the DB
                tmpRegistration.commit()

                #Increment the bar
                bar.next()

        bar.finish()

    logger.info("Completed Registration Import, total row count " + str(rowCount) + ".")


def export_data():

    import_sql.row_factory = sqlite3.Row
    sqliteCur = import_sql.cursor()

    logger.info("Querying data from SQLite.")

    with yaspin(text="Querying data from SQLite...") as spinner:

        sqliteCur.execute("SELECT registrations.registration, registrations.serial_number, registrations.manufactured_year, \
                    registrations.registrant_type, registrations.name, registrations.street, registrations.city, \
                    registrations.state, registrations.postal_code, registrations.region, registrations.country, \
                    registrations.last_action, registrations.certificate_issue, registrations.certification, \
                    registrations.operations, registrations.aircraft_type, \
                    registrations.status, \
                    registrations.airworthiness_date, registrations.expiration_date as registration_expiration_date, registrations.kit_manufacturer, \
                    registrations.kit_model, registrations.icao24_hex as icao_hex, \
                    aircraft.manufacturer as aircraft_manufacturer, aircraft.model as aircraft_model, \
                    aircraft.category as aircraft_category, aircraft.builder_certification, \
                    aircraft.engine_count, aircraft.seat_count as seats, aircraft.weight, aircraft.speed, \
                    engines.manufacturer as engine_manufacturer, engines.model as engine_model, engines.engine_type as engine_type, \
                    engines.power_value as power_value, engines.power_type as power_type \
                    FROM registrations LEFT JOIN aircraft ON registrations.code_aircraft = aircraft.code \
                    LEFT JOIN engines ON registrations.code_engine = engines.code")
        rows = sqliteCur.fetchall()

        spinner.stop()

    logger.info("SQLite returned " + str(len(rows)) + " rows of data.")

    registrationsDb = mysql.connector.connect(
        host=settings['mySQL']['uri'],
        user=settings['mySQL']['username'],
        password=settings['mySQL']['password'],
        database=settings['mySQL']['database'])

    mysqlCur = registrationsDb.cursor()

    #Ensure the source exists
    mysqlCur.execute("INSERT INTO sources (agency) \
                        SELECT * FROM (SELECT 'US-FAA') AS tmp \
                        WHERE NOT EXISTS ( \
                            SELECT agency FROM sources WHERE agency = 'US-FAA' \
                        ) LIMIT 1;")

    logger.info("Creating temp table in MySQL.")

    mysqlCur.execute("CREATE TEMPORARY TABLE import (icao_hex char(6) NOT NULL, registration varchar(8) NOT NULL, data json NULL, hash char(32) NOT NULL, KEY icao_hex (icao_hex), KEY hash (hash));")
 
    logger.info("Exporting data to MySQL.")

    sqlInsert = "INSERT INTO import (icao_hex, registration, data, hash) VALUES (%s,%s,%s,%s)"

    with Bar("Exporting Data to MySQL...", max=len(rows)) as bar:

        for row in rows:
            objCompleted = {}
            objCompleted['icao_hex'] = row['icao_hex']
            objCompleted['registration'] = row['registration']
            objCompleted['serial_number'] = row['serial_number']
            objCompleted['manufactured_year'] = row['manufactured_year']
            objCompleted['airworthiness_date'] = row['airworthiness_date']
            objCompleted['registration_expiration_date'] = row['registration_expiration_date']
            objCompleted['registrant_type'] = row['registrant_type']
            objCompleted['name'] = json.loads(row['name'])
            objCompleted['street'] = json.loads(row['street'])
            objCompleted['city'] = row['city']
            objCompleted['state'] = row['state']
            objCompleted['postal_code'] = row['postal_code']
            objCompleted['region'] = row['region']
            objCompleted['country'] = row['country']
            objCompleted['last_action'] = row['last_action']
            objCompleted['certificate_issue'] = row['certificate_issue']
            objCompleted['certification'] = json.loads(row['certification'])
            objCompleted['operations'] = json.loads(row['operations'])
            objCompleted['status'] = row['status']            
            objCompleted['aircraft'] = {}
            objCompleted['aircraft']['manufacturer'] = row['aircraft_manufacturer']
            objCompleted['aircraft']['model'] = row['aircraft_model']
            objCompleted['aircraft']['type'] = row['aircraft_type']
            objCompleted['aircraft']['category'] = row['aircraft_category']
            objCompleted['aircraft']['builder_certification'] = row['builder_certification']
            objCompleted['aircraft']['seats'] = row['seats']
            objCompleted['aircraft']['weight'] = row['weight']
            if row['kit_manufacturer'] != "":
                objCompleted['aircraft']['kit_manufacturer'] = row['kit_manufacturer']
            if row['kit_model'] != "":
                objCompleted['aircraft']['kit_model'] = row['kit_model']
            objCompleted['powerplant'] = {}
            if row['engine_manufacturer']:
                objCompleted['powerplant']['manufacturer'] = row['engine_manufacturer']
            if row['engine_model']:
                objCompleted['powerplant']['model'] = row['engine_model']
            if row['power_value']:
                objCompleted['powerplant']['power_value'] = row['power_value']
            if row['power_type']:
                objCompleted['powerplant']['power_type'] = row['power_type']
            if row['engine_count']:
                objCompleted['powerplant']['count'] = row['engine_count']
            if row['engine_type']:
                objCompleted['powerplant']['type'] = row['engine_type']

            if objCompleted['certification'] == []:
                del objCompleted['certification']

            if objCompleted['operations'] == []:
                del objCompleted['operations']

            if objCompleted['aircraft'] == {}:
                del objCompleted['aircraft']
            
            if objCompleted['powerplant'] == {}:
                del objCompleted['powerplant']
            
            mysqlCur.execute(sqlInsert, (objCompleted['icao_hex'], objCompleted['registration'], json.dumps(objCompleted), hashlib.md5(json.dumps(objCompleted).encode('utf-8')).hexdigest(), ))

            #Increment the bar
            bar.next()

        bar.finish()

    logger.info("Committing import data to MySQL.")

    with yaspin(text="Committing import data to MySQL...") as spinner:
        registrationsDb.commit()

        spinner.text = "Committed " + str(mysqlCur.rowcount) + " rows of import data to MySQL.\n"
        spinner.ok()

    logger.info("Committed " + str(mysqlCur.rowcount) + " rows of import data to MySQL.")

    #Delete registrations that don't exist in the import
    logger.info("Deleting deregistered registrations.")

    with yaspin(text="Deleting deregistered registrations...") as spinner:

        mysqlCur.execute("UPDATE registrations, \
                            (SELECT registrations.unique_id FROM registrations \
                            LEFT OUTER JOIN import ON registrations.icao_hex = import.icao_hex \
                            INNER JOIN sources ON registrations.source = sources.unique_id \
                            WHERE import.icao_hex IS NULL AND registrations.deleted IS NULL AND sources.agency = 'US-FAA') as d \
                        SET registrations.deleted = CURRENT_TIMESTAMP \
                        WHERE registrations.unique_id = d.unique_id;")

        logger.info("Committing deletion of deregistered registrations to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Marked " + str(mysqlCur.rowcount) + " missing registrations as deleted.\n"
        spinner.ok("")

    logger.info("Marked " + str(mysqlCur.rowcount) + " missing registrations as deleted.")

    #Delete registrations if we have a new record coming in where the hashes don't match
    logger.info("Deleting obsolete registrations.")

    with yaspin(text="Deleting obsolete registrations...") as spinner:

        mysqlCur.execute("UPDATE registrations, \
                            (SELECT registrations.unique_id FROM registrations \
                                INNER JOIN import ON import.icao_hex = registrations.icao_hex and import.hash <> registrations.hash \
                                INNER JOIN sources ON registrations.source = sources.unique_id \
                                WHERE registrations.deleted IS NULL AND sources.agency = 'US-FAA') AS d \
                        SET registrations.deleted = CURRENT_TIMESTAMP \
                        WHERE registrations.unique_id = d.unique_id ;")

        logger.info("Committing deletion of obsolete registrations to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Marked " + str(mysqlCur.rowcount) + " obsolete registrations as deleted.\n"
        spinner.ok("")

    logger.info("Marked " + str(mysqlCur.rowcount) + " obsolete registrations as deleted.")

    # Create new registrations and mark deleted registrations with a matching has as undeleted
    logger.info("Creating new registrations.")

    with yaspin(text="Creating new registrations...") as spinner:

        mysqlCur.execute("INSERT INTO registrations (icao_hex, registration, data,  hash, source) \
                            (SELECT import.icao_hex, import.registration, import.data,  import.hash, sources.unique_id FROM import \
                            LEFT OUTER JOIN registrations on import.icao_hex = registrations.icao_hex \
                            LEFT OUTER JOIN sources ON sources.agency = 'US-FAA') ON DUPLICATE KEY UPDATE deleted = NULL;")

        logger.info("Committing new registrations to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Created " + str(mysqlCur.rowcount) + " new registrations.\n"
        spinner.ok("")

    logger.info("Created " + str(mysqlCur.rowcount) + " new registrations.")
    
    mysqlCur.close()
    registrationsDb.close()


def parseYYYYMMDD(value):

    if value == "":
        return ""

    return datetime.strptime(value, '%Y%m%d').strftime('%Y-%m-%d')

class registration():

    def __init__(self):
        self.registration = ""
        self.serial_number = ""
        self.code_aircraft = ""
        self.code_engine = ""
        self.manufactured_year = ""
        self.registrant_type = ""
        self.name = []
        self.street = []
        self.city = ""
        self.state = ""
        self.postal_code = ""
        self.region = ""
        self.country = ""
        self.last_action = ""
        self.certificate_issue = ""
        self.certification = []
        self.operations = []
        self.aircraft_type = ""
        self.engine_type = ""
        self.status = ""
        self.icao24_octal = ""
        self.fractional_ownership = False
        self.airworthiness_date = ""
        self.expiration_date = ""
        self.kit_manufacturer = ""
        self.kit_model = ""
        self.icao24_hex = ""

    def set_name(self, value):

        if len(value) > 0:
            self.name.append(value)

    def set_type_registrant(self, value):

        if value == "1":
            self.registrant_type = "Individual"
            return

        if value == "2":
            self.registrant_type = "Partnership"
            return

        if value == "3":
            self.registrant_type = "Corporation"
            return

        if value == "4":
            self.registrant_type = "Co-Owned"
            return

        if value == "5":
            self.registrant_type = "Government"
            return

        if value == "7":
            self.registrant_type = "LLC"
            return

        if value == "8":
            self.registrant_type = "Non-Citizen Corporation"
            return

        if value == "9":
            self.registrant_type = "Non-Citizen Co-Owned"
            return

        if value == "":
            self.registrant_type = "None"
            return

        self.registrant_type = "Unknown"
        logger.warning("Unknown registrant type provided: " + value + " " + str(self.toDict()))
        return

    def set_street(self, street1, street2):

        if street1 != "":
            self.street.append(street1)

        if street2 != "":
            self.street.append(street2)

    def set_region(self, value):

        if value == "1":
            self.region = "Eastern"
            return

        if value == "2":
            self.region = "Southwestern"
            return

        if value == "3":
            self.region = "Central"
            return

        if value == "4":
            self.region = "Western-Pacific"
            return

        if value == "5":
            self.region = "Alaskan"
            return

        if value == "7":
            self.region = "Southern"
            return

        if value == "8":
            self.region = "European"
            return

        if value == "C":
            self.region = "Great Lakes"
            return

        if value == "E":
            self.region = "New England"
            return
        
        if value == "S":
            self.region = "Northwest Mountain"
            return

        if value == "":
            self.region = "None"
            return

        self.region = "Unknown"
        logger.warning("Unknown region type provided: " + value + " " + str(self.toDict()))
        return
    
    def set_certification(self, value):

        value = str(value).upper()

        if value == "":
            self.certification.append("None")
            return

        #Set the airworthiness
        if value[0] == "0":
            self.certification.append("Unknown")
            return

        if value[0] == "1":
            self.certification.append("Standard")
            self.operations_standard(value)
            return

        if value[0] == "2":
            self.certification.append("Limited")
            self.operations_limited(value)
            return

        if value[0] == "3":
            self.certification.append("Restricted")
            self.operations_restricted(value)
            return

        if value[0] == "4":
            self.certification.append("Experimental")
            self.operations_experimental(value)
            return

        if value[0] == "5":
            self.certification.append("Provisional")
            self.operations_provisional(value)
            return

        if value[0] == "6":
            self.operations_multiple(value)
            return

        if value[0] == "7":
            self.certification.append("Primary")
            self.operations_primary(value)
            return

        if value[0] == "8":
            self.certification.append("Special Flight Permit")
            self.operations_sfp(value)
            return

        if value[0] == "9":
            self.certification.append("Light Sport")
            self.operations_ls(value)
            return

        self.certification.append("Unknown")
        logger.warning("Unknown certification type provided: " + value + " " + str(self.toDict()))

    def operations_standard(self, value):

        if len(value) < 2:
            return

        for entry in value[1:]:

            if entry == "N":
                self.operations.append("Normal")
                continue

            if entry == "U":
                self.operations.append("Utility")
                continue

            if entry == "A":
                self.operations.append("Acrobatic")
                continue

            if entry == "T":
                self.operations.append("Transport")
                continue

            if entry == "G":
                self.operations.append("Glider")
                continue

            if entry == "B":
                self.operations.append("Balloon")
                continue

            if entry == "C":
                self.operations.append("Commuter")
                continue

            if entry == "O":
                self.operations.append("Other")
                continue

            logger.warning("Standard airworthiness type has an unknown operation provided: " + entry + " " + str(self.toDict()))

    def operations_limited(self, value):

        if len(value) < 2:
            return
        
        logger.warning("Limited airworthiness type has an unknown operation provided: " + value + " " + str(self.toDict()))

    def operations_restricted(self, value):
        
        if len(value) < 2:
            return

        for entry in value[1:]:

            if entry == "0":
                self.operations.append("Other")
                continue

            if entry == "1":
                self.operations.append("Agriculture and Pest Control")
                continue

            if entry == "2":
                self.operations.append("Aerial Surveying")
                continue

            if entry == "3":
                self.operations.append("Aerial Advertising")
                continue

            if entry == "4":
                self.operations.append("Forest")
                continue

            if entry == "5":
                self.operations.append("Patrolling")
                continue

            if entry == "6":
                self.operations.append("Weather Control")
                continue

            if entry == "7":
                self.operations.append("Carriage of Cargo")
                continue

            logger.warning("Restricted airworthiness type has an unknown operation provided: " + value + " " + str(self.toDict()))

    def operations_experimental(self, value):

        if len(value) < 2:
            return

        prior_entry = 0

        for entry in value[1:]:

            if entry == "0":
                prior_entry = 0
                self.operations.append("To show compliance with FAR")
                continue

            if entry == "1":
                prior_entry = 0
                self.operations.append("Research and Development")
                continue

            if entry == "2":
                prior_entry = 0
                self.operations.append("Amateur Built")
                continue

            if entry == "3":
                prior_entry = 0
                self.operations.append("Exhibition")
                continue

            if entry == "4":
                prior_entry = 0
                self.operations.append("Racing")
                continue

            if entry == "5":
                prior_entry = 0
                self.operations.append("Crew Training")
                continue

            if entry == "6":
                prior_entry = 0
                self.operations.append("Market Survey")
                continue

            if entry == "7":
                prior_entry = 0
                self.operations.append("Operating Kit Built Aircraft")
                continue

            if entry == "8":
                prior_entry = 8
                continue

            if prior_entry == 8 and entry == "A":
                prior_entry = 0
                self.operations.append("Reg. Prior to 01/31/08")
                continue

            if prior_entry == 8 and entry == "B":
                prior_entry = 0
                self.operations.append("Operating Light-Sport Kit-Built")
                continue

            if prior_entry == 8 and entry == "C":
                prior_entry = 0
                self.operations.append("Operating Light-Sport Previously issued cert under 21.190")
                continue

            if entry == "9":
                prior_entry = 9
                continue

            if prior_entry == 9 and entry == "A":
                prior_entry = 0
                self.operations.append("Unmanned Aircraft - Research and Development")
                continue

            if prior_entry == 9 and entry == "B":
                prior_entry = 0
                self.operations.append("Unmanned Aircraft - Market Survey")
                continue

            if prior_entry == 9 and entry == "C":
                prior_entry = 0
                self.operations.append("Unmanned Aircraft - Crew Training")
                continue

            if prior_entry == 9 and entry == "D":
                prior_entry = 0
                self.operations.append("Unmanned Aircraft - Exhibition")
                continue

            if prior_entry == 9 and entry == "E":
                prior_entry = 0
                self.operations.append("Unmanned Aircraft - Compliance with CFR")
                continue

            logger.warning("Experimental airworthiness type has an unknown operation provided: " + value + " " + str(self.toDict()))
        
    def operations_provisional(self, value):
        
        if len(value) < 2:
            return

        for entry in value[1:]:

            if entry == "1":
                self.operations.append("Class I")
                continue

            if entry == "2":
                self.operations.append("Class II")
                continue

            logger.warning("Provisional airworthiness type has an unknown operation provided: " + entry + " " + str(self.toDict()))

    def operations_multiple(self, value):

        #Handle the multiple certification types
        for entry in value[1:3]:

            if entry == "1":
                self.certification.append("Standard")
                continue

            if entry == "2":
                self.certification.append("Limited")
                continue

            if entry == "3":
                self.certification.append("Restricted")
                continue

            logger.warning("Multiple certifications has an unknown certification provided: " + entry + " " + str(self.toDict()))

        #Handle the operation types
        for entry in value[4:]:

            if entry == "0":
                self.operations.append("Other")
                continue

            if entry == "1":
                self.operations.append("Agriculture and Pest Control")
                continue

            if entry == "2":
                self.operations.append("Aerial Surveying")
                continue

            if entry == "3":
                self.operations.append("Aerial Advertising")
                continue

            if entry == "4":
                self.operations.append("Forest")
                continue

            if entry == "5":
                self.operations.append("Patrolling")
                continue

            if entry == "6":
                self.operations.append("Weather Control")
                continue

            if entry == "7":
                self.operations.append("Carriage of Cargo")
                continue

            logger.warning("Multiple airworthiness type has an unknown operation provided: " + value + " " + str(self.toDict()))

    def operations_primary(self, value):
        
        if len(value) > 1:
            logger.warning("Primary airworthiness type has an unknown operation provided: " + value + " " + str(self.toDict()))

    def operations_sfp(self, value):
        
        if len(value) < 2:
            return

        for entry in value[1:]:

            if entry == "1":
                self.operations.append("Ferry flight for repairs, alterations, maintenance or storage")
                continue

            if entry == "2":
                self.operations.append("Evacuate from area of impending danger")
                continue

            if entry == "3":
                self.operations.append("Operation in excess of maximum certificated")
                continue

            if entry == "4":
                self.operations.append("Delivery or export")
                continue

            if entry == "5":
                self.operations.append("Production flight testing")
                continue

            if entry == "6":
                self.operations.append("Customer Demo")
                continue

            logger.warning("Special Flight Permit airworthiness type has an unknown operation provided: " + entry + " " + str(self.toDict()))

    def operations_ls(self, value):

        if len(value) < 2:
            return

        for entry in value[1:]:

            if entry == "A":
                self.operations.append("Airplane")
                continue

            if entry == "G":
                self.operations.append("Glider")
                continue

            if entry == "L":
                self.operations.append("Lighter than Air")
                continue

            if entry == "P":
                self.operations.append("Power-Parachute")
                continue

            if entry == "W":
                self.operations.append("Weight-Shift-Control")
                continue         

            logger.warning("Light Sport airworthiness type has an unknown operation provided: " + entry + " " + str(self.toDict()))

    def set_aircraft_type(self, value):
        
        if value == "1":
            self.aircraft_type = "Glider"
            return

        if value == "2":
            self.aircraft_type = "Balloon"
            return

        if value == "3":
            self.aircraft_type = "Blimp/Dirigible"
            return

        if value == "4":
            self.aircraft_type = "Fixed wing single engine"
            return

        if value == "5":
            self.aircraft_type = "Fixed wing multi engine"
            return

        if value == "6":
            self.aircraft_type = "Rotorcraft"
            return

        if value == "7":
            self.aircraft_type = "Weight-shift-control"
            return

        if value == "8":
            self.aircraft_type = "Powered Parachute"
            return

        if value == "9":
            self.aircraft_type = "Gyroplane"
            return

        if value == "H":
            self.aircraft_type = "Hybrid Lift"
            return

        if value == "O":
            self.aircraft_type = "Other"
            return

        self.aircraft_type = "Unknown"
        logger.warning("Unknown aircarft type provided: " + value + " " + str(self.toDict()))
        return

    def set_engine_type(self, value):

        if value == "0":
            self.engine_type = "None"
            return
        
        if value == "1":
            self.engine_type = "Reciprocating"
            return

        if value == "2":
            self.engine_type = "Turbo-prop"
            return

        if value == "3":
            self.engine_type = "Turbo-shaft"
            return
        
        if value == "4":
            self.engine_type = "Turbo-jet"
            return

        if value == "5":
            self.engine_type = "Turbo-fan"
            return

        if value == "6":
            self.engine_type = "Ramjet"
            return

        if value == "7":
            self.engine_type = "2 Cycle"
            return

        if value == "8":
            self.engine_type = "4 Cycle"
            return

        if value == "9":
            self.engine_type = "Unknown"
            return

        if value == "10":
            self.engine_type = "Electric"
            return

        if value == "11":
            self.engine_type = "Rotary"
            return

        #Default "Unknown"
        self.engine_type = "Unknown"
        logger.warning("Unknown engine type provided: " + value + " " + str(self.toDict()))
        return

    def set_status(self, value):

        value = str(value).upper()

        if value == "A":
            self.status = "The Triennial Aircraft Registration form was mailed and has not been returned by the Post Office"
            return

        if value == "D":
            self.status = "Expired Dealer"
            return

        if value == "E":
            self.status = "The Certificate of Aircraft Registration was revoked by enforcement action"
            return

        if value == "M":
            self.status = "Valid - Aircraft assigned to the manufacturer under the manufacturer’s Dealer Certificate"
            return

        if value == "N":
            self.status = "Non-citizen Corporations which have not returned their flight hour reports"
            return

        if value == "R":
            self.status = "Registration pending"
            return

        if value == "S":
            self.status = "Second Triennial Aircraft Registration Form has been mailed and has not been returned by the Post Office"
            return

        if value == "T":
            self.status = "Valid Registration from a Trainee"
            return

        if value == "V":
            self.status = "Valid Registration"
            return

        if value == "W":
            self.status = "Certificate of Registration has been deemed Ineffective or Invalid"
            return

        if value == "X":
            self.status = "Enforcement Letter"
            return

        if value == "Z":
            self.status = "Permanent Reserved"
            return

        if value == "1":
            self.status = "Triennial Aircraft Registration form was returned by the Post Office as undeliverable"
            return

        if value == "2":
            self.status = "N-Number Assigned - but has not yet been registered"
            return

        if value == "3":
            self.status = "N-Number assigned as a Non Type Certificated aircraft - but has not yet been registered"
            return

        if value == "4":
            self.status = "N-Number assigned as import - but has not yet been registered"
            return

        if value == "5":
            self.status = "Reserved N-Number"
            return

        if value == "6":
            self.status = "Administratively canceled"
            return

        if value == "7":
            self.status = "Sale reported"
            return

        if value == "8":
            self.status = "A second attempt has been made at mailing a Triennial Aircraft Registration form to the owner with no response"
            return

        if value == "9":
            self.status = "Certificate of Registration has been revoked"
            return

        if value == "10":
            self.status = "N-Number assigned, has not been registered and is pending cancellation"
            return

        if value == "11":
            self.status = "N-Number assigned as a Non Type Certificated (Amateur) but has not been registered that is pending cancellation"
            return

        if value == "12":
            self.status = "N-Number assigned as import but has not been registered that is pending cancellation"
            return

        if value == "13":
            self.status = "Registration Expired"
            return

        if value == "14":
            self.status = "First Notice for Re-Registration/Renewal"
            return

        if value == "15":
            self.status = "Second Notice for Re-Registration/Renewal"
            return

        if value == "16":
            self.status = "Registration Expired - Pending Cancellation"
            return

        if value == "17":
            self.status = "Sale Reported - Pending Cancellation"
            return

        if value == "18":
            self.status = "Sale Reported - Canceled"
            return

        if value == "19":
            self.status = "Registration Pending - Pending Cancellation"
            return

        if value == "20":
            self.status = "Registration Pending - Canceled"
            return

        if value == "21":
            self.status = "Revoked - Pending Cancellation"
            return

        if value == "22":
            self.status = "Revoked - Canceled"
            return

        if value == "23":
            self.status = "Expired Dealer (Pending Cancellation)"
            return

        if value == "24":
            self.status = "Third Notice for Re-Registration/Renewal"
            return

        if value == "25":
            self.status = "First Notice for Registration Renewal"
            return

        if value == "26":
            self.status = "Second Notice for Registration Renewal"
            return

        if value == "27":
            self.status = "Registration Expired"
            return

        if value == "28":
            self.status = "Third Notice for Registration Renewal"
            return

        if value == "29":
            self.status = "Registration Expired - Pending Cancellation"
            return
    
        #Default "Unknown"
        self.status = "Unknown"
        logger.warning("Unknown engine type provided: " + value + " " + str(self.toDict()))
        return

    def set_fractional_ownership(self, value):

        value = str(value).upper()

        if value == "Y":
            self.fractional_ownership = True
    
    def commit(self):
        
        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO registrations (registration, serial_number, code_aircraft, code_engine, manufactured_year, \
                            registrant_type, name, street, city, state, postal_code, region, country, last_action, certificate_issue, \
                            certification, operations, aircraft_type, engine_type, status, icao24_octal, fractional_ownership, airworthiness_date, \
                            expiration_date, kit_manufacturer, kit_model, icao24_hex) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        parameters = (self.registration,
                        self.serial_number,
                        self.code_aircraft,
                        self.code_engine,
                        self.manufactured_year, 
                        self.registrant_type,
                        json.dumps(self.name), 
                        json.dumps(self.street), 
                        self.city, 
                        self.state, 
                        self.postal_code, 
                        self.region, 
                        self.country, 
                        self.last_action,
                        self.certificate_issue,
                        json.dumps(self.certification), 
                        json.dumps(self.operations), 
                        self.aircraft_type, 
                        self.engine_type, 
                        self.status, 
                        self.icao24_octal, 
                        self.fractional_ownership, 
                        self.airworthiness_date, 
                        self.expiration_date, 
                        self.kit_manufacturer, 
                        self.kit_model,
                        self.icao24_hex)

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        #Close the cursor
        dbCursor.close()

        #Destroy itself


    def toDict(self):
        return self.__dict__

class engine():

    def __init__(self):
        self.code = ""
        self.manufacturer = ""
        self.model = ""
        self.engine_type = ""
        self.power_value = ""
        self.power_type = ""


    def set_engine_type(self, value):

        if value == "0":
            self.engine_type = "None"
            return
        
        if value == "1":
            self.engine_type = "Reciprocating"
            return

        if value == "2":
            self.engine_type = "Turbo-prop"
            return

        if value == "3":
            self.engine_type = "Turbo-shaft"
            return
        
        if value == "4":
            self.engine_type = "Turbo-jet"
            return

        if value == "5":
            self.engine_type = "Turbo-fan"
            return

        if value == "6":
            self.engine_type = "Ramjet"
            return

        if value == "7":
            self.engine_type = "2 Cycle"
            return

        if value == "8":
            self.engine_type = "4 Cycle"
            return

        if value == "9":
            self.engine_type = "Unknown"
            return

        if value == "10":
            self.engine_type = "Electric"
            return

        if value == "11":
            self.engine_type = "Rotary"
            return

        #Default "Unknown"
        self.engine_type = "Unknown"
        logger.warning("Unknown engine type provided: " + value + " " + str(self.toDict()))
        return

    def set_power(self, horsepower, thrust):

        if horsepower > 0:
            self.power_type = "Horsepower"
            self.power_value = horsepower
            return

        if thrust > 0:
            self.power_type = "Thrust"
            self.power_value = thrust
            return
    
    def toDict(self):
        return self.__dict__

    def commit(self):

        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO engines (code, manufacturer, model, engine_type, power_value, power_type) VALUES (?,?,?,?,?,?)"
        parameters = (self.code, self.manufacturer, self.model, self.engine_type, self.power_value, self.power_type)

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        #Close the cursor
        dbCursor.close()

class aircraft():

    def __init__(self):
        self.code = ""
        self.manufacturer = ""
        self.model = ""
        self.aircraft_type = ""
        self.engine_type = ""
        self.category = ""
        self.builder_certification = ""
        self.engine_count = ""
        self.seat_count = ""
        self.weight = ""
        self.speed = ""

    def set_aircraft_type(self, value):
        
        if value == "1":
            self.aircraft_type = "Glider"
            return

        if value == "2":
            self.aircraft_type = "Balloon"
            return

        if value == "3":
            self.aircraft_type = "Blimp/Dirigible"
            return

        if value == "4":
            self.aircraft_type = "Fixed wing single engine"
            return

        if value == "5":
            self.aircraft_type = "Fixed wing multi engine"
            return

        if value == "6":
            self.aircraft_type = "Rotorcraft"
            return

        if value == "7":
            self.aircraft_type = "Weight-shift-control"
            return

        if value == "8":
            self.aircraft_type = "Powered Parachute"
            return

        if value == "9":
            self.aircraft_type = "Gyroplane"
            return

        if value == "H":
            self.aircraft_type = "Hybrid Lift"
            return

        if value == "O":
            self.aircraft_type = "Other"
            return

        self.aircraft_type = "Unknown"
        logger.warning("Unknown aircarft type provided: " + value + " " + str(self.toDict()))
        return

    def set_engine_type(self, value):

        if value == "0":
            self.engine_type = "None"
            return
        
        if value == "1":
            self.engine_type = "Reciprocating"
            return

        if value == "2":
            self.engine_type = "Turbo-prop"
            return

        if value == "3":
            self.engine_type = "Turbo-shaft"
            return
        
        if value == "4":
            self.engine_type = "Turbo-jet"
            return

        if value == "5":
            self.engine_type = "Turbo-fan"
            return

        if value == "6":
            self.engine_type = "Ramjet"
            return

        if value == "7":
            self.engine_type = "2 Cycle"
            return

        if value == "8":
            self.engine_type = "4 Cycle"
            return

        if value == "9":
            self.engine_type = "Unknown"
            return

        if value == "10":
            self.engine_type = "Electric"
            return

        if value == "11":
            self.engine_type = "Rotary"
            return

        #Default "Unknown"
        self.engine_type = "Unknown"
        logger.warning("Unknown engine type provided: " + value + " " + str(self.toDict()))
        return

    def set_category(self, value):

        if value == "1":
            self.category = "Land"
            return

        if value == "2":
            self.category = "Sea"
            return

        if value == "3":
            self.category = "Amphibian"
            return

        #Default "Unknown"
        self.category = "Unknown"
        logger.warning("Unknown category type provided: " + value + " " + str(self.toDict()))
        return

    def set_builder_certification(self, value):

        if value == "0":
            self.builder_certification = "Type Certificated"
            return

        if value == "1":
            self.builder_certification = "Not Type Certificated"
            return

        if value == "2":
            self.builder_certification = "Light Sport"
            return

        #Default "Unknown"
        self.builder_certification = "Unknown"
        logger.warning("Unknown builder certification type provided: " + value + " " + str(self.toDict()))
        return
    
    def set_weight(self, value):

        if value == "CLASS 1":
            self.weight = "Up to 12,499lbs"
            return

        if value == "CLASS 2":
            self.weight = "12,500 - 19,999lbs"
            return

        if value == "CLASS 3":
            self.weight = "Exceeds 20,000lbs"
            return

        if value == "CLASS 4":
            self.weight = "UAV up to 55lbs"
            return

        #Default "Unknown"
        self.weight = "Unknown"
        logger.warning("Unknown weight provided: " + value + " " + str(self.toDict()))
        return

    def toDict(self):
        return self.__dict__

    def commit(self):

        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO aircraft (code, manufacturer, model, aircraft_type, engine_type, category, builder_certification, engine_count, seat_count, weight, speed) VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        parameters = (self.code, self.manufacturer, self.model, self.aircraft_type, self.engine_type, self.category, self.builder_certification, self.engine_count, self.seat_count, self.weight, self.speed)

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        #Close the cursor
        dbCursor.close()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Imports the FAA N-Number Registry')
    parser.add_argument(dest='download_url', metavar="download_url", help='URL of the FAA N-Number registry to download.')

    args = parser.parse_args()

    #Setup the configuration required
    setup(args)

    main()
