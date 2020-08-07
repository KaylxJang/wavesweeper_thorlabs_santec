1. Open GitBash or your favorite terminal.

2. cd to: 
	/c/users/labuser/desktop/wave_sweeper_program
	
	GitBash uses shift+insert to paste.

3. Copy+paste this line with [ABC###] changed, to set the wavesweeper settings:
	python wave_sweeper_thorlabs_santec.py [output_folder_name] [start wavelength] [end wavelength] [step] 
    
	Example: python wave_sweeper_thorlabs_santec.py data_dump_folder 1290 1310 0.5
	Remember: the numbers are in nanometers.

4. Enjoy!


Don't be afraid to jump into the file and edit.add to it.  
It was made quickly, so for example, the Thorlabs channel 2 power recording is not fully implemented yet
and the graph units are not in scientific notation.




TROUBLESHOOTING:

For major VISA or pyvisa problems, consult "Optical Sweep Troubleshooter with Santec, VISA, Python, Git Bash"
document on Google Drive.

Make sure GPIB to USB from Santec and USB-B to USB from Thorlabs is connected!  Can use NI-MAX to make sure.

Instrument addresses are hard coded in lines 48, 49.  If laser or OPM is different, find address in NI-MAX.

The output graph picture and CSV is saved in a "data" folder in same directory as this .py.

ctrl+c to kill program.

More advanced wavesweeper program that Chen wrote using Santec TSL-550 and Santec MPM-210 located at
C:\Work\lab_workspaces\ws_optical_char\optical_sweep
Use same directions as steps 1 and 2 above.