document.addEventListener('DOMContentLoaded', (event) => {
    contentLoaded();
});

function checkAPIKeyStored(){
    if(localStorage['x-api-key']){
        $("#apiKeyLink").html("Logout");
        return true;
    }
    else{
        $("#apiKeyLink").html("Login");
        return false;
    }
}

function login(){
    localStorage['x-api-key'] = document.getElementById("xapikey").value;
    checkAPIKeyStored();
    document.getElementById("xapikey").value = "";
}

function logout(){
    document.getElementById("apiKeyModal").value = "";
    localStorage.clear();
    checkAPIKeyStored();
}

function onclick_loginLogout(){
    if(checkAPIKeyStored() == true){
        logout();
    }else{
        $("#apiKeyModal").modal("show");
    }
}

function displayErrorToast(message){
    document.getElementById("toastFailureText").innerText = message.trim()
    $("#toastFailure").toast("show");
}

function displayWarningToast(message){
    document.getElementById("toastWarningText").innerText = message.trim()
    $("#toastWarning").toast("show");
}

function displaySuccessToast(message){
    document.getElementById("toastSuccessText").innerText = message.trim()
    $("#toastSuccess").toast("show");
}

function formatErrorDisplay(data){
    var displayMessage = data['status'] + ": ";
    if(data['statusText'] != ""){
        displayMessage += data['statusText'] + " "
    }
    if(data['responseText'] != ""){
        displayMessage += data['responseText'] + " "
    }
    displayErrorToast(displayMessage);
}

function setDisplayMessage(message){

    switch(message){

      case "no_records":

        document.getElementById("displayMessage").style.visibility = "visible";
        document.getElementById("displayMessage").innerHTML = "<p>There are no records to display.</p>"
        break;

      case "not_logged_in":

        document.getElementById("displayMessage").style.visibility = "visible";
        document.getElementById("displayMessage").innerHTML = "<p>You must be logged in to view this data.</p>"
        break;

      default:
        document.getElementById("displayMessage").style.visibility = "hidden";
    }
  }

function confirmExpireFlight(ident, origin, destination){

    document.getElementById("expireModalText").innerText = "Are you sure you want to expire " + ident + " from " + origin + " to " + destination +"?"
    document.getElementById("expireConfirmButton").onclick = function(){
      expireFlight(ident, origin, destination);
    }
    $("#expireModal").modal("show");
}

function expireFlight(ident, origin, destination){

    if(checkAPIKeyStored() == false){
        displayErrorToast("You must log in before performing this action.")
        return;
    }

    $.ajax({

        beforeSend: function(request) {
            request.setRequestHeader("x-api-key", localStorage['x-api-key']);
        },
        type: 'DELETE',
        url: location.protocol + "//" + location.host + "/flight/" + ident + "/" + origin + "/" + destination,

        success: function(data) {
        displaySuccessToast("Successfully expired " + ident + " from " + origin + " to " + destination +".")
        expireFlightSuccess();

        },

        error: function(data){
            formatErrorDisplay(data)
        }
    });
}