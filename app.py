from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'solaria_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# In-memory database tracking all flashed and currently connected boards
inventory_file = "flashed_boards.json"

def load_inventory():
    try:
        with open(inventory_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_inventory(data):
    with open(inventory_file, 'w') as f:
        json.dump(data, f)

# Initialize boards state
boards_status = load_inventory()
# Reset all boards to Offline on server boot until they ping back
for board_id in boards_status:
    boards_status[board_id]['status'] = 'Offline'

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print("Device connected.")

@socketio.on('register_table')
def handle_register(data):
    table_id = data.get('table_id')
    if table_id:
        # If it's a brand new board, mark it as newly flashed/registered
        if table_id not in boards_status:
            boards_status[table_id] = {
                "status": "Online",
                "assistance": False,
                "orders": [],
                "flashed_date": "Just Now"
            }
            save_inventory(boards_status)
        else:
            boards_status[table_id]['status'] = "Online"
        
        emit('update_dashboard', boards_status, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    # In a production environment with persistent WebSockets, 
    # you can track which client disconnected here.
    pass

@socketio.on('request_assistance')
def handle_assistance(data):
    table_id = data.get('table_id')
    needs_help = data.get('needs_help', False)
    if table_id in boards_status:
        boards_status[table_id]['assistance'] = needs_help
        emit('update_dashboard', boards_status, broadcast=True)

@socketio.on('new_order')
def handle_order(data):
    table_id = data.get('table_id')
    items = data.get('items', [])
    if table_id in boards_status and items:
        boards_status[table_id]['orders'].extend(items)
        emit('update_dashboard', boards_status, broadcast=True)

@socketio.on('clear_assistance')
def handle_clear_assistance(data):
    table_id = data.get('table_id')
    if table_id in boards_status:
        boards_status[table_id]['assistance'] = False
        emit('update_dashboard', boards_status, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
