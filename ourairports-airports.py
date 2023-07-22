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

# https://davidmegginson.github.io/ourairports-data/airports.csv


def setup(args):
    global logger
    global applicationName
    global settings
    global import_sql

    settings = {}

    try:

        filePath = os.path.dirname(os.path.realpath(__file__)) + "/"

        applicationName = "OurAirports Airports"

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
            databaseFile = os.path.join(filePath, "ourairports-airports.db")

            if os.path.exists(databaseFile):
                
                #Delete the old database
                os.remove(databaseFile)

            if os.path.exists(os.path.join(filePath, "ourairports-airports.db-journal")):

                #Delete the old database journal
                os.remove(os.path.join(filePath, "ourairports-airports.db-journal"))

            import_sql = sqlite3.connect(os.path.join(filePath, "ourairports-airports.db"))
        
        cursor = import_sql.cursor()

        #Create the temporary tables in memory
        cursor.execute("CREATE TABLE airports (icao_code text, iata_code text, name text, city text, region text, country text, phonic text)") 
    
    except Exception as ex:
        logger.error(ex)
        print(ex)
        exitApp(1)

def main():

    try:

        #Get the files
        if settings['skip_download'] != True:
            download()

        #Import the airports file
        import_airports()

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

    #Get the file from OurAirports
    logger.info("Beginning file download from OurAirports.  File: " + settings['download_url'])

    with yaspin(text="Downloading file from OurAirports...") as spinner:
        response = requests.get(settings['download_url'])

        spinner.text = "Completed file download from OurAirports.\n"
        spinner.ok()
   
    if response.status_code != 200:
        raise Exception("Response code from download was " + str(response.status_code) + ".")

    #Write the file to disk
    with open(downloadFileDestination, 'wb') as downloadedFile:
        downloadedFile.write(response.content)

    logger.info("Completed file download from OurAirports.")


def import_airports():

    airportsFile = os.path.join(settings['tempPath'], "airports.csv")

    logger.info("Beginning Airports Import.")

    #Make sure the file exists
    if os.path.exists(airportsFile) == False:
        raise Exception ("Airports file does not exist.  Expected " + airportsFile)

    rowCount = totalLines(airportsFile)

    with open(airportsFile, "r") as csvfile:
        fileReader = csv.DictReader(csvfile, delimiter=',')

        #Skip the headers
        fileReader.__next__()

        with Bar("Importing Airports...", max=rowCount) as bar:

            for row in fileReader:

                if str(row['type']).strip().lower() == "closed":
                    #Increment the bar
                    bar.next()
                    continue

                #Only (seemingly) valid ICAO codes will be allowed
                if len(str(row['ident']).strip()) != 4:
                    #Increment the bar
                    bar.next()
                    continue

                tmpAirport = airport()

                #Import data by name
                tmpAirport.icao_code = str(row['ident']).strip()
                tmpAirport.iata_code = str(row['iata_code']).strip()
                tmpAirport.name = str(row['name']).strip()
                tmpAirport.city = str(row['municipality']).strip()
                tmpAirport.region = str(row['iso_region']).strip()
                tmpAirport.country = str(row['iso_country']).strip()
                tmpAirport.set_phonic()

                #Clean up bad data
                if len(tmpAirport.iata_code) == 0 or tmpAirport.iata_code == "0":
                    tmpAirport.iata_code = None

                #Store it in the DB
                tmpAirport.commit()

                #Increment the bar
                bar.next()

            bar.message = "Done Importing Airports."

        bar.finish()

        logger.info("Completed Airport Import, total row count " + str(rowCount) + ".")


