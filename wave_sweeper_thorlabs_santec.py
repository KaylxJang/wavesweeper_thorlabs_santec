import visa
import numpy
import time
import decimal
import matplotlib.pyplot as plt
import csv
from datetime import datetime
import os
import argparse
import itertools
import sys
import threading


# run if this file is the main program
if __name__ == '__main__':

    print("""
    
    """)

    parser = argparse.ArgumentParser()
    parser.add_argument('output_folder', type=str, help='Name of folder to dump sweep data.')
    parser.add_argument('start_wavelength', type=int, help='Start wavelength of sweep.  Needs to be an integer.')
    parser.add_argument('stop_wavelength', type=int, help='Stop wavelength of sweep.  Needs to be an integer.')
    parser.add_argument('step_wavelength', type=float, help='Step of sweep in nanometers [nm].')

    args = parser.parse_args()


    rm = visa.ResourceManager()
    resources = rm.list_resources()
    ##print(resources)

    power_meter = rm.open_resource('USB0::0x1313::0x8022::M00521521::INSTR')
    laser = rm.open_resource('GPIB0::1::INSTR')


    '''
    Interface independent commands using 
    standardized IEEE 488.2 SCPI commands
    '''
    _SANTEC_CMD_LIST_GPIB = {
        'id?' :                 '*IDN?',
        'sweep_speed?' :        ':SOUR:WAV:SWE:SPE?',
        'ld_enable?' :          ':SOUR:POW:STAT?',
        'ext_trig' :            'SOUR:TRIG:INP:EXT 0',
        'trig_mode' :           ':TRIG:OUTP %d',
        'trig_step' :           ':TRIG:OUTP:STEP %.4f',
        'sweep_status?' :       ':SOUR:WAV:SWE:STAT?',
        'enable_input_trig':    ':SOUR:TRIG:INP:EXT %d',
        'wavelength' :          ':SOUR:WAV %0.4f',
        'power' :               ':SOUR:POW:LEV %0.4f',
        'power_units' :         ':SOUR:POW:UNIT %d',
        'ld_enable' :           ':SOUR:POW:STAT %d',
        'open_shutter' :        ':SOUR:POW:SHUT 1',
        'close_shutter' :       ':SOUR:POW:SHUT 0',
        'sweep_start' :         ':SOUR:WAV:SWE:STAR %.4f',
        'sweep_end' :           ':SOUR:WAV:SWE:STOP %.4f',
        'sweep_step' :          ':SOUR:WAV:SWE:STEP %.4f',
        'sweep_speed' :         ':SOUR:WAV:SWE:SPE %.1f',
        'sweep_mode' :          ':SOUR:WAV:SWE:MOD %d',
        'sweep_number' :        ':SOUR:WAV:SWE:CYCL %d',
        'sweep_delay' :         ':SOUR:WAV:SWE:DEL %.4f',
        'step_dwell' :          ':SOUR:WAV:SWE:DWEL %.4f',
        'start_sweep' :         ':SOUR:WAV:SWE:STAT 1',
        'stop_sweep' :          ':SOUR:WAV:SWE:STAT 0',
        'reset' :               '*RST',
        'wavelength?' :         ':SOUR:WAV?', # get wavelength
        'power?' :              ':SOUR:POW?' # get power
    }


    SANTEC_CMD_TABLE_SERIAL = {
        'id?': '*IDN?',
        'sweep_speed?': 'SN',
        'ext_trig': 'TRE',
        'trig_mode': 'TM%d',
        'trig_step': 'TW%.4f',
        'wavelength': 'WA%.4f',
        'power': 'OP%.4f',
        'open_shutter': 'SO',
        'close_shutter': 'SC',
        'sweep_start': 'SS%.4f',
        'sweep_end': 'SE%.4f',
        'sweep_speed': 'SN%.1f',
        'sweep_mode': 'SM%d',
        'start_sweep': 'SG1',
        'stop_sweep': 'SG0',
        'reset': '*RST',
        'wavelength?': 'WA',  # get wavelength
        'power?': 'OP',
    }


    class SantecTSL550():

        def get_id(self):
            return laser.query('*IDN?')

        def check_shutter(self):
            return int(laser.query(':POW:SHUT?'))

        def open_shutter(self):
            return laser.write(':POW:SHUT 0')

        def close_shutter(self):
            return laser.write(':POW:SHUT 1')

        def get_wavelength(self):
            return float(laser.query(':SOUR:WAV?'))

        def set_wavelength(self, wavelength):
            #print(wavelength)
            return laser.write(':WAV %0.4f' % (wavelength))

        def is_operation_complete(self):
            return laser.query('*OPC?')


    class ThorlabsPM320E():

        def get_id(self):
            return power_meter.query('*IDN?')

        def start_measurement_channel_1(self):
            power_meter.write(':MEAS:INIT1')

        def start_measurement_channel_2(self):
            power_meter.write(':MEAS:INIT2')

        def check_measurement_status_channel_1(self):
            return power_meter.query(':MEAS:CHECK1?')
            # returns unicode aka a string
            # '1\n' means still measuring
            # '0\n' means measurement is done

        def check_measurement_status_channel_2(self):
            return power_meter.query(':MEAS:CHECK2?')
            # returns unicode aka a string
            # '1\n' means still measuring
            # '0\n' means measurement is done

        def get_power_channel_1(self):
            return float(power_meter.query(':FETCH:POW1:VAL?'))

        def get_power_channel_2(self):
            return float(power_meter.query(':FETCH:POW2:VAL?'))

        def is_operation_complete(self):
            return power_meter.query('*OPC?')


        # The 2 methods below in line 161-165 use the 'POW[1,2]:VAL?' command instead, which
        # immediately grabs the power value.
        # Sometimes this causes '+- inf' overflow errors in the Thorlabs OPM.  Mostly w/ short sweeps.
        # A better sequence is implemented as such: set wavelength, wait until wavelength is reached, start
        # measurement, wait until measurement is done, fetch power value, loop back.

        #def get_power_channel_1(self):
        #    return float(power_meter.query(':POW1:VAL?'))

        #def get_power_channel_2(self):
        #    return float(power_meter.query(':POW2:VAL?'))


    # used to interpolate numbers between start and stop points with a floating point (decimal) number step
    def float_range(start, stop, step):
        while start < stop:
            yield float(start)
            start += decimal.Decimal(step)

    # asynchronous spinner displayed when measurements are being taken.
    # creates separate thread for spinner.
    # Google 'python asynchronous progress spinner' to see where I jacked the code from.
    def spinner():
        spinner = itertools.cycle('-/|\\')
        while True:
            sys.stdout.write(spinner.next())  # write the next character
            sys.stdout.flush()  # flush stdout buffer (actual character display)
            sys.stdout.write('\b')  # erase the last written char
            time.sleep(0.05)
            if done:
                return

    '''
    # I tried to get an icon to spin while measuring.  Ended up stalling the program.
    # Spinner uses parallel thread.  Google 'python asynchronous progress spinner' to see
    # where I jacked the code from.
    
    spinner = itertools.cycle('-/|\\')
    while True:
        sys.stdout.write(spinner.next())  # write the next character
        sys.stdout.flush()  # flush stdout buffer (actual character display)
        sys.stdout.write('\b')  # erase the last written char
        time.sleep(0.05)
    '''

    # objects for Santec laser, thorlabs OPM classes, and args
    s = SantecTSL550()
    t = ThorlabsPM320E()
    start = args.start_wavelength
    stop = args.stop_wavelength
    step = args.step_wavelength


    # open shutter if closed
    if s.check_shutter() == 1:
        s.open_shutter()
        print('Shutter Opened!')

    '''
    # start spinner in separate thread
    done = False
    spin_thread = threading.Thread(target=spinner)
    spin_thread.start()
    '''

    # generate list of wavelengths to be swept
    wavelength_list = list(float_range(start, stop + step, step))
    #print(wavelength_list)

    # create empty list to dump power values into
    power_list = []

    # set wavelength
    counter = 0
    for i in wavelength_list:
        print('Set Wavelength to: %f' % i)
        s.set_wavelength(i)
        #print('Operation not complete if zero: {0}'.format(s.is_operation_complete()))

        while s.is_operation_complete() != '1\n':
            #print('Set operation not complete yet!  Wavelength is now: {0}'.format(s.get_wavelength()))
            time.sleep(0.05)
            counter += 1

            # Sometimes the set_wavelength sets to the correct wavelength, but
            # operation is not marked as complete.
            # This just waits a few cycles and moves on.  The values are correct.
            if counter > 10:
                break

        # reset counter
        counter = 0

        #print('Set operation complete.  Evidence: {0}'.format(s.is_operation_complete()))
        #print('This is the actual wavelength set : %f' % s.get_wavelength())
        #print('Wavelength to be measured: %f' % s.get_wavelength())

        # now that wavelength is set, start measurement
        power_meter.write(':MEAS:INIT1')

        # wait for measurement to complete
        # the string '1\n' means still measuring
        # the string '0\n' means measurement is done
        # sometimes the measurement is so fast it skips this while loop
        while power_meter.query(':MEAS:CHECK1?') == '1\n':
            #print('I am measuring!')
            time.sleep(0.05)
            # time.sleep of 0.05 or 50ms is enough for about one loop.  Shorter times like 0.005 loop more.

        # add fetched power to power_list defined above
        power_list.append(t.get_power_channel_1())
        print('Done measuring!  Appended to list!')

        # print power appended to list
        #print('Fetch: {}'.format(power_meter.query(':FETCH:POW1:VAL?')))


    # create interweaved list of wavelength1, power1, wavelength2, power2, etc...
    power_wavelength_list = [val for pair in zip(wavelength_list, power_list) for val in pair]
    #print(power_wavelength_list)


    # directory creation
    # create 'data' folder with date and time in same directory as this 'sweep.py', then save plot graph and csv there
    the_date_time = datetime.now().strftime('%m-%d-%Y @ %I.%M.%S%p')

    #folder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '%s', 'data', '%s' % (args.output_folder, the_date_time)))
    folder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', '%s %s' % (args.output_folder, the_date_time)))
    #print(folder_path)
    # if folder does not exist, then create it!
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)




    # generate and format plot
    fig = plt.figure()

    plt.plot(wavelength_list, power_list)
    #plt.plot(wavelength_list, 10*numpy.log10(power_list*1000))    
    plt.title('Thorlabs PM320E OPM Power vs. Santec TSL-550 Laser Wavelength')
    plt.xlabel('Wavelength [nm]')
    plt.ylabel('Power [W]')
    #plt.ylabel('Power [dBm]')    
    plt.autoscale(enable=True, axis="y", tight=False)
    plt.grid(which='major', axis='both')

    # save graph and csv
    fig.savefig(os.path.join(folder_path, 'graph.png'))

    data_path = folder_path + "\data.txt"
    file_handle = open(data_path, 'w+')
    file_handle.write(str(power_wavelength_list))
    file_handle.close()

    '''
    # stop spinner and combine threads
    done = True
    spin_thread.join()
    print('Done!')
    '''

    #show plot at end
    plt.show()










