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

#https://wwwapps.tc.gc.ca/Saf-Sec-Sur/2/CCARCS-RIACC/download/ccarcsdb.zip


def setup(args):
    global logger
    global applicationName
    global settings
    global import_sql

    settings = {}

    try:

        filePath = os.path.dirname(os.path.realpath(__file__)) + "/"

        applicationName = "Transport Canada Registration Manager"

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

        if "database" not in settings:
            raise Exception("The MySQL database information (database) is not populated in the settings.json file.")

        if "uri" not in settings['database']:
            raise Exception("The MySQL database uri (database -> uri) is not populated in the settings.json file.")

        if "username" not in settings['database']:
            raise Exception("The MySQL database username (database -> username) is not populated in the settings.json file.")

        if "password" not in settings['database']:
            raise Exception("The MySQL database password (database -> password) is not populated in the settings.json file.")

        if "name" not in settings['database']:
            raise Exception("The MySQL database name (database -> name) is not populated in the settings.json file.")

        #Get the SQL mode, defaulting to "memory"
        if 'localdb_mode' not in settings:
            settings['localdb_mode'] = "memory"

        if str(settings['localdb_mode']).lower() == "memory":

            import_sql = sqlite3.connect(":memory:")
        else:
            settings['localdb_mode'] = "disk"
            databaseFile = os.path.join(filePath, "ca-tc-registration.db")

            if os.path.exists(databaseFile):
                
                #Delete the old database
                os.remove(databaseFile)

            if os.path.exists(os.path.join(filePath, "ca-tc-registration.db-journal")):

                #Delete the old database journal
                os.remove(os.path.join(filePath, "ca-tc-registration.db-journal"))

            import_sql = sqlite3.connect(os.path.join(filePath, "ca-tc-registration.db"))
        
        cursor = import_sql.cursor()

        #Create the temporary tables in memory
        cursor.execute("CREATE TABLE aircraft (registration text NOT NULL, registration_type text, manufacturer_name_common text, manufacturer_name text, model text, serial_number text, eligibility_basis text, category text, import_date text, engine_manufacturer text, power_glider text, engine_category text, engine_count integer, seat_count integer, weight real, sale_reported text, issue_date text, effective_date text, ineffective_date text, use text, flight_authority text, manufacture_or_assembly text, country_manufactured text, manufactured_date text, base_operations_country text,  base_operations_province text, base text, type_certificate_number text, status text, multiple_owners text, modified_date text, icao_hex text NOT NULL, ex_military_registration text)")
        cursor.execute("CREATE TABLE owners (registration text NOT NULL, name text, trade_name text, street text, city text, province text, postal_code text, country text, type text, status text, care_of text, region text, mail_recipient text)")   
    
    except Exception as ex:
        logger.error(ex)
        print(ex)
        exitApp(1)

def main():

    try:

        #Get the files
        if settings['skip_download'] != True:
            download()

        #Import the aircraft file
        import_aircraft()

        #Import the registrations
        import_owners()

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
    if settings['localdb_mode'] == "disk":
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
    with open(filename, encoding = "ISO-8859-1") as f:
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

    #Get the file from the TC
    logger.info("Beginning file download from Transport Canada.  File: " + settings['download_url'])

    with yaspin(text="Downloading file from Transport Canada...") as spinner:
        response = requests.get(settings['download_url'])

        spinner.text = "Completed file download from Transport Canada.\n"
        spinner.ok()
   
    if response.status_code != 200:
        raise Exception("Response code from download was " + str(response.status_code) + ".")

    #Write the file to disk
    with open(downloadFileDestination, 'wb') as downloadedFile:
        downloadedFile.write(response.content)

    logger.info("Completed file download from Transport Canada.")

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

    #Rename the files to not have duplicate extensions
    for extractedFile in os.listdir(settings['tempPath']):
        if ".txt.txt" in extractedFile:
            os.rename(os.path.join(settings['tempPath'], extractedFile), os.path.join(settings['tempPath'], os.path.splitext(extractedFile)[0]))


