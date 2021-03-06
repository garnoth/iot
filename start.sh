#/bin/bash
prefix=cb11952a43
name=gateway

certdir=/home/pi/cert/
endpoint=a1w6lfyecyp33x-ats.iot.us-west-2.amazonaws.com
rootCA=AmazonRootCA3.pem
cert=$prefix-certificate.pem.crt
key=$prefix-private.pem.key

# don't start unless the i2c busses see the temperature and ADC chip online
i2cdetect -y 1 0x48 0x77 > bus.tmp
if grep -q 77 bus.tmp &&  grep -q 48 bus.tmp ; then
	echo "I2C bus online: starting"
else
	echo "I2C detection failed: exit"
	rm bus.tmp
	exit 0
fi
rm bus.tmp

python3 mainLoop.py --endpoint $endpoint --root-ca $certdir$rootCA --cert $certdir$cert --key $certdir$key --client-id $name
