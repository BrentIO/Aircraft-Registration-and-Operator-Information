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
        if(isset($_GET_lower['airline_designator']) == FALSE){

            throw new Exception("Parameter 'airline_designator' is required.", 400);

        }

        //Only allow GET operations
        if(strtolower($_SERVER['REQUEST_METHOD']) != "get"){

            throw new Exception(NULL, 405);

        }

        //Query the database for the data
        $response = $database->query("SELECT airline_designator, name, callsign, country FROM operators WHERE airline_designator = '" . strtolower($_GET_lower['airline_designator']) . "' AND deleted is null;");

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