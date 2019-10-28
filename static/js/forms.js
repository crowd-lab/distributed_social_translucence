$(document).ready(function(){
  resetForms();
});

/**
* Sets form mode to 'working', clears inputs/textareas and marks fieldsets
* as untouched.
*/
function resetForms(){
  $('.user-col form').attr('data-mode', 'working');
  // $('.user-col fieldset, .user-col textarea').addClass('untouched');
  $('.pairwise-decision, .pairwise-guidelines').addClass('untouched');
  // $('.pairwise-reasoning').removeClass('untouched')
  $('.user-col input').prop('checked', false);
  $('.user-col textarea').val('');
}

/**
* Get the 'data-mode' attribute of
* the closest `form` element to a jQuery object.
*/
function getFormState($object) {
  return $object.closest('form').attr('data-mode');
}
/**
* Set the 'data-mode' attribute of
* the closest `form` element to a jQuery object.
*/
function setFormState($object, state) {
  $object.closest('form').attr('data-mode', state);
}

/**
* On form change, set the field to touched and check
* if the form is valid yet. Allows us to escape the
* `waiting` condition if the user decides to change
* an old answer.
*/
function inputEdit($this) {
  $this.closest('.untouched').removeClass('untouched');
  if (validForm($this)) {
    setFormState($this, 'complete');
  }
}
$('form :input').change(function(){
  inputEdit($(this));
});
$('form textarea').on('keypress input selectionchange change keyup', function () {
  console.log("yes we're getting here")
  inputEdit($(this));
});

/**
* When .done-button clicked, double-check that the form
* is truly valid and set data-mode to 'waiting' if so.
*
* If all forms are set to "waiting," then go to next task.
*/
$('.done-wrap .done-button').click(function(){
  if (validForm($(this))) {
    setFormState($(this), 'waiting');
  }
  numForms = $('form').length;
  numWaiting = $('form[data-mode=waiting]').length;
  if (numForms == numWaiting) {
    nextTask(); // defined in new_work.html
  }
});

/**
* Return whether the form's data would be an acceptable response.
* - Fieldsets must contain one checked radio or checkbox.
* - Textareas must have at least as many characters as their data-min-char
*   attributes, even if
*/
function validForm($object){

  $form = $object.closest('form');

  $form.find('fieldset:not(.untouched)').each(function() {

    if ($(this).find('input[type=checkbox], input[type=radio]').length) {
      // fieldset is a checklist / radio
      if ($(this).find('input:checked').length == 0) {
        $(this).addClass('warn');
        setFormState($(this), 'working');
      } else {
        $(this).removeClass('warn');
      }

    } else if ($(this).find('textarea').length) {
      // fieldset is a textarea
      var $textarea = $(this).find('textarea').first();
      var minChar = $textarea.attr('data-min-char');
      if ($.trim($textarea.val()).length < minChar) {
        $(this).addClass('warn');
        setFormState($(this), 'working');
      } else {
        $(this).removeClass('warn');
      }

    } else {
      // don't know what kind of fieldset this is, ignore
    }
  });

  var numFields = $form.find('fieldset').length;
  var numCompleted = $form.find('fieldset:not(.warn, .untouched)').length;
  var formValid = (numFields == numCompleted);

  return formValid;
};