'''
spinner = itertools.cycle('-/|\\')
    while True:
        sys.stdout.write(spinner.next())  # write the next character
        sys.stdout.flush()  # flush stdout buffer (actual character display)
        sys.stdout.write('\b')  # erase the last written char
        time.sleep(0.05)
'''


'''
# Laser takes time to move, so sometimes it's not yet in place.
# Usually the small step size and fast laser sweep are quick enough to skip this while loop.              
while s.get_wavelength() != i:

    # Santec sometimes gets stuck on a previous wavelength and then gets trapped in this while loop
    # b/c the loop is waiting for the current wavelength.  Santec gets stuck b/c the first
    # 's.set_wavelength(i)' is not recieved, possibly b/c it's busy with a previous command.
    # A counter keeps track of the santec delay and if it hangs too long (10 is arbitrary) the desired
    # wavelength is set again.
    # If counter is set to 100, the wavelength usually sets itself around the 50th count, however
    # if counter is set to 10, the wavelength usually sets itself around the 13th count.
    # It appears that either waiting or spamming the OPM works, though there may be deeper implications
    # here.
    # There's a lot to be said about this stupid counter.
    if counter > 10:
        s.set_wavelength(i)
        print('This wavelength was set again: {0}'.format(s.set_wavelength(i)))

    print('Number of loops waiting for wavelength to reach set_wav: %d' % counter)
    counter += 1

# reset counter to 0 when while loop is exited
counter = 0
'''

