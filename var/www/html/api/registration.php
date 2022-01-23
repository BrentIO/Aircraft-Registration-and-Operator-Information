<?php
    
    require_once('getConfig.php');
    require_once('simpleRest.php');
    require_once('database.php');

    $simpleRest = new simpleRest();

    $_GET_lower = array_change_key_case($_GET, CASE_LOWER);

    try {

        $database = new database();

        //Always assume success
        $simpleRest->setHttpHeaders(200);

        //Populate the breaker object with a preferene for the URL rather than the payload
        if((isset($_GET_lower['icao_hex']) == FALSE && isset($_GET_lower['registration']) == FALSE) || (isset($_GET_lower['icao_hex']) == True && isset($_GET_lower['registration']) == True)){

            throw new Exception("Either 'icao_hex' or 'registration' parameter is required.", 400);

        }

        //Only allow GET operations
        if(strtolower($_SERVER['REQUEST_METHOD']) != "get"){

            throw new Exception(NULL, 405);

        }

        //Determine if detailed data is being requested or simple.  Default is simple.
        if(isset($_GET_lower['detailed']) == True){

            if($_GET_lower['detailed'] == "true"){

                $tableName = "registrations";

            }else{

                $tableName = "simple";
            }
        }else{

            $tableName = "simple";
        }

        if(isset($_GET_lower['icao_hex']) == True){

            //Query the database for the data
            $response = $database->query("SELECT data FROM " . $tableName . " WHERE icao_hex = '" . strtolower($_GET_lower['icao_hex']) . "' AND deleted is null;");

            switch($database->rowsAffected){

                case 1:
                    print($response);
                break;

                case 0:
                    throw new Exception(NULL, 404);
                break;

                default:
                    throw new Exception(NULL, 409);
                break;
            }

            //Stop processing
            return;

        }

        if(isset($_GET_lower['registration']) == True){

            //Query the database for the data
            $response = $database->query("SELECT data FROM " . $tableName . " WHERE registration = '" . strtolower($_GET_lower['registration']) . "' AND deleted is null;");

            switch($database->rowsAffected){

                case 1:
                    print($response);
                break;

                case 0:
                    throw new Exception(NULL, 404);
                break;

                default:
                    throw new Exception(NULL, 409);
                break;
            }

            //Stop processing
            return;

        }

    }
    
    catch (Exception $e){

        //Set the error message to be returned to the user
        $simpleRest->setErrorMessage($e->getMessage());

        //Set the HTTP response code appropriately
        if($e->getCode() != 0){
            $simpleRest->setHttpHeaders($e->getCode());
        }else{
            $simpleRest->setHttpHeaders(500);
        }
    }
?>