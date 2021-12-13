import subprocess, time
from datetime import date
from collections import deque
from threading import Thread, Condition
import myfitnesspal
from gpiozero import Servo

food_nutrition = {}
FOOD_ITEM_NAME = "Milano Mint Cookies"
starting_weight = 0
food_nutrition_serving_index = 1
calorie_deficit = 0

def weight_reader(proc, q_hx711_weight, cv_hx711_thread):
    print("HX711 Thread: Entered thread", flush=True)
    print("HX711 Thread: waiting for output from HX711", flush=True)
    for line in iter(proc.stdout.readline, b'START\n'):
        # print("Thread: waiting for START, status = {status}".format(status = line))
        continue

    print("HX711 Thread: reading lines", flush=True)
    for line in iter(proc.stdout.readline, b''):
        q_hx711_weight.append(line.decode('utf-8')[:-1])
        cv_hx711_thread.acquire()
        cv_hx711_thread.notify()
        cv_hx711_thread.release()
        # print("Thread: line = {l}".format(l = line), flush=True)
    print("HX711 Thread: Done reading, ending thread", flush=True)

def myfitnesspal_reader(q_day_data, q_goals, client, cv_mfp_thread):
    print("Fitness Thread: Entered thread", flush=True)
    try:
        while True:
            today = date.today()
            day = client.get_date(today.year, today.month, today.day)
            q_day_data.append(day.totals)
            q_goals.append(day.goals)

            cv_mfp_thread.acquire()
            cv_mfp_thread.notify()
            cv_mfp_thread.release()
            # time.sleep(4)

    except (KeyboardInterrupt, SystemExit):
        return

if __name__ == "__main__":
    proc = subprocess.Popen(["python", "./read_weight.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("Opened process")
    # time.sleep(20)
    q_hx711_weight = deque(maxlen=5)
    cv_hx711_thread = Condition()
    t_hx711 = Thread(target=weight_reader, args=(proc, q_hx711_weight, cv_hx711_thread))
    t_hx711.daemon = True
    t_hx711.start()
    print("Started hx711 thread")

    print("Creating MyFitnessPal client")
    client = myfitnesspal.Client('pranavburugula', password='qxPtaA8z')
    print("Done creating MyFitnessPal client")

    food_nutrition = client.get_food_search_results(FOOD_ITEM_NAME)[2]
    print("{food_name}: calories = {cal}, servings = {s}, sugar = {sugar}".format(food_name = FOOD_ITEM_NAME, cal = food_nutrition.calories, s = food_nutrition.servings, sugar = food_nutrition.sugar))
    # print("Serving: ", food_nutrition.servings[0].nutrition_multiplier)
    q_day_data = deque(maxlen=1)
    q_goals = deque(maxlen=1)
    cv_mfp_thread = Condition()
    t_mfp = Thread(target=myfitnesspal_reader, args=(q_day_data, q_goals, client, cv_mfp_thread))
    t_mfp.daemon = True
    t_mfp.start()
    print("Started myfitnesspal thread")

    servo = Servo(25)
    servo.min()

    first_iter = True
    try:
        while True:
            # print("Iteration {iter}: reading queue".format(iter = i))
            # weight = starting_weight
            # if first_iter:
            #     print("Place snacks in box")
            #     for i in range(20):
            #         print("Starting in {count}".format(count = 20 - i))
            #         time.sleep(1)
            #     cv_hx711_thread.acquire()
            #     cv_hx711_thread.wait()
            #     cv_hx711_thread.release()
            #     weight = float(q_hx711_weight.pop())
            #     starting_weight = weight
            #     first_iter = False
            #     print("starting weight = ", starting_weight)
            # else:
            cv_hx711_thread.acquire()
            cv_hx711_thread.wait()
            cv_hx711_thread.release()
            weight = float(q_hx711_weight.pop())
            if weight > starting_weight:
                starting_weight = weight
            print("weight = ", weight)
            print("starting weight = ", starting_weight)

            cv_mfp_thread.acquire()
            cv_mfp_thread.wait()
            cv_mfp_thread.release()
            day_data = q_day_data.pop()
            goals = q_goals.pop()
            print("day_data = ", day_data)
            print("goals = ", goals)

            calorie_deficit = (starting_weight - weight) * food_nutrition.calories / food_nutrition.servings[food_nutrition_serving_index].value

            print("calorie deficit = ", calorie_deficit)

            if bool(day_data) and day_data['calories'] + calorie_deficit > goals['calories']:
                print("Exceeded goals, locking box")
                servo.max()
            elif calorie_deficit > goals['calories']:
                print("Exceeded goals, locking box")
                servo.max()
            else:
                servo.min()

            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        proc.terminate()
        try:
            proc.wait(timeout=0.2)
            print('== subprocess exited with rc =', proc.returncode)
        except subprocess.TimeoutExpired:
            print('subprocess did not terminate in time')