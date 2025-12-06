```python
import os
import base64
from flask import Flask, request, jsonify, send_file, send_from_directory
from processor import process_image
from werkzeug.middleware.shared_data import SharedDataMiddleware
from whitenoise import WhiteNoise

app = Flask(__name__, static_folder='static')
app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/', prefix='static/') 

# Increase max upload size to 16MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    try:
        # Read file bytes
        image_bytes = file.read()
        
        # Process image
        processed_io = process_image(image_bytes)
        
        # Convert to base64 for easy frontend display without file storage mgmt
        processed_b64 = base64.b64encode(processed_io.getvalue()).decode('utf-8')
        
        return jsonify({
            'success': True,
            'image': f"data:image/png;base64,{processed_b64}"
        })
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
