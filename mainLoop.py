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

class SensorMessage:
    def __init__(self, topic, message):
        self.topic = topic
        self.message = message
    def getTopic(self):
        return self.topic

    def getMessage(self):
        return self.message


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

received_count = 0
received_all_event = threading.Event()
#mutex = threading.Lock()
OUTBOX = deque() # create a linked list to handle messages for sensor readings to send to AWS

## the certificate name doesn't quite match our MQTT name
## Edit this for each device
DEVICE_NAME = 'gateway'

global CONNECTED

ACTION_ON_TERMINATION = ""

global SYSTEM_RUNNING

SUB_TOPIC = f"sensors/+/{DEVICE_NAME}"
print(SUB_TOPIC)

ledEvent = threading.Event()
waterEvent = threading.Event()
soilEvent = threading.Event()

ledObj = led.ledManager(ledEvent)
waterObj = water.waterManager(waterEvent)
soilObj = soil.soilManager(soilEvent)

ledThread = threading.Thread(name='LED subsystem', target=ledObj.start)
waterThread = threading.Thread(name='Water subsystem', target=waterObj.start)
soilThread = threading.Thread(name='Soil subsystem', target=soilObj.start)

ledThread.start()
WaterThread.start()
SoilThread.start()

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



# Callback when the subscribed topic receives a message
def receive_loop(topic, payload, **kwargs):
    print("Received message from topic '{}': {}".format(topic, payload))
    global received_count
    global DEVICE_NAME
    received_count += 1
    if received_count == args.count:
        received_all_event.set()

    topic_parsed = False    
    if "/" in topic:        
        parsed_topic = topic.split("/")        
        if len(parsed_topic) == 3:            
            # this topic has the correct format
            # the only root topic supported is sensors/ and only parse if this is for me
            if (parsed_topic[0] == 'sensors') and (parsed_topic[2] == DEVICE_NAME):
                # a thing is a sensor,actuator,information or command 
                thing = parsed_topic[1]
                print('debug: parsing: ',thing)
                payloadJson = json.loads(payload)
                if thing == 'temp' or thing == 'humidity' or thing == 'altitude' or thing == 'pressure':
                    # all of these sensors are on the same sensor device
                    print("Received weather sensor request: {}".format(payload))
                    parseSensor(topic, payloadJson, thing)
                elif thing == 'soilHumidity': # soil humidity sensor module
                    print("Received soil humidity request: {}".format(payload))
                    parseSoil(topic, payloadJson)
                elif thing == 'watering': # watering module
                    print("Received watering request: {}".format(payload))
                    parseWater(topic, payloadJson)
                elif thing == 'led': # module to contol LED blinking
                    print("Received light request: {}".format(payload))
                    parseLight(topic, payloadJson)
                elif thing == 'info': # various sensor infos? TODO: needed?
                    print("Received info request: {}".format(payload))
                    parseInfo(topic, payloadJson)
                elif thing == 'cmd': # the sensor receives system commands here
                    print("received command request: {}".format(payload))
                    parseCommand(topic, payloadJson)
                elif thing == 'bulk': # request or publish bulk sensor readings
                    print("received bulk request: {}".format(payload))
                    parseBulk(topic, payloadJson)
        
        print("Debug: Unrecognized message topic or sensor type, or it's my previous msg")

## because these 4 sensor readings all come from the same device, we will handle them
## from the same function
# TODO handle turning on and off the sensor for power saving
def parseSensor(topic, payload, thing):
    msg = {}
    if 'get' in payload:
        if payload['get'] == "status":
            # TODO check the sensor status, is it on or off
            print('fart')

        if payload['get'] == "value":
            if thing == 'temp':
                msg = getTemp()
            elif thing == 'humidity':
                msg = getHumidity()
            elif thing == 'altitude':
                msg = getAltitude()
            elif thing == 'pressure':
                msg = getPressure()
        ## TODO create and query a device status object?
    if 'set' in payload:
        if payload['set'] == 'off':
            ## todo turn the sensor off
            print('todo')
            msg['status'] == 'off'
        elif payload['set'] == 'on':
            ## todo turn the sensor on
            msg['status'] == 'on'

    if msg: # check if the message is not empty
        print("Debug filled in some value:", msg)
        composeMessage(topic, msg)
    else: 
        print("ERROR: bad request for sensor")

def getBulk(topic):
    msg = {}
    msg.append(getTemp())
    msg.append(getHumidity())
    msg.append(getAltitude())
    msg.append(getPressure())
    msg.append(getLEDStatus()))
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

# soil humidity sensor doesn't take on or off settings because if the user leaves the sensor on,
# it will damage the sensor in just a few days. It will corrode itself. So the module takes care of turning itself
# on or off and we will only provide readings
def parseSoil(topic, payload):
    msg = {}
    if 'set' in payload:
        if payload['set'] == 'on' or payload['set'] == 'off':
            msg['status'] = 'ActionDenied'

    if 'get' in payload:
        if payload['get'] == 'value':
        msg = getSoilHumidity()
    if msg:
        composeMessage(topic, msg)

def parseWater(topic, payload):
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

def getLEDStatus():
    msg = {}
    state = "on" if ledEvent.isSet() else 'off'
    msg['status'] = state
    return msg

## IP
def getSoilHumidity():
    msg = {}
    soilEvent.set()
    msg['value'] = reading
    return msg


def parseInfo(topic, payload):
    print('stub')

def parseCommand(topic, payload):
    msg = {}
    global ACTION_ON_TERMINATION
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
    


def composeMessage(topic, msg):
    #   global mutex
  #  mutex.acquire()
    OUTBOX.append(SensorMessage(topic, msg))
#    mutex.release()

## system functions
# define a custom function to query unique system information
def getSystemUptime():
    return "{:0>8}".format(str(timedelta(seconds=int(uptime()))))


def reportUptime(topic, msg):
    msg = {}
    msg['uptime'] = getSystemUptime()
    if msg: # might be pointless here but useful to check if changes are made later
        composeMessage(topic, msg)

# function to set the global loop variable to false so we exit out
def disconnectLoop():
    print('entering disconnected state')
    global CONNECTED
    CONNECTED=False

if __name__ == '__main__':
##    global SYSTEM_RUNNING     
    # Spin up resources
    global CONNECTED
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
    #while SYSTEM_RUNNING and CONNECTED:
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
    soilObj.terminate()
    
    ledThread.join() # LED thread finish
    waterThread.join() # Water thread finish
    soilThread.join() # Soil thread finish
    
    if ACTION_ON_TERMINATION == 'reboot':
        os.system("reboot")
