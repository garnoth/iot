from time import sleep     # Import the sleep function from the time module
import threading
import RPi.GPIO as GPIO    # Import Raspberry Pi GPIO library
WATER_PIN = 20  # the choses GPIO pin for controlling the water valve

GPIO.setwarnings(False)    # Ignore warning for now
GPIO.setup(WATER_PIN, GPIO.OUT, initial=GPIO.LOW)   # Set GPIO PIN 20 to be the output pin and set it LOW by default

DEFAULT_WATERING_TIME_SEC = 8
TIMEOUT = 3

# TODO add in function to change the watering time safely

class waterManager:
    def __init__(self, e, wateringTime):
        self.running = True
        self.mutex = threading.Lock()
        self.event = e
        self.isWatering = False
        ## set the default and then check to see if were passed a sane value
        self.wateringTime = DEFAULT_WATERING_TIME_SEC
        ## Protect against invalid values for watering time in seconds
        if wateringTime > 0 and wateringTime < 121:
            self.wateringTime = wateringTime
        else:
            print('Error: value for watering time was too high or too low')
        
        ## number of seconds this unit has watered since being cleared
        self.wateringTotal = 0
        ## track how many seconds this system has had the water valve open since being on
        self.wateringCumulative = 0
    
    # since the start thread blocks, we have to trigger an event after setting runnning to false
    def terminate(self):
        self.running = False
        self.event.set()
   
    # returns true if the system is currently dispensing water
    def getState(self):
        return self.isWatering
    
    def getCurrentTotal(self):
        return self.wateringTotal

    def getTotalRuntime(self):
        return self.wateringCumulative

    # reset the watering total, useful if upstream is tracking this total
    def clearRuntime(self):
        self.wateringTotal = 0

# For safty reasons, this function will only water for the pre-determined set to time and then it will unset the event
# This is helpful if changes to the calling code forget to clear the state and we could continuously water which might
# cause physical damage to property by flooding
    def start(self):
        print("Watering system starting")
        while self.running:
            self.event.wait() # block until we are ready
            # check both or else we can't exit properly since we need to trigger an event to terminate
            if self.event.isSet() and self.running:
                self.mutex.acquire()
                self.isWatering = True
                
                ## turn on and off
                GPIO.output(WATER_PIN, GPIO.HIGH)
                sleep(self.wateringTime)
                GPIO.output(WATER_PIN, GPIO.LOW) 

                self.isWatering = False
                ## increment statistics
                self.wateringTotal += self.wateringTime
                self.wateringCumulative += self.wateringTime
                self.event.clear() # only water once
                self.mutex.release()

        print("Watering system terminating")

