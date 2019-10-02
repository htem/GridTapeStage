Installation
======

IDE
====
The newest version (1.6.11) should be fine.
https://www.arduino.cc/en/Guide/HomePage

Libraries
====
You will also need to install three additional libraries.
https://www.arduino.cc/en/Guide/Libraries  see Manual Installation towards 
the bottom of the page

dSPIN
====
https://github.com/braingram/dSPIN

Comando
====
https://github.com/braingram/comando

HX711
====
https://github.com/bogde/HX711/tree/7ef05358e286980469da54ab3b6235102f44c4f2
The newest commits have changed the way the tension is read so use commit: 7ef05358e286980469da54ab3b6235102f44c4f2

Updating
======
Open the sketch temcagt_reel/temcagt_reel.ino in the Arduino IDE. Make sure 
the electronics are hooked up to the computer. Make sure the correct board 
is selected by checking Tools->Board, it should be something like Arduino Uno.
Make sure the correct port is selected in Tools->Port. Click the upload button.