def import_aircraft():
    
    aircraftFile = os.path.join(settings['tempPath'], "carscurr.txt")

    logger.info("Beginning Aircraft Import.")

    #Make sure the file exists
    if os.path.exists(aircraftFile) == False:
        raise Exception ("Aircraft file does not exist.  Expected " + aircraftFile)

    rowCount = totalLines(aircraftFile)

    with open(aircraftFile, "r", encoding = "ISO-8859-1") as csvfile:
        fileReader = csv.reader(x.replace('\0', '') for x in csvfile)

        #Skip the headers
        fileReader.__next__()

        with Bar("Importing Aircraft...", max=rowCount) as bar:

            for row in fileReader:

                #TC appends an empty row followed by the row count at the end, stop when we hit the empty row
                if row == []:
                    break

                tmpAircraft = aircraft()

                #Import data by address
                tmpAircraft.set_registration(str(row[0]).strip())
                tmpAircraft.registration_type = str(row[1]).strip()
                tmpAircraft.manufacturer_name_common = str(row[3]).strip()
                tmpAircraft.model = str(row[4]).strip()
                tmpAircraft.serial_number = str(row[5]).strip()
                tmpAircraft.manufacturer_name = str(row[7]).strip()
                tmpAircraft.eligibility_basis = str(row[8]).strip()
                tmpAircraft.category = str(row[10]).strip()
                tmpAircraft.import_date = parseYYYYMMDD(str(row[12]).strip())
                tmpAircraft.engine_manufacturer = str(row[13]).strip()
                tmpAircraft.set_power_glider(str(row[14]).strip())
                tmpAircraft.engine_category = str(row[15]).strip()
                tmpAircraft.set_engine_count(str(row[17]).strip())
                tmpAircraft.set_seat_count(str(row[18]).strip())
                tmpAircraft.set_weight(row[19])
                tmpAircraft.set_sale_reported(str(row[20]).strip())
                tmpAircraft.issue_date = parseYYYYMMDD(str(row[21]).strip())
                tmpAircraft.effective_date = parseYYYYMMDD(str(row[22]).strip())
                tmpAircraft.ineffective_date = parseYYYYMMDD(str(row[23]).strip())
                tmpAircraft.use = str(row[24]).strip()
                tmpAircraft.flight_authority = str(row[26]).strip()
                tmpAircraft.set_manufacture_or_assmbly(str(row[28]).strip())
                tmpAircraft.country_manufactured = str(row[29]).strip()
                tmpAircraft.manufactured_date = parseYYYYMMDD(str(row[31]).strip())
                tmpAircraft.base_operations_country = str(row[32]).strip()
                tmpAircraft.base_operations_province = str(row[34]).strip()
                tmpAircraft.base = str(row[36]).strip()
                tmpAircraft.type_certificate_number = str(row[37]).strip()
                tmpAircraft.status = str(row[38]).strip()
                tmpAircraft.set_multiple_owners(str(row[40]).strip())
                tmpAircraft.modified_date = parseYYYYMMDD(str(row[41]).strip())
                tmpAircraft.set_icao_hex(str(row[42]).strip())
                tmpAircraft.ex_military_registration = str(row[45]).strip()

                #Store it in the DB
                tmpAircraft.commit()

                #Increment the bar
                bar.next()

            bar.finish()

        logger.info("Completed Aircraft Import, total row count " + str(rowCount) + ".")


def import_owners():

    registrationFile = os.path.join(settings['tempPath'], "carsownr.txt")

    logger.info("Beginning Owner Import.")

    #Make sure the file exists
    if os.path.exists(registrationFile) == False:
        raise Exception ("Owner file does not exist.  Expected " + registrationFile)

    rowCount = totalLines(registrationFile)

    with open(registrationFile, "r", encoding = "ISO-8859-1") as csvfile:
        fileReader = csv.reader(x.replace('\0', '') for x in csvfile)

        #Skip the headers
        fileReader.__next__()

        with Bar("Importing Owners...", max=rowCount) as bar:

            for row in fileReader:

                #TC appends an empty row followed by the row count at the end, stop when we hit the empty row
                if row == []:
                    break

                tmpOwner = owner()

                #Import data by address
                tmpOwner.set_registration(str(row[0]).strip())
                tmpOwner.name = str(row[1]).strip()
                tmpOwner.trade_name = str(row[2]).strip()
                tmpOwner.set_street(str(row[3]).strip(), str(row[4]).strip())
                tmpOwner.city = str(row[5]).strip()
                tmpOwner.province = str(row[6]).strip()
                tmpOwner.postal_code = str(row[8]).strip()
                tmpOwner.country = str(row[9]).strip()
                tmpOwner.type = str(row[11]).strip()
                tmpOwner.set_status(str(row[13]).strip())
                tmpOwner.care_of = str(row[14]).strip()
                tmpOwner.region = str(row[15]).strip()
                tmpOwner.set_mail_recipient(str(row[18]).strip())               

                #Store it in the DB
                tmpOwner.commit()

                #Increment the bar
                bar.next()

        bar.finish()

    logger.info("Completed Owner Import, total row count " + str(rowCount) + ".")


