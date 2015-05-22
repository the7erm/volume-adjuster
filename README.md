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

To ensure the program is working open up `pavucontrol` and check the `Playback` tab.
- The peak bar fluctuate.
- The db volume should change automatically.
![pavucontrol](https://cloud.githubusercontent.com/assets/2530157/7775237/9d8adb06-006e-11e5-9d54-bd9e93ab1cf8.png)

#### Trouble shooting.
If the sound is distorted you'll need to run `paman` and on the `Devices Tab` open each item in `Sources` and  `Reset` their volume so the volume is `100%`.
![Devices Tab](https://cloud.githubusercontent.com/assets/2530157/7775073/1db4661e-006d-11e5-90e3-abd20484e02a.png)
This needs to be done for the `alsa_input.*` and `alsa_output.*` Sources.
![Source Example](https://cloud.githubusercontent.com/assets/2530157/7775093/4afea774-006d-11e5-9e8c-9c160e060b8e.png)

#### Graph
![graph](https://cloud.githubusercontent.com/assets/2530157/5500637/ee5681b2-8705-11e4-82ff-45f1772fce55.png)

The graph shows the last 10 seconds of activity.  If you don't like it just close it.  It won't show up until you restart the program.

The dotted line is a reference point for "100%" in pulse audio.  The solid black line is the volume (you can open `pavucontrol` and watch it in action via the playback tab.)

The program samples the audio level 10 times a second.  Out of those 10 times the light blue peak represents the "highest" level.  The medium blue represents the "average" level, and the dark blue  represents the "lowest" level.

If the volume is too soft ... it raises the volume.  To loud lowers.  Simple as that.  No more constantly moving your mouse to adjust the volume via the speaker icon.


