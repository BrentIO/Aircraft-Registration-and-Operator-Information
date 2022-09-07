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