def export_data():

    import_sql.row_factory = sqlite3.Row
    aircraftCur = import_sql.cursor()
    ownersCur = import_sql.cursor()

    logger.info("Querying aircraft data from SQLite.")

    with yaspin(text="Querying aircraft data from SQLite...") as spinner:

        aircraftCur.execute("SELECT aircraft.registration, aircraft.manufacturer_name_common, aircraft.manufacturer_name, aircraft.model, aircraft.serial_number, \
                            aircraft.eligibility_basis, aircraft.category, aircraft.import_date, aircraft.engine_manufacturer, aircraft.power_glider, \
                            aircraft.engine_category, aircraft.engine_count, aircraft.seat_count, aircraft.weight, aircraft.issue_date, aircraft.effective_date, \
                            aircraft.use, aircraft.flight_authority, aircraft.manufacture_or_assembly, aircraft.country_manufactured, \
                            aircraft.manufactured_date, aircraft.base_operations_country, aircraft.base_operations_province, aircraft.base, \
                            aircraft.type_certificate_number, aircraft.status, aircraft.modified_date, aircraft.icao_hex, \
                            aircraft.ex_military_registration \
                            FROM aircraft WHERE ineffective_date = ''")

        arrayAircraft = aircraftCur.fetchall()

        spinner.stop()

    logger.info("SQLite returned " + str(len(arrayAircraft)) + " rows of aircraft data.")

    registrationsDb = mysql.connector.connect(
        host=settings['database']['uri'],
        user=settings['database']['username'],
        password=settings['database']['password'],
        database=settings['database']['name'])

    logger.info("Creating temp table in MySQL.")

    mysqlCur = registrationsDb.cursor()

    #Ensure the source exists
    mysqlCur.execute("INSERT INTO sources (agency) \
                        SELECT * FROM (SELECT 'CA-TC') AS tmp \
                        WHERE NOT EXISTS ( \
                            SELECT agency FROM sources WHERE agency = 'CA-TC' \
                        ) LIMIT 1;")
    
    mysqlCur.execute("CREATE TEMPORARY TABLE import (icao_hex char(6) NOT NULL, registration varchar(8) NOT NULL, data json NULL, hash char(32) NOT NULL, KEY icao_hex (icao_hex), KEY hash (hash));")
    
    logger.info("Exporting data to MySQL.")

    sqlInsert = "INSERT INTO import (icao_hex, registration, data, hash) VALUES (%s,%s,%s,%s)"

    with Bar("Exporting Data to MySQL...", max=len(arrayAircraft)) as bar:

        for aircraft in arrayAircraft:

            objCompleted = {}
            objCompleted['aircraft'] = {}
            objCompleted['powerplant'] = {}
            objCompleted['base_operations'] = {}
            objCompleted['owners'] = []

            objCompleted['icao_hex'] = aircraft['icao_hex']
            objCompleted['registration'] = aircraft['registration']
            objCompleted['serial_number'] = aircraft['serial_number']
            objCompleted['status'] = aircraft['status']
            objCompleted['modified_date'] = aircraft['modified_date']

            if aircraft['import_date'] != '':
                objCompleted['import_date'] = aircraft['import_date']

            if aircraft['issue_date'] != '':
                objCompleted['issue_date'] = aircraft['issue_date']

            if aircraft['manufactured_date'] != '':
                objCompleted['manufactured_date'] = aircraft['manufactured_date']

            objCompleted['effective_date'] = aircraft['effective_date']
            objCompleted['use'] = aircraft['use']

            if aircraft['ex_military_registration'] != "":
                objCompleted['ex_military_registration'] = aircraft['ex_military_registration']

            if aircraft['flight_authority'] != '':
                objCompleted['flight_authority'] = aircraft['flight_authority']
                     
            if aircraft['manufacturer_name_common'] != "":
                objCompleted['aircraft']['manufacturer_name_common'] = aircraft['manufacturer_name_common']
            
            if aircraft['manufacturer_name'] != "":
                objCompleted['aircraft']['manufacturer_name'] = aircraft['manufacturer_name']

            objCompleted['aircraft']['model'] = aircraft['model']
            objCompleted['aircraft']['eligibility_basis'] = aircraft['eligibility_basis']
            objCompleted['aircraft']['category'] = aircraft['category']

            if aircraft['seat_count'] != '':
                objCompleted['aircraft']['seat_count'] = aircraft['seat_count']

            if aircraft['weight'] != '':
                objCompleted['aircraft']['weight'] = aircraft['weight']

            if aircraft['manufacture_or_assembly'] != '':
                objCompleted['aircraft']['manufacture_type'] = aircraft['manufacture_or_assembly']

            if aircraft['country_manufactured'] != '':
                objCompleted['aircraft']['country_manufactured'] = aircraft['country_manufactured']

            if aircraft['type_certificate_number'] != '':
                objCompleted['aircraft']['type_certificate_number'] = aircraft['type_certificate_number']

            if aircraft['engine_manufacturer'] != '':
                objCompleted['powerplant']['manufacturer'] = aircraft['engine_manufacturer']
            
            if aircraft['power_glider'] != '':
                objCompleted['powerplant']['power_glider'] = aircraft['power_glider']

            if aircraft['engine_category'] != '':
                objCompleted['powerplant']['category'] = aircraft['engine_category']

            if aircraft['engine_count'] != '':
                objCompleted['powerplant']['count'] = aircraft['engine_count']

            if aircraft['base_operations_country'] != '':
                objCompleted['base_operations']['country'] = aircraft['base_operations_country']

            if aircraft['base_operations_province'] != '':
                objCompleted['base_operations']['province'] = aircraft['base_operations_province']

            if aircraft['base'] != '':
                objCompleted['base_operations']['base'] = aircraft['base']

            #Get the owner data
            ownersCur.execute("SELECT * FROM owners WHERE registration = '" + objCompleted['registration'] + "' AND status = 'Active'")

            arrayOwners = ownersCur.fetchall()

            for owner in arrayOwners:

                objOwner = {}
                objOwner['name'] = owner['name']

                if owner['trade_name'] != '':
                    objOwner['trade_name'] = owner['trade_name']

                objOwner['street'] = json.loads(owner['street'])
                objOwner['city'] = owner['city']

                if owner['province'] != '':
                    objOwner['province'] = owner['province']

                if owner['postal_code'] != '':
                    objOwner['postal_code'] = owner['postal_code']

                objOwner['country'] = owner['country']
                objOwner['type'] = owner['type']

                if owner['care_of'] != '':
                    objOwner['care_of'] = owner['care_of']

                objOwner['region'] = owner['region']
                objOwner['mail_recipient'] = owner['mail_recipient']

                objCompleted['owners'].append(objOwner)

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
                            WHERE import.icao_hex IS NULL AND registrations.deleted IS NULL AND sources.agency = 'CA-TC') as d \
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
                                WHERE registrations.deleted IS NULL AND sources.agency = 'CA-TC') AS d \
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
                            LEFT OUTER JOIN sources ON sources.agency = 'CA-TC') ON DUPLICATE KEY UPDATE deleted = NULL;")

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

    return datetime.strptime(value, '%Y/%m/%d').strftime('%Y-%m-%d')


