# imports to get the Bosch atmospheric sensor working
# All of the functions are simple enough to not wrap in a class

#import board
#import busio
#import adafruit_bme280
#i2c = busio.I2C(board.SCL, board.SDA)
#bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c)

# this value changes overtime by the hour
#bme280.sea_level_pressure = 1016.7

## subs for the BME280 hardware

class bme280:
    temperature = 55
    relative_humidity = 55
    altitude = 55
    pressure = 55
    #def __init__(self):

