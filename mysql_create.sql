SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';


-- -----------------------------------------------------
-- Schema registrations
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `registrations` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci ;
USE `registrations` ;

-- -----------------------------------------------------
-- Table `registrations`.`registrations`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `registrations`.`registrations` (
  `unique_id` INT NOT NULL AUTO_INCREMENT,
  `icao_hex` CHAR(6) NOT NULL,
  `registration` VARCHAR(8) NOT NULL,
  `data` JSON NOT NULL,
  `hash` CHAR(32) NOT NULL,
  `source` INT NOT NULL,
  `created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `deleted` DATETIME NULL DEFAULT NULL,
  PRIMARY KEY (`unique_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;

CREATE UNIQUE INDEX `unique_id_UNIQUE` ON `registrations`.`registrations` (`unique_id` ASC) VISIBLE;

CREATE UNIQUE INDEX `icao_hex_hash` ON `registrations`.`registrations` (`icao_hex` ASC, `hash` ASC) VISIBLE;

CREATE INDEX `icao_hex` ON `registrations`.`registrations` (`icao_hex` ASC) VISIBLE;

CREATE INDEX `hash` ON `registrations`.`registrations` (`hash` ASC) VISIBLE;

CREATE INDEX `registration` ON `registrations`.`registrations` (`registration` ASC) VISIBLE;


-- -----------------------------------------------------
-- Table `registrations`.`sources`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `registrations`.`sources` (
  `unique_id` INT NOT NULL AUTO_INCREMENT,
  `agency` VARCHAR(50) NOT NULL,
  PRIMARY KEY (`unique_id`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;