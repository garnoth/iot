# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import os
import argparse
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
import threading
import logging
import time
from uuid import uuid4
from collections import deque
from uptime import uptime
from datetime import timedelta
import weatherSensor as ws
import json
import lights as led
import soilHumidity as soil
import waterController as water

class SensorMessage:
    def __init__(self, topic, message):
        self.topic = topic
        self.message = message
    def getTopic(self):
        return self.topic

    def getMessage(self):
        return self.message

def startTaskRoutine():
    print('fart')

# This sample uses the Message Broker for AWS IoT to send and receive messages
# through an MQTT connection. On startup, the device connects to the server,
# subscribes to a topic, and begins publishing messages to that topic.
# The device should receive those same messages back from the message broker,
# since it is subscribed to that same topic.

parser = argparse.ArgumentParser(description="Send and receive messages through and MQTT connection.")
parser.add_argument('--endpoint', required=True, help="Your AWS IoT custom endpoint, not including a port. " +
        "Ex: \"abcd123456wxyz-ats.iot.us-east-1.amazonaws.com\"")
parser.add_argument('--cert', help="File path to your client certificate, in PEM format.")
parser.add_argument('--key', help="File path to your private key, in PEM format.")
parser.add_argument('--root-ca', help="File path to root certificate authority, in PEM format. " +
        "Necessary if MQTT server uses a certificate that's not already in " +
        "your trust store.")
parser.add_argument('--client-id', default="test-" + str(uuid4()), help="Client ID for MQTT connection.")
parser.add_argument('--topic', default="test/topic", help="Topic to subscribe to, and publish messages to.")
parser.add_argument('--message', default="Hello World!", help="Message to publish. " +
        "Specify empty string to publish nothing.")
parser.add_argument('--count', default=10, type=int, help="Number of messages to publish/receive before exiting. " +
        "Specify 0 to run forever.")
parser.add_argument('--use-websocket', default=False, action='store_true',
        help="To use a websocket instead of raw mqtt. If you " +
        "specify this option you must specify a region for signing, you can also enable proxy mode.")
parser.add_argument('--signing-region', default='us-east-1', help="If you specify --use-web-socket, this " +
        "is the region that will be used for computing the Sigv4 signature")
parser.add_argument('--proxy-host', help="Hostname for proxy to connect to. Note: if you use this feature, " +
        "you will likely need to set --root-ca to the ca for your proxy.")
parser.add_argument('--proxy-port', type=int, default=8080, help="Port for proxy to connect to.")
parser.add_argument('--verbosity', choices=[x.name for x in io.LogLevel], default=io.LogLevel.NoLogs.name,
        help='Logging level')

# Gloabls area
args = parser.parse_args()

io.init_logging(getattr(io.LogLevel, args.verbosity), 'stderr')

global received_count
received_count = 0
received_all_event = threading.Event()
#mutex = threading.Lock()
OUTBOX = deque() # create a linked list to handle messages for sensor readings to send to AWS

## the certificate name doesn't quite match our MQTT name
## Edit this for each device
# TODO set these via the commandline args

REPORTING_TIME = 3600 # default to 1 hour in seconds
global CONNECTED
WATERING_TIME_SEC = 8 # the default ammount of time to water

# the list of supported actions we support
SUPPORTED_ACTIONS = ['get','set', 'setTime', 'deviceState']

ACTION_ON_TERMINATION = ""

SUB_TOPIC = f"sensors/+/{args.client_id}"
print(SUB_TOPIC)

print("Starting up sensor sub-systems")
ledEvent = threading.Event()
waterEvent = threading.Event()
#tasksEvent = threading.Event()

ledObj = led.ledManager(ledEvent)
waterObj = water.waterManager(waterEvent, WATERING_TIME_SEC)
soilObj = soil.soilManager()
#tasksOjb = task.taskManager()

ledThread = threading.Thread(name='LED subsystem', target=ledObj.start)
waterThread = threading.Thread(name='Water subsystem', target=waterObj.start)
#soilThread = threading.Thread(name='Soil subsystem', target=soilObj.start)
#tasksThread = threading.Thread(name='Task reporting subsystem', target=startTaskRoutine, args =(REPORTING_TIME,))

ledThread.start()
waterThread.start()
#tasksThread.start()
print("All sensor sub-systems started")

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print("Connection interrupted. error: {}".format(error))


# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print("Connection resumed. return_code: {} session_present: {}".format(return_code, session_present))

    if return_code == mqtt.ConnectReturnCode.ACCEPTED and not session_present:
        print("Session did not persist. Resubscribing to existing topics...")
        resubscribe_future, _ = connection.resubscribe_existing_topics()

        # Cannot synchronously wait for resubscribe result because we're on the connection's event-loop thread,
        # evaluate result with a callback instead.
        resubscribe_future.add_done_callback(on_resubscribe_complete)


def on_resubscribe_complete(resubscribe_future):
    resubscribe_results = resubscribe_future.result()
    print("Resubscribe results: {}".format(resubscribe_results))

    for topic, qos in resubscribe_results['topics']:
        if qos is None:
            sys.exit("Server rejected resubscribe to topic: {}".format(topic))


## my code starts here ##
def supportedAction(payload):
    action = list(payload.keys())[0]
    # Since we only support single key + value commands, just check the first item, if it's a supported command then return true
    return action in SUPPORTED_ACTIONS

# Callback when the subscribed topic receives a message
def receive_loop(topic, payload, **kwargs):
    global received_count
    print("Received message from topic '{}': {}".format(topic, payload))
    received_count += 1


    #if received_count == args.count:
     #   received_all_event.set()

    topic_parsed = False    
    if "/" in topic:        
        parsed_topic = topic.split("/")        
        if len(parsed_topic) == 3:            
            # this topic has the correct format
                # the only root topic supported is sensors/ and only parse if this is for me
                if (parsed_topic[0] == 'sensors') and (parsed_topic[2] == args.client_id):
                    # a thing is a sensor,actuator,information or command 
                    thing = parsed_topic[1]
                    #print('Debug: parsing: ',thing)
                    payloadJson = json.loads(payload)
                    # we can filter out our message responses here and skip processing if the request doesn't contain a supported
                    # action, because it likely is just our own message response
                    if supportedAction(payloadJson):
                        if thing == 'temp' or thing == 'humidity' or thing == 'altitude' or thing == 'pressure':
                            # all of these sensors are on the same sensor device
                            print("Received weather sensor request: {}".format(payload))
                            parseSensor(topic, payloadJson, thing)
                            topic_parsed = True
                        elif thing == 'soil': # soil humidity sensor module
                            print("Received soil humidity request: {}".format(payload))
                            parseSoil(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'water': # watering module
                            print("Received watering request: {}".format(payload))
                            parseWater(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'led': # module to contol LED blinking
                            print("Received light request: {}".format(payload))
                            parseLight(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'info': # requests for data that might be bigger than a single response
                            print("Received info request: {}".format(payload))
                            parseInfo(topic, payloadJson)
                            topic_parsed = True
                        elif thing == 'cmd': # the sensor receives system commands here
                            print("received command request: {}".format(payload))
                            parseCommand(topic, payloadJson)
                            topic_parsed = True
    if not topic_parsed:
        print("Debug: Unrecognized message topic or sensor type, or it's my previous msg")

## Command parsing and validating function ##
#############################################

## because these 4 sensor readings all come from the same device, we will handle them
## from the same function
## I tested the power consumption of the weather sensor and it was about 2mA so we don't bother turning 
## it on an off, it will stay on
def parseSensor(topic, payload, thing):
    msg = {}
    if 'get' in payload:
        target = payload['get']
        if target == "status":
            # TODO check the sensor status, is it on or off
            # this would handle error conditions where some of the sensors didn't come
            # online when the program started. 
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
        print("Debug: ignored request for weather sensor")

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
            print("getting soil reading")
            msg = getSoilHumidity()
    if msg:
        composeMessage(topic, msg)

# parse the request or command for the water module
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
            print("debug: non-integer value for time")

    if 'get' in payload:
        action = payload['get']
        if action == 'status' or action == 'state':
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

# handles the led and informs LED thread if it should blink or not
# the current behavior for 'on' means blink. We could add in function to keep
# led steady and not just blink, optional
def parseLight(topic, payload):
    msg = {}
    if 'set' in payload:
        if payload['set'] == 'on':
            ledEvent.set()
            msg['status'] = 'on'
        elif payload['set'] == 'off':
            ledEvent.clear()
            msg['status'] = 'off'

    if 'get' in payload:
        if payload['get'] == 'status':
            msg = getLEDStatus()
    if msg:
        composeMessage(topic, msg)

# the Info topic can multisystem responses, in contrast to the rest of the sensor topics
# which only return a single status
def parseInfo(topic, payload):
    msg = {}
    if 'get' in payload:
        if payload['get'] == 'bulk':
            msg = getBulk()
    if msg:
        composeMessage(topic, msg)

def parseCommand(topic, payload):
    msg = {}
    global ACTION_ON_TERMINATION
    if 'get' in payload:
        if payload['get'] == 'uptime':
            msg = getUptime()
    if 'deviceState' in payload:
        if payload['deviceState'] == 'off':
            msg['status'] = 'shutting down'
            disconnectLoop()
        elif payload['deviceState'] == 'reboot':
            msg['status'] = 'rebooting'
            disconnectLoop()
            ACTION_ON_TERMINATION = 'reboot'
    if msg:
        composeMessage(topic, msg)

## Sensor data retrieval functions ## 
#####################################

## this function gathers all availble sensor data and device status information and sends in one
## pre-formatted message
def getBulk(topic):
    msg = {}
    msg.append(getTemp())
    msg.append(getHumidity())
    msg.append(getAltitude())
    msg.append(getPressure())
    msg.append(getLEDStatus())
    msg.append(getSoilHumidity())
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

# this function reports the soil humidity value
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

## system functions

# returns a formatted (system) uptime value for this device
def getSystemUptime():
    return "{:0>8}".format(str(timedelta(seconds=int(uptime()))))

 
def getUptime():
    msg = {}
    msg['uptime'] = getSystemUptime()
    return msg

# function to set the global loop variable to false so we exit out
def disconnectLoop():
    print('entering disconnected state')
    global CONNECTED
    CONNECTED=False

## Main ##
##########
if __name__ == '__main__':
    # Spin up resources
    event_loop_group = io.EventLoopGroup(1)
    host_resolver = io.DefaultHostResolver(event_loop_group)
    client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

    if args.use_websocket == True:
        proxy_options = None
        if (args.proxy_host):
            proxy_options = http.HttpProxyOptions(host_name=args.proxy_host, port=args.proxy_port)

        credentials_provider = auth.AwsCredentialsProvider.new_default_chain(client_bootstrap)
        mqtt_connection = mqtt_connection_builder.websockets_with_default_aws_signing(
                endpoint=args.endpoint,
                client_bootstrap=client_bootstrap,
                region=args.signing_region,
                credentials_provider=credentials_provider,
                websocket_proxy_options=proxy_options,
                ca_filepath=args.root_ca,
                on_connection_interrupted=on_connection_interrupted,
                on_connection_resumed=on_connection_resumed,
                client_id=args.client_id,
                clean_session=False,
                keep_alive_secs=6)

    else:
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

        print("Connecting to {} with client ID '{}'...".format(
            args.endpoint, args.client_id))

        connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    print("Connected!")

    # Subscribe
    print("Subscribing to topic '{}'...".format(SUB_TOPIC))
    subscribe_future, packet_id = mqtt_connection.subscribe(
            topic=SUB_TOPIC,
            #qos=mqtt.QoS.AT_LEAST_ONCE,
            qos=mqtt.QoS.AT_MOST_ONCE,
            callback=receive_loop)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))
    CONNECTED = True

    publish_count = 1
    # publish a message saying we are online
    while CONNECTED:
        if OUTBOX:
            msg = OUTBOX.popleft()
            ## we have an item
            print("Publishing message to topic '{}': {}".format(msg.getTopic(), msg.getMessage() ))
            print("topic:",msg.getTopic())
            mqtt_connection.publish(
                    topic=msg.getTopic(),
                    payload=json.dumps(msg.getMessage()), # don't forget to convert to binary before sending
                    qos=mqtt.QoS.AT_LEAST_ONCE)
            publish_count += 1
        else:
            time.sleep(1)
    print("Waiting for all messages to be received...")
    #received_all_event.wait()

       #message = "{} [{}]".format(args.message, publish_count)

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    #if args.count != 0 and not received_all_event.is_set():
    print("{} message(s) received.".format(received_count))

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")

    ## Clean up area ##
    ledObj.terminate()
    waterObj.terminate()
    soilObj.terminate() # is the needed?

    ledThread.join() # LED thread finish
    waterThread.join() # Water thread finish
    #tasksThread.join() # Tasks thread finish

    ## only works if script run a root
    if ACTION_ON_TERMINATION == 'reboot':
        os.system("reboot")



