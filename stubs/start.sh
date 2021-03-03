#/bin/bash
prefix=cb11952a43
name=gateway

certdir=/home/pi/cert/
endpoint=a1w6lfyecyp33x-ats.iot.us-west-2.amazonaws.com
rootCA=AmazonRootCA3.pem
cert=$prefix-certificate.pem.crt
key=$prefix-private.pem.key

python3 mainLoop.py --endpoint $endpoint --root-ca $certdir$rootCA --cert $certdir$cert --key $certdir$key --client-id $name
