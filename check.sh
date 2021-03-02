#!/bin/bash

i2cdetect -y 1 0x48 0x77 > bus.tmp
if grep -q 77 bus.tmp &&  grep -q 48 bus.tmp ; then
	echo "found them both"
fi

rm bus.tmp
