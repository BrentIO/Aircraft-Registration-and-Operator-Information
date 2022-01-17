<?php

    //Enable additional data for debugging
    if(getConfig("debugMode")){

        ini_set('display_errors', 'On');

    }

    
    function getConfig($key){

        $config = array();
        
        if(count($config) == 0){

            #Only read the file from disk once
            $configFile = file_get_contents("/var/www/settings.json");
            $config = json_decode($configFile, true);

        }

        #Cycle through each key to find the one we want
        foreach($config as $jkey => $value){
            if(strtolower($jkey) == strtolower($key)){
                return $value;
            }
        }
    }

?>