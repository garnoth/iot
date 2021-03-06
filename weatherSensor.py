# imports to get the Bosch atmospheric sensor working
# All of the functions are simple enough to not wrap in a class


import board
import busio
import adafruit_bme280
i2c = busio.I2C(board.SCL, board.SDA)
bme280 = adafruit_bme280.Adafruit_BME280_I2C(i2c)

# this value changes overtime by the hour
bme280.sea_level_pressure = 1016.7
