## stub version has GPIO and hardware requirements commented out
#import RPi.GPIO as GPIO    # Import Raspberry Pi GPIO library
from time import sleep     # Import the sleep function from the time module
import threading

# Author: Peter Van Eenoo
# CSS 532 IoT - class project
# March 2021

LED_PIN = 21  # the choses GPIO 21/physical pin 40, for blinking our LED
#GPIO.setwarnings(False)    # Ignore warning for now
#GPIO.setmode(GPIO.BOARD)   # Use physical pin numbering
#GPIO.setup(LED_PIN, GPIO.OUT, initial=GPIO.LOW)   # Set pin 40 to be the output pin and set it LOW by default
BLINK_SPEED = 0.7
TIMEOUT = 2

class ledManager:
    def __init__(self, e):
        self.running = True
        self.event = e
    def terminate(self):
        self.running = False

    def start(self):
        print("LED system starting")
        while self.running:
            self.event.wait(TIMEOUT) # block until main thread gets signal to turn on led
            while self.event.isSet() and self.running: # if we get terminated while inside this loop 
                # we can get stuck unless we check both states
                #GPIO.output(LED_PIN, GPIO.HIGH) # Turn on
                sleep(BLINK_SPEED) 
                #GPIO.output(LED_PIN, GPIO.LOW) # Turn off
                sleep(BLINK_SPEED) 
    
        print("LED system terminating")

