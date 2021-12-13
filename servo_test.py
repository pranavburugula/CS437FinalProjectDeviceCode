from gpiozero import Servo
import time

servo = Servo(25)

servo.min()
time.sleep(1)
# servo.mid()
# time.sleep(1)
# servo.max()
# time.sleep(1)
