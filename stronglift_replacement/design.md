Why:
Stronglift app on my rooted device stopped working, we need a new app for tracking workout
on that note please disable screen locker functionality until app is ready to go and fully tested functionally

Functional Requirements:
    Tracks workouts (current {sets}x{reps}x{weight (in kg)}):
        Workout A:
            Dumbbell Lunge 5x12x7.5
            Dumbbell Bench Press 5x12x22.5
            Dumbbell Row 4x6x22.5
            Dumbbell Curl 3x12x12.5

        Workout B:
            Dumbbell Romanian Deadlift 5x7x27.5
            Dummbbell Overhead Press 5x12x7.5
            Dumbbell Bench Press 5x12x22.5
            Situp 3x30x10


Exercisees succeeded means that the user was able to do ALL sets with ALL reps
Automatically increases weight (in increments of 2.5kg) or number of reps (if maximum weight of 27.5 kg was reached for given exercise (see Dumbbell Romanian Deadlift) Situp has maximum weight of 10kg)
if user succeeded in doing this exercise in a continuous way for between 1-5 days in a row (selectable by user unless max weight reached in which case 27.5 kg should always be chosen)
automatically decreases weight (in decrements of 2.5kg) if user failed to do the exercise for 1-5 days in a row (selectable by user)
automatically decreases weight if user had a break from using the app
Tracks how much time workout took -> Fully automatically, user CANNOT set it manually
Adds optional warmup exercises (With weight equal 2/3 of target weight (rounding DOWN to nearest increment of 2.5kg) and always having 5 reps exactly and exactly one set) before each exercise (after warmup 3 minutes break too)
adds breaks between exercises (3 minutes if exercise succeeded and 5 minutes if it failed)
The user selects exercise as done by tapping on a circle with number of reps for this exercise, exercises are organized in rows where one row = one full set of one exercise, tapping on a circle again means that
the user failed to do the exercise and it decreases the rep by "1" tappign again further reduces this count, if user holds finger over the specific circle they can reset the state of this circle (which should
cancel any failed/succeed state)
shows history of workouts and a graph for showing progress
Crucial: The app should be able to communicate with this pc (arch linux) and inform it if the user had succeed to do the exercises and transfer full info about todays workout to the pc, crucially:
time and how many sets reps and weight was done, change screen locker if needed
The app should be capable of working in the background without any problem and display status notifications allowing user to click on "done rep" from the status bar
After break time is over app should play a sound and vibrate the phone and generally point the user attention towards the app

Technical Requirements:
App should work on rooted and unrooted phones with minimum android version of at least 12
Full test coverage (100%) (but first check the functionality and if the functionality fully works and is approved by user THEN start writing ANY tests at all please)
I connected an unrooted phone with adb on to the pc use it for testing

Nice to have:
    make it work on both desktops (linux only is fine) and android phones (just android is fine)
