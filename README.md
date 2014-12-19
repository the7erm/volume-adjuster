volume-adjuster
===============

Simple script that auto-adjusts pulseaudio volume so you don't have to keep fiddling with the volume.

#### Installing
```
git clone https://github.com/the7erm/volume-adjuster.git
cd volume-adjuster/
git submodule init
git submodule update
```

#### Running
Open up your command line and run `./new-volume-adjuster.py` play some sound.

If it doesn't work run `pavucontrol` and look at the settings make sure everything looks right.


#### Graph
![graph](https://cloud.githubusercontent.com/assets/2530157/5500637/ee5681b2-8705-11e4-82ff-45f1772fce55.png)

The graph shows the last 10 seconds of activity.  If you don't like it just close it.  It won't show up until you restart the program.

The dotted line is a reference point for "100%" in pulse audio.  The solid black line is the volume (you can open `pavucontrol` and watch it in action via the playback tab.)

The program samples the audio level 10 times a second.  Out of those 10 times the light blue peak represents the "highest" level.  The medium blue represents the "average" level, and the dark blue  represents the "lowest" level.

If the volume is too soft ... it raises the volume.  To loud lowers.  Simple as that.  No more constantly moving your mouse to adjust the volume via the speaker icon.


