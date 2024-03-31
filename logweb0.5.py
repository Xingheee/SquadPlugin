import asyncio
import websockets
import os
import http.server
import socketserver
from threading import Thread


#请修改第51行的ip为你自己服务器公网ip，端口请勿修改，那个端口是ws的，如果要修改请把所有的3099都修改


# Path to the file to watch
file_path = 'squad.log'

async def handler(websocket, path):
    # Store the last known size of the file
    last_known_size = os.path.getsize(file_path)

    while True:
        # Check if the file size has changed
        current_size = os.path.getsize(file_path)
        if current_size != last_known_size:
            # If the file size has changed, read the last 5000 lines of the file and send its contents
            with open(file_path, 'r', encoding='utf-8') as file:
                file_contents = file.readlines()
            last_5000_lines = ''.join(file_contents[-5000:])
            await websocket.send(last_5000_lines)
            # Update the last known size
            last_known_size = current_size
        # Sleep for a bit to avoid busy-waiting
        await asyncio.sleep(1)

class MyHttpRequestHandler(http.server.SimpleHTTPRequestHandler):
    def handle(self):
        try:
            http.server.SimpleHTTPRequestHandler.handle(self)
        except ConnectionResetError:
            pass

    def do_GET(self):
        # ... rest of your code ...
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = """
            <html>
            <body>
                <pre id="content"></pre>
                <script>
                    var socket = new WebSocket('ws://180.188.188.188:3099');
                    var content = document.getElementById('content');
                    var shouldScroll = true;
                    var timeout;

                    // Listen for scroll events on the window, not the content element
                    window.addEventListener('scroll', function() {
                        // If the user has scrolled, stop auto-scrolling
                        shouldScroll = false;
                        // If the user hasn't scrolled for 5 seconds, start auto-scrolling again
                        clearTimeout(timeout);
                        timeout = setTimeout(function() {
                            shouldScroll = true;
                        }, 5000);
                    });

                    socket.onmessage = function(event) {
                        content.textContent = event.data;
                        // Scroll to the bottom if shouldScroll is true
                        if (shouldScroll) {
                            window.scrollTo(0, document.body.scrollHeight);
                        }
                    };
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode())
        else:
            super().do_GET()

handler_object = MyHttpRequestHandler

PORT = 3999
my_server = socketserver.TCPServer(("0.0.0.0", PORT), handler_object)

def run_http_server():
    my_server.serve_forever()

# Create the WebSocket server
start_server = websockets.serve(handler, '0.0.0.0', 3099)

# Start the HTTP server in a new thread
http_server_thread = Thread(target=run_http_server)
http_server_thread.start()

# Start the WebSocket server in the main thread
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()