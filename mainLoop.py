# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

# major modifications made by Peter Van Eenoo
# for CSS 532 at UW Bothell

import os
import argparse
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
import threading
import logging
import time
from collections import deque
from uptime import uptime
from datetime import timedelta
import json
import weatherSensor as ws
import lights as led
import soilHumidity as soil
import waterController as water
from datetime import datetime

## logging setup for different test methods

#logging.basicConfig(level=logging.DEBUG)
#logging.basicConfig(level=logging.INFO)

#logging.basicConfig(filename='debug.log', level=logging.DEBUG)
logging.basicConfig(filename='info.log', level=logging.INFO)


# this simple class holds a message and a topic string
# we will then create a deque that holds SensorMessages
class SensorMessage:
    def __init__(self, topic, message):
        self.topic = topic
        self.message = message
    def getTopic(self):
        return self.topic

    def getMessage(self):
        return self.message

# grab and parse the arguments
parser = argparse.ArgumentParser(description="Send and receive messages through and MQTT connection.")
parser.add_argument('--endpoint', required=True, help="Your AWS IoT custom endpoint, not including a port. " +
        "Ex: \"abcd123456wxyz-ats.iot.us-east-1.amazonaws.com\"")
parser.add_argument('--cert', help="File path to your client certificate, in PEM format.")
parser.add_argument('--key', help="File path to your private key, in PEM format.")
parser.add_argument('--root-ca', help="File path to root certificate authority, in PEM format. " +
        "Necessary if MQTT server uses a certificate that's not already in " +
        "your trust store.")
parser.add_argument('--client-id', default="test-", help="Client ID for MQTT connection.")
parser.add_argument('--topic', default="test/topic", help="Topic to subscribe to, and publish messages to.")
parser.add_argument('--message', default="Hello World!", help="Message to publish. " +
        "Specify empty string to publish nothing.")
parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
        help='Logging level')

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    logging.info("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    logging.info("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
    resubscribe_results = resubscribe_future.result()
    logging.info("Resubscribe results: {}".format(resubscribe_results))

    for topic, qos in resubscribe_results['topics']:
        if qos is None:
            sys.exit("Server rejected resubscribe to topic: {}".format(topic))

## end of Amazon Sample code ##

###### Gloabls area for main program and setup #########
args = parser.parse_args()

io.init_logging(getattr(io.LogLevel, args.verbosity), 'stderr')

global received_count
received_count = 0
received_all_event = threading.Event()
OUTBOX = deque() # create a linked list to handle messages for sensor readings to send to AWS
LOOP_TIMEOUT = 5 # Time timeout for the message sending loop, use this or it will never check to see if we have disconnected

global CONNECTED 
WATERING_TIME_SEC = 8 # the default ammount of time to water

# the list of supported actions our program will response to
SUPPORTED_ACTIONS = ['get','set', 'setTime', 'deviceState']

# can be set to reboot or halt
ACTION_ON_TERMINATION = ""


SUB_TOPIC = f"sensors/+/{args.client_id}"
## main program message event to wake-up and check for messages
msgEvent = threading.Event()


# globals done, start up the sensor subsystems
logging.info("Starting up sensor subsystems")
ledEvent = threading.Event()
waterEvent = threading.Event()

ledObj = led.ledManager(ledEvent)
waterObj = water.waterManager(waterEvent, WATERING_TIME_SEC)
soilObj = soil.soilManager()

ledThread = threading.Thread(name='LED subsystem', target=ledObj.start)
waterThread = threading.Thread(name='Water subsystem', target=waterObj.start)

ledThread.start()
waterThread.start()
logging.info("All sensor subsystems started")


##################

# return true if the json formatted payload contains a valid 'command' that we support
def supportedAction(payload):
    action = list(payload.keys())[0]
    # Since we only support single key + value commands, just check the first item, if it's a supported command then return true
    return action in SUPPORTED_ACTIONS

# Callback when the subscribed topic receives a message
def receive_loop(topic, payload, **kwargs):
    global received_count
    logging.debug("Received message from topic '{}': {}".format(topic, payload))
    received_count += 1
    topic_parsed = False    
    if "/" in topic:        
        parsed_topic = topic.split("/")        
        if len(parsed_topic) == 3:            
            # this topic has the correct format
                # the only root topic supported is sensors/ and only parse if this is for me
                if (parsed_topic[0] == 'sensors') and (parsed_topic[2] == args.client_id):
                    # a thing is a sensor,actuator,information or command 
                    thing = parsed_topic[1]
                    logging.debug('Started parsing thing: {}'.format(thing))
                    payloadJson = json.loads(payload)
                    # we can filter out our message responses here and skip processing if the request doesn't contain a supported
                    # action, because it likely is just our own message response
                    if supportedAction(payloadJson):
                        if thing == 'temp' or thing == 'humidity' or thing == 'altitude' or thing == 'pressure':
                            # all of these sensors are on the same sensor device
                            logging.debug("Received weather sensor request: {}".format(payload))
                            parseSensor(topic, payloadJson, thing)
                            topic_parsed = True
                        elif thing == 'soil': # soil humidity sensor module
                            logging.debug("Received soil humidity request: {}".format(payload))
                            parseSoil(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'water': # watering module
                            logging.debug("Received watering request: {}".format(payload))
                            parseWater(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'led': # module to contol LED blinking
                            logging.debug("Received light request: {}".format(payload))
                            parseLight(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'info': # requests for data that might be bigger than a single response
                            logging.debug("Received info request: {}".format(payload))
                            parseInfo(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'cmd': # the sensor receives system commands here
                            logging.debug("received command request: {}".format(payload))
                            parseCommand(topic, payloadJson)
                            topic_parsed = True
    #if not topic_parsed:
    #    logging.debug("Unrecognized message topic or sensor type, or it's my previous msg")

## Command parsing and validating function ##
#############################################

## because these 4 sensor readings all come from the same device, we will handle them
## from the same function
def parseSensor(topic, payload, thing):
    msg = {}
    if 'get' in payload:
        target = payload['get']
        if target == "status": # we can't start without this sensor being online because of i2c dependencies
            # so it's pointless to try to turn it off or on
            msg['status'] = 'on'

        elif target == "value":
            if thing == 'temp':
                msg = getTemp()
            elif thing == 'humidity':
                msg = getHumidity()
            elif thing == 'altitude':
                msg = getAltitude()
            elif thing == 'pressure':
                msg = getPressure()
    if 'set' in payload:
        action = payload['set']
        if action == 'off' or action == 'off':
            # we don't support turning this sensor on/off
            msg['status'] = 'ActionDenied'

    if msg: # check if the message is not empty
        composeMessage(topic, msg)
    else: 
        logging.debug("ignored request for weather sensor")

# check and see the we have recieved a valid request for the soil humidity sensor
def parseSoil(topic, payload):
    msg = {}
    if 'set' in payload:
        action = payload['set']
        if action == 'on' or action == 'off':
            msg['status'] = 'ActionDenied'

    if 'get' in payload:
        action = payload['get']
        if action == 'value' or action == 'status' or action == 'reading':
            logging.debug("getting soil reading")
            msg = getSoilHumidity()
    if msg:
        composeMessage(topic, msg)
    else: 
        logging.debug("ignored request for soil sensor")

# parse the request for the water module
def parseWater(topic, payload):
    msg = {}
    if 'set' in payload:
        action = payload['set']
        # this just triggers the system to water for a pre-determined amount of time for now
        if action == 'on':
            waterEvent.set()
            msg['status'] = 'on'
        
        elif action == 'off':
            # interrupt the hose and tell it to shut-off
            msg = interruptWater()

        ## clear resets the water systems current total counter for seconds watered
        elif action == 'clear':
            msg = clearWaterCounter()

    if 'setTime' in payload:
        time = payload['setTime'] # the sub-functions check and enforce the validity for int/float values
        try:
            time = int(time)
            msg = setWateringTime(time)
        except ValueError:
            logging.debug("non-integer value for time")

    if 'get' in payload:
        action = payload['get']
        if action == 'status' or action == 'state' or action == 'value':
            msg = getWaterState()
        elif action == 'cumulative':
            msg = getWaterCumulativeTotal()
        elif action == 'total':
            msg = getWaterCurrentTotal()
        
        # get the currently set watering time in seconds
        elif action == 'time':
            msg = getWateringTime()
    
    if msg:
        composeMessage(topic, msg)
    else: 
        logging.debug("ignored request for water system")

# handles the led and informs LED thread if it should blink or not
# the current behavior for 'on' means blink. We could add in function to keep
# led steady and not just blink, optional
def parseLight(topic, payload):
    msg = {}
    if 'set' in payload:
        action = payload['set']
        if action == 'on':
            ledEvent.set()
            msg['status'] = 'on'
        elif action == 'off':
            ledEvent.clear()
            msg['status'] = 'off'

    if 'get' in payload:
        action = payload['get']
        if action == 'status' or action == 'value':
            msg = getLEDStatus()
    if msg:
        composeMessage(topic, msg)
    else: 
        logging.debug("ignored request for light/led system")

# the Info topic can multisystem responses, in contrast to the rest of the sensor topics
# which only return a single status
def parseInfo(topic, payload):
    msg = {}
    if 'get' in payload:
        if payload['get'] == 'bulk':
            msg = getBulk(topic)
    if msg:
        composeMessage(topic, msg)
    else:    
        logging.debug("ignored request for info")

# parse a command request
def parseCommand(topic, payload):
    msg = {}
    global ACTION_ON_TERMINATION
    if 'get' in payload:
        if payload['get'] == 'uptime':
            msg = getUptime()
        if payload['get'] == 'timestamp':
            msg = getTimeStamp()
    if 'deviceState' in payload:
        action = payload['deviceState']
        if action == 'disconnect':
            msg['status'] = 'disconnecting'
            disconnectLoop()
        elif action == 'reboot':
            msg['status'] = 'rebooting'
            ACTION_ON_TERMINATION = 'reboot'
            disconnectLoop()
        elif action == 'halt' or action == 'off':
            msg['status'] = 'halting'
            ACTION_ON_TERMINATION = 'halt'
            disconnectLoop()
    if msg:
        composeMessage(topic, msg)
    else:    
        logging.debug("ignored request for command")

## Sensor data retrieval functions ## 
#####################################

## this function gathers all availble sensor data and device status information and sends in one
## pre-formatted message
def getBulk(topic):
    msg = {}
    msg.update(getTemp())
    msg.update(getHumidity())
    msg.update(getAltitude())
    msg.update(getPressure())
    msg.update(getLEDStatus())
    msg.update(getSoilHumidity())
    if msg:
        composeMessage(topic, msg)

def getTemp():
    msg = {}
    msg['temp'] = ws.bme280.temperature
    return msg

def getHumidity():
    msg = {}
    msg['humidity'] = ws.bme280.relative_humidity
    return msg

def getAltitude():
    msg = {}
    msg['altitude'] = ws.bme280.altitude
    return msg

def getPressure():
    msg = {}
    msg['humidity'] = ws.bme280.pressure
    return msg

def getLEDStatus():
    msg = {}
    state = "on" if ledEvent.isSet() else 'off'
    msg['status'] = state
    return msg

# report the soil humidity reading
# the soil humidity class and getSoilHumidity() function manages it's own power-state 
# because leaving it on will damange the sensor, so the state cannot be set by the user
def getSoilHumidity():
    msg = {}
    msg['value'] = soilObj.getSoilHumidity() 
    return msg

def clearWaterCounter():
    waterObj.clearRuntime()
    return getWaterCurrentTotal()

# this returns the number of seconds that the water system has been open since it was last cleared
def getWaterCurrentTotal():
    msg = {}
    msg['current total'] = waterObj.getCurrentTotal()
    return msg

# this return the number of seconds that the water system has been open since the device came online
def getWaterCumulativeTotal():
    msg = {}
    msg['cumulative total'] = waterObj.getTotalRuntime() 
    return msg

# this can inform the user if the hose is open or closed
def getWaterState():
    msg = {}
    state = 'water on' if waterObj.getState() else 'water off'
    msg['status'] = state
    return msg

# returns the currently set, ammount of time the hose will water for when turned on
def getWateringTime():
    msg = {}
    value = waterObj.getWateringTime()
    msg['watering set for'] = value
    return msg

# user can request the hose be turned off
def interruptWater():
    msg = {}
    if waterObj.getState():
        # it's currently on, interrupt it
        waterObj.interruptHose()
        msg['status'] = 'water interrupted'
    else:
        # the water hose isn't currently on
        msg['status'] = 'water already off'
    return msg

# request to change the water system's time in seconds that the hose is on for
def setWateringTime(value):
    msg = {}
    ## the sub-process to set new watering time block, this can hang the MQTT connection
    ## if we don't send a response soon enough, so report an error if watering is in prog
    if not waterObj.getState():
        value = waterObj.changeWateringTime(value)
        msg['watering time'] = value
    else:
        msg['notifyWait'] = 'watering currently in-progress'
    return msg


## Misc commands section ##
###########################

# Appends a message to the outbox queue which will be sent later by the main loop
def composeMessage(topic, msg):
    OUTBOX.append(SensorMessage(topic, msg))
    msgEvent.set() # wake up the send loop


# returns a formatted (system) uptime value for this device
def getSystemUptime(raw):
    return "{:0>8}".format(str(timedelta(seconds=int(uptime()))))

# return the formatted system uptime
def getUptime():
    msg = {}
    msg['uptime'] = getSystemUptime()
    return msg

# useful for latency testing
def getTimeStamp():
    msg = {}
    msg['ts'] = datetime.utcnow().isoformat()
    ## we can use this to see how fast we are sending these
    logging.debug("Sending TS response at: {}".format(datetime.now()))
    return msg

# function to set the global loop variable to false so we exit out
def disconnectLoop():
    logging.info('entering disconnected state')
    global CONNECTED
    CONNECTED=False

## Main ##
##########
if __name__ == '__main__':
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=args.endpoint,
            cert_filepath=args.cert,
            pri_key_filepath=args.key,
            client_bootstrap=client_bootstrap,
            ca_filepath=args.root_ca,
            on_connection_interrupted=on_connection_interrupted,
            on_connection_resumed=on_connection_resumed,
            client_id=args.client_id,
            clean_session=False,
            keep_alive_secs=6)

    logging.info("Connecting to {} with client ID '{}'...".format(
        args.endpoint, args.client_id))

    connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    logging.info("Connected!")

    # Subscribe
    logging.info("Subscribing to topic '{}'...".format(SUB_TOPIC))
    subscribe_future, packet_id = mqtt_connection.subscribe(
            topic=SUB_TOPIC,
            # to minimize traffic over our 802.15.4 links, don't provide guarenteed delivery
            #qos=mqtt.QoS.AT_LEAST_ONCE,
            qos=mqtt.QoS.AT_MOST_ONCE,
            callback=receive_loop)

    subscribe_result = subscribe_future.result()
    logging.info("Subscribed with {}".format(str(subscribe_result['qos'])))
    CONNECTED = True
    # compose an initial online status message
    msg = {}
    msg['status'] = 'online'
    composeMessage(f"sensors/info/{args.client_id}", msg)
    pub_count = 0
    # publish a message saying we are online
    while CONNECTED:
        msgEvent.wait(LOOP_TIMEOUT)
        if OUTBOX: # check and see if there are any messages to send
            msg = OUTBOX.popleft()
            mqtt_connection.publish(
                    topic=msg.getTopic(),
                    payload=json.dumps(msg.getMessage()), # don't forget to convert to binary before sending
                    #qos=mqtt.QoS.AT_LEAST_ONCE)
                    qos=mqtt.QoS.AT_MOST_ONCE)
            pub_count += 1
   
    ## out of loop, disconnect must have been called
    logging.info("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    logging.info("Disconnected!")
    logging.info("Sent '{}' messages".format(pub_count))
    ## Clean up area ##
    ledObj.terminate()
    waterObj.terminate()
    soilObj.terminate() 

    ledThread.join() # LED thread finish
    waterThread.join() # Water thread finish

    ## if a reboot was requested
    if ACTION_ON_TERMINATION == 'reboot':
        os.system("sudo halt --reboot")
    elif ACTION_ON_TERMINATION == 'halt':
        os.system("sudo halt -p")

