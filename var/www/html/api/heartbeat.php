<?php
   
    require_once('getConfig.php');
    require_once('simpleRest.php');
    require_once('database.php');

    //Do not require authentication for this page
    $simpleRest = new simpleRest(false);

    try{

        $database = new database();
    
        //Always assume success
        $simpleRest->setHttpHeaders(200);

        $procCall = $database->query("SELECT CURRENT_TIMESTAMP AS 'current_time', VERSION() AS 'version';");

        //Check to make sure the procedure was successful
        if($procCall == true)
        {
            $response = new stdClass();
            $response -> time = date('c', time());
            $response -> status = "ok";
            
            //Output the time
            print(json_encode($response));

        }else{

            throw new Exception(NULL, 500);
            
        }
    }
    catch (Exception $e){

        //Set the error message to be returned to the user
        $simpleRest->setErrorMessage($e->getMessage());

        //Set the HTTP response code appropriately
        if($e->getCode() != 0){
            $simpleRest->setHttpHeaders($e->getCode());
        }else{
            $simpleRest->setHttpHeaders(503);
        }
    }
?>
