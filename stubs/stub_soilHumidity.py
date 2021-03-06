## stub version has GPIO and hardware requirements commented out
from time import sleep     # Import the sleep function from the time module
import threading
#import board
#import busio
#import RPi.GPIO as GPIO    # Import Raspberry Pi GPIO library
#import adafruit_ads1x15.ads1015 as ADS
#from adafruit_ads1x15.analog_in import AnalogIn


# Author: Peter Van Eenoo
# CSS 532 IoT - class project
# March 2021

## calibrated values for this unique sensor
#CEILING = 14000
#FLOOR = 25000

CEILING = 20845
FLOOR = 22280

SOIL_POWER_PIN = 16  # the GPIO pin for controlling power to the soil moisture sensor
HARDCODED_RETV = 55
#GPIO.setwarnings(False)    # Ignore warning for now
#GPIO.setup(SOIL_POWER_PIN, GPIO.OUT, initial=GPIO.LOW)   # Set GPIO PIN 16 to be the output pin and set it LOW by default


TIMEOUT = 3
WAIT_TIME = 1 # time to wait for soil chip to come online
class soilManager:
    def __init__(self):
        self.running = True
        self.soilValue = 0.0

        # this system is a little more simple so we don't need to use threading events
        self.mutex = threading.Lock()
        # Create the I2C bus
        #self.i2c = busio.I2C(board.SCL, board.SDA)

        # Create the ADC object using the I2C bus
        #self.ads = ADS.ADS1015(self.i2c)

        # Create single-ended input on channel 0
        #self.chan = AnalogIn(self.ads, ADS.P0)

    def terminate(self):
        self.running = False

    def getPercentHumidity(self, reading):
        ## this is a little confusing because we are using negative numbers because higher values
        ## means more resistance which means it's less humid so we need to invert our percentage range
        if reading > FLOOR:
            # humidity is very low
            return 0.0
        elif reading > CEILING:
            difference = ( -1 * FLOOR) - ( -1 * CEILING)
            return 100 * (1 - ((-1 *reading) - (-1 * CEILING)) / difference)
        else:
            ## reading is less than ceiling, must be very wet and moist
            return 100.0

    # for safty reasons this sensor manages it's own on and off state. The sensor will corrode itself after a few days if left on
    def getSoilHumidity(self):
        # just in case we get requests too fast, only perform 1 reading at a time
        self.mutex.acquire()

        #GPIO.output(SOIL_POWER_PIN, GPIO.HIGH) # Turn on and wait for sensor
        sleep(WAIT_TIME) 
        self.soilValue = HARDCODED_RETV
        #print("debug:{:.2f}".format(round(self.soilValue, 2)))

        #GPIO.output(SOIL_POWER_PIN, GPIO.LOW) # Turn off
        self.mutex.release()
        ## test and see if we should return an average reading instead of a single reading?
        return self.soilValue
