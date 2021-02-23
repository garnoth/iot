#/bin/bash
certdir=/home/pi/cert/
endpoint=a1w6lfyecyp33x-ats.iot.us-west-2.amazonaws.com
rootCA=AmazonRootCA3.pem
cert=cb11952a43-certificate.pem.crt
key=cb11952a43-private.pem.key

python3 mainLoop.py --endpoint $endpoint --root-ca $certdir$rootCA --cert $certdir$cert --key $certdir$key --topic sensor/+/gateway --client-id RPI-GW-01
