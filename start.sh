#/bin/bash
certdir=/home/pi/cert/
prefix=cb11952a43
endpoint=a1w6lfyecyp33x-ats.iot.us-west-2.amazonaws.com
rootCA=AmazonRootCA3.pem
cert=$prefix-certificate.pem.crt
key=$prefix-private.pem.key
name=RPI-GW-0

python3 mainLoop.py --endpoint $endpoint --root-ca $certdir$rootCA --cert $certdir$cert --key $certdir$key --topic "sensors/+/gateway" --client-id $name
#python3 pubsub.py --endpoint $endpoint --root-ca $certdir$rootCA --cert $certdir$cert --key $certdir$key --topic "sensor/+/gateway" --client-id RPI-GW-01
