## stub version has GPIO and hardware requirements commented out
from time import sleep     # Import the sleep function from the time module
import threading
#import RPi.GPIO as GPIO    # Import Raspberry Pi GPIO library
WATER_PIN = 20  # the choses GPIO pin for controlling the water valve

#GPIO.setwarnings(False)    # Ignore warning for now
#GPIO.setup(WATER_PIN, GPIO.OUT, initial=GPIO.LOW)   # Set GPIO PIN 20 to be the output pin and set it LOW by default

DEFAULT_WATERING_TIME_SEC = 8
TIMEOUT = 3
MAX_WATERING_TIME_SEC = 121 # this seems long enough for a single watering

class waterManager:
    def __init__(self, e, wateringTime):
        self.running = True

        # mutexA is the outer watering loop mutex
        self.mutexA = threading.Lock()

        #mutexB is the inner loop mutex used to interrupt and stop the watering process if requested
        self.mutexB = threading.Lock()

        self.event = e
        self.isWatering = False

        # this is used to interrupt to hose by a user
        # guarged by mutexB
        self.emergencyStop = False

        ## set the default and then check to see if reasonable values for watering time were passed in
        self.wateringTime = DEFAULT_WATERING_TIME_SEC
        ## Protect against invalid values for watering time in seconds
        if wateringTime > 0 and wateringTime < MAX_WATERING_TIME_SEC:
            self.wateringTime = wateringTime
        else:
            print('Error: value for watering time was too high or too low, using default time in seconds')

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

    def getWateringTime(self):
        return self.wateringTime

    # reset the watering total, useful if upstream is tracking this total
    def clearRuntime(self):
        self.wateringTotal = 0

    # the user can request the system to change the amount of time this device waters for
    def changeWateringTime(self, value):
        if value > 0 and value < MAX_WATERING_TIME_SEC:
            # the user has requested a reasonable time change
            # but don't change the watering time if watering is in progress
            self.mutexA.acquire()
            self.wateringTime = value
            self.mutexA.release()

        # else: nothing changes and we return the current value anyways 
        return self.wateringTime

    # stop the hose if it's currently watering
    def interruptHose(self):
        self.mutexB.acquire()
        self.emergencyStop = True
        self.mutexB.release()


# For safty reasons, this function will only water for the pre-determined set to time and then it will unset the event
# This is helpful if changes to the calling code forget to clear the state and we could continuously water which might
# cause physical damage to property by flooding
    def start(self):
        print("Watering system starting")
        while self.running:
            self.event.wait() # block until we are ready
            # check both or else we can't exit properly since we need to trigger an event to terminate
            if self.event.isSet() and self.running:
                self.mutexA.acquire()
                self.isWatering = True

                ## turn hose on
                #GPIO.output(WATER_PIN, GPIO.HIGH)
                counter = 0
                while counter < self.wateringTime:
                    self.mutexB.acquire()
                    if not self.emergencyStop:
                        self.mutexB.release()
                        counter += 1    
                        sleep(1)
                    else: # emergency stop
                        self.emergencyStop = False
                        self.mutexB.release()
                        break
                    ## release and loop again

                #GPIO.output(WATER_PIN, GPIO.LOW) # turn off the hose

                self.isWatering = False
                ## increment statistics
                self.wateringTotal += counter
                self.wateringCumulative += counter
                self.event.clear() # only water once
                self.mutexA.release()

        print("Watering system terminating")

