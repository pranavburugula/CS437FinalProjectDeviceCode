import subprocess, time
from datetime import date
from collections import deque
from threading import Thread, Condition
import myfitnesspal
from gpiozero import Servo
from flask import Flask, render_template

food_nutrition = {}
FOOD_ITEM_NAME = "ritz crackers"
starting_weight = 0
food_nutrition_serving_index = 0
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
    

def device_thread(q_food_name):
    global food_nutrition
    global FOOD_ITEM_NAME
    global starting_weight
    global food_nutrition_serving_index
    global calorie_deficit

    print("Device: Entered thread", flush=True)
    proc = subprocess.Popen(["python", "./read_weight.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print("Device: Opened process", flush=True)
    # time.sleep(20)
    q_hx711_weight = deque(maxlen=5)
    cv_hx711_thread = Condition()
    t_hx711 = Thread(target=weight_reader, args=(proc, q_hx711_weight, cv_hx711_thread))
    t_hx711.daemon = True
    t_hx711.start()
    print("Device: Started hx711 thread", flush=True)

    print("Device: Creating MyFitnessPal client", flush=True)
    client = myfitnesspal.Client('pranavburugula', password='qxPtaA8z')
    print("Device: Done creating MyFitnessPal client", flush=True)

    food_nutrition = client.get_food_search_results(FOOD_ITEM_NAME)[0]
    print("Device: {food_name}: calories = {cal}, servings = {s}, sugar = {sugar}".format(food_name = FOOD_ITEM_NAME, cal = food_nutrition.calories, s = food_nutrition.servings, sugar = food_nutrition.sugar), flush=True)
    # print("Serving: ", food_nutrition.servings[0].nutrition_multiplier)
    q_day_data = deque(maxlen=1)
    q_goals = deque(maxlen=1)
    cv_mfp_thread = Condition()
    t_mfp = Thread(target=myfitnesspal_reader, args=(q_day_data, q_goals, client, cv_mfp_thread))
    t_mfp.daemon = True
    t_mfp.start()
    print("Device: Started myfitnesspal thread", flush=True)

    servo = Servo(25)
    servo.min()

    first_iter = True
    try:
        while True:
            # print("Iteration {iter}: reading queue".format(iter = i))
            weight = starting_weight
            if first_iter:
                print("Device: Place snacks in box (starting in 10 secs)", flush=True)
                time.sleep(10)
                
                cv_hx711_thread.acquire()
                cv_hx711_thread.wait()
                cv_hx711_thread.release()
                weight = float(q_hx711_weight.pop())
                starting_weight = weight
                first_iter = False
                print("Device: starting weight = ", starting_weight, flush=True)
            else:
                cv_hx711_thread.acquire()
                cv_hx711_thread.wait()
                cv_hx711_thread.release()
                weight = float(q_hx711_weight.pop())
                print("Device: weight = ", weight, flush=True)

            cv_mfp_thread.acquire()
            cv_mfp_thread.wait()
            cv_mfp_thread.release()
            day_data = q_day_data.pop()
            goals = q_goals.pop()
            print("Device: day_data = ", day_data, flush=True)
            print("Device: goals = ", goals, flush=True)

            calorie_deficit = (starting_weight - weight) * food_nutrition.calories / food_nutrition.servings[food_nutrition_serving_index].value

            print("Device: calorie deficit = ", calorie_deficit, flush=True)

            if bool(day_data) and day_data['calories'] + calorie_deficit > goals['calories']:
                print("Device: Exceeded goals, locking box", flush=True)
                servo.max()
            elif calorie_deficit > goals['calories']:
                print("Device: Exceeded goals, locking box", flush=True)
                servo.max()
            else:
                servo.min()

            q_food_name_copy = q_food_name.copy()
            new_food = q_food_name_copy.pop()
            if new_food != FOOD_ITEM_NAME:
                food_nutrition = client.get_food_search_results(new_food)[0]
                print("Device: New food: {food_name}: calories = {cal}, servings = {s}, sugar = {sugar}".format(food_name = FOOD_ITEM_NAME, cal = food_nutrition.calories, s = food_nutrition.servings, sugar = food_nutrition.sugar), flush=True)
                for i, serving in enumerate(food_nutrition.servings):
                    if serving.unit == "g":
                        food_nutrition_serving_index = i
                        break

            # time.sleep(5)
    except (KeyboardInterrupt, SystemExit):
        proc.terminate()
        try:
            proc.wait(timeout=0.2)
            print('Device: == subprocess exited with rc =', proc.returncode, flush=True)
        except subprocess.TimeoutExpired:
            print('Device: subprocess did not terminate in time', flush=True)

app = Flask(__name__)

item_name = ''
item_quantity = 0
item_weight = 0
q_food_name = deque(maxlen=1)
q_food_name.append(FOOD_ITEM_NAME)

@app.route('/')
def default(): 
    return render_template('html.html', item_name=item_name, item_quantity=item_quantity, item_weight=item_weight)

@app.route('/', methods = ['POST'])
def updateItemData():
    global item_name 
    global item_quantity
    global item_weight
    global q_food_name

    item_name = request.form['item_name']
    item_quantity = request.form['item_quantity']
    item_weight = request.form['item_weight']

    q_food_name.append(item_name)
    return default()

@app.route('/getItemData')
def getItemData():
    return {'item_name': item_name, 'item_quantity': item_quantity, 'item_weight': item_weight}
if __name__ == "__main__":
    print("Starting device thread")
    t_device = Thread(target=device_thread, args=(q_food_name,))
    t_device.daemon = True
    t_device.start()
    print("Device thread started")
    print("Starting Flask app")
    app.run(debug=True)