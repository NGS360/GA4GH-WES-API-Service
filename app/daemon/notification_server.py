"""
Simple HTTP server to receive workflow notifications
"""
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Dict, Any, Optional


class NotificationHandler(BaseHTTPRequestHandler):
    """HTTP request handler for workflow notifications"""
    
    # This will be set by the NotificationServer
    callback_function: Optional[Callable[[str], None]] = None
    
    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            run_id = data.get('run_id')
            
            if not run_id:
                self.send_error(400, "Missing run_id in request")
                return
            
            # Call the callback function with the run_id
            if self.callback_function:
                self.callback_function(run_id)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'status': 'success'}).encode('utf-8'))
            else:
                self.send_error(500, "Callback function not set")
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
        except Exception as e:
            self.send_error(500, str(e))
    
    def log_message(self, format, *args):
        """Override log_message to use the logger"""
        logging.getLogger(__name__).info("%s - %s", self.client_address[0], format % args)


class NotificationServer:
    """Server to receive workflow notifications"""
    
    def __init__(self, host: str = 'localhost', port: int = 5001, 
                 callback: Callable[[str], None] = None):
        """
        Initialize the notification server
        
        Args:
            host: The host to bind to
            port: The port to listen on
            callback: Function to call when a notification is received
        """
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self.logger = logging.getLogger(__name__)
        
        # Set the callback function
        NotificationHandler.callback_function = callback
    
    def start(self):
        """Start the notification server in a separate thread"""
        if self.server:
            self.logger.warning("Server already running")
            return
        
        try:
            self.server = HTTPServer((self.host, self.port), NotificationHandler)
            self.logger.info(f"Starting notification server on {self.host}:{self.port}")
            
            # Start the server in a separate thread
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.daemon = True
            self.thread.start()
            
            self.logger.info("Notification server started")
        except Exception as e:
            self.logger.error(f"Error starting notification server: {e}")
            raise
    
    def stop(self):
        """Stop the notification server"""
        if self.server:
            self.logger.info("Stopping notification server")
            self.server.shutdown()
            self.server.server_close()
            self.thread.join()
            self.server = None
            self.thread = None
            self.logger.info("Notification server stopped")