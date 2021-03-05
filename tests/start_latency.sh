#/bin/bash
prefix=lappytoppy
name=lappytoppy

certdir=/Users/petervaneenoo/iot/
endpoint=a1w6lfyecyp33x-ats.iot.us-west-2.amazonaws.com
rootCA=AmazonRootCA3.pem
cert=lappytoppy.cert.pem
key=lappytoppy.private.key

python3 testClient.py --endpoint $endpoint --root-ca $certdir$rootCA --cert $certdir$cert --key $certdir$key --client-id $name