'''
print('Query: {}'.format(power_meter.query(':POW1:VAL?')))
#print(power_meter.query(':FETCH:POW1:VAL?'))

print('Init Meas.')
power_meter.write(':MEAS:INIT1')

while power_meter.query(':MEAS:CHECK1?') == '1\n':
    print('I am measuring!')
    time.sleep(0.05)

print(power_meter.query(':MEAS:CHECK1?'))

print('Fetch: {}'.format(power_meter.query(':FETCH:POW1:VAL?')))




date_time = str(datetime.datetime.now())
results_dir = os.path.join('data',"%s_%s-%s-%s" % (args.output_folder, date_time[0:10], date_time[11:13], date_time[14:16]))

if not os.path.exists(results_dir):
    os.makedirs(results_dir)

power_wavelength_list.write_to_file("%s/%s" % (results_dir, "data.csv"))
power_wavelength_list.write_plot_to_file("%s/%s" % (results_dir, "plot.png"), show = True, write = True)
print "Dumped data in %s" % (results_dir)




# interweave two lists of equal length
l1 = [1,2,3,4,5,6,7,8,9]
l2 = [1,2,3,4,5,6,7,8,9]

print([val for pair in zip(l1,l2) for val in pair])




# alternative step number generator but is more complicated,
# working with number of samples rather than step size.
samples = 1 / step * (stop - start) + 1
for i in numpy.linspace(start, stop, num=samples, endpoint=True, retstep=True):
     print(i) 

'''