class owner():

    def __init__(self):
        self.registration = ""
        self.name = ""
        self.trade_name = ""
        self.street = []
        self.city = ""
        self.province = ""
        self.postal_code = ""
        self.country = ""
        self.type = ""
        self.status = ""
        self.care_of = ""
        self.region = ""
        self.mail_recipient = ""

    def set_registration(self, value):

        value = value.strip()

        if len(value) == 3:
            self.registration = "CF-" + str(value)
            return

        if len(value) == 4:
            self.registration = "C-" + str(value)
            return

        if len(value) not in (3, 4):
            logger.warn("Undefined registration length for '" + str(value) + "', setting value as passed.")
            self.registration = str(value)
            return

    def set_street(self, street1, street2):

        if street1 != "":
            self.street.append(street1)

        if street2 != "":
            self.street.append(street2)

    def set_status(self, value):

        if str(value).lower() == "a":
            self.status = "Active"

        if str(value).lower() == "i":
            self.status = "Inactive"

    def set_mail_recipient(self, value):

        if str(value).lower() == "y":
            self.mail_recipient = "Yes"

        if str(value).lower() == "n":
            self.mail_recipient = "No"
    
    def commit(self):
        
        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO owners (registration, name, trade_name, street, city, province, postal_code, country, type, status, care_of, region, mail_recipient) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
        
        parameters = (self.registration,
                        self.name,
                        self.trade_name,
                        json.dumps(self.street),
                        self.city, 
                        self.province,
                        self.postal_code,
                        self.country,
                        self.type,
                        self.status,
                        self.care_of,
                        self.region,
                        self.mail_recipient)

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        #Close the cursor
        dbCursor.close()

        #Destroy itself


    def toDict(self):
        return self.__dict__

