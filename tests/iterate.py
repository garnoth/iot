# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0.

# major modifications made by Peter Van Eenoo
# for CSS 532 at UW Bothell
# testing file use to iterate through a client node's sensors and request data from them in a loop to simulate a high-workload 

# Author: Peter Van Eenoo
# CSS 532 IoT - class project
# March 2021

import os
import argparse
from awscrt import io, mqtt, auth, http
from awsiot import mqtt_connection_builder
import sys
import threading
import logging
import time
from datetime import datetime
from collections import deque
from uptime import uptime
from datetime import timedelta
import json

logging.basicConfig(level=logging.DEBUG)
#logging.basicConfig(level=logging.INFO)


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
global WAIT
received_count = 0

global CONNECTED 
#SUB_TOPIC = f"sensors/+/node2"
## main program message event to wake-up and check for messages
msgEvent = threading.Event()


# the list of supported actions our device will response to
SUPPORTED_ACTIONS = ['get','set', 'setTime', 'deviceState']


# return true if the json formatted payload contains a valid 'command' that the
# device supports
def supportedAction(payload):
    action = list(payload.keys())[0]
    return action in SUPPORTED_ACTIONS


global coll # our list for collecting the latency value
# Callback when the subscribed topic receives a message
def receive_loop(topic, payload, **kwargs):
    payload=json.loads(payload)
    global sent_ts
    global WAIT
    global coll
    if not supportedAction(payload): # the message should be a response from the
        # device and not our reqest
        recv_ts = datetime.now()
        diff = recv_ts - sent_ts
        print(diff.microseconds / 1000) 
        x = diff.microseconds / 1000
        coll.append(x)
        WAIT = False

## Sensor data retrieval functions ## 
#####################################


# Appends a message to the outbox queue which will be sent later by the main loop
def composeMessage(topic, msg):
    OUTBOX.append(SensorMessage(topic, msg))
    msgEvent.set() # wake up the send loop

## system functions


# function to set the global loop variable to false so we exit out
def disconnectLoop():
    logging.info('entering disconnected state')
    global CONNECTED
    CONNECTED=False

## Main ##
##########
if __name__ == '__main__':
    global WAIT
    global sent_ts
    global coll
    coll = []
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

        logging.info("Connecting to {} with client ID '{}'...".format(
            args.endpoint, args.client_id))

        connect_future = mqtt_connection.connect()

    # Future.result() waits until a result is available
    connect_future.result()
    logging.info("Connected!")

    # Subscribe
    logging.info("Subscribing to topic '{}'...".format("sensors/+/node2"))
    subscribe_future, packet_id = mqtt_connection.subscribe(
            topic="sensors/+/node2",
            #qos=mqtt.QoS.AT_LEAST_ONCE,
            qos=mqtt.QoS.AT_MOST_ONCE,
            callback=receive_loop)

    subscribe_result = subscribe_future.result()
    logging.info("Subscribed with {}".format(str(subscribe_result['qos'])))
    CONNECTED = True
    # compose an initial online status message
    pub_count = 0
    # publish a message saying we are online
    qos=mqtt.QoS.AT_MOST_ONCE
    
    msg = {}
    msg['get'] = 'value'
    pp = json.dumps(msg)
    i = 0
    # the supported topics for each device we are testing
    devices=['temp','pressure','humidity', 'altitude', 'soil', 'water', 'led']
    

    while pub_count < 100:
        if i > len(devices):
            i = 0
        
        target_sensor = devices[i] # iterate through the device system
        target_client = 'node2'
        target_topic = f"sensors/{target_sensor}/{target_client}"
        WAIT = True
        mqtt_connection.publish(
                    topic=target_topic,
                    payload=pp,
                    qos=mqtt.QoS.AT_MOST_ONCE)

        sent_ts = datetime.now()
        logging.debug("Sent message to topic'{}':{}".format(target_topic, pp))
        pub_count += 1
        i += 1
        while WAIT: # wait until we recived a response before we loop again
            time.sleep(.5)

	time.sleep(5) # wait 5 seconds before we send another request

    
    time.sleep(1)
    avg = sum(coll)/len(coll)
    print("averge latency in ms:", avg)
    
    ## out of loop, disconnect must have been called
    logging.info("Disconnecting...")
    disconnect_future = mqtt_connection.disconnect()
    disconnect_future.result()
    logging.info("Disconnected!")
    logging.info("Sent '{}' messages".format(pub_count))

