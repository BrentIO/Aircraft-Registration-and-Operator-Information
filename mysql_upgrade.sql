SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

/* Add the 'source' column to operators */

SELECT IF (
    EXISTS (
        SELECT DISTINCT column_name FROM information_schema.columns WHERE TABLE_NAME = 'operators' AND COLUMN_NAME = 'source' )
		, 'EXISTS'
		, 'NOT_EXISTS') into @columnTest;
               
SELECT IF ( @columnTest = 'NOT_EXISTS',
	'ALTER TABLE operators ADD COLUMN source INT NOT NULL AFTER hash;',
	'SELECT ''Operators Already Contains Source Column; Ignoring''') into @actionCommand;

PREPARE stmtCreateColumn FROM @actionCommand;
EXECUTE stmtCreateColumn;
DEALLOCATE PREPARE stmtCreateColumn;

SELECT IF ( @columnTest = 'NOT_EXISTS',
'UPDATE operators SET source = (SELECT unique_id FROM sources where agency = ''Mictronics-IndexedDB'') WHERE source = 0;',
'SELECT ''Operator Source Already Set; Ignoring''') into @actionCommand;

PREPARE stmtUpdateData FROM @actionCommand;
EXECUTE stmtUpdateData;
DEALLOCATE PREPARE stmtUpdateData;

CREATE TABLE IF NOT EXISTS `airports` (
  `icao_code` char(4) NOT NULL,
  `iata_code` char(3) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `region` varchar(25) DEFAULT NULL,
  `country` char(2) DEFAULT NULL,
  `phonic` varchar(255) DEFAULT NULL,
  `hash` char(32) DEFAULT NULL,
  `source` int DEFAULT NULL,
  PRIMARY KEY (`icao_code`),
  KEY `IATA` (`iata_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE `operators_unknown` (
  `airline_designator` varchar(10) NOT NULL,
  `count` int DEFAULT '1',
  `created` datetime DEFAULT CURRENT_TIMESTAMP,
  `deleted` datetime DEFAULT NULL,
  PRIMARY KEY (`airline_designator`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;