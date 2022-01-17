<?php 

	require_once('getConfig.php');

	/*
	A simple RESTful webservices base class
	Use this as a template and build upon it
	Based on https://phppot.com/php/php-restful-web-service/
	*/

	class SimpleRest {

		private $httpVersion = "HTTP/1.1";
		private $contentType = "application/json";

		function __construct($AuthRequired = True) {

			#Optionally do not require authorization
			if($AuthRequired != False){

				#Ensure the key is correct
				$headers = array_change_key_case(apache_request_headers(), CASE_LOWER);

				if(isset($headers['x-api-key'])){
					
					if($headers['x-api-key'] != getConfig("x-api-key")){
						$this->setHttpHeaders(401);
						exit();
					}

				}else{
						$this->setHttpHeaders(401);
						exit();
				}
			}
		}

		public function setHttpHeaders($statusCode){
			
			$statusMessage = $this -> getHttpStatusMessage($statusCode);

			header($this->httpVersion. " ". $statusCode ." ". $statusMessage);
			header("Content-Type:". $this->contentType);
						
		}

		public function setErrorMessage($message = NULL){

			if($message == ""){
				$message = NULL;
			}

			if($message != NULL){

				$errorObject = new stdClass();
				$errorObject->error = $message;
				print(json_encode($errorObject));

			}
		}
		
		public function getHttpStatusMessage($statusCode){
			$httpStatus = array(
				100 => 'Continue',  
				101 => 'Switching Protocols',  
				200 => 'OK',
				201 => 'Created',  
				202 => 'Accepted',  
				203 => 'Non-Authoritative Information',  
				204 => 'No Content',  
				205 => 'Reset Content',  
				206 => 'Partial Content',  
				300 => 'Multiple Choices',  
				301 => 'Moved Permanently',  
				302 => 'Found',  
				303 => 'See Other',  
				304 => 'Not Modified',  
				305 => 'Use Proxy',  
				306 => '(Unused)',  
				307 => 'Temporary Redirect',  
				400 => 'Bad Request',  
				401 => 'Unauthorized',  
				402 => 'Payment Required',  
				403 => 'Forbidden',  
				404 => 'Not Found',  
				405 => 'Method Not Allowed',  
				406 => 'Not Acceptable',  
				407 => 'Proxy Authentication Required',  
				408 => 'Request Timeout',  
				409 => 'Conflict',  
				410 => 'Gone',  
				411 => 'Length Required',  
				412 => 'Precondition Failed',  
				413 => 'Request Entity Too Large',  
				414 => 'Request-URI Too Long',  
				415 => 'Unsupported Media Type',  
				416 => 'Requested Range Not Satisfiable',  
				417 => 'Expectation Failed',
				418 => 'I\'m a Teapot',
				500 => 'Internal Server Error',  
				501 => 'Not Implemented',  
				502 => 'Bad Gateway',  
				503 => 'Service Unavailable',  
				504 => 'Gateway Timeout',  
				505 => 'HTTP Version Not Supported');
			return ($httpStatus[$statusCode]) ? $httpStatus[$statusCode] : $status[500];
		}
	}
?>