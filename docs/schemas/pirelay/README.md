Waveshare RPi Relay Board — schematic.
Source: https://files.waveshare.com/upload/d/d7/RPi-Relay-Board-Schematic.pdf
Wiki:   https://www.waveshare.com/wiki/RPi_Relay_Board

What matters here: header pin 37 reaches IN_CH1 only through the CH1 jumper
(Relay_JMP), and the optocoupler side is fed from header pin 1 (3V3).
Opto input is active LOW. Relay coils run from 5V (header 2).
