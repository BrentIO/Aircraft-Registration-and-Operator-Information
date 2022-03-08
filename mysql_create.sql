SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';


-- -----------------------------------------------------
-- Table `registrations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `registrations` (
  `unique_id` INT NOT NULL AUTO_INCREMENT,
  `icao_hex` CHAR(6) NOT NULL,
  `registration` VARCHAR(20) NOT NULL,
  `data` JSON NOT NULL,
  `hash` CHAR(32) NOT NULL,
  `source` INT NOT NULL,
  `created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `deleted` DATETIME NULL DEFAULT NULL,
  PRIMARY KEY (`unique_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;

CREATE UNIQUE INDEX `unique_id_UNIQUE` ON `registrations` (`unique_id` ASC) VISIBLE;

CREATE UNIQUE INDEX `icao_hex_hash` ON `registrations` (`icao_hex` ASC, `hash` ASC) VISIBLE;

CREATE INDEX `icao_hex` ON `registrations` (`icao_hex` ASC) VISIBLE;

CREATE INDEX `hash` ON `registrations` (`hash` ASC) VISIBLE;

CREATE INDEX `registration` ON `registrations` (`registration` ASC) VISIBLE;


-- -----------------------------------------------------
-- Table `simple`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `simple` (
  `unique_id` INT NOT NULL AUTO_INCREMENT,
  `icao_hex` CHAR(6) NOT NULL,
  `registration` VARCHAR(20) NOT NULL,
  `data` JSON NOT NULL,
  `hash` CHAR(32) NOT NULL,
  `source` INT NOT NULL,
  `created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `deleted` DATETIME NULL DEFAULT NULL,
  PRIMARY KEY (`unique_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;

CREATE UNIQUE INDEX `unique_id_UNIQUE` ON `simple` (`unique_id` ASC) VISIBLE;

CREATE UNIQUE INDEX `icao_hex_hash` ON `simple` (`icao_hex` ASC, `hash` ASC) VISIBLE;

CREATE INDEX `icao_hex` ON `simple` (`icao_hex` ASC) VISIBLE;

CREATE INDEX `hash` ON `simple` (`hash` ASC) VISIBLE;

CREATE INDEX `registration` ON `simple` (`registration` ASC) VISIBLE;


-- -----------------------------------------------------
-- Table `sources`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `sources` (
  `unique_id` INT NOT NULL AUTO_INCREMENT,
  `agency` VARCHAR(50) NOT NULL,
  PRIMARY KEY (`unique_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `operators`
-- -----------------------------------------------------
CREATE TABLE `operators` (
  `unique_id` int NOT NULL AUTO_INCREMENT,
  `airline_designator` varchar(10) NOT NULL,
  `name` varchar(255) NOT NULL,
  `callsign` varchar(45) NOT NULL,
  `country` varchar(45) NOT NULL,
  `hash` char(32) NOT NULL,
  `created` datetime DEFAULT CURRENT_TIMESTAMP,
  `deleted` datetime DEFAULT NULL,
  PRIMARY KEY (`unique_id`),
  UNIQUE KEY `unique_id_UNIQUE` (`unique_id`),
  UNIQUE KEY `airline_designator_hash` (`airline_designator`,`hash`),
  KEY `airline_designator` (`airline_designator`),
  KEY `hash` (`hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;