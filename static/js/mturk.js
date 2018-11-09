/**Use with LegionTools
 *
 *  gup(name) :: retrieves URL parameters if provided
 *
 *  Prepares the page for MTurk on load.
 *  1. looks for a form element with id="mturk_form", and sets its METHOD / ACTION
 *    1a. All that the task page needs to do is submit the form element when ready
 *  2. disables form elements if HIT hasn't been accepted
 *
 **/

// selector used by jquery to identify your form
var form_selector = "#mturk_form";

// function for getting URL parameters
function gup(name) {
  name = name.replace(/[\[]/,"\\\[").replace(/[\]]/,"\\\]");
  var regexS = "[\\?&]"+name+"=([^&#]*)";
  var regex = new RegExp(regexS);
  var results = regex.exec(window.location.href);
  if(results == null)
    return "";
  else return unescape(results[1]);
}

//  Turkify the captioning page.
$(document).ready(function () {
  // is assigntmentId is a URL parameter
  var hitid =   gup('hitId');
  var workerid = gup('workerId');
  var submit_url=gup("turkSubmitTo");
  var aid = gup("assignmentId");

  if($(form_selector).length<=0){
    //alert("ERROR : assignment ID not available. this page cannot be submitted");
    //return;
  }

    // If the HIT hasn't been accepted yet, disabled the form fields.
  if(aid == "ASSIGNMENT_ID_NOT_AVAILABLE") {
    //$('input,textarea,select,button').attr("DISABLED", "disabled");
    //alert("ERROR : assignment ID not available. this page cannot be submitted");
    //return;
  }

  if(hitid == "") {
  //  $('input,textarea,select,button').attr("DISABLED", "disabled");
    //alert("ERROR : hitid ID not available. this HITpage cannot be submitted");
  //  return;
  }

  if(workerid == "") {
 //   $('input,textarea,select,button').attr("DISABLED", "disabled");
    //alert("ERROR : workerid ID not available. this HITpage cannot be submitted");
   // return;
  }

  if(submit_url=="") {
   // alert("ERROR : turkSubmitTo not available. this HIT cannot be submitted");
//    return;
  }

  // Add a new hidden input element with name="assignmentId" that
  // with assignmentId as its value.
  //var aid_input = $("<input type='hidden' name='assignmentId' value='" + aid + "'>").appendTo($(form_selector));
  //var hitid_input = $("<input type='hidden' name='hitId' value='" + hitid + "'>").appendTo($(form_selector));
  //var workerid_input = $("<input type='hidden' name='workerId' value='" + workerid + "'>").appendTo($(form_selector));

  // Make sure the submit form's method is POST
  $(form_selector).attr('method', 'POST');

  // Set the Action of the form to the provided "turkSubmitTo" field
  var assignmentId = $('#assignmentId').val();
  $(form_selector).attr('action', "https://workersandbox.mturk.com" + '/mturk/externalSubmit?assignmentId=' + assignmentId + '&fill=true');

  $('#submit_mturk').click(function(){
    $('#mturk_form').submit();
  });

});