def export_data():

    import_sql.row_factory = sqlite3.Row
    sqliteCur = import_sql.cursor()

    logger.info("Querying data from SQLite.")

    with yaspin(text="Querying data from SQLite...") as spinner:

        sqliteCur.execute("SELECT icao_code, iata_code, name, city, region, country, phonic FROM airports;")
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
                        SELECT * FROM (SELECT 'OurAirports') AS tmp \
                        WHERE NOT EXISTS ( \
                            SELECT agency FROM sources WHERE agency = 'OurAirports' \
                        ) LIMIT 1;")

    logger.info("Creating temp table in MySQL.")

    mysqlCur.execute("CREATE TEMPORARY TABLE import (icao_code char(4) NOT NULL, iata_code char(3), name varchar(255), city varchar(100), region varchar(25), country char(2) NOT NULL, phonic varchar(255), hash char(32) NOT NULL, KEY icao_code (icao_code), KEY hash (hash));")
 
    logger.info("Exporting data to MySQL.")

    sqlInsert = "INSERT INTO import (icao_code, iata_code, name, city, region, country, phonic, hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"

    with Bar("Exporting Data to MySQL...", max=len(rows)) as bar:

        for row in rows:
            objCompleted = {}
            objCompleted['icao_code'] = row['icao_code']
            objCompleted['iata_code'] = row['iata_code']
            objCompleted['name'] = row['name']
            objCompleted['city'] = row['city']
            objCompleted['region'] = row['region']
            objCompleted['country'] = row['country']
            objCompleted['phonic'] = row['phonic']           
            
            mysqlCur.execute(sqlInsert, (objCompleted['icao_code'], objCompleted['iata_code'], objCompleted['name'], objCompleted['city'], objCompleted['region'], objCompleted['country'], objCompleted['phonic'], hashlib.md5(json.dumps(objCompleted).encode('utf-8')).hexdigest(), ))

            #Increment the bar
            bar.next()

        bar.finish()

    logger.info("Committing import data to MySQL.")

    with yaspin(text="Committing import data to MySQL...") as spinner:
        registrationsDb.commit()

        spinner.text = "Committed " + str(mysqlCur.rowcount) + " rows of import data to MySQL.\n"
        spinner.ok()

    logger.info("Committed " + str(mysqlCur.rowcount) + " rows of import data to MySQL.")

    #Delete registrations if we have a new record coming in where the hashes don't match
    logger.info("Deleting existing airports.")

    with yaspin(text="Deleting existing airports...") as spinner:

        mysqlCur.execute("DELETE FROM airports;")
        spinner.ok("")

    # Create new registrations and mark deleted registrations with a matching has as undeleted
    logger.info("Creating new airports.")

    with yaspin(text="Creating new airports...") as spinner:

        mysqlCur.execute("INSERT INTO airports (icao_code, iata_code, name, city, region, country, phonic, hash, source) \
                            (SELECT import.icao_code, import.iata_code, import.name, import.city, import.region, import.country, import.phonic, import.hash, sources.unique_id FROM import \
                            LEFT OUTER JOIN sources ON sources.agency = 'OurAirports');")

        logger.info("Committing new airports to MySQL.")
        registrationsDb.commit()
        
        spinner.text = "Created " + str(mysqlCur.rowcount) + " new airports.\n"
        spinner.ok("")

    logger.info("Created " + str(mysqlCur.rowcount) + " new airports.")
    
    mysqlCur.close()
    registrationsDb.close()


class airport():

    def __init__(self):
        self.icao_code = ""
        self.iata_code = ""
        self.name = ""
        self.city = ""
        self.region = ""
        self.country = ""
        self.phonic = ""

    def toDict(self):
        return self.__dict__

    def set_phonic(self):

        if self.city.replace("/", " ").replace("-", " ") not in self.name:
            self.phonic = self.city + " " + self.name
        else:
            self.phonic = self.name

        self.removeInternationalAirport()
        self.special_handling()


    def special_handling(self):

        #Ensure airports beginning with "Greater" use their name exactly
        if self.name.lower().startswith("greater"):
            self.phonic = self.name
            return
      
        #Ensure these airports use their name exactly
        if self.icao_code in ["KIAD", "KDFW", "KRDU", "KCVG", "CYUL", "KEWR", "KPIE", "KROC"]:
            self.phonic = self.name
            self.removeInternationalAirport()
            return

        #Keep airports as-is if they contain "of" (KOUN, KPAO, KSUS)
        if " of " in self.name:
            self.phonic = self.name
            self.removeInternationalAirport()
            return

        #Sorry, not sorry.  No.
        if self.icao_code == "KMLB":
            self.phonic = "Melbourne"
            return

        if self.icao_code == "KLGA":
            self.phonic = self.phonic.replace("La Guardia", "LaGuardia")
            return

        #Break the airport name into an array and check if the city is the last word.  If so, we want to move it to the first word (KCMH, KMSY, KIAH, KHVN, etc)
        if self.phonic.endswith(self.city):
            self.phonic = self.city + " " + self.name.replace(self.city, "").strip()
            self.removeInternationalAirport()

        #Fix situations where the city name was after a slash (MRCR, PAKU)
        if self.phonic.endswith("/") or self.phonic.endswith("-"):
            self.phonic = self.name
            self.removeInternationalAirport()

        self.phonic = self.phonic.replace("/", " ")
        self.phonic = self.phonic.replace("-", " ")
        self.phonic = self.phonic.replace("  ", " ")
        self.phonic = self.phonic.replace("  ", " ")         

    def removeInternationalAirport(self):
        #Remove "International" and "Airport", and unnecessary spaces
        self.phonic = self.phonic.replace("International", "")
        self.phonic = self.phonic.replace("Airport", "")
        self.phonic = self.phonic.replace("  ", " ")
        self.phonic = self.phonic.strip()


    def commit(self):

        dbCursor = import_sql.cursor()

        insert_statement = "INSERT INTO airports (icao_code, iata_code, name, city, region, country, phonic) VALUES (?,?,?,?,?,?,?)"
        parameters = (self.icao_code, self.iata_code, self.name, self.city, self.region, self.country, self.phonic)

        #Insert the record into the table
        dbCursor.execute(insert_statement, parameters)

        #Close the cursor
        dbCursor.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Imports OurAirports Airports')
    parser.add_argument(dest='download_url', metavar="download_url", help='URL of the OurAirports airport file to download.')

    args = parser.parse_args()

    #Setup the configuration required
    setup(args)

    main()
