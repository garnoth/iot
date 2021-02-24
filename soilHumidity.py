from time import sleep     # Import the sleep function from the time module
import threading
import board
import busio
import adafruit_ads1x15.ads1015 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

## calibrated values for this unique sensor
CEILING = 14000
FLOOR = 25000

SOIL_POWER_PIN = 12  # the choses GPIO pin for controlling the water valve

GPIO.setwarnings(False)    # Ignore warning for now
GPIO.setup(SOIL_POWER_PIN, GPIO.OUT, initial=GPIO.LOW)   # Set GPIO PIN 12 to be the output pin and set it LOW by default

#print("{:>5}\t{:>5}".format("raw", "v"))
print ("Soil Humidity:")
val = 0
while True:
    #    print("{:>5}\t{:>5.3f}".format(chan.value, chan.voltage))
 #   print("{:>5}\t{:>5.3f}".format(chan.value, chan.voltage))
    val = getPercentHumidity(chan.value)
    print("{:.2f}".format(round(val, 2)))
    time.sleep(2)
#######


TIMEOUT = 3
WAIT_TIME = 2 # time to wait for soil chip to come online
class soilManager:
    def __init__(self, e):
        self.running = True
        self.event = e
        
        # Create the I2C bus
        self.i2c = busio.I2C(board.SCL, board.SDA)

        # Create the ADC object using the I2C bus
        self.ads = ADS.ADS1015(i2c)

        # Create single-ended input on channel 0
        self.chan = AnalogIn(ads, ADS.P0)

    def terminate(self):
        self.running = False

    def getPercentHumidity(reading):
        self.e.set()
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
    def start(self):
        print("Soil Humidity system starting")
        while self.running:
            self.event.wait(TIMEOUT) # block for a bit, waiting for main thread to signal to turn the water on
            if self.event.isSet()
                GPIO.output(SOIL_POWER_PIN, GPIO.HIGH) # Turn on and wait for sensor
                sleep(WAIT_TIME) 
                val = getPercentHumidity(self.chan.value) ## test and see if we should return an average reading instead of a single one
                GPIO.output(SOIL_POWER_PIN, GPIO.LOW) # Turn off
                self.event.clear() # so we don't try to read again

        print("Soil system terminating")

