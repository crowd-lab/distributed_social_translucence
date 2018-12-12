# distributed_social_translucence

Black Box Images
----------------
- c_441.png
- c_462.png
- c_533.png
- c_1931.png
- c_1941.png
- c_1944.png
- c_2777.png
- l_887.png
- l_1429.png
- l_1440.png
- l_1464.png
- l_1868.png
- l_2859.png

Known Issues
------------
- TogetherJS dialogues and the "I'm ready" popup shouldn't be visible on the wait page. Currently, TogetherJS is being initialized on the wait page to avoid issues where one user wouldn't properly connect to the room on the work page. We discussed fixing these issues by removing all of the TogetherJS logic on the wait page, and relying on a delayed call to TogetherJS's initialization function only after both users have entered the work page (which can be checked using some sort of server polling). Assuming we leave the TogetherJS configurations on the wait page, however, there are several changes that must be made to fix this issue. First, cursor and clicks from either user should not be visible. Clicks can be disabled using Together's "dontShowClicks" configuration setting, but the cursors will likely need to be disabled in its source code. Next, the connected users dock must be hidden (the blue box on the right side of the screen). This can be done using a "display: none important!;" CSS setting for the #togetherjs-container and #togetherjs-dock elements. See the top of work.html for an example. There are also some messages that are displayed in the top-left corner of the screen when other users join the room, which can likely also be hidden using CSS. Lastly, the "I'm ready" confirmation popup shouldn't show. This will probably need to be disabled in Together's source code.
- First edge case moderator should not see the observer's cursor. We discussed a possibility of simply allowing the first moderator to know an observer is watching them, but if we did want to disable the observer cursor, it would likely need to be done in TogetherJS's source code.
- Moderator should not see selection highlights from the observer, including the observer's submission button, the Yes/No radio buttons, and the observations text box. We tried using an "outline: none important!;" CSS flag for textarea:focus and input:focus elements, but this didn't work. It might also be important to note that the outline doesn't always correctly reflect the actual dimensions and location of the element, e.g. the blue outline box shown on the moderator screen is slightly larger than the box displayed on the observer screen. This issue seemed to arise when Bootstrap's CSS file was removed. If the issue cannot be fixed in CSS, it may need to be modified in Together's source code.
- Observer shouldn't be able to interact with the moderator interface. Currently, the observer can select the Yes/No radio button selectors and cause them to update on both the observer's own screen and the moderator's screen. Ideal behavior would be allowing the moderator to select Yes/No and cause the selection to update on both screens, while not allowing the observer to change the input at all. This problem seemed to arise when significant UI and code refactoring changes were made, even though the logic appears similar to the previous working version.
- Moderator must select the "Yes" or "No" label to make a response, rather than selecting the radio buttons themselves. This issue is likely occurring because Bootstrap's CSS file was removed, and Bootstrap's carousel logic depends on labels made to look like buttons, ignoring input to the radio buttons altogether. This can probably be fixed either by overriding Bootstrap's logic and allowing radio button input and having it update the carousel, or by making CSS changes to hide the radio buttons and make the Yes/No labels look like buttons, similarly to how Bootstrap did it.
- The pair ID of the working users is not being saved in the moderations table in the database. This is likely because the pair_id parameter passed to the wait and/or work page templates is unset or None. Check the logic for these pages in accountability.py to make sure this parameter is being set properly.
