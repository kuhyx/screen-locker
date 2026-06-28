This is a continouation from design.md file with what is left to be done and what new ideas came to me since the last time arranged in order of importance

Crucial (max 1 feature):
    If user starts workout and later either exit the app completely or clicks the arrow in upper left the workout gets reset completely, all progress is lost this is very bad
    once user starts workout only by tapping finish and confirming that they INDEED finished workout should end it OR if user clicks and confirms RESET button, NOTHING ELSE

High (max 2 features):
    adds breaks between REPS (3 minutes if REP succeeded (as in all reps were done) and 5 minutes if it failed) <-- currently app ads breaks between SETS which wrong
    After break time (after REPS) is over app should play a sound and vibrate the phone and generally point the user attention towards the app

Mid (max 3 features):
    change warmup exercises weight from 2/3 to 3/4 of target weight
    Warmups should be a selectable circles in a separate screen, optional but still interactive and after doing them give the user a 3 minute break ALSO
    The app should change between workout A and B AUTOMATICALLY, no user interaction if last workout done was "A" the next one should be "B" and then "A" and so on...

Low (max 4 features):
    If set is finished user cannot modify reps on this set for some reason -> this is a bug user should ALWAYS be able to modify ANY reps in ANY exercise
    shows history of workouts and a graph for showing progress
    The app should be capable of working in the background without any problem and display status notifications allowing user to click on "done rep" from the status bar
    automatically decreases weight if user had a break from using the app <-- not sure if implemented (maybe implemented but did not have a change to check it add fallback manual setting of weights by user)


Technical Requirements:
App should work on rooted and unrooted phones with minimum android version of at least 12
Full test coverage (100%) (but first check the functionality and if the functionality fully works and is approved by user THEN start writing ANY tests at all please)
I connected an unrooted phone with adb on to the pc use it for testing
