<?php

    require_once('getConfig.php');

    class database{

        /* Performs low-level database SELECT and CALLs */

        private $dsn;
        private $conn;
        public $rowsAffected;
        public $id;

        function __construct(){

            $this->conn = mysqli_connect(getConfig('sqlServer'), getConfig('sqlUsername'), getConfig("sqlPassword"), getConfig("database"));

            if($this->conn == False){
                throw new Exception("Database unavailable", 503);
            }
        }


        function __destruct(){

            //Clean up the connection if it was successully opened
            if($this->conn != False){
                mysqli_close($this->conn);
            }
        }


        private function minify($json){

            return json_encode(json_decode($json), JSON_UNESCAPED_SLASHES);
        }


        public function query($sql, $includeColumnName = false, $encodeToJson = false){

            /* Queries the data from SQL and returns a JSON object (if only one entry) or array (if multiple entries) */

            $result = mysqli_query($this->conn, $sql);

            //Get the number of rows to determine if we should return an object or an array
            if(mysqli_num_rows($result) == 1) {

                //If we only have one column and we don't need the column name (field contains JSON)
                if(mysqli_num_fields($result) == 1 && $includeColumnName == false){

                    //Just get the row
                    $r = mysqli_fetch_row($result);
        
                    //See if we need to encode it or can send the row data raw
                    if($encodeToJson == true){

                        //Encode the row data
                        return json_encode($r[0], JSON_UNESCAPED_SLASHES);
                    }else{

                        //Get the number of affected rows
                        $this->rowsAffected = mysqli_affected_rows($this->conn);

                        //Row data must already include JSON, just send it as-is
                        return $r[0];
                    }
                    

                }else{

                    //We have more than one field OR we requested the field name to be included in the object response
                    $r = mysqli_fetch_object($result);

                    $rows[] = $r;

                    //Get the number of affected rows
                    $this->rowsAffected = mysqli_affected_rows($this->conn);

                    //We at least a field and a value, they must always be encoded
                    return json_encode($r, JSON_UNESCAPED_SLASHES);
                
                }

            }else{

                //0 or > 1 rows, return an array
                $rows = array();

                if($includeColumnName == true){
                    $sqlMode = MYSQLI_ASSOC;
                }else{                
                    $sqlMode = MYSQLI_NUM;
                }

                //Flip through every row in the result
                while($r = mysqli_fetch_array($result, $sqlMode)) {

                    
                    if($includeColumnName == true){

                        $rows[] = $r;

                    }else{
                            
                        //If we are not including column names, the data must be JSON, decode it so that it can be encoded properly
                        $rows[] = json_decode($r[0]);

                    }

                }

                //Get the number of affected rows
                $this->rowsAffected = mysqli_affected_rows($this->conn);

                return json_encode($rows);
                
            }
        }


        public function callProcedure($sql, $varTypes = NULL, $variables = NULL){
 
            $prepare = mysqli_prepare($this->conn, $sql);

            if($varTypes != NULL){

                mysqli_stmt_bind_param($prepare, $varTypes, ...$variables);
            }

            if($prepare == false){

                //If the error number is 1644, that is a user-defined error, pass the data to the user
                if(mysqli_errno($this->conn) == 1644){
                    throw new Exception (mysqli_error($this->conn), 400);

                } elseif(getConfig('debugMode')) {

                    //Likely a SQL permission missing, if in debug, show the raw message
                    throw new Exception (mysqli_error($this->conn));

                } else {
                    
                    //In debug, hide the odd exception
                    throw new Exception ("Database request failed");
                }             
            }
            
            //Execute the statement
            mysqli_stmt_execute($prepare);

            if(mysqli_error($this->conn)){

                //If the error number is 1644, that is a user-defined error, pass the data to the user
                if(mysqli_errno($this->conn) == 1644){
                    throw new Exception (mysqli_error($this->conn), 400);

                } elseif(getConfig('debugMode')) {

                    //Likely a SQL permission missing, if in debug, show the raw message
                    throw new Exception (mysqli_error($this->conn));

                } else {
                    
                    //In debug, hide the odd exception
                    throw new Exception ("Database request failed");
                }  

            }

            //Get the number of affected rows
            $this->rowsAffected = mysqli_affected_rows($this->conn);
            $this->id = mysqli_insert_id($this->conn);

            if($varTypes != NULL){

                //Get the ID of the record inserted
                $result = mysqli_query($this->conn, "SELECT LAST_INSERT_ID();");
                $r = mysqli_fetch_row($result);

                $this->id = $r[0];

            }

            return true;
            
        }
    }

?>