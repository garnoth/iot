from time import sleep
import lights as led
import threading

e = threading.Event()
t = threading.Thread(name='non-block', target=led.blinkLed, args=(e, 2))
t.start()


print("sleeping 2 seconds:")
sleep(2)
e.set()
sleep(4)
e.clear()
print("main thread waiting 5 seconds")
sleep(5)
e.set()
count = 1
while True:
    print("main doing fun things: ", count)
    count +=1
    sleep(1)
