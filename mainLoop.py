# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

import os
import argparse
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
import threading
import time
from uuid import uuid4
from collections import deque
from uptime import uptime
from datetime import timedelta
import weatherSensor as ws
import json



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
CONNECTED = False
ACTION_ON_TERMINATION = ""


SUB_TOPIC = f"sensors/+/{DEVICE_NAME}"
print("subbing to: " + SUB_TOPIC)

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
            if (parsed_topic[0] == 'sensors') and (parsed_topic[2] == DEVICE_NAME):
                # a thing is a sensor,actuator,information or command 
                thing = parsed_topic[1]
                payloadJson = json.loads(payload)
                # the only root topic supported is sensor/ and only parse if this is for me
                if thing == 'temp' or 'humidity' or 'altitude' or 'pressure':
                    print("Received weather sensor request: {}".format(payload))
                    topic_parsed = True
                    parseSensor(topic, payloadJson, thing)
                elif (thing == 'soilhumidity'):
                    print("Received soil humidity request: {}".format(payload))
                    topic_parsed = True
                    parseSoilHumidity(topic, payloadJson)
                elif (thing == 'light'):
                    print("Received light request: {}".format(payload))
                    topic_parsed = True
                    parseLight(topic, payloadJson)
                elif (thing == 'info'):
                    print("Received info request: {}".format(payload))
                    topic_parsed = True
                    parseInfo(topic, payloadJson)
                elif (thing == 'cmd'):
                    print("Received command request: {}".format(payload))
                    topic_parsed = True
                    parseCmd(topic, payloadJson)

    if not topic_parsed:
        print("Unrecognized message topic or sensor type")

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
                msg[thing] = ws.bme280.temperature
            elif thing == 'humidity':
                msg[thing] = ws.bme280.relative_humidity
            elif thing == 'altitude':
                msg[thing] = ws.bme280.altitude
            elif thing == 'pressure':
                msg[thing] = ws.bme280.pressure
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
        print("We filled in some value:", msg)
        composeMessage(topic, msg)
    else: 
        print("ERROR: bad request for sensor")

def parseSoilHumidity(topic, payload):
    print('stub')

def parseLight(topic, payload):
    print('stub')

def parseInfo(topic, payload):
    print('stub')

def parseCmd(topic, payload):
    global CONNECTED 
    global ACTION_ON_TERMINATION
    if 'deviceState' in payload:
        if payload['deviceState'] == 'off':
            CONNECTED = False
        elif payload['deviceState'] == 'reboot':
            CONNECTED = False
            ACTION_ON_TERMINATION = 'reboot'
            


def composeMessage(topic, msg):
 #   global mutex
  #  mutex.acquire()
    OUTBOX.append(SensorMessage(topic, msg))
#    mutex.release()

## system functions
# define a custom function to query unique system information
def getSystemUptime():
    return "{:0>8}".format(str(timedelta(seconds=int(uptime()))))


def reportUptime(msg):
    MSG_RESP = {}
    MSG_RESP['device'] = DEVICE_NAME
    MSG_RESP['uptime'] = getSystemUptime()
    msg.setMessage(MSG_RESP)

# function to set the global loop variable to false so we exit out
def disconnectLoop():
    print('entering disconnected state')
    global CONNECTED
    CONNECTED=False

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
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=receive_loop)

    subscribe_result = subscribe_future.result()
    print("Subscribed with {}".format(str(subscribe_result['qos'])))
    CONNECTED = True

    publish_count = 1
    # publish a message saying we are online

    while CONNECTED:
        ## TODO implement bailout routine for graceful termination message
        if OUTBOX:
            msg = OUTBOX.popleft()
            ## we have an item
            print("Publishing message to topic '{}': {}".format(msg.getTopic(), msg.getMessage() ))
            mqtt_connection.publish(
                    topic=msg.getTopic(),
                    payload=msg.getMessage(),
                    qos=mqtt.QoS.AT_LEAST_ONCE)
            publish_count += 1
        else:
            time.sleep(1)
    print("Waiting for all messages to be received...")
    received_all_event.wait()

       #message = "{} [{}]".format(args.message, publish_count)

    # Wait for all messages to be received.
    # This waits forever if count was set to 0.
    if args.count != 0 and not received_all_event.is_set():
        print("{} message(s) received.".format(received_count))

    # Disconnect
    print("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    print("Disconnected!")
    if ACTION_ON_TERMINATION == 'reboot':
        os.system("reboot")
