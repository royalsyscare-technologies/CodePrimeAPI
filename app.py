import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO 
from flask_cors import CORS  # <-- Add this import
import threading
import queue
import contextlib
import io
import builtins
import re
import os  # <-- Add this import for environment variables

app = Flask(__name__)
CORS(app)  # <-- Enable CORS
socketio = SocketIO(app)

input_queue = queue.Queue()
output_queue = queue.Queue()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('run_code')
def handle_run_code(data):
    code = data.get('code', '')

    # === Smart Loop Detection ===
    if re.search(r'while\s+True', code):
        socketio.emit('output', '⚠️ Infinite loop detected (while True). Server may overload.\n===EOF===')
        return

    if re.search(r'while\s+False', code):
        socketio.emit('output', '⚠️ Useless loop detected (while False). Skipping execution.\n===EOF===')
        return

    # Detect large for-loops like: for i in range(1000000)
    match = re.search(r'for\s+\w+\s+in\s+range\((\d+)\)', code)
    if match and int(match.group(1)) > 1000:
        socketio.emit('output', '⚠️ Loop exceeds 1000 iterations. Skipping to prevent overload.\n===EOF===')
        return

    def mock_input(prompt=''):
        output_queue.put(prompt)
        return input_queue.get()

    def execute():
        buffer = io.StringIO()
        original_input = builtins.input
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                builtins.input = mock_input
                exec(code, {"__builtins__": builtins})
        except Exception as e:
            buffer.write(str(e))
        finally:
            builtins.input = original_input
            output_queue.put(buffer.getvalue())
            output_queue.put("===EOF===")

    threading.Thread(target=execute).start()
    socketio.start_background_task(send_output)

@socketio.on('user_input')
def handle_user_input(data):
    input_queue.put(data)

def send_output():
    while True:
        msg = output_queue.get()
        if msg == "===EOF===":
            break
        socketio.emit('output', msg)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # <-- Read port from env or use 5000 by default
    socketio.run(app, host='0.0.0.0', port=port)
