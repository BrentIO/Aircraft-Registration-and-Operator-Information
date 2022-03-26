# Aircraft Registration and Operator Information
Enrich ADS-B information with aircraft registration and operator data

## What Does it Do?
Aircraft Registration and Operator Information (AROI) imports aircraft registrations and operator information from various sources, stores them in MySQL, and makes that data available to retrieve via API microservice.  It is designed to work as a microservice for [SkyFollower](https://github.com/BrentIO/SkyFollower).

## How does it Work?



## Prerequisites
AROI can run on pretty much any operating system that runs Python3, but this document will be focused exclusively on explaining how to do so under Ubuntu 20.04 (Focal Fossa).


### Required packages
Using apt, install the prerequisite packages, if you don't already have them installed:
```
sudo apt-get install -y python3 python3-pip mysql-server
```

Python also requires a number of packages that must be installed:
```
sudo pip3 install requests progress yaspin mysql-connector-python pymongo
```

## Download and Install AROI
Clone AROI from GitHub:
```
sudo git clone https://github.com/BrentIO/Aircraft-Registration-and-Operator-Information.git /etc/P5Software/AROI 
```


### MySQL Configuration
>Note, to exit the mysql command line, type `\q`

Log into MySQL:

```
sudo mysql
```


Change the root user to use a native password, in this case the root password will be changed to `password`, but you should choose something more secure:
```
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'password';
```

If you are running MySQL on a separate server, you will need to allow non-localhost connections in MySQL.

>   _Only perform this step if you are running MySQL on a separate server, or if you want to use MySQL Workbench on a separate computer._ 

```
sudo sed -i 's/127.0.0.1/0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf
```

Restart MySQL:
```
sudo systemctl restart mysql
```

Login to MySQL with the updated root account, and enter the password when prompted:
```
mysql -u root -p
```

Create the database, which will be named `AROI`:
```
CREATE DATABASE AROI;
```
> If you use a different database name, adjust the steps below in this guide as well as the settings.json file.

Create the new account, in this case the user will be named `aroi` and the password will be `my_clear_text_password`, but you should choose something more secure:
```
CREATE USER 'aroi'@'%' IDENTIFIED BY 'my_clear_text_password';
```
> Be sure to update the password in the settings.json file.

Grant the user above to have super admin privileges on the database we created, `AROI`:
```
GRANT ALL PRIVILEGES ON AROI.* TO 'aroi'@'%' WITH GRANT OPTION;
```


Flush the privileges table to pick up the changes:

```
FLUSH PRIVILEGES;
```

Create the tables in the database using the username, password, and database created in the previous steps:
```
mysql -u aroi -p AROI < /etc/P5Software/AROI/mysql_create.sql
```


## Required Configuration
You *must* configure these settings in the settings.json file.

```
sudo nano /etc/P5Software/AROI/settings.json
```

| Parameter     | Default   | Description |
----------------|-----------|-------------|
|`mySQL -> password`| my_clear_text_password | Clear text password to use when connecting to MySQL |
| `api -> x-api-key` | 5d95bb51-64b1-4269-b812-2e20e59cb3c5 | Key used when to provide minimal security when accessing the API.   Any string of characters maybe used, or a new UUID generated. |


## Optional Configuration
The settings.json file contains all of the user-configurable settings for AROI.  In addition to those in the Required Configuration section, optional parameters are described below.

| Parameter | Default | Description |
|-----------|---------|-------------|
|`mySQL -> uri`| localhost | MySQL Server IP address or domain name.  Special configuration is required in MySQL to allow remote connections (disabled in MySQL by default) if you are not running AROI and MySQL on the same device.|
|`mySQL -> database`| AROI | The MySQL database name|
|`mySQL -> username`| aroi | Username to use when connecting to MySQL|
|`api -> port`| 8480 | Port number for the API server, as an integer.|
|`skip_download`| false | Indicates if the download should be skipped when importing a new file.  If omitted, defaults to `false`.  For debugging purposes only.|
| `local_database_mode` | memory | Determines if the cached database is stored in memory or disk.  Options are `disk` or `memory`.  If using disk, be mindful that this will cause significant writes, may cause dramatic reduction in speed, and is intended for debugging purposes only.  The local database is only used when actively importing data from an external source.  If omitted, defaults to `memory`.|
|`limit`| false | Limits the number of records that will be imported to only 500 records.  If omitted, defaults to `false`.  For debugging purposes only.|


## Service Installation

Copy the service file to the systemctl directory
```
sudo mv /etc/P5Software/AROI/AROI.service /lib/systemd/system/
```

Reload the systemctrl daemon to pick up the new AROI service
```
sudo systemctl daemon-reload
```

Enable the service to run
```
sudo systemctl enable AROI.service
```

Start the service
```
sudo systemctl start AROI.service
```

## Import Agency Data
To load the data into MySQL, you need to download data from at least one agency.  Detailed data comes from government authorities, such as the FAA and Transport Canada.  Summary data and operator data comes from Mictronics, and is not an official source.

Data is retained forever in the database and it is assumed the latest file imported contains the newest data.

| Agency | Data Type | Import Script | Release Frequency | URL |
|--------|-----------|---------------|-------------------|-----|
| US FAA | Detailed | us-faa.py | Daily at 23:30 Central | https://registry.faa.gov/database/ReleasableAircraft.zip |
| Transport Canada | Detailed | ca-tc.py | Unknown | https://wwwapps.tc.gc.ca/Saf-Sec-Sur/2/CCARCS-RIACC/download/ccarcsdb.zip |
Mictronics IndexedDB | Simple | mictronics-indexeddb.py | Weekly on Sundays | https://www.mictronics.de/aircraft-database/indexedDB.php |


> Each agency's data is different and may take a number of minutes to import depending on the speed of your computer.

### Mictronics IndexedDB

_Use of this agency is strongly recommended_

Mictronics collects and releases a data extract based on a number of sources, which are not known.  Because they collect data worldwide, it contains most active aircraft on the globe with a high degree of quality.

This appears to be a volunteer effort, so be cognizant that this data is important and don't spam their servers with unnecessary requests.

`sudo crontab -e`

Download the dataset and update the data weekly on Tuesdays at 05:10:
```
10 5 * * 2 python3 /etc/P5Software/AROI/mictronics-indexeddb.py https://www.mictronics.de/aircraft-database/indexedDB.php
```

Force the script to run now:

```
sudo python3 /etc/P5Software/AROI/mictronics-indexeddb.py https://www.mictronics.de/aircraft-database/indexedDB.php
```


### United States FAA

_Use of this agency is optional_

Databases as old as 2017 can be downloaded from the FAA website and processed by specifying their URL when calling the python script.  _If you choose to do this, be sure to do this before running the current file._

The FAA releases databases daily, but there are usually a small number of updates.  It is also a very large dataset that will take a non-trivial amount of time to import, so weekly updates should be sufficient for most users.

`sudo crontab -e`

Download the dataset and update the data weekly on Saturdays at 05:10:
```
10 5 * * 6 python3 /etc/P5Software/AROI/us-faa.py https://registry.faa.gov/database/ReleasableAircraft.zip
```

Force the script to run now:

```
sudo python3 /etc/P5Software/AROI/us-faa.py https://registry.faa.gov/database/ReleasableAircraft.zip
```

### Transport Canada

_Use of this agency is optional_

`sudo crontab -e`

Download the dataset and update the data weekly on Sundays at 05:10:
```
10 5 * * 7 python3 /etc/P5Software/AROI/ca-tc.py https://wwwapps.tc.gc.ca/Saf-Sec-Sur/2/CCARCS-RIACC/download/ccarcsdb.zip
```

Force the script to run now:

```
sudo python3 /etc/P5Software/AROI/ca-tc.py https://wwwapps.tc.gc.ca/Saf-Sec-Sur/2/CCARCS-RIACC/download/ccarcsdb.zip
```

## FAQ
- Can I host this on a public website?
  - You can, but it's not a good idea -- the HTTP server is not designed to handle significant volume and implements only minimal security.
  - Some agencies license the use of their data, and doing so could be a violation of that license.
- The service won't start and there's nothing in any of the logs.  What do I do?
  - Try starting the service manually by using `sudo python3 api.py`.  If there is an error, it will usually be printed on the screen for you to see.

## Credits and Thanks
- [Mictronics](https://github.com/mictronics) for the awesome work with the IndexedDB database.  They also make a really great [ADS-B decoder](https://github.com/Mictronics/readsb).