$(document).ready(function(){
  $('.progress-bar').each(function(){
    updateProgress($(this));
  });
});

function updateProgress($bar){

  var level = Number($bar.attr('level'));
  var max = Number($bar.attr('max'));

  // Update .progress-level content
  $bar.find('.progress-level').each(function(){
    $(this).html(level.toString());
  });

  // Update .progress-max content
  $bar.find('.progress-max').each(function(){
    $(this).html(max.toString());
  });

  var percentage = (100*(level/max)).toString() + "%";
  $bar.find('.progress-fill').width(percentage);

  var difference = max - level;

  if (level <= 0) {
    $bar.attr('mode', 'empty');

  } else if (level < max) {
    $bar.attr('mode', 'in-progress');

  } else if (level == max) {
    $bar.attr('mode', 'complete');

  } else if (level > max) {
    $bar.attr('mode', 'overflow'); // undefined behavior
  }
}


function setProgress($this, newLevel){
  $this.attr('level', newLevel);
  updateProgress($this);
}

// $('.progress-bar').click(function(){
//   var level = Number($(this).attr('level'));
//   setProgress($(this), level+1);
// });
