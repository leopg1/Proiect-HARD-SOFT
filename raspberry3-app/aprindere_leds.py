import RPi.GPIO as GPIO
import time

LED1 = 16
LED2 = 27

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED1, GPIO.OUT)
GPIO.setup(LED2, GPIO.OUT)

print("🔴 LED1 ON")
GPIO.output(LED1, GPIO.HIGH)
time.sleep(2)

print("🔵 LED2 ON")
GPIO.output(LED1, GPIO.LOW)
GPIO.output(LED2, GPIO.HIGH)
time.sleep(2)

print("⚫ LED-uri OFF")
GPIO.output(LED1, GPIO.LOW)
GPIO.output(LED2, GPIO.LOW)

GPIO.cleanup()
