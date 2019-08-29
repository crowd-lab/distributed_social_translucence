// Allows html form checklists to implement a "none of the above" option which
// unchecks all other check boxes when selected, and vice versa.
// Assumes a structure of:
//  <fieldset>
//    <some wrapper>
//      <input class="nota-ex" type="checkbox"/>
//      <label>...</label>
//    </>
//    <some wrapper>
//      <input class="nota" type="checkbox"/>
//      <label>None of the above</label>
//    </>
//  </fieldset>

/*
Clicking a nota-exclusive option clears the nota option
*/
$('.nota-ex').click(function(event){
  // console.log('nota false');
  $(this).closest('fieldset').find('.nota').prop('checked', false);
});

/*
Clicking a nota option clears all of the nota-exclusive options
*/
$('.nota').click(function(event){
  // console.log('nota true');
  $(this).closest('fieldset').find('.nota-ex').prop('checked', false);
});