class aircraft():

    def __init__(self):
        self.registration = ""
        self.registration_type = ""
        self.manufacturer_name_common = ""
        self.manufacturer_name = ""
        self.model = ""
        self.serial_number = ""
        self.eligibility_basis = ""
        self.category = ""
        self.import_date = ""
        self.engine_manufacturer = ""
        self.power_glider = ""
        self.engine_category = ""
        self.engine_count = ""
        self.seat_count = ""
        self.weight = ""
        self.sale_reported = ""
        self.issue_date = ""
        self.effective_date = ""
        self.ineffective_date = ""
        self.use = ""
        self.flight_authority = ""
        self.manufacture_or_assembly = ""
        self.country_manufactured = ""
        self.manufactured_date = ""
        self.base_operations_country = ""
        self.base_operations_province = ""
        self.base = ""
        self.type_certificate_number = ""
        self.status = ""
        self.multiple_owners = ""
        self.modified_date = ""
        self.icao_hex = ""
        self.ex_military_registration = ""

    def set_icao_hex(self, value):

        #Convert the binary to hex and get the value after 0x
        self.icao_hex = str(hex(int(value, 2))).upper()[2:]

        return

    def set_registration(self, value):

        value = value.strip()

        if len(value) == 3:
            self.registration = "CF-" + str(value)
            return

        if len(value) == 4:
            self.registration = "C-" + str(value)
            return

        if len(value) not in (3, 4):
            logger.warn("Undefined registration length for '" + str(value) + "', setting value as passed.")
            self.registration = str(value)
            return

    def set_power_glider(self, value):

        if str(value).lower() == "y":
            self.power_glider = "Yes"
            return

        if str(value).lower() == "n":
            self.power_glider = "No"
            return

    def set_engine_count(self, value):

        if value != "":
            self.engine_count = int(value)
        return

    def set_seat_count(self, value):

        if value != "":
            self.seat_count = int(value)
        return

    def set_weight(self, value):

        if value != "":
            self.weight = float(value)
        return

    def set_manufacture_or_assmbly(self, value):

        if str(value).lower() == "m":
            self.manufacture_or_assembly = "Manufactured"
            return

        if str(value).lower() == "a":
            self.manufacture_or_assembly = "Assembled"
            return

    def set_sale_reported(self, value):

        if str(value).lower() == "y":
            self.sale_reported = "Yes"
            return

        if str(value).lower() == "n":
            self.sale_reported = "No"
            return

    def set_multiple_owners(self, value):

        if str(value).lower() == "y":
            self.multiple_owners = "Yes"
            return

        if str(value).lower() == "n":
            self.multiple_owners = "No"
            return


    def toDict(self):
        return self.__dict__

    def commit(self):

        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO aircraft (registration, registration_type, manufacturer_name_common, manufacturer_name, model, serial_number, eligibility_basis, category, import_date, engine_manufacturer, power_glider, engine_category, engine_count, seat_count, weight, sale_reported, issue_date, effective_date, ineffective_date, use, flight_authority, manufacture_or_assembly, country_manufactured, manufactured_date, base_operations_country,  base_operations_province, base, type_certificate_number, status, multiple_owners, modified_date, icao_hex, ex_military_registration) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        parameters = (self.registration, self.registration_type, self.manufacturer_name_common, self.manufacturer_name, self.model, self.serial_number, self.eligibility_basis, self.category, self.import_date, self.engine_manufacturer, self.power_glider, self.engine_category, self.engine_count, self.seat_count, self.weight, self.sale_reported, self.issue_date, self.effective_date, self.ineffective_date, self.use, self.flight_authority, self.manufacture_or_assembly, self.country_manufactured, self.manufactured_date, self.base_operations_country, self.base_operations_province, self.base, self.type_certificate_number, self.status, self.multiple_owners, self.modified_date, self.icao_hex, self.ex_military_registration)

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        #Close the cursor
        dbCursor.close()

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Imports the Transport Canada Registry')
    parser.add_argument(dest='download_url', metavar="download_url", help='URL of the Transport Canada registry to download.')

    args = parser.parse_args()

    #Setup the configuration required
    setup(args)

    main()
