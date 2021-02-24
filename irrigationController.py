from time import sleep     # Import the sleep function from the time module
import threading

WATER_PIN = 20  # the choses GPIO pin for controlling the water valve

GPIO.setwarnings(False)    # Ignore warning for now
GPIO.setup(WATER_PIN, GPIO.OUT, initial=GPIO.LOW)   # Set GPIO PIN 20 to be the output pin and set it LOW by default

# the amount of time to keep the valve open for watering a plant, in seconds
WATERING_TIME = 8 
TIMEOUT = 3

class irrigationManager:
    def __init__(self, e):
        self.running = True
        self.event = e
    def terminate(self):
        self.running = False

# For safty reasons, this function will only water for the pre-determined set to time and then it will unset the event
# This is helpful if changes to the calling code forget to clear the state and we could continuously water which might
# cause physical damage to property
    def start(self):
        print("Watering system starting")
        while self.running:
            self.event.wait(TIMEOUT) # block for a bit, waiting for main thread to signal to turn the water on
            if self.event.isSet()
                self.event.clear() # only water once
                GPIO.output(WATER_PIN, GPIO.HIGH) # Turn on
                sleep(WATERING_TIME) 
                GPIO.output(WATER_PIN, GPIO.LOW) # Turn off

        print("Watering system terminating")

