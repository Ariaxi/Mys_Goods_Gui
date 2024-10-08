"""
@Author: mxyooR
@upDateTime: 2024/08/24
@Description: 用来自动用米游币兑换米游社商品,仅供学习使用，请勿用于非法用途
"""
from flask import Flask, render_template, request, redirect, url_for, jsonify,send_file
from scripts import details,tools,login
from scripts.exchange import ExchangeTask
import json
import os
import global_vars 
from global_vars import base_dir,goodslist_path,config_path,tasklistpath
from concurrent.futures import ThreadPoolExecutor
import asyncio
from concurrent.futures import ThreadPoolExecutor
from scripts.log import log_message, setup_logger
import uuid


tasks = {} # 存储任务的字典
executor = ThreadPoolExecutor(max_workers=10)#最大同时运行10个兑换任务
app = Flask(__name__)
task_instances = {}# 存储正在运行的任务对象的字典


"""
log_message
所有的报错信息为英文
成功信息为中文
"""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/view_log')
def view_log():
    log_path = os.path.join(app.root_path, 'log.log')
    return send_file(log_path, mimetype='text/plain')

@app.route('/open_task_list')
def open_task_list():
    os.startfile(tasklistpath)
    return "已打开"



#####################
# 开始任务 #
#####################

@app.route('/start_task', methods=['GET', 'POST'])
async def start_task():
    try:
        with open(tasklistpath, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
            log_message("成功读取任务清单")
    except Exception as e:
        log_message(f"Error loading tasklist.json: {e}")
        return redirect(url_for('create_task', alert="请先创建任务清单"))

    return render_template('start_task.html', tasks=tasks, task_running=any(instance.task_running for instance in task_instances.values()))

# 获取任务状态
@app.route('/get_task_status', methods=['GET'])
def get_task_status():
    for task_instance in task_instances.values():
        if task_instance.task_running:
            return jsonify(task_running=True)
    return jsonify(task_running=False)


# 获取正在运行的任务
@app.route('/get_running_tasks', methods=['GET'])
def get_running_tasks():
    running_tasks = list(task_instances.keys())
    log_message(f"正在运行的任务: {running_tasks}")
    return jsonify(running_tasks=running_tasks)

# 异步运行任务
def run_asyncio_task(task_name, task_dict):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task_instance = ExchangeTask(task_dict)  # 实例化 ExchangeTask 对象
    task_instances[task_name] = task_instance  # 将对象存储在字典中
    loop.run_until_complete(task_instance.schedule_task())  # 调用类的方法
    loop.close()

# 运行任务
@app.route('/run_task', methods=['POST'])
def run_task():
    with open(tasklistpath, 'r', encoding="utf-8") as f:
        tasks = json.load(f)
    selected_task_name = request.form.get('task')
    selected_task = next((task for task in tasks if task['name'] == selected_task_name), None)
    if selected_task:
        task_name = selected_task.get('name')
        if not task_name:
            return jsonify({"error": "Task name is missing"}), 400

        # 检查任务是否已经在运行
        if task_name in task_instances:
            return jsonify({"error": f"Task '{task_name}' is already running"}), 409

        count = selected_task.get('count', 5)  # 默认值为5，如果count不存在
        try:
            count = int(count)
        except Exception as e:
            log_message(f"Error converting count to integer: {e}")
            log_message(f"自动改成默认值count: {count}")
            count = 5
        
        selected_task['count'] = count  # 确保count是整数

        log_message(f"任务已经开始: {task_name}")
        executor.submit(run_asyncio_task, task_name, selected_task)
        return jsonify({"message": "Task is running", "task_name": task_name})
    else:
        return jsonify({"error": "Task not found"}), 404

# 获取任务消息
@app.route('/get_task_messages', methods=['GET'])
def get_task_messages():
    task_name = request.args.get('task_name')
    messages = {}
    if task_name:
        task_instance = task_instances.get(task_name)
        if task_instance and task_instance.task_messages:
            messages[task_name] = task_instance.task_messages.copy()
            task_instance.task_messages.clear()

    return jsonify(messages=messages)

# 停止任务
@app.route('/stop_task', methods=['POST'])
def stop_task():
    task_name = request.form.get('task_name')
    task_instance = task_instances.get(task_name)
    if task_instance:
        task_instance.task_running = False
        del task_instances[task_name]
        message = f"任务 {task_name} 已经停止"
        log_message(message)
        return jsonify(messages=message)
    else:
        return jsonify(messages="Task not found"), 404
#####################
#获取个人信息
#####################

@app.route('/get_user_info')
def get_user_info():
    alert = request.args.get('alert')
    # 获取二维码 URL
    qr_code_url, ticket = login.get_qr_code()
    # 使用 login.py 中的 show_qrcode 生成并保存二维码图片
    qr_image_path = os.path.join(base_dir, "static/code.png")
    qr_image_url = url_for('static', filename='code.png')
    login.show_qrcode(qr_code_url)
    log_message(f"二维码已成功保存在:{qr_image_path}")

    if alert:
        return render_template('get_user_info.html', qr_image_url=qr_image_url, ticket=ticket, alert=alert)
    else:
        return render_template('get_user_info.html', qr_image_url=qr_image_url, ticket=ticket)


@app.route('/check_qr_login', methods=['POST']) #扫码登陆
def check_qr_login():
    log_message("开始尝试二维码登录")
    ticket = request.json.get('ticket')
    try:
        cookie_dict,device_id = login.ReturnTotalCookie(ticket)
        if not cookie_dict:
            log_message(f"Failed to generate cookie")
            return jsonify({'status': 'error', 'message': 'Failed to generate cookie'}), 500
        global_vars.cookie_str =tools.dict_to_string(cookie_dict)
        global_vars.cookie_dict["cookies_list"] = cookie_dict
        global_vars.cookie_dict["device_id"] = device_id
        config_data = global_vars.cookie_dict
        log_message(f"成功添加cookie到config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4)
        return jsonify({'status': 'success', 'cookie': global_vars.cookie_str})
    except Exception as e:
        log_message(f"An error occurred during QR login check: {e}")
        return jsonify({'status': 'error', 'message': 'Internal server error'}), 500
    

#手动获取信息登录   
@app.route('/submit_manual', methods=['POST'])
def submit_manual():
    log_message("开始尝试手动登录")
    cookie = request.form.get('cookie')
    cookie_dict_temp = tools.parse_cookies(cookie)
    #print(cookie)
    try:
        global_vars.cookie_dict = {}
        global_vars.cookie_dict["cookies_list"] = {}
        cookies = global_vars.cookie_dict["cookies_list"]
        cookies["ltoken"] = str(cookie_dict_temp["ltoken"])
        # cookies["login_ticket"] = str(cookie_dict_temp["login_ticket"])
        cookies["ltuid"] = str(cookie_dict_temp["ltuid"])
        cookies["account_id"] = str(cookie_dict_temp["account_id"])
        cookies["cookie_token"] = str(cookie_dict_temp["cookie_token"])
        cookies["account_mid_v2"] = str(cookie_dict_temp["account_mid_v2"])
        global_vars.cookie_dict["device_id"] = uuid.uuid4().hex

        global_vars.cookie_str = tools.dict_to_string(global_vars.cookie_dict["cookies_list"])
        
        tools.add_to_config(global_vars.cookie_dict)
        log_message("成功添加cookie到config.json")
        return render_template('index.html', alert="success")
    except Exception as e:
        log_message(f"Error adding cookie to config: {e}")
        return render_template('index.html', alert="error")






#####################
#获取商品列表
#####################
@app.route('/product_list', methods=['GET', 'POST'])
def product_list_view():
    products = []
    golds=details.get_point(global_vars.cookie_str)
    if request.method == 'POST':
        selected_category = request.form.get('category')
        global_vars.game_biz = selected_category
        products = details.get_goods_list(selected_category, global_vars.cookie_str)
        
    return render_template('product_list.html', products=products, game_biz=global_vars.game_biz,golds=golds)
#添加到心愿单
@app.route('/add_to_wishlist', methods=['POST'])
def add_to_wishlist():
    product_id = request.form.get('product_id')
    product_time = request.form.get('product_time')
    product_name = request.form.get('product_name')
    product_biz = request.form.get('product_biz')

    # 使用 tools.py 中的 add_to_wishlist 函数
    tools.add_to_wishlist(product_name,product_id, product_time,product_biz)
    log_message(f"商品已经添加到备选清单:  {product_name}")
    return jsonify({'status': 'success', 'message': '已成功添加到备选清单'})


# 删除心愿单中的商品
@app.route('/clear_wishlist', methods=['POST'])
def clear_wishlist():
    try:
        tools.clear_goodslist()
        log_message("备选清单已经清空")
        return jsonify({"message": "备选清单已经清空",'status': 'success'}), 200
    except Exception as e:
        log_message(f"Error clearing wishlist: {e}")
        return jsonify({"message": "错误",'status': 'error'}), 500



#####################
#新建任务
#####################

@app.route('/create_task', methods=['GET', 'POST'])
def create_task():
    if request.method == 'GET':
        # 检查是否已登录
        if not global_vars.cookie_str:
            return redirect(url_for('get_user_info', alert="请先登录"))
        address_data = details.getaddress(global_vars.cookie_str)
        log_message(f"成功获取地址")
        # 尝试读取商品清单
        try:
            with open(goodslist_path, 'r', encoding='utf-8') as f:
                goods_list = json.load(f)
        except json.JSONDecodeError as e:
            log_message(f"Error decoding JSON from {goodslist_path}: {e}")
            goods_list = []
        # 尝试获取地址列表
        try:
            addresses = address_data.get('data', {}).get('list', [])
            if not addresses:
                raise ValueError("No addresses found in the provided data.")
        except KeyError as e:
            log_message(f"Key error accessing address data: {e}")
            addresses = []
        except ValueError as e:
            log_message(f"Value error: {e}")
            addresses = []
        except Exception as e:
            log_message(f"Unexpected error when accessing address data: {e}")
            addresses = []
        addresses.append({'id': '', 'addr_ext': '空地址，兑换游戏内商品选这个'})
        #print(addresses)
        default_time = goods_list[0]['time'] if goods_list else ''
        return render_template('create_task.html', addresses=addresses, goods_list=goods_list, default_time=default_time)
    
    




#新建任务清单 starttask从任务清单里面读取
@app.route('/add_to_tasklist', methods=['POST'])
def add_to_tasklist():
    try:
            uid = global_vars.cookie_dict['cookies_list']["account_id"]
            cookie = global_vars.cookie_str
            device_id = global_vars.device_id
    except IndexError:
            log_message(f"Error retrieving account_id or device_id from global_vars: {e}")
            return jsonify({'status': 'error', 'message': '无法获取用户ID和设备ID'}), 500

    # 从请求中获取其他参数
    goods_id = request.json.get('goods_id')
    address_id = request.json.get('address')
    time = request.json.get('task_time')
    name = request.json.get('task_name')
    count = request.json.get('count')
    game_biz = request.json.get('biz')


    if not goods_id  or not time or not name or not game_biz or not count:
        log_message("Missing required parameters")
        return jsonify({'status': 'error', 'message': '请求数据缺失'}), 400

    try:
        tools.add_to_tasklist(goods_id, uid, game_biz, address_id, device_id, cookie, time, name,count)
        log_message(f"Task added successfully: {name}")
        return jsonify({'status': 'success', 'message': '已成功添加到任务清单'})
    except Exception as e:
        log_message(f"Error adding task: {e}")
        return jsonify({'status': 'error', 'message': f'添加任务时发生错误: {str(e)}'}), 500


# 删除任务清单中的任务
@app.route('/clear_tasklist', methods=['POST'])
def clear_tasklist():
    tools.clear_tasklist()
    log_message("任务清单已经清空")
    return jsonify({"message": "任务清单已经清空"}), 200



#####################
#入口
#####################

def load_config():
    """
    从 config.json 文件中加载 cookie 和 device
    """ 
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            global_vars.cookie_dict = config
            global_vars.device_id = config['device_id']
            global_vars.cookie_str = tools.dict_to_string(global_vars.cookie_dict['cookies_list'])
            log_message("成功读取config.json")
        
    except Exception as e:
        print(f"None Cookie Exists: {e}")

if __name__ == '__main__':
    setup_logger() 
    # 检查 goodslist.json 是否存在，不存在则创建  不然会报错
    if not os.path.exists(goodslist_path):
        with open(goodslist_path, 'w') as f:
            json.dump([], f)  
        log_message(f"goodlist不存在，已创建文件：{goodslist_path}")
    load_config()
    app.run(debug=True,port=5000)
    #webbrowser.open("http://127.0.0.1:5000/")
